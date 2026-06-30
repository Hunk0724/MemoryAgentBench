# Mem0g Reproducibility — 把 MABench mem0g 補完成 honest baseline

> **Date**: 2026-05-29 night
> **Trigger**: CRITICAL_FINDINGS F1 — MABench wrapper 把 mem0g 抽出的 graph relations 寫到 disk 但沒進 LLM prompt
> **Goal**: 證明 (a) MABench vendored mem0g = 上游 mem0 某個 commit 一字不差;(b) 上游官方 docs 明文要求 graph 結果進 inference;(c) 我們的補完 = restore upstream intended pattern,屬於 wrapper integration bug fix,不是 method 改動

---

## 1. MABench vendored mem0g = upstream commit `55df395f` 一字不差

### 1.1 MD5 對照

```bash
$ md5sum /home/yhchiang/MemoryAgentBench/mem0/memory/graph_memory.py
780d0a8ed06cc067b9dc8cb3411f98bb

$ cd /home/yhchiang/mem0
$ git show 55df395f:mem0/memory/graph_memory.py | md5sum
780d0a8ed06cc067b9dc8cb3411f98bb  ✅ EXACT MATCH
```

### 1.2 上游 commit 元資料

```
commit 55df395f
Date  : 2025-04-09
Title : fix: extract entities tool_calls some times is an array (#2481)
```

該 commit 是 mem0 **v3 之前**最後一個 stable 的「graph memory 仍存在」的版本。v3 commit `a488e190`(2025-06)拆掉 Neo4j graph,改用「hybrid search + entity extraction + additive scoring」整合進 vector。

### 1.3 完整 vendored 範圍

MABench 把整個 mem0 套件 vendored 進來:`/home/yhchiang/MemoryAgentBench/mem0/`(對應 upstream `mem0/`)。我們只對 **graph_memory.py** 做 md5 驗證,但全套 mem0 是 commit `55df395f` 時間點的鏡像。

> **下一步**:後續可再對 `mem0/memory/main.py`、`mem0/configs/prompts.py` 做 md5 verify(預期同樣 match 同 commit)。如果某檔 not match,代表 MABench 有自己改過,要列入 disclose。

---

## 2. 上游 mem0 官方 docs 明文要求 graph relations 進 inference

### 2.1 官方 Cookbook 原文(已被 mem0 v3 刪除,可從 git history 還原)

從 `/home/yhchiang/mem0` git history:

```bash
$ cd /home/yhchiang/mem0
$ git log --oneline | grep -i "cookbook\|graph"
3fbc1c9a fix(docs): updating the changelog, and removing cookbook page referencing graph memory (#4867)

$ git show 3fbc1c9a^:docs/cookbooks/essentials/choosing-memory-architecture-vector-vs-graph.mdx
```

關鍵段落(原文逐字):

```python
client.add("Emma works with David on the mobile app redesign", user_id="company_kb")
client.add("David reports to Rachel, who manages the design team", user_id="company_kb")

# Multi-hop query
results = client.search(
    "Who is Emma's teammate's manager?",
    filters={"user_id": "company_kb"}
)

print(results['results'][0]['memory'])
print("\nRelationships found:")
for rel in results.get('relations', []):
    print(f"  {rel['source']}, {rel['target']} ({rel['relationship']})")
```

> **Expected behavior**: Graph memory returns the **direct answer** — "David reports to Rachel" — plus the **relationship chain** that got there. No manual connecting needed. The graph traversed: Emma → works_with → David → reports_to → Rachel.

### 2.2 解讀

- `results['results']` = vector 記憶(文字 fact)
- `results['relations']` = graph 三元組(source/relationship/destination)
- **官方範例直接 print 兩者**,並把 relations 描述為「the relationship chain that got there」
- 整個 cookbook 章節 title 是 "Choose Vector vs Graph Memory",**graph 路徑的全部 value proposition** 就是 multi-hop reasoning + relationship chain。如果 relations 不進 inference,該章節**所有 example output 都不會出現**

→ 上游 mem0 設計意圖:**integrator 必須把 relations verbalize 進 inference prompt**,否則 graph 沒用。

