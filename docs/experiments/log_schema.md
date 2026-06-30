# mem0 / mem0g 實驗 Log Schema

> 建立日期:2026-05-24
> 目的:讓未來分析者(包含未來的 Claude session)知道每次 pilot 跑出來「什麼東西存在哪、欄位代表什麼、怎麼串到 MQuAKE GT 做 hop-level 分析」

---

## 0. 三層 Log 總覽

每跑一個 `(agent_name, sub_dataset)` 組合(例如 `Structure_rag_mem0g_gemini-2.5-flash-lite × factconsolidation_mh_6k`),系統會自動產出三層 log:

```
outputs/
├── <output_dir>/Conflict_Resolution/<sub>_..._results.json   ← Layer C (主結果)
└── rag_retrieved/<agent_name>/k_<retrieve_num>/<sub_dataset>/chunksize_<size>/
    ├── ingestion_context_0.jsonl                              ← Layer A (ingest events)
    ├── ingestion_context_1.jsonl
    ├── ...
    ├── query_0_context_0.json                                 ← Layer B (retrieve events)
    ├── query_1_context_0.json
    └── ...
```

- **Layer A — ingest events** (per chunk 寫入):mem0/mem0g 把對話歷史每個 chunk 抽出來、跟既有記憶比對、決定 ADD/UPDATE/DELETE/NOOP 的紀錄
- **Layer B — retrieve events** (per query 一個 JSON):每題 query 拿到的 memories(向量+圖)、組成 context、最終 LLM 答案
- **Layer C — final results** (per run 一個 JSON):agent_config / dataset_config 完整快照 + 每題 metrics(exact_match / f1 / rougeL...)

三層串起來才能做 hop-level fail case 分析。

---

## 1. Layer A:Ingest Events(`ingestion_context_N.jsonl`)

每行 JSON,每次 `memory.add()` 一筆。

