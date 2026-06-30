# v1 Experiment Plan — HippoRAG-v2 衝突機制設計 (2026-05-11 lock)

> **本文件目的**: 整合 motivation 觀察 → v1 三 Phase 方法設計 → 實驗清單 → 資源預估 → 監測方案,作為今天動手的 single source of truth。
>
> **配讀**: [`current_focus/`](current_focus/) 下 5 份檔案

---

## §1 從 Motivation 到 v1 Method 的橋接

### §1.1 我們在 motivation 中觀察到什麼

| 觀察(motivation §) | 數字 | 解讀 |
|---|---|---|
| PureChain task solvability(§1.A) | 97% | 任務本身可解, FC-MH 崩盤不是 task-intrinsic |
| Top-10 retrieval 覆蓋(§1.5) | chain_new 94%, chain_old 97%, 83% corpus | **崩盤不在 recall, 在新舊混入 LLM context** |
| OracleClean-ThisChain ceiling(§2.A) | vanilla 22% → +34pp = 56% | filter 必須 query-aware(移本題 chain_old +34, 移其他 olds 只 +5) |
| n_inject 0→1 dose-response(§2.A.b2) | 0 chain_old: 87%, 1 chain_old: 38%, drop 49pp | 一個 chain_old 足夠崩盤 → filter recall 要高 |
| V1/V2/V3 scaffold on clean(§2.B) | OA2 55% → +scaffold 83%, +28-31pp | scaffold 在乾淨 context 才釋放, 髒 context 救不了(vanilla +scaffold 僅 +2pp) |
| **Mem0/Zep detection × EM 解耦**(§4.3.B)| Mem0 MH all_detected 41 題 → EM 仍只 63%; Zep MH all_detected 20 題 → EM 只 40% | **偵測全對 ≠ 解題對**。偵測完不做 retrieval-side 處理仍會錯 |
| Mem0 filter-at-write vs Zep annotation-at-inference(§4.4)| 物理刪除留遺孤 vs 保留兩版讓 LLM 自判 | 兩種哲學各有缺陷 → HippoRAG-v2 KG 可走 hybrid: 標 metadata 不刪 + retrieval-time 過濾 |

### §1.2 三個 Phase 各自解什麼觀察問題

```
觀察                                  →   v1 Phase 對應                      →   驗證 (Assertion)
─────────────────────────────────────────────────────────────────────────────────────────
§4.3 Mem0/Zep 偵測單獨不夠              →   Phase 1: write-time 標 supersession    →   A1.1 EM 不變 22% ±1pp
§4.3.B 偵測全對 EM 仍低                                                                  A1.2 detection recall ≥ 41%

§2.A 移本題 chain_old +34pp           →   Phase 2: query-time chain-aware filter  →   A2.1 P1+P2 EM ∈ [35%, 50%]
§4.4 Mem0 physical delete 在 MH 失敗                                                     A2.2 filter precision ≥ 85%
                                                                                         A2.3 FC-SH 退步 < 3pp

§2.B clean context 上 scaffold +28pp  →   Phase 3: universal reasoning scaffold  →   A3.1 OracleClean+scaffold ≥ 75%
§2.B 髒 context scaffold +2pp                                                            A3.2 MuSiQue/2Wiki 退步 < 2pp
                                                                                         A4.1 P1+P2+P3 EM ∈ [45%, 60%]
```

### §1.3 Phase 1 — Conflict-Aware Fact Annotation (寫入時)

**動機**: §4.3.B 揭示「偵測 ≠ 解題」 — Mem0 偵測到的 41 個 case, EM 只 63%, 證明偵測必要但不充分。我們需要先把偵測做對(Phase 1), 才能讓 Phase 2 / 3 有東西可用。

**機制**: 掃 OpenIE 抽出的所有 triples, 同 `(S, R)` 不同 `O` → 後出現的 O 為 active, 早出現的 fact 在 fact_key 層標 `superseded_by`。**新舊 fact 都保留, 不刪, 不修 PPR**。

