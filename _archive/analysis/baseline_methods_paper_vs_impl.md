# Baseline 方法分析:mem0g / Zep / HippoRAG-v2 — 論文 vs 實作對齊

**建立日期**:2026-05-24
**目的**:作為未來與 Claude 討論本 repo 對比 baseline 時的參考文件。回答兩個核心問題:
1. 在學術論述上對比這些方法時,應根據**論文宣稱**還是**實際程式碼**?
2. 從論文預期的對比結論,能不能從目前 MABench vendored 實作中找到佐證?

文件 self-contained,未來 Claude 沒看過原對話也能 pick up。

---

## 0. TL;DR(決策摘要)

- **mem0g**:用 [MABench/mem0/](../mem0/) vendored 版本(v2 fork)。**論文宣稱 soft invalidate + temporal reasoning,但實作是 hard `DELETE r`**,且 upstream v3 已完全移除圖記憶。
- **Zep**:用 MABench 內 `zep_cloud` SDK call(走雲端後端),**Graphiti OSS 才是論文的官方實作**,對應度極高。未來若 fail case analysis 需深挖機制,再換 [/home/yhchiang/graphiti/](../../graphiti/) 本地化。
- **HippoRAG-v2**:vendored 在 [MABench/methods/hipporag/](../methods/hipporag/),與論文一致。
- **學術論述對比策略**:**根據實作為主**(凍結、可重現),**對齊論文宣稱的部分用論文佐證**,**論文宣稱但實作沒做的要透明標註**。

---

## 1. 三方法系統架構速覽

