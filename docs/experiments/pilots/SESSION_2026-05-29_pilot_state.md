# Pilot Session 狀態紀錄 — 2026-05-29

> 目的:這是 2026-05-29 整天 pilot 跑後的 checkpoint。讓未來自己 / 未來 Claude session / 跟 chat 討論時可以快速 pick up state。
> 本文件 self-contained。

---

## 0. TL;DR

- ✅ **3 個可信 finding 已 lock**(SH/MH × LCA/Mem0/Mem0g 已知 EM 數字)
- ✅ **9 個 monkey-patches** 已寫進 agent.py(處理 vendored mem0/mem0g internal bug + SQLite/qdrant 並行衝突)
- ❌ **4 個 runs 因 SQLite 並行衝突或 KeyError crash 需要重跑**
- ✅ **Mem0g MH 32k 已完成:32% EM**(P9 KeyError tolerance 有效,沒崩)
- 🔥 **NEW**:晚間 trace mem0/mem0g pipeline 發現 **3 個 paper-改寫級 bug**(F1/F2/F3),見 [[../../baseline_methods/CRITICAL_FINDINGS_2026-05-29_evening.md]]
- 📋 等 user 對 F1/F2/F3 處理 decision 後,實作三向分析 + 跑剩餘 ctx sweep

### 0.1 NEW Critical Findings(2026-05-29 night)— 詳見 CRITICAL_FINDINGS_2026-05-29_evening.md

- **F1**:Mem0g 抽取的 graph relations 在 `agent.py:899` **從未進入** final inference prompt;v1.3 §27.2 「圖層扣 9pp」claim 收回
- **F2**:Final prompt 無 conflict / temporal hint,反事實 FC 題對 mem0 是最壞情境
- **F3**:Temperature 偏離 benchmark 預設(我們 0/0.1 vs benchmark 0.7),需 disclose 或改回

---

## 1. 所有 monkey-patches 完整清單(在 agent.py `_initialize_mem0_agent`)

| # | Patch | Bug 來源 | 詳細文件 |
|---|---|---|---|
| **P1** | `LlmFactory.provider_to_class["gemini"]` → `VertexGeminiLLM` | mem0 LLM whitelist 不含 vertexai;我們的 ADC wrapper 走 gemini provider 改 model class | [[../../baseline_methods/baseline_methods_paper_vs_impl.md]] |
| **P2** | `EmbedderFactory.provider_to_class["vertexai"]` → `VertexADCEmbedding` | Mem0 預設 vertexai embedder 要 service account JSON,我們的 wrapper 用 ADC | [methods/mem0_vertex_adc_embedder.py](../../../methods/mem0_vertex_adc_embedder.py) |
| **P3** | `EmbedderFactory.create` wrap (vector_config optional) | mem0 vendored 內部 API drift:`main.py` 用 3-arg,`graph_memory.py` 用 2-arg | [[../../baseline_methods/mem0g_vendored_bugs.md §1]] |
| **P4** | L1 prompt fix (移除 2 rejection few-shots) | mem0 預設 prompt 對 FC 拒收 declarative facts | [[../../baseline_methods/mem0_l1_prompt_fix.md]] |
| **P5** | `MemoryGraph._add_entities` backtick wrap + audit log | LLM 抽出 entity_type 含 `/` 等不合法字元,Cypher 拒收 | [[../../baseline_methods/mem0g_vendored_bugs.md §2]] |
| **P6** | `MemoryGraph._delete_entities` backtick wrap | 同 P5,relationship name 也 escape | 同上 |
| **P7** | qdrant path/collection 用 sub_dataset 後綴 | 並行跑 mem0/mem0g 多個 task 共用 `/tmp/qdrant_mem0_vertex_t4` → file lock 衝突 | (本文件 §3.2) |
| **P8** | `~/.mem0/history.db` SQLite path 用 sub_dataset 後綴 | 並行 mem0 process 共用 `~/.mem0/history.db` → SQLite write lock → `"attempt to write a readonly database"` → update phase silent fail | (本文件 §3.3) |
| **P9** | `MemoryGraph._remove_spaces_from_entities` 用 `.get()` 處理 missing key | vendored 直接 `item["relationship"]`,LLM 有時回 entity 缺 relationship key → KeyError mid-ingest crash | (本文件 §3.4) |

---

## 2. 目前所有 runs 的可信度 / 結果表