**為什麼掛 fact_key 不掛 edge** (chat §B.7.1): HippoRAG-v2 graph fact edge 把 relation collapse(同 entity pair 不同 relation 共用一條 edge), edge 級 metadata ambiguous。fact_key = md5 of (s,r,o), 自然保留 relation。

**為什麼用 fact 粒度** (對應你的提問):
- HippoRAG-v2 本來就在 fact level 操作(`fact_embedding_store` + OpenIE triples), 沒引入新顆粒度
- Phase 1 metadata 跟既有 KG / embedding store 解耦(新建 `superseded_facts` dict + `chunk_to_fact_keys` map), 容易 serialize 跟 vanilla 對照
- v1 用「同 (S, R) 不同 O」當起手規則最簡, 對 v0 prototype 的 41% detection 已是合理對標
- 後續若 detection recall 不夠, 可加 entity/relation alias normalization(利用 HippoRAG-v2 既有 synonymy edges), 或考慮 hop-2+ propagation(對應 chat §B.7.2 discoverability asymmetry, v2 動作)

### §1.4 Phase 2 — Chain-Aware Passage Filtering (查詢時)

**動機**: §2.A 「移本題 chain_old +34pp / 移其他 olds 只 +5pp」 證明 filter 必須 **query-aware**, 不能 query-agnostic(像 Mem0 的 write-time 物理刪除)。

**機制**(精確版本):

> PPR 在 HippoRAG-v2 graph 上跑的是 **entity (phrase node) + passage (chunk node)**, **fact 不在 graph 中**(fact 只活在 `fact_embedding_store` 影響 retrieval 第一階段)。
>
> 1. PPR 收斂後, 取 **phrase node** 上 mass top-X% (X=20) 為 `high_mass_entities`(代表「query 相關 entity 集合」)
> 2. 對 candidate passage, 用 Phase 1 持久化的 `chunk_to_fact_keys` 反查它的 source triples
> 3. 對每個 fact: 若被 Phase 1 標為 superseded **且**它的 `(s_entity, o_old_entity)` **兩端都在 `high_mass_entities`** → 判定為「本題 chain_old」 → hard filter 整個 passage
> 4. 兩端都 high_mass ≈ 此 superseded fact 跟 query 推理鏈相關(對應 §2.A 移本題 chain_old 的設計理由)

**核心隱含假設 — C5** (chat §B.7.2.bis): PPR mass 能否區分 chain_new 相關 entity vs unrelated old entity? 如果分布混在一起,「兩端 high_mass」proxy 失效, Phase 2 規則 v1 階段就要改。**進 Phase 1 實作前必須先驗 C5。**

**Phase 2 對 Phase 1 的依賴**: Phase 2 不修 KG / 不重 indexing, 只在查詢時讀 Phase 1 寫好的兩個 dict。**Phase 2 的 effective recall 上限 = Phase 1 detection recall**。

### §1.5 Phase 3 — Universal Reasoning Scaffold (推論時)

**動機**: §2.B V1/V2/V3 三個 prompt 變體在乾淨 context 上都 +28-31pp, scaffold signal 對 prompt 措辭不敏感 → 用最 universal-safe 那版即可。同時 §2.B vanilla+scaffold 只 +2pp, 確認 scaffold 救不了髒 context, 必須跟 Phase 1+2 配合。

**Scaffold 草案**(universal, 不提序號 / conflict / supersedence):

> "When the answer requires connecting multiple facts, briefly list the intermediate entities or facts you use, and ensure that any entity appearing in multiple steps is referenced consistently."

**跟 V1/V2/V3 的關係**: V1 (trailer) / V2 (cite-source) / V3 (decompose) 是 motivation 階段的 prompt 變體探索。Phase 3 取最 universal 那版, 但 **v1 完成後**可在 Step 3 4-way ablation 對比哪個 framing 跟 Phase 1+2 結合最好。若想再細, 後續 v2 ablation 比較 V1/V2/V3 各自在乾淨 + 髒 context 行為。

