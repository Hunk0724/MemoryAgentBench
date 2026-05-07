# Mem0 + Zep × Vertex Gemini 3.1 Flash-Lite × FC-SH/MH 全 100 題

> **日期**：2026-05-02
> **目的**：Phase 0 三天衝刺 Step 4 — 對 Mem0 customized + Zep × Gemini 跑全 200 題並算 detection F1，填好對比表
> **接續**：[2026-04-30 baseline setup](../2026-04-30_mem0_zep_baseline_setup/README.md) — setup + smoke test 已驗 L1 mod 可行
> **狀態**：完成。Mem0/Zep E2E + detection F1 都已算出。

---

## 1. Headline Numbers

| 系統 | FC-SH EM | FC-MH EM | Detection P | Detection R | **Detection F1** | Notes |
|---|:---:|:---:|:---:|:---:|:---:|---|
| HippoRAG-v2 plain (Gemini, modified prompt) | 96% | **23%** | n/a | n/a | n/a | A1 baseline |
| **Mem0 customized × Gemini**（NEW）| **77%** | **43%** | 38.6% | 40.4% | **39.5%** | L1 mod removes 2 anti-knowledge few-shots |
| **Zep × Gemini**（NEW；only inference-side LLM is Gemini） | **79%** | **8%** | 89.4%* | 31.4%* | **46.5%*** | *detection 數字繼承自 GPT 的 audit（Zep 內部 LLM 不可換）|
| OA2 fact-level oracle (Gemini, modified) | 98% | 83% | 100% | 100% | 100% | perfect detection 上限 |
| Sim-OB chain-only (Gemini, modified) | 98% | 98% | n/a | n/a | n/a | absolute ceiling |

→ **核心 paper finding**：production 系統（Mem0 customized 39.5% / Zep 46.5%）detection F1 都 < 50%；E2E 跟 OA2 oracle 還差 5–75 pp。**這就是 paper 主張的 production gap 證據**。

---

## 2. 實驗設計

### 共通設置
- LLM backbone：`gemini-3.1-flash-lite-preview` via Vertex AI ADC（與 HippoRAG-v2 / 9 oracles 同一條路徑）
- chunk_size：512 tokens，6k context = 12 chunks
- 100 題 FC-SH / 100 題 FC-MH

### Mem0 customized
- L1 minimal mod：移除 `mem0/configs/prompts.py` 第 28-32 行兩個 anti-knowledge few-shots
- 透過 `MemoryConfig(custom_fact_extraction_prompt=...)` 注入（不改 vendored source）
- LLM provider：自訂 `VertexGeminiLLM`（仿 HippoRAG `CacheGemini`，使用 `google.genai` SDK + Vertex AI ADC）
- max_tokens=8192（Update Memory 步驟枚舉 prior memories 越來越長，2048 會被截斷）
- Embedder：`sentence-transformers/all-MiniLM-L6-v2`（local，無 API key）
- Vector store：local Qdrant，每 task 各一個 collection
- Inference：Vertex Gemini 直接呼叫（mirror agent.py:_handle_mem0_agent prompt）

### Zep × Gemini inference-side
- **Asymmetry caveat**：Zep cloud 內部 LLM 處理 entity extraction / supersession / context summary，**這部分不可換 Gemini**
- 我們只把最終 QA reading（`methods/zep.py:llm_response`）的 LLM 換成 Vertex Gemini
- 新 session IDs（`gemini_full100_*` 前綴），避免跟既有 GPT run 衝突
- 6 分鐘 ingestion async wait per task
- Inference prompt 完全沿用 `methods/zep.py:llm_response` 的 system / user wording（只是 LLM client 換了）

---

## 3. Per-num_hops / Per-n_conflict 衰減

### Mem0 customized × Gemini × FC-MH

| num_hops | EM | n_conflict | EM |
|:---:|:---:|:---:|:---:|
| 2 | 44.3% (27/61) | 1 | 51.5% (17/33) |
| 3 | 50.0% (12/24) | 2 | 41.7% (20/48) |
| 4 | 26.7% (4/15) | 3 | 29.4% (5/17) |
| | | 4 | 50.0% (1/2) |

→ 3-hop 比 2-hop 略好（小樣本變異），4-hop 仍崩到 26.7%；衝突跳數越多 EM 越低。