| Run | Method × Task × ctx | EM | Ingest Health | 可信? | 為什麼 |
|---|---|---:|---|---|---|
| 1 | LCA SH 6k | **96.0%** | LCA 無 ingest | ✅ | LCA 不受 mem0 衝突影響 |
| 2 | LCA SH 32k | **91.0%** | 同上 | ✅ | 同上 |
| 3 | LCA MH 6k | **16.0%** | 同上 | ✅ | 之前獨立跑 |
| 4 | LCA MH 32k | **16.0%** | 同上 | ✅ | 之前獨立跑 |
| 5 | LCA MH 64k | **12.0%** | 同上 | ✅ | 之前獨立跑 |
| 6 | LCA MH 262k | **4.0%** | 同上 | ✅ | 之前獨立跑 |
| 7 | Mem0 MH 6k | **50.0%** | 405 events ✅ | ✅ | 獨立跑,SQLite 沒衝突 |
| 8 | Mem0 SH 6k | 72.0% | **6 DELETE only** ❌ | ❌ | **SQLite 衝突**,需重跑 |
| 9 | Mem0 SH 32k | 86.0% | **6 DELETE only** ❌ | ❌ | **SQLite 衝突**,需重跑 |
| 10 | Mem0 MH 32k | 37.0% | **4 DELETE only** ❌ | ❌ | **SQLite 衝突**,需重跑 |
| 11 | Mem0g MH 6k (sanitizer) | 43.0% | 405+ events ✅ | ⚠️ | 用 sanitizer 跑,sanitizer 跟 backtick 差 2pp |
| 12 | Mem0g MH 6k (backtick) | **41.0%** | 330 events ✅ | ✅ | 用 backtick 跑,7 個 label wrap 紀錄在 audit log |
| 13 | Mem0g SH 6k | **71.0%** | 338 + 462 graph ✅ | ✅ | Backtick;跑時並行 process 少,SQLite 沒衝突 |
| 14 | Mem0g SH 32k | crash | 跑到 chunk 45 ❌ | ❌ | **KeyError 'relationship' P9 fix**,需重跑 |
| 15 | Mem0g MH 32k | **32.0%** | 100/100 跑完 ✅ | ✅ | **P9 KeyError tolerance 有效**,沒崩 |

**可信 + 未來實驗會 reuse**:1-7, 12-13, 15(9 個 cells)
**需要重跑**:8-10, 14(4 個 cells)

### 2.1 信賴 cells 主表(2026-05-29 20:56 update,加 Mem0g MH 32k)

| Method | SH 6k | SH 32k | MH 6k | MH 32k | MH 64k | MH 262k |
|---|---:|---:|---:|---:|---:|---:|
| LCA | **96%** | **91%** | **16%** | **16%** | **12%** | **4%** |
| Mem0(vec) | ⏳ rerun | ⏳ rerun | **50%** | ⏳ rerun | TBD | TBD |
| Mem0g(vec+graph) | **71%** | ⏳ rerun | **41%** | **32%** | TBD | TBD |

**Mem0g 6k→32k**:MH 41%→32%(-9pp),記憶長以後檢索/抽取被噪音稀釋,但相對 LCA 仍 +16pp(LCA 32k MH=16%)。圖層在 32k 依然存在「相對 vector 扣分」的可能,等 Mem0 MH 32k 重跑後才能 confirm。

---

## 3. 主要發現紀錄

### 3.1 LCA 是 SH 的天花板,MH 是 memory method 的主舞台

| Task | LCA 6k EM | LCA 32k EM | LCA 退化模式 |
|---|---:|---:|---|
| SH | **96%** | 91% | 微下降(-5pp) |
| MH | 16% | 16% | 平,但 64k=12%, 262k=4% |

**對 paper 的 implication**:
- SH 任務:**LCA 已接近 ceiling,memory method 在 SH 上「輸 LCA」是預期**,不是 method 缺陷
- MH 任務:**memory method 的真正舞台**(LCA 6k 才 16%,memory method 可以發揮)
- → **Paper §6.3 主表應主推 MH**,SH 當補充表

### 3.2 Mem0 在 MH 6k 完勝 LCA(+34 pp),但圖層(Mem0g)反扣 9 pp

| Method | MH 6k EM | M-core LEAK | M-core CLEAN |
|---|---:|---:|---:|
| LCA | 16% | — | — |
| **Mem0**(向量) | **50%** | 54.3% | 38.8% |
| **Mem0g**(向量+圖,backtick) | **41%** | 58.5% | 31.9% |

**對 paper main narrative**:
- Memory abstraction 在 dense conflict 任務上**確實有用**(+34pp)
- 但**圖層 hard-delete 過度激進**,反而傷害 EM(-9pp)
- 這跟 mem0 v3 上游拋棄圖層的決定**完全 vindicate**
- → 我們的方法應該避免 mem0g 的 hard-delete pattern,做 **soft invalidation**(對應 Graphiti bi-temporal 設計)

### 3.3 Mem0 在 MH 32k 從 50% 降到 37%

Memory method 在 longer ctx 上的 ceiling:

| ctx | LCA MH | Mem0 MH | Δ |
|---|---:|---:|---:|
| 6k | 16% | 50% | +34 |
| 32k | 16% | 37%(待重跑驗證) | +21 |
| 64k | 12% | TBD | TBD |
| 262k | 4% | TBD | TBD |