**4-way ablation** (method_v1_spec §6 Step 3 預設):

| 條件 | 預期 EM | 對應 motivation |
|---|---|---|
| vanilla | 22% | baseline |
| P3 only (scaffold on vanilla) | ~22-25% | §2.B vanilla→V1 +2pp(髒 context 救不了) |
| P1+P2 only | 35-45% | §2.A OracleClean-ThisChain +34pp |
| P1+P2+P3 全套 | 45-55% | §2.B OracleClean→V1 +28pp(乾淨 context 才釋放 scaffold) |

---

## §2 實驗清單 + 資源預估

順序按相依性 + 風險遞增。每步預估數字根據 [hardware_request_6k.md](hardware_request_6k.md) 實測。

| Step | 目的 | 觸發 reindex? | GPU peak | 系統 RAM | 時間 | API tokens (估) | Cost (估) |
|---|---|---|---|---|---|---|---|
| **A1** 建監測基礎設施 | 寫 sidecar + wrapper + LLM hook + config_utils patch | ❌ | 0 | 1 GB | 30-60 min | 0 | $0 |
| A2 git tag baseline | `git tag vanilla-baseline-2026-05-11 HEAD` 鎖當前 state | ❌ | 0 | 0 | <1s | 0 | $0 |
| **A3** Step 0 warm cache sanity | `bash run_hipporag_gemini.sh`(resume 模式, 用既有 cache) | ❌ | <1 GB | <2 GB | 2-5 min | ~0(全 cache hit) | ~$0 |
| **A4** Step 0 **cold rebuild** | mv cache → backup, fresh rebuild 6k SH+MH | ✅ | **14.6-19.7 GB** | 16-32 GB | 15-25 min | OpenIE 12 calls + QA 200 calls ≈ 150K in / 10K out | ~$0.5 |
| **A5** Step 0 equivalence diff | 比對 new vs backup: OpenIE / fact_emb L2 / top-10 retrieval / EM | ❌ | 0 | 1 GB | 5 min | 0 | $0 |
| **B** C5 驗證 | 用既有 KG, 跑 100 queries, 算 chain_new vs unrelated old entity 的 PPR mass separability | ❌ | <1 GB | 2 GB | 30-40 min | 0 (用 cached retrieval) | $0 |
| **C** Step 0.5 chunks vs raw_chunks delta | revert agent.py L909, rebuild, 跑 MH, 比 EM, revert | ✅ | 14.6-19.7 GB | 16-32 GB | 30-60 min | OpenIE 12 calls 重抽 + QA 100 calls | ~$0.5 |
| D1 Phase 1 實作 | code 改 augment_graph + 2 dict + flag + persist JSON | ❌ | 0 | 1 GB | 1-2 hr | 0 | $0 |
| D2 Phase 1 跑+驗 | enable_supersession on, rebuild KG, 跑 MH+SH | ✅ | 14.6-19.7 GB | 16-32 GB | 15-25 min | 同 vanilla | ~$0.5 |
| E1 Phase 2 實作 | 改 run_ppr return signature + 寫 _phase2_filter_chain_old | ❌ | 0 | 1 GB | 1-3 hr | 0 | $0 |
| E2 Phase 2 跑+驗 | enable_phase2_filter on, **不需 reindex** | ❌ | <1 GB | <8 GB | 10-15 min | 同 vanilla | ~$0.3 |
| F1 Phase 3 實作 | scaffold + flag | ❌ | 0 | 0 | 30 min | 0 | $0 |
| **F2** Phase 3 4-way ablation | 跑 vanilla / P3 only / P1+P2 / P1+P2+P3 | 視 flag | 14.6-19.7 GB peak (P1 開時) | 16-32 GB | 30-45 min | 4× QA round | ~$1 |
| G MuSiQue/2Wiki 一般化測試 | scaffold 在非 KU multi-hop 是否有害 | ✅(新 dataset) | 14.6-19.7 GB | 16-32 GB | 1-2 hr | ~300 queries × ~10K tokens | ~$2 |
| H FC-MH 答錯題 Type-1/2/3 標註 | LLM annotate, 量化 hop-2+ satellite 比例 (chat §B.7.2) | ❌ | 0 | 1 GB | 1-2 hr | ~80 annotation calls | ~$1 |