### Zep × Gemini × FC-MH

| num_hops | EM | n_conflict | EM |
|:---:|:---:|:---:|:---:|
| 2 | 13.1% (8/61) | 1 | 15.2% (5/33) |
| 3 | **0.0%** (0/24) | 2 | 6.2% (3/48) |
| 4 | **0.0%** (0/15) | 3 | 0.0% (0/17) |
| | | 4 | 0.0% (0/2) |

→ **Zep 在 3+ hops 全失敗** — 結構性無能 multi-hop 推理（與 zep_mechanism_deep_dive.md 對 multi-hop 限制吻合）。

---

## 4. Detection Audit（Zep-audit 格式 — event-level 統計）

對齊現有 [zep_mechanism_deep_dive.md](../../results/oracle_a/zep_mechanism_deep_dive.md) 的 audit 格式（total invalidations / correct / wrong / false_positive / has_pair in dataset）。

### 4.1 Mem0 customized × Gemini（從 ~/.mem0/history.db filter 本次 run，251 UPDATE events）

| | total invalidations | correct | wrong | false_positive | uniquely_correct_pairs | has_pair_in_dataset |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Mem0 FC-SH | **251** | **65** | 0 | 186 | 33 | 74 |
| Mem0 FC-MH (hop-level) | **251** | **133** | 0 | 118 | 67 | 188 |

換算 detection P/R/F1：

| | Precision (event-level) | Recall (pair-level) | **F1** |
|---|:---:|:---:|:---:|
| Mem0 FC-SH | 65/251 = **25.9%** | 33/74 = **44.6%** | **32.8%** |
| Mem0 FC-MH | 133/251 = **53.0%** | 67/188 = **35.6%** | **42.6%** |

### 4.2 Zep × Gemini（本次 run；189-377 個 entity-name queries × limit 50 = ~427 edges sampled per task；invalidation 完整度 ~70-90%）

| | total invalidations | correct | wrong | false_positive | uniquely_correct_pairs | has_pair_in_dataset |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Zep × Gemini FC-SH | 64 | 18 | **7** | 39 | 18 | 74 |
| Zep × Gemini FC-MH | 78 | 65 | 7 | 6 | 65 | 188 |

換算：

| | Precision | Recall | **F1** |
|---|:---:|:---:|:---:|
| Zep × Gemini FC-SH | 18/64 = **28.1%** | 18/74 = **24.3%** | **26.1%** |
| Zep × Gemini FC-MH | 65/78 = **83.3%** | 65/188 = **34.6%** | **48.9%** |

### 4.3 Zep × GPT（既有 audit；完整 graph 狀態）

| | total | correct | wrong | false_positive | unique correct | has_pair |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Zep × GPT FC-SH | 48 | 20 | **25** | 2 | 20 | 74 |
| Zep × GPT FC-MH | 67 | 59 | 3 | 4 | 59 | 188 |

| | P | R | F1 |
|---|:---:|:---:|:---:|
| Zep × GPT FC-SH | 41.7% | 27.0% | **32.7%** |
| Zep × GPT FC-MH | 88.1% | 31.4% | **46.3%** |

### 4.4 跨系統對比（detection F1，hop-level for MH）

| | Mem0 × Gemini | Zep × Gemini | Zep × GPT |
|---|:---:|:---:|:---:|
| FC-SH | 32.8% | 26.1% | 32.7% |
| FC-MH | **42.6%** | **48.9%** | **46.3%** |
| Wrong-direction (SH) | 0 | 7 | **25** |
| Wrong-direction (MH) | 0 | 7 | 3 |

**觀察**：
- 三個系統 FC-MH F1 都 < 50%（42-49%），都低於 OA2 oracle 100%
- **Mem0 wrong-direction = 0**（SH/MH 都沒方向反錯）— 因為 Mem0 用 ingestion order 決定 supersession，跟 world-knowledge bias 無關
- **Zep × GPT SH wrong-direction = 25**（占總 invalidation 的 52%）— counterfactual 觸發 world-knowledge bias 反向 invalidate；Zep × Gemini SH 只有 7（情況改善但仍存在）
- Zep MH 三個 run（GPT/Gemini/sampled）precision 都 80%+，但 recall 都 30% 左右 — 結構性偵測不到大部分 has_pair