**潛在 paper finding**:Memory method 隨 ctx 變大優勢縮小,但仍維持絕對贏 LCA → angle C(memory scaling)narrative

注意:37% 是被 SQLite 衝突影響的數字,**ingest 不健康(只 4 DELETE events)**,實際 EM 純由 LLM 用 question 自己答出。重跑後預期更高。

### 3.4 衝突偵測 metric × EM 強相關(supports M-detection as mechanism evidence)

從 Mem0/Mem0g 6k:

| | All-CLEAN → EM | Not-Clean → EM | Δ |
|---|---:|---:|---:|
| Mem0 6k | **90%**(18/20) | 40%(32/80) | +50 pp |
| Mem0g 6k | 81%(13/16) | 36%(30/84) | +45 pp |

→ **M-detection 是 strong predictor of M1 EM**,validate spec §4 的 metric 設計

### 3.5 Memory representation × update_gap 互動(對應 spec §11 hypothesis)

從 Mem0 6k:

| Update Gap | Mem0 EM | All-CLEAN | Mem0g EM |
|---|---:|---:|---:|
| close (≤50) | **10.0%** | **0%** | 30.0% |
| mid (51-200) | 46.8% | 21.3% | 40.4% |
| far (>200) | **62.8%** | 23.3% | 48.8% |

**直接驗證 spec §11**:
- `flat_vector` (Mem0):小 gap 上 All-CLEAN=0%(無結構區分),大 gap 反而好(vector 易區分)
- `kg_dedup` (Mem0g):小 gap 表現好(30% EM),大 gap 反而沒拉開

→ Paper §11 narrative 「為什麼選 kg_passage_anchored」有 empirical support

### 3.6 Mem0 SH ingest 異常(比 SH 32k 嚴重)

Mem0 SH 6k 跟 SH 32k 都顯示「0 ADD + 6 DELETE」異常 — 但 SH EM 仍 72%-86%(LLM 用 world knowledge 答)。

可能原因:
- SQLite 衝突(主因,已 P8 fix)
- SH input format LLM 對 L1 prompt 仍邊緣 reject(待重跑後驗證)

### 3.7 Backtick wrap 對 EM 影響極小(+/- 2pp = noise)

Mem0g MH 6k:**sanitizer 43% vs backtick 41%** — 在 `temperature=0.1` 的隨機 noise 範圍。

**Audit log 顯示 7 個 unique entity_type 被 backtick wrap**:
`country/empire`, `country/state`, `book/film`, `book/game/series`, `book/work`, `religion/belief`, `song/album`

→ Backtick 完整保留 LLM 原意(`country/empire` 跟 `country_state` 是不同 label),sanitizer 會混淆;**未來實驗用 backtick 為 default**

---

## 4. 三個 baseline modification 框架更新

對應 [[../../baseline_methods/mem0_setup_deltas_vs_paper.md §20.2]] 的分類:

| Class | 改動 | 頂會接受度 | 我們的 |
|---|---|---|---|
| **A. API hygiene** | retry, max_tokens, version compat | 完全接受,通常不需 ablation | ✅ max_tokens 16384, ✅ P3/P5/P6/P7/P8/P9 (6 個 vendored bug fix) |
| **B. Cross-method convention** | chunk size 按 method-task 選 | 接受,需 disclose | ✅ chunk=512 對齊 HippoRAG FC convention |
| **C. Minimal prompt repair** | 移除有害 few-shot | 接受,**必須** ablation | ✅ L1 prompt fix (95/3173 chars = 3%) |
| **D. Substantive prompt engineering / method mod** | Craft 新 CoT, 改 algo | **危險區** | ❌ 沒進入 |

**我們的 6 個 vendored bug fix(P3/P5/P6/P7/P8/P9)全部屬 A 類**,paper 不需要 ablation,只需 appendix disclose 即可。

---

## 5. 重跑計畫(等 mem0g MH 32k 完成後)

### 5.1 第一批:被 SQLite 衝突影響的 mem0(無 Neo4j)

| Run | yaml | dataset | 預估時間 |
|---|---|---|---|
| Mem0 SH 6k | mem0_chunk512 | sh_6k | 10 min |
| Mem0 SH 32k | mem0_chunk512 | sh_32k | 50 min |
| Mem0 MH 32k | mem0_chunk512 | mh_32k | 50 min |

### 5.2 第二批:被 KeyError 影響的 mem0g(需 Neo4j on)

| Run | yaml | dataset | 預估時間 |
|---|---|---|---|
| Mem0g SH 32k | mem0g_chunk512 | sh_32k | 80 min |

> 註:Mem0g MH 32k 如果順利完成且 ingest 健康,**不需重跑**;如果 crash,加入第二批。