**Schema**(來自 [agent.py:599-603](../../agent.py#L599-L603)):

```json
{
  "query_id": null,
  "vector_results": {
    "results": [
      {"id": "uuid-1", "memory": "Charles Darwin authored Our Mutual Friend.", "event": "ADD"},
      {"id": "uuid-2", "memory": "Charles Darwin married Amala Paul.", "event": "UPDATE",
       "previous_memory": "Charles Darwin married Emma Darwin."},
      {"id": "uuid-3", "memory": "Amala Paul is from India.", "event": "DELETE"},
      {"id": "uuid-4", "memory": "Steve Jobs founded Apple.", "event": "NONE"}
    ],
    "relations": [
      {"source": "Our Mutual Friend", "relation": "authored_by", "destination": "Charles Darwin"},
      {"deleted_entities": [...], "added_entities": [...]}
    ]
  }
}
```

### 欄位解釋

| 欄位 | 含義 | 哪個方法會有 |
|---|---|---|
| `query_id` | 若是 ingest 階段為 `null`,query 階段不會寫到此檔 | 都有 |
| `vector_results.results[].event` | LLM 在 update 階段判定的動作: `ADD` / `UPDATE` / `DELETE` / `NONE` | mem0 + mem0g |
| `vector_results.results[].memory` | 該 event 對應的 fact 文本 | 都有 |
| `vector_results.results[].previous_memory` | UPDATE 時舊版 fact | 都有 |
| `vector_results.relations` | mem0g 圖層回傳:`deleted_entities` / `added_entities`(triple list) | **mem0g only** |

### 一個 chunk 對應多少行?

通常一個 chunk 抽出 5-15 個 facts,每個 fact 走一個 event。所以一個 chunk **產生一筆 `memory.add()` call**,在 jsonl 上是**一行**,但裡面 `results` 是 list,包多個 event。

### 怎麼用這個 log 分析

- **D1 ADD/UPDATE/DELETE 統計**:讀全部 jsonl line,Counter event 字串
- **D2 衝突偵測 fail 分析**:當 chunk 同時包含 gt_seq 和 old_seq 對應的 fact 時,應該有對應的 UPDATE 或 DELETE。沒有 = fail mode A
- **D7 hard delete 影響**:讀所有 `event == "DELETE"`,看是否誤刪正確 fact(對 mem0g 特別重要)

---

## 2. Layer B:Retrieve Events(`query_I_context_J.json`)

每題 query 一個 JSON 檔(`I` 是 query_id,`J` 是 context_id)。

**Schema**(來自 [agent.py:643-654](../../agent.py#L643-L654)):

```json
{
  "retrieved_memories": [
    {"id": "uuid-1", "memory": "...", "score": 0.82, ...},
    {"id": "uuid-2", "memory": "...", "score": 0.79, ...}
  ],
  "retrieved_relations": [
    {"source": "Alice", "relation": "lives_in", "destination": "London", ...}
  ],
  "memories_str": "- memory text 1\n- memory text 2\n...",
  "system_prompt": "You are a helpful AI...",
  "user_message": "...... Current Time: ......",
  "response": "Belgium.",
  "prompt_tokens": 1234,
  "completion_tokens": 5
}
```

### 欄位解釋

| 欄位 | 含義 |
|---|---|
| `retrieved_memories` | mem0 向量檢索的 top-k facts(k=`retrieve_num`,通常 100) |
| `retrieved_relations` | **mem0g only** — 圖檢索的 BM25-reranked triples |
| `memories_str` | 餵給 LLM 的 context 文本 |
| `response` | LLM 最終答案 |
| `prompt_tokens` / `completion_tokens` | Token usage(用於 cost 分析 D5) |

### 怎麼用這個 log 分析

- **D3 retrieve recall**:對每題,看 gt_seq 對應的 fact text 是否出現在 `retrieved_memories` 裡(用 [align_mem0_mquake.py](../../analysis/align_mem0_mquake.py) 自動完成)
- **D8 mem0 vs mem0g ablation**:對比 `retrieved_memories` 和 `retrieved_relations` 提供的訊息差異
- **D9 top-k rank 分佈**:把 gt_seq 對應 memory 的位置(rank)累積成 histogram

---

## 3. Layer C:Final Results(`<output_dir>/Conflict_Resolution/<sub>_..._results.json`)

**Schema**(來自 [main.py:65-91](../../main.py#L65-L91)):

```json
{
  "agent_config": {
    "agent_name": "Structure_rag_mem0g_gemini-2.5-flash-lite",
    "model": "gemini-2.5-flash-lite",
    "mem0_config": {...},   ← 完整 yaml 內容
    ...
  },
  "dataset_config": {
    "sub_dataset": "factconsolidation_mh_6k",
    "context_max_length": 6000,
    "chunk_size": 4096,
    ...
  },
  "data": [
    {
      "qa_pair_id": "factconsolidation_mh_6k_no0",
      "query": "...",
      "answer": ["Belgium"],
      "output": "Belgium.",
      "parsed_output": "Belgium",
      "exact_match": true,
      "f1": 1.0,
      "memory_construction_time": 123.4,
      "query_time_len": 2.1,
      ...
    },
    ...
  ],
  "metrics": {"exact_match": [...], "f1": [...]},
  "averaged_metrics": {"exact_match": 0.5, "f1": 0.6},
  "time_cost_list": [...]
}
```

### 欄位解釋

| 欄位 | 含義 |
|---|---|
| `agent_config` | yaml 完整快照(包含 `mem0_config`,讓未來能 reproduce) |
| `dataset_config` | dataset yaml 完整快照 |
| `data[].exact_match` / `f1` / `rougeL_f1` | metrics per query |
| `data[].memory_construction_time` | ingest 階段累積時間 |
| `data[].query_time_len` | 該 query retrieve + LLM 答題時間 |

### 怎麼用這個 log 分析

- **總體準確度**(`averaged_metrics`)
- **D5 latency / cost**:`memory_construction_time` + `query_time_len`,加 Layer B 的 token counts
- **跑了什麼配置**:任何 reproducibility 需求都看這

---

## 4. 三層 Log 串接 → Hop-level Fail Analysis

完整 fail case 分析需要把 Layer A + B + C + **MQuAKE GT** 串起來:

```
Layer C: data[i].exact_match = false                          ← 知道哪題答錯
      ↓
Layer B: query_i_context_0.json → retrieved_memories          ← 看 retrieve 抓到什麼
      ↓
Layer A: ingestion_context_0.jsonl → ADD/UPDATE/DELETE list   ← 看 ingest 怎麼處理
      ↓
MQuAKE align: analysis/results/mh_512_mquake_analysis.json    ← 對應 hop 的 gt_seq, old_seq
      ↓
  align_mem0_mquake.py 自動結合上面所有資訊輸出:
  {"qa_pair_id": ..., "hops": [{"gt_in_memories": ..., "old_in_memories": ...,
                                  "gt_memory_rank": ..., ...}], "error_type": ...}
```

執行命令(以 mem0g × FC-MH 6k 為例):

```bash
python analysis/align_mem0_mquake.py \
  --results outputs/gemini-2.5-flash-lite-mem0g/Conflict_Resolution/factconsolidation_mh_6k_*_results.json \
  --context analysis/contexts/factconsolidation_6k_context.txt \
  --mode mh \
  --retrieval-dir outputs/rag_retrieved/Structure_rag_mem0g_gemini-2.5-flash-lite/k_100/factconsolidation_mh_6k/chunksize_4096 \
  --out analysis/results/mem0g_gemini-2.5-flash-lite_mh_6k_mquake.json
```

輸出包含 §1 §2 §3 + MQuAKE 的所有資訊融合的 per-query × per-hop JSON。

---

## 5. Reproducibility 注意事項

| 要 capture 的東西 | 已 capture? | 在哪 |
|---|---|---|
| agent yaml 內容 | ✅ | Layer C `agent_config` |
| dataset yaml | ✅ | Layer C `dataset_config` |
| mem0 內部 LLM model | ✅ | `agent_config.mem0_config.llm.config.model` |
| mem0 embedding model | ✅ | `agent_config.mem0_config.embedder.config.model` |
| 答題 LLM model | ✅ | `agent_config.model` |
| Neo4j 連線 | ✅(URL 在 yaml) | `agent_config.mem0_config.graph_store.config.url` |
| Neo4j version | ⚠️ 未自動 capture | 手動記在 [docs/infrastructure/neo4j_setup.md](../infrastructure/neo4j_setup.md) |
| mem0 vendored 版本(commit hash) | ⚠️ 未自動 capture | 因為是 vendored 不是 git 追蹤;可手動記 |
| git hash of MABench | ⚠️ 未自動 | 跑前可手動 `git rev-parse HEAD > outputs/.../git_hash.txt` |

未來若要做更嚴格 reproducibility,可在 main.py 加 dump git hash 的小段 — 不過 v1 pilot 不需要。

---

## 6. Dataset 隔離怎麼讓 log 不互相污染

mem0/mem0g 用 `user_id = f"context_{context_id}_{sub_dataset}"`(見 [agent.py:583](../../agent.py#L583))。所以即使所有實驗共享同一個 Neo4j 容器,**圖、SQLite history、vector store 都按 user_id 隔離**(mem0g Cypher query 都帶 `user_id` filter,見 [mem0/memory/graph_memory.py:107](../../mem0/memory/graph_memory.py#L107))。

→ 設計上**不需要清空,跑完所有 pilot 後資料庫內含所有實驗的快照**,任何時候都能回查任一個。詳見 [[../infrastructure/neo4j_setup.md]] §3。

---

## 7. 跨文件引用

- 怎麼跑 pilot:[[pilots/mem0_mem0g_pilot_plan.md]]
- alignment 詳細邏輯:[[../ground_truth/mquake_alignment_guide.md]]
- Neo4j 設置:[[../infrastructure/neo4j_setup.md]]
- baseline 方法比較:[[../baseline_methods/baseline_methods_paper_vs_impl.md]]