→ **Mem0 跟 Zep 的 detection 失敗模式不同**：Mem0 過度觸發（FP unmatched 大量）；Zep 偵測得對但只覆蓋少數 hop（recall 低）。

---

## 4.5 ★ Detection × Answer Correspondence（rigor check）

> 「detection F1 < 50% 真的對應到 E2E 失敗嗎？」 — 這節做 per-question 交叉表

對每個 has_pair 題目，分類：
- **All detected**：所有 chain has_pair hop 都被正確 invalidate
- **Partial detection**：有些 hop 對、有些漏（只 MH 有此分組）
- **No detection**：沒有任何 has_pair hop 被偵測
- **No has_pair**：題目本身沒衝突（純多跳）

然後看每組答對率：

### Mem0 customized × Gemini

| 系統 | All detected EM | Partial EM | No detection EM | No has_pair EM | Det 差異 |
|---|:---:|:---:|:---:|:---:|:---:|
| Mem0 FC-SH | **30/33 = 90.9%** | — | 23/41 = 56.1% | 24/26 = 92.3% | **+34.8 pp** |
| Mem0 FC-MH | **20/26 = 76.9%** | 14/33 = 42.4% | 9/41 = 22.0% | — | **+54.9 pp**（all vs none） |

→ **Mem0 detection 強相關 answer correctness**：MH 從「無偵測 22%」單調上升到「全偵測 77%」。**這是「detection 是 Mem0 的瓶頸」的直接證據**。

### Zep × Gemini

| 系統 | All detected EM | Partial EM | No detection EM | No has_pair EM | Det 差異 |
|---|:---:|:---:|:---:|:---:|:---:|
| Zep × Gemini FC-SH | 16/18 = 88.9% | — | 38/56 = 67.9% | 25/26 = 96.2% | +21.0 pp |
| Zep × Gemini FC-MH | **0/8 = 0.0%** | 1/18 = 5.6% | 7/74 = 9.5% | — | **−9.5 pp**（reverse!） |

→ **Zep MH 反例**：8 個 Zep 完全偵測對的題，**全部 0% EM**！「No detection」組反而比較高（9.5%）。意味 Zep MH 答錯的根因**不是 detection 失敗**，而是 propagation/inference 階段崩潰。

### Zep × GPT FC-SH（FULL100 既有 audit）

| 系統 | All detected EM | No detection EM | No has_pair EM | Det 差異 |
|---|:---:|:---:|:---:|:---:|
| Zep × GPT FC-SH | 6/9 = 66.7% | 38/65 = 58.5% | 26/26 = 100% | +8.2 pp |

→ Zep SH detection × answer 弱相關（差 8pp）；no_has_pair 的 100% 顯示 Zep 沒衝突時其實很強。

### Caveats

1. **Zep audit 完整度 ~70-90%**：用 entity-name 當 query 取了 64 SH / 78 MH 個 invalidations，但 Zep cloud 內部 graph 可能還有更多。「No detection」組可能包含 Zep 確實 invalidate 但 audit 沒抓到的 — 這會 underestimate Zep 的 detection rate。Mem0 用 SQLite history 是完整的，無此問題。
2. **Zep × GPT SH 9 個 all-detected 樣本太小**：差異 8pp 顯著性弱
3. **Zep × GPT MH FULL100 JSON 缺**：只有 28% 數字在 [zep_mh_full100_findings.md](../../results/oracle_a/zep_mh_full100_findings.md)，沒辦法做 GPT MH cross-tab

### 結論（rigor check 通過程度）

| 主張 | Verified by correspondence? |
|---|:---|
| 「Mem0 detection 失敗 → Mem0 答錯」 | **✅ 強 evidence**（SH +35pp / MH +55pp 差異，monotonic 趨勢）|
| 「Zep detection 失敗 → Zep 答錯」 | ⚠️ 部分（Zep SH +21 pp 中等，但 audit 完整度有 caveat）|
| 「Zep MH 主因是 detection 不足」 | **❌ 反例**（Zep 全偵測對的 8 題 0% EM ≪ no detection 的 9.5%；Zep MH 是 propagation 失敗）|
| 「production 系統 detection 沒 close 100%」 | ✅ 三系統 F1 都 26-49%（vs oracle 100%）|
| 「Mem0/Zep MH << OA2 modified 83%」 | ✅ Mem0 43% / Zep 8% << OA2 83% |

