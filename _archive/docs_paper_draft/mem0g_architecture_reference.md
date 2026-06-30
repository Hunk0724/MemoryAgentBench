# Mem0g 架構理解(對手方法系統流程)

> **目的**:把對手 mem0g 的完整方法流程(ingestion + query + final inference)整理成可查參考,作為兩個核心主張的結構根據。
> **驗證**:全部對照 vendored 原始碼逐行確認(本檔 file:line 皆可點)。vendored = upstream mem0 commit `55df395f`,graph_memory.py / tools.py / utils.py 三檔皆 byte-identical(見 [mem0g_reproducibility.md §1](../baseline_methods/mem0g_reproducibility.md))。
> **相關**:核心主張與 TODO 見 [research_core_claims_TODO_2026-06-01.md](research_core_claims_TODO_2026-06-01.md);two-store divergence 見 [mem0g_reproducibility.md §8](../baseline_methods/mem0g_reproducibility.md)。

---

## 0. 頂層編排:兩庫平行、互不同步

mem0g = **Mem0(vector-only)再並聯一條 graph 路徑**。同一份輸入同時走兩條獨立 pipeline,用 `ThreadPoolExecutor` 平行跑,**除 `delete_all()` 外彼此無 reconciliation**。

```python
# ingestion — main.py:160-185
with ThreadPoolExecutor() as executor:
    future1 = executor.submit(self._add_to_vector_store, ...)  # Qdrant
    future2 = executor.submit(self._add_to_graph, ...)         # Neo4j
    wait([future1, future2])
return {"results": vector_store_result, "relations": graph_result}

# query — main.py:489-503
future_memories = executor.submit(self._search_vector_store, ...)  # → results (top-100)
future_graph     = executor.submit(self.graph.search, ...)          # → relations (top-5)
return {"results": [...], "relations": [...]}   # 兩 key 永遠分開
```

→ vector L2 與 graph G4 是**兩個獨立 LLM 決策**,各自只看自己 store 的既有狀態 → 結構性 two-store divergence。

---

## 1. Ingestion — vector path