### 5.3 注意事項

- P7 (qdrant path) + P8 (SQLite path) + P9 (KeyError tolerate) 已加進 agent.py,**重跑時自動套用**
- 並行多個 mem0 process 現在安全(各自獨立 path)
- Neo4j 共享 graph 但用 `user_id` filter 隔離,不需重啟
- LCA 不需要重跑(都信賴)

---

## 6. 接下來的 ctx sweep(paper angle C)

重跑完成後,啟動:

| 任務 | 預計時間 | 為什麼 |
|---|---|---|
| Mem0 MH 64k | 100 min | LCA 12%,看 mem0 是否仍贏 |
| Mem0 MH 262k | 200 min | LCA 4%,**paper main angle C 重頭戲** |
| Mem0g MH 64k | 150 min | 看圖層 deficit 在長 ctx 上是否仍在 |
| Mem0g MH 262k | 300 min | 同上 |

預期 dominated by 262k,約 6 小時。可一夜跑完。

---

## 7. 待跑 OOB ablation(spec §23)

| Setup | L1 | chunk | max_tokens | 期望 EM | 已跑? |
|---|---|---|---|---:|---|
| Mem0 OOB(paper convention)| ❌ | 4096 | 預設 | 0% | ✅ 6k confirmed |
| Mem0 OOB + chunk=512 | ❌ | 512 | 預設 | ? | ⏳ |
| Mem0 OOB + max_tokens=8192 | ❌ | 4096 | 8192 | ? | ⏳ |
| **Mem0 Full(本研究主結果)** | ✅ | 512 | 16384 | **50%** | ✅(MH 6k) |
| Mem0 OOB + GPT-4o-mini(reference) | ❌ | 512 | 預設 | 1% | ✅ historical |

跑完 ctx sweep 後再補 ablation。

---

## 8. 相關文件

- 三個 baseline modification 框架:[[../../baseline_methods/mem0_setup_deltas_vs_paper.md]]
- Vendored mem0g bugs 詳細:[[../../baseline_methods/mem0g_vendored_bugs.md]]
- L1 prompt fix:[[../../baseline_methods/mem0_l1_prompt_fix.md]]
- LCA ctx sweep:[[../../paper_draft/lca_backbone_ctx_sweep.md]]
- Metrics spec(同步 chat):[[../../sync_with_claude_chat/FC_metrics_spec.md]]
- chunk size convention:[[../chunk_size_convention.md]]
- Neo4j lifecycle:[[../../infrastructure/neo4j_setup.md]]

---

## 9. 重要 file paths(future reference)

### Agent.py 改動
- [agent.py:_initialize_mem0_agent](../../../agent.py) — 所有 9 個 monkey-patches 集中
- [agent.py:_create_answer_client](../../../agent.py) — Vertex Gemini answer LLM
- [agent.py:_answer_with_client](../../../agent.py) — 統一 OpenAI/Gemini 介面

### Methods
- [methods/mem0_vertex_gemini_llm.py](../../../methods/mem0_vertex_gemini_llm.py) — VertexGeminiLLM wrapper (ADC)
- [methods/mem0_vertex_adc_embedder.py](../../../methods/mem0_vertex_adc_embedder.py) — VertexADCEmbedding wrapper
- [methods/mem0_fc_prompt_fix.py](../../../methods/mem0_fc_prompt_fix.py) — L1 prompt fix

### Yaml(20 個)
- `configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0{,g}_<MODEL>_chunk{512,4096}.yaml`

### Dataset Yaml(我們改的 max_test_samples)
- `configs/data_conf/Conflict_Resolution/Factconsolidation_{sh,mh}_{32k,64k,262k}.yaml` — 從 1 → null,backup 在 `.session_backups/`

### Analysis Scripts
- [analysis/align_mem0_mquake.py](../../../analysis/align_mem0_mquake.py)
- [analysis/compute_m_core.py](../../../analysis/compute_m_core.py)
- [analysis/compute_m_detection.py](../../../analysis/compute_m_detection.py)
- [analysis/check_mquake_coverage.py](../../../analysis/check_mquake_coverage.py)

### Results
- `outputs/<run>/Conflict_Resolution/factconsolidation_..._results.json` — 主 results
- `outputs/rag_retrieved/<agent>/k_100/<sub>/chunksize_<C>/ingestion_context_0.jsonl` — ingest events
- `outputs/rag_retrieved/<agent>/k_100/<sub>/chunksize_<C>/mem0g_label_audit.jsonl` — backtick audit
- `analysis/results/<run>_<task>_<ctx>_align.json` — MQuAKE alignment
- `analysis/results/<run>_<task>_<ctx>_mcore.json` — CLEAN/LEAK/MISS
- `analysis/results/<run>_<task>_<ctx>_mdetection.json` — All-CLEAN/Any-LEAK