| 面向 | mem0g | HippoRAG-v2 | Zep (cloud SDK) / Graphiti (OSS) |
|---|---|---|---|
| **儲存形式** | Neo4j + 向量 | iGraph + Parquet 嵌入(chunk/entity/fact 三套) | Neo4j(Graphiti) / Zep cloud 託管 |
| **圖結構** | 必須 | 必須(多跳是核心) | 必須(Episode + Entity + Community 三層) |
| **Ingest 抽 fact** | LLM 抽 triple | OpenIE NER + Triple | Graphiti:LLM extract_edges;Zep cloud:後端非同步 |
| **檢索方式** | 純向量 + BM25 rerank(可選) | 多跳遍歷 + LLM verdict + DSPy rerank | 三 search(cos / BM25 / BFS)+ RRF/MMR/cross-encoder rerank |
| **時間感知** | 無 | 無 | **Bi-temporal 四欄位** |
| **後端靈活性** | 高(原 v2 支援多種 graph backend) | 中(綁 iGraph) | 低(綁 Neo4j) |
| **MABench 入口** | [agent.py:464-492](../agent.py#L464-L492) `_handle_mem0_agent` | [agent.py:744-780](../agent.py#L744-L780) `_handle_hippo_rag` | [agent.py:503-541](../agent.py#L503-L541) `_handle_zep_agent` |

---

## 2. 衝突偵測機制 — 三方法詳細對比

### 2.1 mem0g

**主流程**:[mem0/memory/graph_memory.py:49-67](../mem0/memory/graph_memory.py#L49-L67) 的 `add()`,五步走:
1. 抽實體
2. LLM 抽新 triple
3. 用向量相似度從 Neo4j 撈出可能受影響的既有 node/edge
4. **`_get_delete_entities_from_search_output()`** → LLM 判斷哪些舊邊該刪 ([graph_memory.py:260-285](../mem0/memory/graph_memory.py#L260-L285))
5. 先刪舊邊、再加新邊

**衝突判定 prompt**:[mem0/graphs/utils.py:57-91](../mem0/graphs/utils.py#L57-L91) 的 `DELETE_RELATIONS_SYSTEM_PROMPT`:

> Deletion Criteria: Delete a relationship only if it meets at least one of these conditions:
> - **Outdated or Inaccurate**: The new information is more recent or accurate.
> - **Contradictory**: The new information conflicts with or negates the existing information.
>
> **DO NOT DELETE** if there is a possibility of same type of relationship but different destination nodes.

工具定義:[mem0/graphs/tools.py:310-371](../mem0/graphs/tools.py#L310-L371) 的 `DELETE_MEMORY_TOOL_GRAPH`。

**實際刪除動作**:[mem0/memory/graph_memory.py:287-313](../mem0/memory/graph_memory.py#L287-L313):
```cypher
MATCH (n {name: $source_name, user_id: $user_id})
-[r:{relationship}]->
(m {name: $dest_name, user_id: $user_id})
DELETE r          ← 真實 hard delete,沒有 SET r.invalid_at
```

**特點**:LLM 判斷 + hard delete + 保留多值關係。沒有時間欄位。

### 2.2 Zep / Graphiti

#### 客戶端(zep_cloud SDK)能看到的

[methods/zep.py:33-35](../methods/zep.py#L33-L35) 和 [agent.py:757-790](../agent.py#L757-L790):
- 每個 edge 有 `valid_at` / `invalid_at` 兩個時間欄位
- 客戶端無法看到 conflict 判定過程,只能看到結果(被標 invalid 的舊邊)
- MABench 已把每個 query 的 edges/nodes/episodes dump 到 `./outputs/rag_retrieved/<agent>/k_X/<subset>/chunksize_Y/query_*.json`

#### Graphiti OSS(官方實作)真正的衝突偵測

(若未來需要白盒分析才會用到)

**主流程**:[graphiti_core/graphiti.py:980](../../graphiti/graphiti_core/graphiti.py#L980) 的 `add_episode()`

**Edge 衝突核心**:[edge_operations.py:325-535](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L325-L535) 的 `resolve_extracted_edges`

候選邊撈取兩通道:
- 同端點直查:[edge_operations.py:367-370](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L367-L370) — `EntityEdge.get_between_nodes(source, target)`
- 混合搜尋 RRF:[edge_operations.py:392-430](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L392-L430) — 向量 + BM25
  - `related_edges`(限同端點)用於去重
  - `edge_invalidation_candidates`(全圖)用於衝突偵測

LLM 雙標籤判定:[edge_operations.py:623](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L623) 回傳 `EdgeDuplicate(duplicate_facts, contradicted_facts)`,prompt 在 [dedupe_edges.py:43-100](../../graphiti/graphiti_core/prompts/dedupe_edges.py#L43-L100)

時間規則層:[edge_operations.py:538-573](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L538-L573) 的 `resolve_edge_contradictions`:
```python
elif edge.valid_at < resolved_edge.valid_at:
    edge.invalid_at = resolved_edge.valid_at   # 舊邊有效到新邊生效那一刻
    edge.expired_at = utc_now()                # 系統標記時間
    invalidated_edges.append(edge)
```

**Bi-temporal 四欄位**([edges.py:271-282](../../graphiti/graphiti_core/edges.py#L271-L282)):
| 欄位 | 含義 |
|---|---|
| `created_at` | 邊寫入 Neo4j 的物理時間 |
| `valid_at` | 事實在現實成真的時間 |
| `invalid_at` | 事實在現實失效的時間 |
| `expired_at` | 系統標記失效的物理時間 |

**特點**:雙通道候選 + LLM 雙標籤(duplicate vs contradict)+ 時間規則 + soft invalidate + bi-temporal。

### 2.3 三方法對比表

| 面向 | mem0g | Graphiti (OSS) | Zep cloud (黑盒) |
|---|---|---|---|
| 候選撈取 | 向量相似度 | 雙通道:同端點 + RRF | 不可見 |
| LLM 判定維度 | 一維(DELETE or not) | **二維**(`duplicate_facts` + `contradicted_facts`) | 不可見 |
| 時間規則層 | 無 | 有(`resolve_edge_contradictions`) | 結果可見(`invalid_at` 欄位) |
| 處理動作 | **Hard DELETE 邊** | **Soft invalidate**(設 `invalid_at` + `expired_at`) | Soft invalidate(僅結果) |
| 時間欄位 | 無 | 4 欄位 bi-temporal | 2 欄位(`valid_at` / `invalid_at`)可見 |
| 可回溯歷史 | 不行(邊已刪) | 可以 | 部分(SDK 可能需特殊參數) |
| 多值容忍 | prompt 明寫不刪同類型不同 destination | 用時間區間判斷 | 不可見 |

---

## 3. 論文 vs 開源實作對齊度(關鍵發現)

這是寫論文時要小心的地方。

### 3.1 mem0g — 論文宣稱 ≠ 實作(且 upstream 已死)

**論文** ([arXiv 2504.19413](https://arxiv.org/pdf/2504.19413), Chhikara et al., 2025-04-28) §2.2:
> "An LLM-based update resolver determines if certain relationships should be obsolete, **marking them as invalid rather than physically removing them to enable temporal reasoning**."

**實作** (MABench vendored,即 v2 fork):
- [mem0/memory/graph_memory.py:287-313](../mem0/memory/graph_memory.py#L287-L313) Cypher `DELETE r` — **真實 hard delete**
- 沒有 `valid_at` / `invalid_at` 任何時間欄位定義
- prompt 名稱叫 `DELETE_RELATIONS_SYSTEM_PROMPT`,不是 invalidation

**upstream 演進**:
- v2(MABench fork 的時期):有 `mem0/memory/graph_memory.py`(744 行)+ `mem0/graphs/` 整個目錄
- **commit `a488e190` (2026-04-14, v3 pipeline)**:一刀砍掉 graph_memory.py、apache_age_memory.py、kuzu_memory.py、memgraph_memory.py、Neptune backend 等,合計移除 3000+ 行圖記憶相關程式
- 取代:新增 `mem0/utils/entity_extraction.py`(spaCy 規則抽 entity)+ `lemmatization.py` + `scoring.py`(additive scoring)
- 現在 upstream [/home/yhchiang/mem0/mem0/memory/](../../mem0/mem0/memory/) 只剩 main.py / base.py / storage.py / utils.py

**結論**:**mem0g 只在 MABench 內存在**。upstream v3 不再有圖記憶。

### 3.2 Zep / Graphiti — 對應度極高(同團隊論文+實作)

**論文** ([arXiv 2501.13956](https://arxiv.org/pdf/2501.13956), Rasmussen et al., 2025-01-20) §1:
> "we introduce Zep, a memory layer service **powered by Graphiti**"

**逐條對照**:

| 論文段落 | Graphiti OSS 程式碼 | 對齊度 |
|---|---|---|
| §2.2.3 *"invalidates the affected edges by setting their t_invalid to the t_valid of the invalidating edge"* | [edge_operations.py:569-571](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L569-L571) — `edge.invalid_at = resolved_edge.valid_at; edge.expired_at = utc_now()` | **逐字對應** |
| §2.2.2 *"hybrid search for relevant edges is constrained to edges existing between the same entity pairs"* | [edge_operations.py:367-370](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L367-L370) — `EntityEdge.get_between_nodes(source_uuid, target_uuid)` | **逐字對應** |
| §2 bi-temporal 四欄位 `t'_created / t'_expired / t_valid / t_invalid` | [edges.py:271-282](../../graphiti/graphiti_core/edges.py#L271-L282) — `created_at / expired_at / valid_at / invalid_at` | 命名一致 |
| §3 三 search:`φ_cos` / `φ_bm25` / `φ_bfs`;reranker:RRF / MMR / cross-encoder | Graphiti 都有 | 對應 |

**時間落差**:論文發表時(2025-01-20)Graphiti 已有 213 commits 但還沒到 v0.1;現在(2026-05)是 v0.29.1。核心機制保留,prompt / reranker / community 持續迭代。

**結論**:Graphiti OSS 是 Zep 論文的**正向實作**,跟 mem0g 完全相反的狀況。

### 3.3 HippoRAG-v2

vendored 在 [methods/hipporag/](../methods/hipporag/),與論文一致(自家 repo)。Phase 0-3 結構([HippoRAG.py:247-296](../methods/hipporag/HippoRAG.py#L247-L296))對應論文 4 階段設計。

---

## 4. 學術公平性的決策

### 4.1 為什麼用 MABench vendored 為主

| 公平性層次 | 定義 | MABench vendored 是否達成 |
|---|---|---|
| Reproducibility | 別人 clone repo 能跑出同結果 | mem0g ✅ / HippoRAG ✅ / **Zep ❌**(後端會變) |
| Implementation fidelity | 跑的 code 對應論文 | mem0g ⚠️ / HippoRAG ✅ / Zep 不可驗證 |
| Temporal alignment | 各方法在同時間點 | mem0g v2 + HippoRAG paper 版 + Zep 即時版 — **不對齊** |

**決策**:Reproducibility 優先,所以 mem0g 和 HippoRAG 用 vendored;Zep 暫時接受不對稱(走 SDK),如果 fail case analysis 需要深挖機制再換 Graphiti。

### 4.2 換 Graphiti OSS 的觸發條件

預先設好 trigger 避免卡住:
- ✅ **黑盒夠用**:論文 claim 停留在「Zep 在 X% 案例下衝突偵測失敗」
- ❌ **必須換 Graphiti**:要 claim「**為什麼**失敗 — 候選邊撈取太窄 / LLM prompt 缺陷 / 時間規則 bug」這類**機制層級**論點

換句話說:**測量 fail rate → 黑盒夠;歸因 fail cause → 要白盒**。

### 4.3 換 Graphiti 的工程預估

- 改寫 [methods/zep.py](../methods/zep.py) 把 `zep_cloud` SDK call 替換成 `graphiti_core.Graphiti`
- 需要本地 Neo4j(`docker run -p 7687:7687 neo4j`)
- 改寫 [agent.py:503-541](../agent.py#L503-L541) `_handle_zep_agent` 的 ingest / retrieve 邏輯
- 對齊 embedder / LLM(論文用 `gpt-4o-mini-2024-07-18` + BGE-m3)
- 工程量:約一週

---

## 5. Fail Case Analysis 策略

### 5.1 黑盒(zep_cloud SDK)下能做的分類

MABench 已存的 JSON([agent.py:757-790](../agent.py#L757-L790))內含 `edges` 帶 `valid_at` / `invalid_at`、`response`、`context_block`。可分類:

| Fail mode | 判定方式(僅靠 JSON) |
|---|---|
| **A. Conflict 未偵測** | 同 `source/target/relation` 的兩條 edge 都 `invalid_at=None` 且 fact 語意對立 |
| **B. 偵測到但答案錯** | `invalid_at` 設了,但 `response` 引用了失效事實 |
| **C. Recall 失敗** | golden answer 對應的事實不在 edges/episodes |
| **D. Temporal 順序錯** | 時間區間跟 ground truth 衝突 |
| **E. Entity resolution 失敗** | 同一現實對象散在多個 node UUID |

### 5.2 黑盒下看不到的(需 Graphiti 白盒)

- Zep 為什麼判定衝突 / 為什麼沒判定(後端 LLM prompt + output)
- 候選邊撈了哪些
- Entity dedupe 過程
- LLM silent failure

### 5.3 不換 Graphiti 下最大化分析的技巧

1. **時間旅行 query**:檢查 `client.graph.search(search_filters=...)` 能否抓含失效邊的歷史快照
2. **Ingest 前後 diff**:在 [agent.py:689](../agent.py#L689) `client.graph.add()` 前後各 query 一次,diff 出新被設 `invalid_at` 的邊 → 重建衝突偵測時間線(看到結果差異,但仍看不到 prompt)

---

## 6. 核心開放問題:論文論述對比應根據什麼?

### 6.1 建議的決策框架

**主原則**:**根據實作為主,論文宣稱為輔,落差明確透明化**。

理由:
- 學術倫理:你跑的數字來自實作,論述就要對得起實作
- Reproducibility:讀者重現實驗看的是程式碼,不是論文文字
- 避免被 reviewer 抓:「你說 mem0g 有 temporal reasoning,但你跑的版本實際是 hard delete」

### 6.2 各情境下的策略

| 對比場景 | 策略 |
|---|---|
| Related Work 介紹方法 | 引論文,寫方法**設計理念** |
| Baselines 章節描述實驗設定 | 寫實際**跑的 code 來源 + 版本 + 與論文宣稱的落差** |
| Experiments 章節做 claim | 基於**實作行為**,不是論文宣稱 |
| Discussion 章節談 implication | 可以對比「論文宣稱 vs 實作能力」這個落差本身 → 變成研究觀察 |

### 6.3 三方法的具體論述模板

**mem0g**(注意!):
> "We compare against mem0's graph variant (mem0g; Chhikara et al., 2025). We use the open-source implementation bundled in MemoryAgentBench (forked from mem0 v2.x prior to the v3 graph-memory removal in April 2026). **Note that the public implementation performs hard deletion of contradicted edges (`DELETE r` in Cypher) rather than the soft invalidation described in the paper**, and does not maintain temporal validity fields."

**Zep**(目前 SDK 版):
> "We evaluate Zep (Rasmussen et al., 2025) through its hosted cloud API (zep_cloud SDK, as bundled in MemoryAgentBench). Unlike mem0g and HippoRAG-v2 which are pinned to OSS snapshots, **Zep's backend may evolve between evaluation runs**. Results reported are from runs conducted between [date range]."

**Zep**(未來換 Graphiti 版):
> "We use Graphiti v0.29.1 (the official open-source implementation of Zep; Rasmussen et al. 2025), which extends the original architecture while preserving the core bi-temporal edge invalidation mechanism described in §2.2.3 of the paper."

**HippoRAG-v2**:
> "We use the HippoRAG-v2 implementation bundled in MemoryAgentBench, which corresponds to the released code from the original authors."

### 6.4 論文預期對比 → 實作佐證的可行性

| 論文預期能 claim 的對比 | MABench vendored 實作能否佐證 |
|---|---|
| mem0g vs Graphiti:soft vs hard invalidation 的 temporal reasoning 差異 | ⚠️ 部分 — mem0g 端能驗證(無時間欄位),Zep 端只看得到 `invalid_at` 結果,看不到內部 |
| Zep 的 bi-temporal 帶來 knowledge-update 題型優勢 | ✅ 能 — LongMemEval `knowledge-update` / `temporal-reasoning` 題型結果可直接比較 |
| Graphiti 雙標籤(duplicate vs contradict)的精度 | ❌ 不能 — Zep cloud 黑盒;需要換 Graphiti OSS |
| HippoRAG 多跳遍歷在 multi-hop 題的優勢 | ✅ 能 — Phase 2 路徑可從 retrieve trace 觀察 |
| mem0g hard delete 在時間問題上的劣勢 | ✅ 能 — 直接從 mem0g 無法回答「她以前在哪工作」這類題目佐證 |

---

## 7. 關鍵程式碼路徑速查

### mem0g
- 入口:[mem0/memory/graph_memory.py:49-67](../mem0/memory/graph_memory.py#L49-L67) `add()`
- 衝突判定:[mem0/memory/graph_memory.py:260-285](../mem0/memory/graph_memory.py#L260-L285) `_get_delete_entities_from_search_output`
- Hard delete Cypher:[mem0/memory/graph_memory.py:287-313](../mem0/memory/graph_memory.py#L287-L313) `_delete_entities`
- Prompt:[mem0/graphs/utils.py:57-91](../mem0/graphs/utils.py#L57-L91) `DELETE_RELATIONS_SYSTEM_PROMPT`
- MABench 整合:[agent.py:464-492](../agent.py#L464-L492) `_handle_mem0_agent`

### Zep (cloud SDK)
- Wrapper:[methods/zep.py](../methods/zep.py)
- MABench 整合:[agent.py:503-541](../agent.py#L503-L541) `_handle_zep_agent`
- Ingest:[agent.py:689-693](../agent.py#L689-L693) `client.graph.add()`
- Retrieve:[agent.py:717](../agent.py#L717) `client.graph.search(scope=...)`
- Edge 序列化(含 `invalid_at`):[agent.py:757-765](../agent.py#L757-L765) `_serialize_edges`
- 輸出 JSON 位置:`./outputs/rag_retrieved/<agent>/k_X/<subset>/chunksize_Y/query_*.json`

### Graphiti (OSS,僅未來需要時)
- 入口:[graphiti_core/graphiti.py:980](../../graphiti/graphiti_core/graphiti.py#L980) `add_episode()`
- Edge 衝突解析:[edge_operations.py:325-535](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L325-L535) `resolve_extracted_edges`
- 單邊衝突判定:[edge_operations.py:623](../../graphiti/graphiti_core/utils/maintenance/edge_operations.py#L623) `resolve_extracted_edge`
- Bi-temporal 欄位:[edges.py:271-282](../../graphiti/graphiti_core/edges.py#L271-L282)
- Prompt:[dedupe_edges.py:43-100](../../graphiti/graphiti_core/prompts/dedupe_edges.py#L43-L100)

### HippoRAG-v2
- 主類別:[methods/hipporag/HippoRAG.py](../methods/hipporag/HippoRAG.py)
- 4 phase:[HippoRAG.py:247-354](../methods/hipporag/HippoRAG.py#L247-L354)
- 三組 EmbeddingStore:[HippoRAG.py:138-146](../methods/hipporag/HippoRAG.py#L138-L146)
- Rerank:[methods/hipporag/rerank.py](../methods/hipporag/rerank.py)
- MABench 整合:[agent.py:744-780](../agent.py#L744-L780) `_handle_hippo_rag`

---

## 8. 待辦 / 後續討論點

- [ ] 從現有 `outputs/rag_retrieved/Structure_rag_zep_*` JSON 跑一輪 fail mode A-E 分類,評估黑盒是否撐得住論文 claim
- [ ] 確認 `zep_cloud` SDK 是否支援 `include_invalidated` 之類參數能抓歷史失效邊
- [ ] 評估若要換 Graphiti 本地化,實際工程量(本地 Neo4j + embedder/LLM 對齊)
- [ ] 決定:論文 Discussion 章節是否要把「mem0 工業界已放棄圖記憶 vs Zep 雙押圖記憶」這個觀察寫入

---

## 9. 參考論文

- mem0:Chhikara et al., *"Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory"*, [arXiv:2504.19413](https://arxiv.org/pdf/2504.19413), 2025-04-28
- Zep:Rasmussen et al., *"Zep: A Temporal Knowledge Graph Architecture for Agent Memory"*, [arXiv:2501.13956](https://arxiv.org/pdf/2501.13956), 2025-01-20
- HippoRAG-v2:原論文(待補)