### 今天目標 (Step A1-C)

**總耗時**: 3-5 小時 wall-clock(含 implementation overhead)
**GPU peak**: ≤ 19.7 GB(在 A4 / C 的 indexing 階段, 預期 < 20 GB)
**RAM peak**: 32 GB(indexing 階段最大值)
**API cost**: < $2

### v1 全套 (A1-H)

**總耗時**: 3-4 天 wall-clock(含 debug 跟結果分析)
**API cost**: < $10
**Bottleneck**: 不在 GPU/CPU, 在 (a) Gemini Vertex rate limit (通常很寬), (b) debug 時間, (c) 等實驗結果決策時間

---

## §3 監測方案

### §3.1 Indexing 階段 vs Query 階段分離量測

`HippoRAG.py` 跟 `agent.py` 在關鍵點有 log/print 輸出, sidecar 用這些當 phase marker:

| 識別字串 (從 stdout / run.log tail) | 對應 phase tag | 量測重點 |
|---|---|---|
| `Performing OpenIE` | `indexing/openie` | OpenIE LLM 呼叫: API tokens, wall time |
| `Adding OpenIE triples to graph.` | **`indexing/embed_kg`** | **GPU peak**(NV-Embed-v2 forward), wall time |
| `Performing Synonymy Edge Construction` | `indexing/synonymy` | KNN over cached embeddings, 一般 GPU < 1 GB |
| `HippoRAG build vectorstore finished` | `transition` | 標記 indexing 結束 |
| `Processing N queries for context 0` | `query` | query loop 開始 |
| (預設) | `init` / `query` | 啟動 / 後續 query |

### §3.2 取樣方案

**每 2 秒一個樣本**(權衡: 對 15-25 min 的 run 夠細, 不會 sidecar 自己佔資源):

| 量項 | 來源 | 在 GB10 上是否可靠 |
|---|---|---|
| GPU memory per-process | `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` | ✓(GB10 unified, 但 per-process compute apps query 可用) |
| GPU utilization (overall %) | `nvidia-smi --query-gpu=utilization.gpu --format=csv` | ✓ |
| 系統 RAM used / available | `psutil.virtual_memory()` | ✓ |
| 主 process RSS | `/proc/<pid>/status` VmRSS | ✓ |
| CPU% (system, main process) | `psutil.cpu_percent()` / `Process.cpu_percent()` | ✓ |
| 時間戳 | `time.time()` | ✓ |
| Current phase tag | tail run.log 對 marker | 自己實作 |

### §3.3 API token / cost tracking

Gemini API 回傳 `usage_metadata.{prompt_token_count, candidates_token_count}`, 我們 patch [`methods/hipporag/llm/gemini_llm.py`](../methods/hipporag/llm/gemini_llm.py) 加 `API_USAGE_LOG` 環境變數 hook, 每次 API 呼叫(非 cache hit)寫一行 JSONL:

```json
{"ts": 1714532400.0, "model": "gemini-3.1-flash-lite-preview", "prompt_tokens": 4231, "completion_tokens": 142, "cache_hit": false}
```

**Phase 歸屬**: sidecar 在 run 結束時讀 api_usage.jsonl + hw_timeline.csv, 用 timestamp 對齊把每筆 API call 歸屬到當下 phase, 生成 per-phase token 跟成本聚合。