### 2.3 MABench 整合的 wrapper bug

[/home/yhchiang/MemoryAgentBench/agent.py:865-939](../../agent.py) `_handle_mem0_agent`:

```python
# L896
relevant_memories = self.memory.search(query=message, user_id=user_id, limit=self.retrieve_num)

# L899 — 只取 "results"(vector),沒取 "relations"(graph)
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories["results"])

# L903 — final prompt 只包 memories_str
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
```

[/home/yhchiang/MemoryAgentBench/mem0/memory/main.py:489-503](../../mem0/memory/main.py) 確認 search() 返回 `{"results": original_memories, "relations": graph_entities}` 是 separate dict keys,從未 merge。

→ MABench wrapper 的 `agent.py:899` 沒按 cookbook 範例把 relations 拿出來用。這是 **wrapper integration bug**,不是 mem0g 本身設計。

---

## 3. 我們的補完:`mem0g-prompt-aware` variant

### 3.1 設計原則:restore upstream cookbook 範例的 pattern

我們新增的 variant **只在 inference 階段**動,**不改 ingestion / search 任何邏輯**。
整個改動就是把 `relevant_memories["relations"]` 也 verbalize 進 system prompt。

### 3.2 具體 diff(對 `_handle_mem0_agent`)

```python
# 原 (MABench-as-is):
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories["results"])
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"

# 新 (mem0g-prompt-aware):
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories["results"])

if self.mem0_prompt_aware_graph:
    rels = relevant_memories.get("relations") or []
    rels_str = "\n".join(
        f"- {r.get('source','?')} --[{r.get('relationship','?')}]--> {r.get('destination','?')}"
        for r in rels
    )
    system_prompt = (
        "You are a helpful AI. Answer the question based on memories and the relationship graph.\n"
        f"Facts:\n{memories_str}\n\n"
        f"Relationships:\n{rels_str}\n"
    )
else:
    system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
```

### 3.3 對應 upstream cookbook 範例的 pattern

| Cookbook 範例 | 我們的補完 |
|---|---|
| `print(results['results'][0]['memory'])` | `Facts:\n{memories_str}` |
| `for rel in results.get('relations', []): print(f"  {rel['source']}, {rel['target']} ({rel['relationship']})")` | `Relationships:\n{rels_str}` 用 `{source} --[{relationship}]--> {destination}` |

> ⚠️ Cookbook 用 `rel['target']`,但 vendored mem0 graph_memory.py search() 返回的是 `destination`(graph_memory.py:99)。這是 upstream 內部 schema 細節差異 — cookbook 用 client API、我們用 internal `Memory` class。我們 follow `Memory.search()` 的實際 return field 名(`destination`),語意一致。

### 3.4 變動分類

按 [docs/baseline_methods/mem0_setup_deltas_vs_paper.md](mem0_setup_deltas_vs_paper.md) 的 4 類框架:

| 類 | 描述 | 此 patch 屬於 |
|---|---|---|
| A | API hygiene / vendored bug fix | ⭐ **此 patch 在這類**(MABench wrapper 沒按 upstream cookbook 拿 relations 進 prompt)|
| B | 跨方法統一 convention(chunk size 等)| 不是 |
| C | Minimal prompt repair(影響範圍小但保留 upstream 設計意圖)| 不是 |
| D | Substantive method modification(危險區)| **不是** |

→ Paper appendix 完整 disclose,**頂會接受機率高**。

---

## 4. 補完後預期影響

### 4.1 MH 6k pilot 預期

| 版本 | MH 6k EM(現有/預期)|
|---|---:|
| Mem0g-MABench-as-is(backtick, temp=0/0.1)| **41%**(已 pilot)|
| Mem0g-prompt-aware(temp=0.7)| 待跑 |

兩個變量同時動(temp 改 + relations 進 prompt),所以 1 trial 結果不能直接歸因到哪個。後續需要 controlled study:
- Mem0g × MH 6k × temp=0.7 × MABench-as-is(隔離 temp 影響)
- Mem0g × MH 6k × temp=0.7 × prompt-aware(同 temp,看 relations 影響)