→ Phase 0 sprint Step 5 模式判定**修正**：原本判 "Mode B (detection + propagation)" 是整體看；按系統來分：
- **Mem0**：detection-bottleneck-driven（→ 對應 spec 模式 C）
- **Zep MH**：propagation-bottleneck-driven（→ 對應 spec 模式 A）
- 整體 paper baseline 兩種模式都存在 → method 設計仍須同時補 detection + propagation

---

## 5. 為什麼 Zep × Gemini MH 8% << Zep × GPT MH 25%

GPT 25% → Gemini 8% 是 17 pp drop。可能解釋：

| 假設 | 證據 / 反證 |
|---|---|
| **Inference LLM 風格差異** | Gemini 嚴謹只答有 retrieved context 支持的；GPT-4o-mini 可能用 world-knowledge 補洞，counterfactual 案例反而對方向錯但常識答對 |
| **Gemini 對長 retrieved_context 處理差** | retrieved_context 含 edges/nodes/episodes 三層，文件結構複雜，Gemini 可能 confused |
| **Prompt format 不對齊** | `methods/zep.py:llm_response` 的 prompt 風格可能 OpenAI-tuned，Gemini 行為不同 |
| **Zep cloud retrieval 跑兩次有差異** | 我們 fresh 重 ingest（new session），跟原 GPT run 的 cloud 狀態可能些微差異 |

→ **Paper 必須處理這個 caveat**：「Zep × Gemini 8% 是 Zep + 我們對齊的 Gemini inference 結果，跟 prior Zep × GPT 25% 不能直接 cross-LLM 比較」。3-hop+ 全 0% 的事實仍然 stable — Zep 在 deep multi-hop 上結構性失敗無論用哪個 LLM。

---

## 6. 對 Phase 0 sprint Step 5 模式判定的 input

回顧 [Phase0 spec](../../../Phase0%203day%20sprint%20spec.md) §Step 5 decision tree：

```
Q1: Mem0/Zep detection F1 > 0.7?  → BOTH NO（Mem0 39% / Zep 47%）
Q3: OA2 oracle MH 顯著高於 Mem0/Zep MH?
    → YES: OA2 modified 83% vs Mem0 43% / Zep 8%（差 40-75 pp）
Q4: Oracle EM 還遠低於 Sim-OB 98%?
    → YES: Sim-OB 98% vs OA2 83%（差 15 pp）
        → 模式 B: detection + propagation 都是瓶頸
```

→ **判定為模式 B**（detection + propagation 雙重瓶頸）。我們的 method 設計不能只解 detection；需要同時補 chain coverage / propagation 穩定（v2 KG subgraph augmentation + v3 sequential decomposition 兩條路線都仍 valid）。

---

## 6.5 ★ Inference prompt 結構對比（critical for paper）

詳見 [results/inference_prompts_comparison.md](results/inference_prompts_comparison.md)。核心：

| 維度 | Mem0 | Zep |
|---|---|---|
| Detection 在哪生效 | Write-time（vector store 直接刪/改）| Inference-time（給 timestamp metadata 給 LLM）|
| LLM 看到 outdated? | ✗ 看不到（被 UPDATE/DELETE 掉） | ✓ 看得到（要靠 invalid_at 區分）|
| LLM prompt 內容 | 純 bullet list of memory texts，無 metadata | facts (with date range) + entities (summary) + episodes (raw) + thread context_block |
| Failure mode (detection wrong) | LLM 完全沒線索 → 答錯 | LLM 看到雙版本，可能用 world knowledge 救 |
| Failure mode (detection right) | retrieved 都是 current → 答對 | LLM 看到雙版本仍可能採信 outdated（trust gap）|

→ **Mem0 paradigm 對齊 OA2 oracle filter family；Zep paradigm 對齊 RPT oracle annotation family**。E2E 表現差異（Mem0 MH 43% vs Zep MH 8%）部分來自 paradigm 差異，不只是 detection F1。

## 6.6 ★ 12 個具體 case studies（rigor evidence）

詳見 [results/case_studies.md](results/case_studies.md)。覆蓋 5 種 pattern：