`_add_to_vector_store` [main.py:187-323](../../mem0/memory/main.py#L187)

```python
def _add_to_vector_store(self, messages, ...):
    facts = LLM(FACT_RETRIEVAL_PROMPT)                    # ① L1
    for fact in facts:
        existing = vector_store.search(fact, limit=5)     # ② 每個 fact 抓 top-5 既有
    events = LLM(UPDATE_MEMORY_PROMPT, facts, existing)   # ③ L2 一次判全部
    for resp in events: execute(ADD/UPDATE/DELETE/NONE)   # ④ 執行
```

**一句話**:抽 facts(①)→ 每個 fact 用 embedding 抓 **top-5** 既有 memory(②)→ LLM 一次性對「新 facts × 既有」判每筆 event(③)→ 執行 ADD/UPDATE/DELETE/NONE(④)。

1. **L1 抽 facts** — `FACT_RETRIEVAL_PROMPT`([main.py:199-218](../../mem0/memory/main.py#L199)):從 chunk 抽原子事實,回 JSON `{"facts": [...]}`。
2. **抓既有候選 — top-5**([main.py:225-230](../../mem0/memory/main.py#L225)):每個新 fact embed → `vector_store.search(limit=5)`;全部候選去重(by id,[main.py:233-236](../../mem0/memory/main.py#L233));UUID 暫映射成整數防 LLM 幻覺([main.py:239-243](../../mem0/memory/main.py#L239))。
3. **L2 判 event** — `DEFAULT_UPDATE_MEMORY_PROMPT`([main.py:245-263](../../mem0/memory/main.py#L245)):一次把「所有新 facts + 去重既有」餵 LLM,回 `{"memory":[{event, text, id?, old_memory?}, ...]}`,event ∈ `{ADD, UPDATE, DELETE, NONE}`。
4. **執行**([main.py:265-315](../../mem0/memory/main.py#L265)):`ADD`→`_create_memory`(新增);`UPDATE`→`_update_memory`(覆寫既有 id,記 previous_memory);`DELETE`→`_delete_memory`(刪既有 id);`NONE`→noop。

> ⚠️ 與 graph 不同:vector 的「找既有 + 判 event」**合在一個 L2 LLM call**;graph 是「找既有(G3 Cypher)」與「判刪(G4 LLM)」**分兩步**,add 與 delete 也拆開。

**實測 event 分佈**(FC-MH 6k ingestion log):255 ADD / 75 UPDATE / **0 DELETE** → 衝突大多沒被偵測,old+new 雙存。

---

## 2. Ingestion — graph path

`MemoryGraph.add` [graph_memory.py:49-67](../../mem0/memory/graph_memory.py#L49)

```python
def add(self, data, filters):
    entity_type_map = self._retrieve_nodes_from_data(...)              # ① G1
    to_be_added     = self._establish_nodes_relations_from_data(...)   # ② G2
    search_output   = self._search_graph_db(node_list=...)            # ③ G3  cosine ≥ 0.7
    to_be_deleted   = self._get_delete_entities_from_search_output(...)# ④ G4  DELETE prompt
    self._delete_entities(to_be_deleted, ...)                         # ⑤ 先刪
    self._add_entities(to_be_added, ..., entity_type_map)             # ⑥ 才 add(MERGE,cosine ≥ 0.9)
```

**一句話**:抽 entity(①,無上限)→ 抽 triple(②,取第 1 個 tool_call)→ 用 entity 以 **cosine 0.7、每 entity top-100** 找既有 triple(③)→ LLM 判該刪哪些(④,無上限)→ **先刪邊**(⑤)→ 再用 **cosine 0.9、top-1 節點去重** MERGE 新 triple(⑥)。

1. **G1 抽 entity + type** — `EXTRACT_ENTITIES_TOOL`:從 chunk 抽 `entity_type_map = {entity: type}`。**無上限**(迴圈讀所有 tool_call,[graph_memory.py:167-171](../../mem0/memory/graph_memory.py#L167))。
2. **G2 抽 relationship → triple** — `EXTRACT_RELATIONS_PROMPT`:拿 G1 entity list,從 chunk 找關係,得 `to_be_added`。
   ```python
   # graph_memory.py:212-213
   entities = []
   if extracted_entities["tool_calls"]:
       entities = extracted_entities["tool_calls"][0]["arguments"]["entities"]
   #                                            ^^^ 只讀第 0 個 tool_call,其餘忽略
   ```
   ⚠️ **只讀 `tool_calls[0]`**——模型若把 triple 拆成多個 tool_call(第 1 call 5 條、第 2 call 5 條),**第 2 個以後全丟**,那些 triple 不進圖。(對比 G1 是迴圈讀全部,upstream 不一致。)
3. **G3 找「圖中既有相關 triple」** — `_search_graph_db`,**cosine ≥ 0.7**([graph_memory.py:219-258](../../mem0/memory/graph_memory.py#L219)):
   - 用 **G1 的 `entity_type_map.keys()`** 當 `node_list`;每個 entity embed → 找 cosine ≥ 0.7 節點 → `MATCH` 進出兩向的邊 → `search_output`。
   - **每 entity `LIMIT 100`**([graph_memory.py:247](../../mem0/memory/graph_memory.py#L247))→ 10 個 entity 可撈近 1000 條候選邊丟給 G4。**chunk 越長 / entity 越多 → 候選爆量(entity 數 × ≤100)**。
4. **G4 判該刪哪些** — `DELETE_RELATIONS_SYSTEM_PROMPT`([graph_memory.py:260-285](../../mem0/memory/graph_memory.py#L260)):把「③既有 triple + 新 chunk 原文」餵 LLM,輸出 `to_be_deleted`(可空)。**無上限**。
   - ⚠️ LLM 看的是「**既有 triple vs 新 chunk 原文**」,不是「既有 triple vs 新 triple」。
   - 候選爆量 → G4 要判的也爆量 → **長 context 下 graph 衝突偵測劣化的來源之一**(對應主張一)。
5. **先刪** — `_delete_entities`([graph_memory.py:287-313](../../mem0/memory/graph_memory.py#L287)):每條跑 `MATCH ()-[r]->() DELETE r`,**只刪邊**。
6. **最後才 add(MERGE,cosine ≥ 0.9 + top-1「節點去重」)** — `_add_entities`([graph_memory.py:315-415](../../mem0/memory/graph_memory.py#L315)):每條 triple → embed source/dest → `_search_source_node`/`_search_destination_node` **cosine ≥ 0.9、top-1** 找既有節點 → 依 source/dest 各自是否存在走 4 個 MERGE 分支:
   - 只有 source 存在 → MERGE 新 destination + 接關係
   - 只有 destination 存在 → MERGE 新 source + 接關係
   - 兩端都存在 → 只 MERGE 中間那條關係
   - 都不存在 → MERGE 兩個新節點 + 關係
   - (cosine 0.9 + top-1 只決定 source/destination 要不要建新節點,跟 ③ 的 0.7「找衝突」是兩回事。)

---

## 3. Query — vector path

`_search_vector_store` [main.py:517-519](../../mem0/memory/main.py#L517)

```python
embeddings = embed(query, "search")
memories = vector_store.search(query, vectors=embeddings, limit=100)   # top-100,無 rerank
```

**一句話**:query embed → Qdrant cosine 抓 **top-100**(`limit=self.retrieve_num=100`,[agent.py:911](../../agent.py#L911))→ 直接回傳,**無 rerank、無 LLM**。

- 純一次向量檢索,**零跳**,無二段 rerank、無 entity 抽取。
- 回傳 `relevant_memories["results"]`(top-100 memory 文字),整包進 prompt 的 `Facts:` 區塊。

---

## 4. Query — graph path

`MemoryGraph.search` [graph_memory.py:69-103](../../mem0/memory/graph_memory.py#L69)

```python
def search(self, query, filters, limit=100):
    entity_map  = self._retrieve_nodes_from_data(query, ...)   # Q1 抽 query entity
    search_out  = self._search_graph_db(node_list=...)         # Q2 cosine ≥ 0.7,每 entity ≤100 邊
    bm25        = BM25Okapi(search_out)                        # Q3 詞彙 rerank
    return bm25.get_top_n(query.split(), ..., n=5)             #    top-5 triple
```

**一句話**:從 query 抽 entity(Q1)→ 用 entity 以 **cosine ≥ 0.7** 找節點、`MATCH` 進出邊得候選 triple(Q2,每 entity ≤100)→ **BM25 詞彙** 對 query rerank 取 **top-5**(Q3)→ 回傳,**不改圖、無 delete**。

1. **Q1 抽 query entity** — `EXTRACT_ENTITIES_TOOL`([graph_memory.py:83](../../mem0/memory/graph_memory.py#L83)):與 G1 同函式;prompt 明令「若是問句,不要回答,只抽 entity」。
2. **Q2 找候選 triple** — `_search_graph_db`,**cosine ≥ 0.7**([graph_memory.py:84,219-258](../../mem0/memory/graph_memory.py#L219)):與 G3 同函式;每 query entity embed → 找 cosine ≥ 0.7 節點 → `MATCH` 進出兩向的邊,**每 entity `LIMIT 100`**。
3. **Q3 BM25 rerank — top-5**([graph_memory.py:92-99](../../mem0/memory/graph_memory.py#L92)):候選 triple 當「文件」、query 切詞當「查詢」,BM25 詞彙計分取 **top-5**(`n=5` 寫死)。
   - ⚠️ 最終 5 條靠**字面字詞重疊**,不是語意向量(triple 沒 embedding,只有節點有)。

> **檢索結構對照**:vector query =「一次 cosine top-100,零跳」;graph query =「LLM 抽 entity → cosine 0.7 定位節點 → **只展開 1-hop 邊** → BM25 top-5」三段唯讀。**兩者都沒有沿關係鏈往深處走的多跳機制**(對應主張二)。

---

## 5. 最終 inference prompt 組成

system + user 兩則訊息([agent.py:939-942](../../agent.py#L939)),依 variant 不同:

**prompt-aware**(restore 上游 cookbook pattern,relations 進 prompt):
```
system:
You are a helpful AI. Answer the question based on the facts and the relationship graph below.
Facts:
- <vector memory 1> ...            ← results,top-100 向量
Relationships:
- <source> --[<rel>]--> <dest> ... ← relations,top-5 BM25 triple
user:
<query>\n\nCurrent Time: YYYY-MM-DD HH:MM:SS
```

**MABench-as-is**(原樣,relations 不進 prompt,等同純 Mem0):
```
system:
You are a helpful AI. Answer the question based on query and memories.
- <vector memory 1> ...            ← 只有 results,無 Relationships 區塊
```

> per-query 檢索內容有完整 dump 在 `outputs/rag_retrieved/<agent>/k_100/<task>/chunksize_512/query_<qid>_context_<cid>.json`(含 retrieved_memories / retrieved_relations / system_prompt / response,[agent.py:960-972](../../agent.py#L960))。

---

## 6. 全景速查表

### LLM call 數
| 階段 | vector | graph | 合計 |
|---|---|---|---|
| Ingestion / chunk | 2(L1 + L2) | 3(G1 + G2 + G4) | **5** |
| Query / query | 0 | 1(Q1) | **1** + 最後 answer 1 |

### top-k / threshold
| 步驟 | 設定 |
|---|---|
| vector ② 找既有 | top-5,cosine |
| vector query | top-100,cosine,無 rerank |
| graph G1/G2/G4 | 無上限(LLM 輸出多少算多少;G2 只取 tool_call[0]) |
| graph G3 找既有 | **cosine ≥ 0.7,每 entity LIMIT 100** |
| graph ⑥ 節點去重 | **cosine ≥ 0.9,top-1** |
| graph query Q2 | cosine ≥ 0.7,每 entity LIMIT 100 |
| graph query Q3 | **BM25 詞彙,top-5** |

### 對應核心主張(見 [research_core_claims_TODO](research_core_claims_TODO_2026-06-01.md))
- **主張一(候選池過大)**:G3/G4 候選 = entity 數 × ≤100,隨圖長(context 長度)膨脹 → write-time 偵測 precision 崩。
- **主張二(無多跳)**:vector 零跳 top-100;graph 只 1-hop 邊 + BM25 → 無沿鏈多跳機制。
- **two-store divergence**:vector L2 與 graph G4 獨立判、互不同步 → 狀態岔開。