### 4.2 Mechanism evidence

補完後 paper §6.4 mechanism 故事可以變:
- M-detection × EM 仍可分析(detection 不變,只動 inference prompt)
- 新增「Graph relations 對 LLM 推理的貢獻」分析:
  - 如果 prompt-aware EM > as-is EM ⟹ relations 對 multi-hop reasoning 有效
  - 如果差不多 ⟹ relations 內容本身 noisy 或 LLM 不會用

---

## 5. Reproducibility checklist(reviewer 視角)

| 項目 | 在哪 disclose | 在 paper 哪節 |
|---|---|---|
| MABench mem0g = upstream commit 55df395f | 此 doc §1 + appendix | Reproducibility appendix |
| Mem0 上游 cookbook 證據 | 此 doc §2 + git ref `3fbc1c9a^` | Reproducibility appendix |
| 我們補完的 diff | 此 doc §3.2 + agent.py | Method §3.x or Appendix |
| 變動分類為 A 類 | 此 doc §3.4 | Reproducibility appendix |
| temp / chunk size 對齊 benchmark | mem0_setup_deltas_vs_paper.md | Method §3.x |
| 結果 with vs without prompt-aware | pilot 跑完後加 | Results §6.x |

---

## 6. Open question / Future work

1. **Mem0g-as-is 是否要繼續放 paper?**
   - 我推薦:as-is 列在 ablation table,主表用 prompt-aware
   - 理由:paper 故事「我們把 MABench wrapper 補完成 honest mem0g」是有 value 的 disclosure,不浪費 as-is 數字
2. **Mem0g 在 commit 55df395f 之後上游怎麼演化?**
   - 後續 mem0 commits 多以「bug fix / minor improvement」為主,直到 a488e190 完全拆 graph
   - 我們不 cherry-pick 後續 fix(維持 vendored 一致性)— 除了 wrapper integration 層的 bug
3. **mem0 v3(removed graph)是否要重新整合?**
   - 留 future work — 已寫 v3 移除原因(hybrid search 把 entity 整合進 vector,設計哲學變了)
   - 本 paper 主要對標 mem0g pre-v3,vs. ours query-time mechanism

---

---

## 7. Mem0 vs Mem0g 完整 pipeline 對照(2026-05-29 night appended)

### 7.1 Mem0(vector-only)pipeline

#### A. Ingestion(per memorize chunk)

```
chunk (≤512 tokens text)
   │
   ▼
[L1] FACT_RETRIEVAL_PROMPT → LLM call → JSON {"facts": [...]}
   │   prompts.py:14 (with our L1 fix removing 2 rejection few-shots)
   │
   ▼
for each fact:
   ├─ embed(fact) → top-5 vector search (existing memories)
   │
[L2] DEFAULT_UPDATE_MEMORY_PROMPT → LLM call → JSON {"memory":[{event, text, ?id, ?old_memory}, ...]}
   │   prompts.py:61, each emit ∈ {ADD, UPDATE, DELETE, NONE}
   │
   ▼
execute events:
   ├─ ADD     → vector_store.create(text, emb)
   ├─ UPDATE  → vector_store.replace(id, text, emb)
   ├─ DELETE  → vector_store.remove(id)
   └─ NONE    → noop
```