**Pricing 用** Gemini 3.1 Flash-Lite Preview 公開定價(input ~$0.075/1M, output ~$0.30/1M, 可調)。

### §3.4 輸出結構

```
monitoring_logs/2026-05-11_HHMMSS_<run-name>/
├── hw_timeline.csv          每 2s 一行 (ts, phase, gpu_mem, gpu_util, ram_used, cpu, ...)
├── api_usage.jsonl          每次 API call 一行
├── hw_phase_summary.md      自動生成, 每 phase 的 GPU peak / RAM peak / wall / tokens / cost
├── run.log                  原 command 的 stdout/stderr
└── manifest.json            run 命令 + git SHA + env (HIPPORAG_EMBED_BATCH_SIZE 等)
```

### §3.5 預期硬體 invariant

| 階段 | GPU peak 預期 | 是否會超過 20 GB? | 對應 batch / max_len |
|---|---|---|---|
| Indexing/embed_kg @ default config | **19.70 GB** | ❌ 邊緣(0.3 GB headroom) | bs=8 max_len=2048 |
| Indexing/embed_kg @ bs=4 (我們改 config) | **16.76 GB** | ❌ 舒適(3 GB headroom) | bs=4 max_len=512 |
| Query 階段(model 常駐) | **~14.6-14.9 GB** | ❌ | n/a |

> **行動**: A1 完成後動 A4 之前, 把 `embedding_batch_size` default 從 16 改成 4(`methods/hipporag/utils/config_utils.py` L117)。理由跟實測在 [hardware_request_6k.md](hardware_request_6k.md)。

---

## §4 使用方式 (動工後)

```bash
# Step A4: 冷重建 + 監測 (從 GX10-2 backup 既有 cache 開始, 換新環境跑)
bash scripts/run_with_monitoring.sh \
    "A4_cold_rebuild_step0" \
    "bash run_hipporag_gemini.sh"

# 完了開 monitoring_logs/<timestamp>_A4_cold_rebuild_step0/hw_phase_summary.md 看
```

每次 v1 method run 都用同樣 wrapper, summary.md 累積比較。

---

## §5 等實驗開跑前必確認的事

1. [x] motivation_narrative §1-§5 全文我都過了, 數字跟解讀都對齊
2. [x] method_v1_spec §0-§7 設計決策 Q1-Q4 都 lock(包含 fact_key 標 metadata、PPR 後 top-X% phrase filter、universal scaffold always-on)
3. [ ] **`embedding_batch_size` 在 A4 之前要從 16 改成 4** (跟 A1 一起做)
4. [ ] A4 之前要 `git tag vanilla-baseline-2026-05-11 HEAD`
5. [ ] A4 之前要備份既有 cache: `mv outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512 .baseline_backup_2026-05-11/` (同 SH)
6. [ ] **C5 驗證在 D1 Phase 1 實作之前要做**(若 PPR mass 區分能力差, Phase 2 規則 v1 階段就要改)

---

## §6 v1 跑完後的決策樹

對應 method_v1_spec §7 reactive decision tree。

| 觀察結果 | v2 動作 |
|---|---|
| A1.2 Phase 1 detection recall < 50% | 加 entity/relation alias normalization(利用 HippoRAG-v2 synonymy edges) |
| A2.2 Phase 2 precision < 80%(誤刪過多)| Hard filter → soft demote |
| A2.1 EM 沒進 [35%, 50%] | X=20% calibrate / 規則放寬到「一端 high_mass」 |
| A2.3 FC-SH 退步 > 3pp | Phase 2 加 trigger gate |
| Step H 標出 Type-2/3 比例 > 30% | OLD-entity propagation (chat §B.7.2 候選 α) |
| FC-MH < 60% 且 chain_old satellite 多 | Subgraph injection (候選 γ) |
| A3.2 非 KU 退步 > 2pp | Phase 3 改 conditional-on-superseded-edge-hit |