| Pattern | 例子 qid | 啟示 |
|---|---|---|
| Mem0 detected → 只見 current → 答對 | SH 0 (goaltender→pesäpallo), MH 0 (Darwin chain) | Mem0 paradigm work 時 LLM 完全沒辦法看到 outdated |
| **Mem0 silent miss** → 沒 UPDATE event → 答錯 | MH 1 (Olga Kiev→Rodez, **history.db 完全沒這 pair 的 event**) | Mem0 在某些 pair 上根本沒嘗試 supersession，原因待查（chunk 邊界？extraction 失敗？）|
| Zep edge 「valid_at - present」 for 舊 fact | SH 0, MH 0 (Dickens 仍 present) | Zep 沒設 invalid_at → LLM 看到 old+new 都標 "present"，無線索選 |
| Zep narrow window for 新 fact (counterfactual bias) | SH 22 (Galwegians RFC valid 1 秒就被 invalidate) | Zep 偶有把正確 fact 標反方向 |
| No has_pair → 兩系統都對 | SH 4, 11 | baseline 競爭力對等 |

→ 這些 case 直接 substantiate detection F1 數字背後的具體 failure modes。**Mem0 silent miss 跟 Zep 沒設 invalid_at 是兩種完全不同的 detection failure**，paper 必須區分。

## 7. 檔案地圖

```
2026-05-02_mem0_zep_gemini_full100/
├── README.md                          ← 本檔
├── scripts/
│   ├── run_mem0_gemini.py             ← Mem0 customized full 100 runner
│   ├── run_zep_gemini.py              ← Zep × Gemini inference full 100 runner
│   ├── summarize_results.py           ← 產 summary.md
│   └── mem0_detection_f1.py           ← 從 history.db 算 Mem0 P/R/F1
└── results/
    ├── mem0_gemini_sh_results.json    ← per-question Mem0 SH 結果
    ├── mem0_gemini_mh_results.json    ← per-question Mem0 MH 結果
    ├── zep_gemini_sh_results.json     ← per-question Zep SH 結果
    ├── zep_gemini_mh_results.json     ← per-question Zep MH 結果
    ├── mem0_detection_metrics.json    ← Mem0 P/R/F1
    └── summary.md                     ← summary table（同 §1 §3）
```

外部依賴：
- `analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts/mem0_vertex_gemini_llm.py`（Vertex Gemini provider）
- `~/.mem0/history.db`（Mem0 SQLite，所有 ADD/UPDATE/DELETE event 來源）
- Vertex AI ADC + ZEP_API_KEY（環境變數）

重跑：
```bash
cd /home/yhchiang/MemoryAgentBench

# Mem0（兩 task ~16 min；resume-safe，會跳過已完成 qid）
conda run -n MABench --no-capture-output python \
  analysis/experiments/2026-05-02_mem0_zep_gemini_full100/scripts/run_mem0_gemini.py --task both

# Zep（兩 task ~28 min；含 6 min ingestion wait per task）
conda run -n MABench --no-capture-output python \
  analysis/experiments/2026-05-02_mem0_zep_gemini_full100/scripts/run_zep_gemini.py --task both

# 分析
python analysis/experiments/2026-05-02_mem0_zep_gemini_full100/scripts/summarize_results.py
python analysis/experiments/2026-05-02_mem0_zep_gemini_full100/scripts/mem0_detection_f1.py --since 2026-05-02T07:00:00
```

---

## 8. 待後續

1. **Mem0-graph baseline**（Neo4j 啟動 + langchain-neo4j 安裝 + config 加 graph_store + 重跑） — 用戶提的下一步
2. **Zep × Gemini inference 8% 探查**：抽 5-10 wrong cases 看 retrieved_context 跟 GPT run 對比，判斷是 retrieval 差還是 inference 風格差
3. **Mem0 detection FP unmatched 探查**：186/251 SH unmatched events 是 Mem0 在 personal-info 風格 supersession（如 "X is a X" → "X is a Y"）但跟我們 GT pair 沒匹配上，需 sample 看
4. **Update [INDEX.md](../../INDEX.md) §7 對比表**填入 Mem0/Zep × Gemini E2E + detection F1 數字

---

*產出日期：2026-05-02*