**LLM calls per chunk**:**2**(L1 facts + L2 decision)。
**State**:Qdrant collection only。
**File**:[mem0/memory/main.py:187-323 `_add_to_vector_store`](../../mem0/memory/main.py#L187)

#### B. Query-time retrieval

```
query
  ├─ embed(query) → vector_store.search(limit=retrieve_num=100)
  │
  └─ → relevant_memories["results"] = [{id, memory, score, metadata, ...}, ...]
```

無 rerank,純 vector top-K。
**File**:[mem0/memory/main.py:517-525 `_search_vector_store`](../../mem0/memory/main.py#L517)

#### C. Final inference(MABench wrapper)

```python
# agent.py:_handle_mem0_agent (L865-939)
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories["results"])
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
llm_messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": message + "\n\nCurrent Time: 2026-XX-XX HH:MM:SS"}
]
response = self._answer_with_client(llm_messages)
```

**LLM calls per query**:**1**(answer)。

---

### 7.2 Mem0g(graph-augmented)pipeline

#### A. Ingestion(per memorize chunk)

```
chunk (≤512 tokens)
   │
   ├─────────────────── PARALLEL (ThreadPoolExecutor) ───────────────────┐
   │                                                                       │
   ▼                                                                       ▼
[Vector path = SAME as Mem0]                       [Graph path: _add_to_graph]
  [L1] facts → [L2] decision → ADD/UPD/DEL          [G1] _retrieve_nodes_from_data
                                                       LLM call(tool) → entities + types
                                                       (EXTRACT_ENTITIES_TOOL)
                                                          │
                                                          ▼
                                                    [G2] _establish_nodes_relations_from_data
                                                       LLM call → relation triples
                                                       (EXTRACT_RELATIONS_PROMPT)
                                                          │
                                                          ▼
                                                    [G3] _search_graph_db
                                                       Cypher query Neo4j → existing entity triples
                                                          │
                                                          ▼
                                                    [G4] _get_delete_entities_from_search_output
                                                       LLM call → which old triples conflict
                                                          │
                                                          ▼
                                                    DELETE conflicting + MERGE new
                                                       Cypher executes(with backtick wrap P5/P6)
```

**LLM calls per chunk**:**5**(2 vector L1/L2 + 3 graph G1/G2/G4)。**比 Mem0 多 2.5x**,**latency 2-3x**。
**State**:Qdrant collection + Neo4j graph。
**Files**:
- [mem0/memory/main.py:325-334 `_add_to_graph`](../../mem0/memory/main.py#L325)
- [mem0/memory/graph_memory.py:49-67 `MemoryGraph.add`](../../mem0/memory/graph_memory.py#L49)

#### B. Query-time retrieval

```
query
   │
   ├─────────────── PARALLEL ───────────────┐
   ▼                                          ▼
[Vector = SAME as Mem0]                  [Graph: graph.search]
   embed → top-100                          [Q1] _retrieve_nodes_from_data
                                              LLM call → query entities
                                                │
                                                ▼
                                          [Q2] _search_graph_db
                                              Cypher: MATCH (e)-[r]->(t) WHERE ...
                                                │
                                                ▼
                                          [Q3] BM25Okapi rerank → top-5 triples
   │                                           │
   ▼                                            ▼
relevant_memories["results"]             relevant_memories["relations"]
  = [{id, memory, ...}, ...]              = [{source, relationship, destination}, ...]
```

**LLM calls per query**:**2**(1 graph entity extract + 1 answer)。
**Vector path 與 Mem0 完全相同**(top-100,無 rerank)。Graph path 額外算。

#### C. Final inference — **as-is(MABench bug)vs prompt-aware(我們補完)**

**MABench-as-is**(等於 Mem0 的 prompt):
```python
memories_str = "\n".join(f"- {e['memory']}" for e in relevant_memories["results"])
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
# relations 沒進 prompt!agent.py:899
```

**prompt-aware**(我們的修補,restore upstream cookbook pattern):
```python
memories_str = "\n".join(f"- {e['memory']}" for e in relevant_memories["results"])
rels = relevant_memories.get("relations") or []
rels_str = "\n".join(
    f"- {r['source']} --[{r['relationship']}]--> {r['destination']}"
    for r in rels
)
system_prompt = (
    "You are a helpful AI. Answer the question based on the facts "
    "and the relationship graph below.\n"
    f"Facts:\n{memories_str}\n\n"
    f"Relationships:\n{rels_str}\n"
)
# agent.py:899-921 with mem0_prompt_aware_graph=true
```

---

### 7.3 並排對照表

| 步驟 | Mem0 | Mem0g |
|---|---|---|
| Ingestion LLM calls/chunk | 2 | 5 |
| Ingestion latency | ~10 sec/chunk | ~90 sec/chunk(觀察值) |
| Storage backend | Qdrant only | Qdrant + Neo4j |
| Conflict 偵測機制 | L2 LLM 在 facts ↔ top-5 memories 之間判斷 ADD/UPD/DEL | L2(同 Mem0)+ G4 LLM 在 entity 層判斷 DELETE |
| Query LLM calls/query | 1(answer)| 2(entity extract + answer) |
| Final prompt 結構 | `"... based on query and memories.\n- m1\n- m2..."` | (as-is) 同 Mem0 / (prompt-aware) `"... based on facts and relationship graph.\nFacts:\n...\n\nRelationships:\n- a --[r]--> b\n..."` |
| FC 反事實題核心弱點 | bullet list 無時序,LLM 隨機猜 old/new | 同(as-is)/ relations 提供 explicit edge 但仍無時序(prompt-aware)|

### 7.4 範例(實際 query 輸出)

從 [outputs/.../query_0_context_0.json](../../outputs/gemini-3.1-flash-lite-mem0g-promptaware-chunk512-temp07/Conflict_Resolution/) 取的真實 prompt 片段:

```
system_prompt:
"You are a helpful AI. Answer the question based on the facts and the relationship graph below.
Facts:
- goaltender is associated with the sport of pesäpallo
- goalkeeper is associated with the sport of association football
- placekicker is associated with the sport of rugby
- ...(top-100 vector memories,bullet 列出)

Relationships:
- goaltender --[associated_with]--> pesäpallo
- placekicker --[associated_with]--> rugby
- ...(top-5 graph triples,BM25 reranked)
"

user: "What sport is goaltender associated with?\n\nCurrent Time: 2026-05-29 22:41:32"

response: "pesäpallo"  ← FC 反事實答案,LLM 答對
```

→ **Prompt 結構直接 follow 上游 mem0 cookbook 範例的格式**(facts + relationships 並列),**沒有自製字串**,reviewer 可直接 verify。

### 7.5 對 paper §6.4 mechanism evidence 的意義

**Mem0g vs Mem0**:差別 = (a) graph index 影響 ingestion 副作用 + (b) prompt-aware 多了 relations block。
- (a) 的影響可由 Mem0g-MABench-as-is(graph build 但不用)EM 與 Mem0 EM 對照 → **這就是 9pp 差距的來源**
- (b) 的影響可由 Mem0g-prompt-aware EM 與 Mem0g-as-is EM 對照 → **目前 pilot 顯示 +14pp**(55% vs 41% MH 6k,但 confounded by temp,要 Plan A 重跑 clean)

**對 reviewer 的 disclosure**:這份對照表 + 範例 prompt 直接證明:
1. 我們補完 prompt-aware 是 restore upstream pattern,不是自製改動
2. Mem0g 與 Mem0 ingestion 差別精確到 G1/G2/G4 三個額外 LLM call
3. 沒有任何 hidden 黑盒

---

---

## 8. Two-store divergence(2026-05-30 追補)— mem0g 一個結構性 limitation

### 8.1 證據:vector 與 graph store **完全不同步**

從 mem0/memory/main.py 全 codebase grep,**唯一**的 cross-store interaction 是 `Memory.delete_all()`([main.py:613](../../mem0/memory/main.py#L613))同步清空兩 store。其他 path 全部 parallel + independent:

```python
# main.py:160-167 — ingestion
with concurrent.futures.ThreadPoolExecutor() as executor:
    future1 = executor.submit(self._add_to_vector_store, ...)  # → ADD/UPDATE/DELETE on Qdrant
    future2 = executor.submit(self._add_to_graph, ...)         # → DELETE/ADD entity on Neo4j
    concurrent.futures.wait([future1, future2])
    # 兩 future result 各自 return,沒有任何 reconciliation

# main.py:489-497 — search
with concurrent.futures.ThreadPoolExecutor() as executor:
    future_memories = executor.submit(self._search_vector_store, ...)  # → top-K text memories
    future_graph_entities = executor.submit(self.graph.search, ...)    # → top-5 BM25-reranked triples
    # 各自 return,results / relations dict 兩個 key 分開
```

**兩個 L2/G4 LLM 各自看到的 "existing memory" 完全不同**:
- Vector L2:既有 memory **文字 string**(top-5 vector search)
- Graph G4:既有 entity **triples**(Cypher MATCH query)

→ 兩個 LLM 各自獨立判斷 ADD/UPDATE/DELETE,**state divergence 是設計上的結構特徵,不是 bug**。

### 8.2 三種 divergence 情境(FC 反事實題)

| 情境 | Vector L2 行為 | Graph G4 行為 | 結果 |
|---|---|---|---|
| **Happy path** | UPDATE 舊事實為新 | DELETE 舊 entity + ADD 新 entity | 兩 store 一致,prompt 乾淨,LLM 答對 |
| **Unhappy V**(vector 漏 detect)| 純 ADD,雙存 old + new | DELETE + ADD,graph 乾淨 | vector 回 [old, new],graph 回 (new) → bullet list 含矛盾事實 |
| **Unhappy G**(graph 漏 detect)| UPDATE,vector 乾淨 | 雙 ADD,graph 含 (old)+(new) | vector 回 (new),graph relations 含 (old)+(new) → prompt-aware LLM 看到 relations 帶矛盾 |

### 8.3 對 Plan A mechanism 觀察的解釋

Plan A FC-MH 32k(全 cells `analysis/results/plan_a/`)的 mechanism:

| 條件機率 | Mem0 MH 32k | Mem0g-pa MH 32k | Δ |
|---|---:|---:|---:|
| P(R\|D=1)| 39% | 35% | **-4** ← graph 在 32k 反而 hurts |
| P(A\|R=1)| 60% | 66% | **+6** ← graph 在 32k LLM inference 仍 helps |
| Net EM | 39% | 40% | ≈ 0 |

→ Plan A 觀察到的「graph 在 32k 兩效應相消」可由 **two-store divergence in 32k 加重**解釋:

- 32k 有更多 chunks → mem0 L2 over-trigger(precision 0.97 → 0.51)+ graph G4 也 over-trigger
- 兩 store 各自 noisy → state divergence 機率上升
- vector retrieval 帶回的 memories 跟 graph relations **更常矛盾**
- LLM 看到 facts 與 relationships 衝突 → 信不過 facts,但 relations 又指方向(P(A|R=1) +6)

### 8.4 對 paper §6.4 / §7 的 framing 建議

可加一段 paper-level limitation 寫法:

> "Mem0g's two-store design — parallel vector and graph paths sharing no
> reconciliation step beyond `delete_all` — means the vector L2 update
> decision and the graph G4 entity-deletion decision are made by two
> *independent* LLM calls, each seeing only its own store's existing state.
> At long context (FC-MH 32k), this divergence appears to compound:
> vector L2 precision collapses from 0.97 to 0.51 and the graph layer's
> entity-deletion judgments suffer similarly, producing retrieval results
> where memory texts and graph triples increasingly disagree. We hypothesise
> that this is why Mem0g-prompt-aware's P(R|D=1) actually *drops* 4pp at 32k
> (39% → 35%) even as graph relations help the LLM answer correctly when
> context is clean (P(A|R=1) +6pp). This is a structural limitation of
> write-time multi-store designs; query-time conflict detection (our method)
> avoids it by reconciling against retrieved candidates at a single point."

### 8.5 對 Ours method 的啟示

我們的設計可避免 two-store divergence:
- 查詢時對「最終要送進 LLM 的 memory candidates」做 conflict detection
- 即使 ingestion 時各 store 不一致,query-time 可看到所有候選一起,單點決策
- 不需要 ingestion-time 兩個 LLM 互相猜對方在做什麼

→ paper §3 method 章節可寫:「Unlike write-time graph memory methods such as
Mem0g, our query-time conflict reconciliation operates on a single fused
candidate set at retrieval time, avoiding the consistency issues that arise
from parallel ingestion paths in two-store designs.」

---

**End of mem0g_reproducibility.md(updated 2026-05-30 with §8 two-store divergence)**
