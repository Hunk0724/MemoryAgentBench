# MemoryAgentBench `analysis/` — INDEX

> **目的**：把 `analysis/` 下散落的 28 份 md、41 支 py、與多層 results/ 子資料夾整理成一張地圖。實體位置不動（Option A），只在這份檔案做語意分組。
>
> **更新**：2026-04-29
> **如何用**：找特定實驗結果 → 跳到 §3 的 series；找關鍵詞 → §6 result reference；不確定縮寫 → §7 glossary。

---

## 1. ★ Main entry points

不確定看哪份時，**從這 3 份開始**：

| 檔案 | 內容 |
|---|---|
| **[fc_mh_research_overview.md](fc_mh_research_overview.md)** | 整個 FC-MH 研究的整合總覽（§0 executive summary 含兩階段架構 + 進度 + caveat + prospective design） |
| **[method_design_brainstorm.md](method_design_brainstorm.md)** | 下一步 method 設計的 brainstorm v3（v2 KG subgraph augmentation + v3 sequential decomposition） |
| **[SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md)** | 2026-04-28 9 個 oracle 實驗的完整 session 紀錄 |

---

## 2. Reading order（給接手者）

1. [fc_mh_research_overview.md](fc_mh_research_overview.md) — 看 §0 知道整體框架
2. [SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md) — 看 §4 / §5 知道實驗細節與 caveat
3. [method_design_brainstorm.md](method_design_brainstorm.md) — 看下一步要做什麼
4. 想 deep dive 哪個 method → 跳到 §3 的對應 series

---

## 3. 實驗系列（按時間順序）

### S1 — Step 1A：初始失敗根因分析（2026-04-16）

**目的**：HippoRAG-v2 在 FC-SH 69%、FC-MH 11% 上的失敗根因；用 MQuAKE-CF GT 精確定位每一跳的新/舊事實，量化 retrieval 取回率與失敗類型分布。

**Docs**:
- [step1a_methodology.md](step1a_methodology.md) — 方法論（GPT-4o-mini × chunk_size=512 × 6k context）
- [step1a_sh_summary.md](step1a_sh_summary.md) — FC-SH 結果摘要 + Oracle 預期
- [session_context.md](session_context.md) — 2026-04-16 之前的研究脈絡

**Scripts**:
- `analyze_sh_512_mquake.py` / `analyze_mh_512_mquake.py` — GPT 分析主腳本
- `analyze_sh_512_mquake_gemini.py` / `analyze_mh_512_mquake_gemini.py` — Gemini 版
- `analyze_sh_512_retrieval.py` — Retrieval 品質分析
- `analyze_lca_mquake.py` — LCA (Long Context Analysis) 不同 context size 對比
- `generate_step1a_charts.py` — 4 張 figs
- `generate_sh_512_report.py` — SH 詳細報告

**Results**:
- `results/{sh,mh}_512_mquake_analysis.json` + `_summary.txt` — **這是後續所有 oracle 都依賴的 per-hop GT mapping**
- `results/sh_512_retrieval_analysis.json`
- `results/sh_512_detailed_report.csv` / `.txt`
- `results/uncertain_no_conflict_pair.txt`
- `results/lca/*.json` / `*.txt` — LCA 跨 context size 結果
- `results/hipporag_gemini/*.json` — Gemini 版 plain HippoRAG 結果
- `results/fig_*.png` — 4 圖（衝突跳數 vs Acc / 失敗分布 / hop composition / retrieval 品質）

---

### S2 — Smoke Test：LLM Inference Probing

**目的**：透過 (A) trace-first / (B) post-hoc explain / (C) plain inference 三條件，probe LLM 在 FC-MH 上的 candidate visibility / signal comprehension / world-knowledge override 行為。產出 H1–H5 假設集。

**Docs**:
- [smoke_test_findings.md](smoke_test_findings.md) — smoke test 結果與假設推導

**Scripts**:
- `smoke_test_diagnostic.py` — 主腳本
- `smoke_test_diagnostic_all.py` — 全條件 (A/B/C) 整合
- `smoke_test_diagnostic_expanded.py` — 擴大樣本
- `smoke_test_diagnostic_gemini.py` — Gemini 版
- `smoke_test_diagnostic_rpt.py` — RPT prompt 條件
- `smoke_test_diagnostic_v2.py` — 第二版
- `expand_smoke_targets.py` — 從 SH/MH 抽 fair-condition targets
- `analyze_smoke_traces.py` / `analyze_smoke_traces_compare.py` — trace 後處理

**Results** (⚠️ 路徑奇怪，traces 在 `results/zep/`)：
- `results/zep/smoke_test_diagnostic_traces.json`
- `results/zep/smoke_test_all_traces.json`
- `results/zep/smoke_test_expanded_traces.json`
- `results/zep/smoke_test_gemini_traces.json`
- `results/zep/smoke_test_rpt_diagnostic_traces.json`
- `results/zep/smoke_test_targets.json` / `_expanded.json`

---

### S3 — Oracle A v1：Passage-level Filter（GPT + Gemini）

**目的**：第一版 Oracle A — 整 passage 移除（粗粒度）。後被 S5 的 OA2 fact-level surgical removal 取代（從 63.6% subset 升到 83% full）。

**Docs**:
- [results/oracle_a/oracle_a_report.md](results/oracle_a/oracle_a_report.md) — Oracle A v1 完整報告（GPT-4o-mini）
- [results/oracle_a/oracle_a_reasoning_comparison.md](results/oracle_a/oracle_a_reasoning_comparison.md) — Oracle A vs other reasoning
- [results/oracle_a/conflict_resolution_mechanisms.md](results/oracle_a/conflict_resolution_mechanisms.md) — 各 method 衝突處理機制概覽

**Scripts**:
- `oracle_a_phase1_validate.py` / `_gemini.py` — Phase 1 GT validation
- `oracle_a_phase2_inference.py` / `_gemini.py` — Phase 2 inference 跑 oracle filter
- `run_full_100.py` — 全 100 題 runner

**Results**:
- `results/oracle_a/oracle_a_{sh,mh}_results.json` — GPT 版 OA1 結果
- `results/oracle_a/baseline_raw_reasoning_{sh,mh}_{512,4096}.json` — 各 chunk_size baseline raw output
- `results/oracle_a/oracle_a_corrected_ranks.json`
- `results/oracle_a_corrected_ranks.json`（top-level，可能是更早版本）
- `results/oracle_a_gemini/oracle_a_{sh,mh}_results.json` — Gemini 版 OA1 結果
- `results/oracle_a_gemini/corrected_ranks.json`

---

### S4 — PAT / RPT / RPT-min：Inference-time Annotation

**目的**：對比 inference-time annotation 的 channel ceiling — PAT 軟標籤、RPT-min inline section、RPT 結構重組 + MUST。

**Docs**:
- [prompts_comparison.md](prompts_comparison.md) — vanilla / OA / PAT / RPT / RPT-min prompt 對照（cross-cutting，所有 method 在這查 prompt）

**Scripts**:
- `pat_gemini.py` — PAT (Gemini, 原 prompt)
- `pat_modified_prompt.py` — PAT (modified prompt, 對齊 A1/B/Sim-OB)
- `restructured_pat_gemini.py` — RPT (Section A/B + MUST)
- `restructured_pat_min_gemini.py` — RPT-min (inline marker, 無 MUST)

**Results**（在 `results/oracle_a_gemini/`）：
- `pat_{sh,mh}_results.json` / `pat_full_{sh,mh}_results.json` — PAT
- `rpt_{sh,mh}_results.json` / `rpt_full_{sh,mh}_results.json` — RPT
- `rpt_min_{sh,mh}_results.json` / `rpt_min_full_{sh,mh}_results.json` — RPT-min
- `results/diagnostic/pat_modified_{mh,sh}_results.json` — modified prompt 版

---

### S5 ★ — Diagnostic 9-Oracle Session（2026-04-28）

**目的**：建立 channel design space oracle benchmark — 把 detection-to-inference channel 各自的上限釘出來，回答「retrieval-time vs inference-time intervention」哪個 ceiling 高。

**Docs**:
- [SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md) — Session 完整紀錄（含 §4.5 修正後 framing 與 §5.5 prompt rigor caveat）
- [diagnostic_methodology.md](diagnostic_methodology.md) — 7 個實驗的方法論（modified prompt 部分）
- [diagnostic_findings.md](diagnostic_findings.md) — 完整數據 + paper-framing

**Scripts** (`analysis/`)：
- `a1_modified_prompt_baseline.py` — A1 modified-prompt baseline (重建 fair-compare)
- `a2_per_hop_diagnosis.py` — A2 per-hop diagnosis (從 A1 抽 per-hop 對齊 GT)
- `b_hop_by_hop_ablation.py` — B 每 hop 當 standalone FC-SH（94.5% per-hop / 87% all-pass）
- `c_no_distractor_conflicts.py` — C 移除非 chain old facts (42%)
- `sim_ob_chain_only.py` — Sim-OB chain-only (98% absolute ceiling)
- `sim_ob_grad_noise.py` — Sim-OB-grad noise gradient
- `oracle_a_fact_level.py` — **OA2 modified prompt** (83%)
- `oracle_a_fact_level_origprompt.py` — **OA2 original prompt** (55%)
- `pat_modified_prompt.py` — PAT modified prompt (補完 missing cell)
- `oa2_thought_error_analysis.py` — OA2 原 prompt 剩餘錯誤的 Thought 分析
- `diagnostic_summary.py` — 統合 summary 產生器

**Results** (`results/diagnostic/`)：
- `a1_modified_baseline_{mh,sh}.json`
- `a2_per_hop_diagnosis.json` + `_summary.txt`
- `b_hop_ablation_results.json`
- `c_no_distractor_conflicts_results.json`
- `sim_ob_chain_only_results.json`
- `sim_ob_grad_results.json`
- `oracle_a_fact_level_{mh,sh}_results.json` — OA2 modified
- `oracle_a_fact_level_origprompt_{mh,sh}_results.json` — OA2 orig
- `pat_modified_{mh,sh}_results.json`
- `oa2_remaining_errors_analysis.json` + `.txt`
- `diagnostic_summary.txt` — 自動生成對比表

---

### S6 — Zep Mechanism Analysis

**目的**：量化 Zep edge invalidation precision/recall vs MQuAKE GT，找 Zep 失敗根因（detection ~50% per-hop 觸發 + date_range 0% LLM 識別）。

**Docs** (⚠️ 散在兩處)：
- `analysis/` root：
  - [zep_methodology.md](zep_methodology.md)
  - [zep_sh_summary.md](zep_sh_summary.md)
  - [zep_mh_summary.md](zep_mh_summary.md)
- `results/oracle_a/`（被歸在 oracle_a 但其實是 Zep 專屬）：
  - [results/oracle_a/zep_mechanism_deep_dive.md](results/oracle_a/zep_mechanism_deep_dive.md) — **最完整的 Zep 機制分析**
  - [results/oracle_a/zep_deep_analysis.md](results/oracle_a/zep_deep_analysis.md)
  - [results/oracle_a/zep_fc_sh_pilot_findings.md](results/oracle_a/zep_fc_sh_pilot_findings.md)
  - [results/oracle_a/zep_full100_final_findings.md](results/oracle_a/zep_full100_final_findings.md)
  - [results/oracle_a/zep_mh_full100_findings.md](results/oracle_a/zep_mh_full100_findings.md)
  - [results/oracle_a/zep_chunk_size_experiment.md](results/oracle_a/zep_chunk_size_experiment.md)

**Scripts**:
- `analyze_zep_mechanism.py` — 主分析
- `analyze_zep_taxonomy_and_overlap.py` — taxonomy + overlap 分析

**Results**:
- `results/zep/{sh,mh}_zep_mechanism.json`
- `results/oracle_a/zep_{sh,mh}_invalidation_audit.json` / `_v2.json`
- `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_{sh,mh}_6k_*.json` — Zep 完整 inference 結果

---

### S7 — Mem0 Analysis

**目的**：量化 Mem0 在 FC 上 detection 失敗（`FACT_RETRIEVAL_PROMPT` 只抽 personal preferences，FC 知識被拒）。

**Docs**:
- [results/oracle_a/mem0_deep_analysis.md](results/oracle_a/mem0_deep_analysis.md)
- [results/oracle_a/mem0_zep_findings.md](results/oracle_a/mem0_zep_findings.md) — Mem0 與 Zep 跨 method 對照

**Scripts**: 無 dedicated 分析腳本（從 outputs 直接分析）

**Results**:
- `outputs/gpt-4o-mini-mem0/Conflict_Resolution/factconsolidation_{sh,mh}_6k_*.json`

---

### S8 — Non-counterfactual Baseline（2026-04-29 NEW，advisor 0422 建議）

**目的**：拆分「6k retrieval noise loss」與「conflict handling loss」 — 移除全部 chain olds（不只本題的）讓 6k 變成 no-conflict 但保留多跳結構。

**Docs**: 尚無專屬 doc（結論已併入 [fc_mh_research_overview.md](fc_mh_research_overview.md) §0.3 進度節）

**Scripts**:
- `non_counterfactual_baseline.py` — modified prompt 版（FC-MH **78%**, FC-SH 97%）
- `non_counterfactual_baseline_origprompt.py` — orig prompt 版（FC-MH **60%**, FC-SH 97%）

**Results** (`results/diagnostic/`)：
- `non_counterfactual_baseline_{mh,sh}_results.json` — modified
- `non_counterfactual_baseline_origprompt_{mh,sh}_results.json` — orig

**核心發現**：
- 4-hop 沒衝突 vanilla 條件下也只 26.7% → 多跳 retrieval 本身是嚴重瓶頸（不只 conflict）
- Trailer effect monotonic with cleanliness：A1 +3 / PAT +12 / NC +18 / OA2 +28

---

### S12 ★★ — Write-time + Query-time 分別評估（2026-05-03）

**Folder**：[experiments/2026-05-03_writetime_querytime_eval/](experiments/2026-05-03_writetime_querytime_eval/)

把 detection 拆成 write-time（GT-pair confusion matrix）+ query-time（retrieval recall），取代之前混 event/pair-level 的 F1 metric。

**Write-time 結果（FC-MH hop-level）**：

| | Mem0 | Zep |
|---|:---:|:---:|
| W1/Z1 correct UPDATE (right direction) | **57%** (108/188) | 37% (70/188) |
| W2/Z2 wrong direction | 1.6% | 4.3% |
| W3 ADD-only / Z3 no_invalidation | 22% | 31% |
| W4/Z4 missed/extraction miss | 19% | 27% |
| **Over-fire**（system fired event but no GT match） | 230/541 = 42% | n/a |

→ Mem0 detection 顯著強於 Zep（+20 pp），但 over-fire 警告（FC fit-artifact 風險）。

**Query-time 結果**：

| | new_recall@K | old_recall@K | both_in_topK | old_invalid_signal |
|---|:---:|:---:|:---:|:---:|
| Mem0 SH (K=100) | 88% | 5% | 3% | — |
| Mem0 MH (K=100) | 77% | 9% | 3% | — |
| Zep SH (K=10) | 100% | 100% | 100% | 24% |
| Zep MH (K=10) | 90% | 95% | **88%** | 22% |

→ paradigm 差異 quantified：Mem0 LLM 看到 old 只 5-9%（filter 把 outdated 清乾淨）；Zep LLM 88%+ 都看到 old+new，但只 22% 有 invalid_at 訊號 → **這是 Zep MH 8% E2E 的直接 explanation**。

---

### S11 ★★ — Mem0 + Zep × Gemini × Full 100q（2026-05-02）

**目的**：Phase 0 sprint Step 4 — 完成 Mem0 customized + Zep × Gemini fair-compare 全 200 題 + detection F1，填好對比表。

**Folder**：[experiments/2026-05-02_mem0_zep_gemini_full100/](experiments/2026-05-02_mem0_zep_gemini_full100/)

**核心結果**：

| | FC-SH EM | FC-MH EM | Detection F1 |
|---|:---:|:---:|:---:|
| Mem0 customized × Gemini | **77%** | **43%** | **39.5%** (MH) |
| Zep × Gemini inference | **79%** | **8%** | **46.5%** (MH, from GPT audit) |
| OA2 modified (oracle) | 98% | 83% | 100% |

→ Phase 0 sprint Step 5 模式判定 = **模式 B（detection + propagation 雙重瓶頸）**

→ Zep MH 3+ hops 全 0%；Mem0 4-hop 26.7%。Production 系統 detection F1 都 < 50%。

---

### S10 ★ — Phase 0 Baseline Setup（2026-04-30，組織化資料夾示範）

**目的**：Phase 0 三天衝刺 Step 1+3 的前置 — Mem0/Zep audit + Gemini fair-compare setup。建立 Mem0 customized + Vertex Gemini + Zep detection F1 計算的工具鏈，**全 100 題實驗待後續 session**。

**為什麼這個 series 跟其他不同**：這是第一個按「腳本 + 結果 + README 集中放在一個資料夾」整理的實驗 series；以後新實驗都仿這個結構。

**Folder**：[experiments/2026-04-30_mem0_zep_baseline_setup/](experiments/2026-04-30_mem0_zep_baseline_setup/)

```
experiments/2026-04-30_mem0_zep_baseline_setup/
├── README.md                 ← session 完整紀錄 (Q1/Q2/Q3 + setup + 待後續)
├── scripts/
│   ├── mem0_vertex_gemini_llm.py   ← Mem0 LLM provider 用 Vertex Gemini ADC
│   ├── mem0_l1_smoke_test.py       ← L1 minimal-mod ingestion smoke
│   └── zep_detection_f1.py         ← Zep P/R/F1 純分析（無 LLM）
└── results/
    ├── mem0_l1_smoke_results.json
    ├── zep_detection_metrics.json
    └── zep_{sh,mh}_invalidation_audit_input.json
```

**核心發現**：
- Mem0 OOB ingestion = 0 facts（FACT_RETRIEVAL_PROMPT 拒收 FC 通用知識）
- Mem0 L1 mod（移 2 個 anti-knowledge few-shots）+ Vertex Gemini + max_tokens=8192 → 12/12 chunks 抽出 448 facts，ADD/UPDATE/DELETE pipeline 全運作（ADD 445 / UPDATE 150 / DELETE 5）
- Zep detection F1：FC-SH 33.1%（precision 42.6% / recall 27.0%）；FC-MH 46.5%（precision 89.4% / recall 31.4%）— 大半 has_pair hop 沒被 detect
- Q1: MAB 預設 Mem0 = vector mode（無 graph），Mem0-graph 是獨立 baseline
- Q2: Zep 換 Gemini **只能改最終 QA reading**，detection / supersession / context summary 永遠 Zep 內部 LLM
- Q3: smoke 真的用了 Mem0 完整 pipeline（150 UPDATE events 證實 supersession 偵測有運作）

---

### S9 — Plain HippoRAG Utilities

**目的**：跑 plain HippoRAG-v2（無 oracle）作為各 oracle 的 reference baseline。

**Scripts**:
- `run_plain_hippo_gemini_full100.py` — Plain HippoRAG Gemini 100 題
- `run_full_100.py` — 通用 full-100 runner

**Results**:
- `results/zep/plain_hippo_gemini_full100.json`（⚠️ 路徑誤導 — 在 zep/ 但其實是 plain HippoRAG）

---

## 4. Cross-cutting References

| 檔案 | 用途 |
|---|---|
| [prompts_comparison.md](prompts_comparison.md) | vanilla / OA / PAT / RPT / RPT-min 各 method 的 inference prompt 對照 |
| [implementation_status.md](implementation_status.md) | 各 oracle / method 實作進度狀態 |
| [fc_mh_hypotheses.md](fc_mh_hypotheses.md) | H1–H5 working hypotheses + 嚴謹度審計（部分內容已併入 overview §2） |
| [next_phase_design_space.md](next_phase_design_space.md) | ⚠️ **已被 [fc_mh_research_overview.md](fc_mh_research_overview.md) 與 [method_design_brainstorm.md](method_design_brainstorm.md) supersede**，保留作歷史參考 |

---

## 5. Project Root Scripts（`MemoryAgentBench/` 目錄下）

### 5.1 主要 Python entry points

| 檔案 | 用途 |
|---|---|
| `main.py` | MemoryAgentBench 主執行入口（dataset × method × model 組合） |
| `agent.py` | Memory agent 抽象 |
| `initialization.py` | 初始化 |
| `conversation_creator.py` | Conversation 建立 |
| `run_zep_full100.py` | Zep 全 100 題 runner |
| `run_zep_mh_full100.py` | Zep MH 100 題 runner |
| `run_zep_refetch_retrieval.py` / `run_zep_refetch_retry.py` | Zep retrieval refetch utility |

### 5.2 Bash wrapper scripts（一鍵跑某 method × model 組合）

| 檔案 | 用途 |
|---|---|
| `run_full_100_all.sh` | 跑全部 method × FC 100 題 |
| `run_hipporag_gemini.sh` | HippoRAG × Gemini |
| `run_oracle_a_gemini.sh` | Oracle A × Gemini |
| `run_pat_gemini.sh` | PAT × Gemini |
| `run_rpt_gemini.sh` / `run_rpt_min_gemini.sh` | RPT / RPT-min × Gemini |
| `run_zep_full100.sh`（暫無） / `run_zep_mem0_phase1.sh` | Zep + Mem0 Phase 1 |
| `run_gpt4omini.sh` / `run_gpt4omini_retry.sh` | GPT-4o-mini × HippoRAG |
| `run_gemini_32k.sh` / `run_gemini_global.sh` | Gemini × 32k context / global location |

---

## 6. 資料輸入與輸出（路徑速查）

### 6.1 知識輸入

| 路徑 | 內容 |
|---|---|
| `analysis/contexts/factconsolidation_6k_context.txt` | FC-SH/MH 共用 6k knowledge pool（455 facts） |
| `analysis/contexts/factconsolidation_32k_context.txt` | 32k 版 knowledge pool |
| `/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json` | MQuAKE-CF GT (3000 cases，FC 100 題從這抽) |
| `/home/yhchiang/MQuAKE/datasets/MQuAKE-T.json` | MQuAKE-T (temporal, 1868 cases) — 目前沒被使用 |
| `analysis/results/{sh,mh}_512_mquake_analysis.json` | **Per-hop GT mapping**（後續 oracle 都依賴） |

### 6.2 Inference outputs（按 model 分）

每個 model 目錄結構：`outputs/<model>/Conflict_Resolution/factconsolidation_{sh,mh}_{6k,32k}_*.json`

| Model dir | Method | 內容 |
|---|---|---|
| `outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/` | HippoRAG-v2 × GPT-4o-mini | FC-SH/MH × {chunk512, chunk4096, baseline_b} |
| `outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/` | HippoRAG-v2 × Gemini 3.1 FL | FC-SH/MH × chunk512 |
| `outputs/gpt-4o-mini-zep/Conflict_Resolution/` | Zep × GPT-4o-mini | FC-SH/MH × chunk512（含 FULL100 變體） |
| `outputs/gpt-4o-mini-mem0/Conflict_Resolution/` | Mem0 × GPT-4o-mini | FC-SH/MH × {chunk512, chunk4096} × k=100 |
| `outputs/gpt-4o-mini/Conflict_Resolution/` | GPT-4o-mini 純 LLM (no memory) | FC-SH/MH × {6k, 32k} |
| `outputs/gemini-2.5-flash-lite/Conflict_Resolution/` | Gemini 2.5 Flash-Lite 純 LLM | FC-SH/MH × {6k, 32k} |
| `outputs/gemini-2.5-flash/Conflict_Resolution/` | Gemini 2.5 Flash 純 LLM | FC-SH/MH × 6k |
| `outputs/gemini-3.1-flash-lite-preview/Conflict_Resolution/` | Gemini 3.1 FL Preview 純 LLM | FC-SH/MH × 6k |

### 6.3 Retrieval cache

| 路徑 | 內容 |
|---|---|
| `outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_{sh,mh}_6k/chunksize_512/query_{qid}_context_0.json` | HippoRAG-v2 × NV-Embed × top-10 passages per query — **9 個 oracle 都依賴此 cache** |
| `outputs/rag_retrieved/Structure_rag_zep/k_10/...` | Zep retrieval cache |
| `outputs/rag_retrieved/Structure_rag_mem0/...` | Mem0 retrieval cache |
| `outputs/rag_retrieved/NV-Embed-v2/factconsolidation_{sh,mh}_6k/...` | 純 embedding retrieval cache |

### 6.4 Agent state（Zep）

| 路徑 | 內容 |
|---|---|
| `agents/Structure_rag_zep_factconsolidation_{sh,mh}_6k_chunk512_modelgpt-4o-mini/exp_0/` | Zep agent state + messages |

---

## 7. ★ Experiment Results（多表速查）

### 7.1 FC-MH EM landscape — Modified prompt（trailer added）

LLM = Gemini 3.1 Flash-Lite Preview，n=100，HippoRAG-v2 retrieval

| Method | EM | Δ vs A1 | Script | Result file |
|---|:---:|:---:|---|---|
| A1 baseline | 23% | — | `a1_modified_prompt_baseline.py` | `results/diagnostic/a1_modified_baseline_mh.json` |
| C 移除非 chain olds | 42% | +19 pp | `c_no_distractor_conflicts.py` | `results/diagnostic/c_no_distractor_conflicts_results.json` |
| PAT modified | 48% | +25 pp | `pat_modified_prompt.py` | `results/diagnostic/pat_modified_mh_results.json` |
| **NC modified（NEW）** | **78%** | **+55 pp** | `non_counterfactual_baseline.py` | `results/diagnostic/non_counterfactual_baseline_mh_results.json` |
| **OA2 fact-level (modified)** | **83%** | **+60 pp** | `oracle_a_fact_level.py` | `results/diagnostic/oracle_a_fact_level_mh_results.json` |
| B all-pass（per-hop standalone） | 87% | +64 pp | `b_hop_by_hop_ablation.py` | `results/diagnostic/b_hop_ablation_results.json` |
| B per-hop（每 hop 獨立 SH） | 94.5% | — | 同上 | 同上 |
| **Sim-OB chain-only** | **98%** | **+75 pp** | `sim_ob_chain_only.py` | `results/diagnostic/sim_ob_chain_only_results.json` |

### 7.2 FC-MH EM landscape — Original prompt（vanilla HippoRAG）

| Method | EM | Script | Result file |
|---|:---:|---|---|
| A1 vanilla baseline | 20% | (既有 outputs) | `outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/.../mh_6k_*.json` |
| Plain HippoRAG (full 100, gemini) | 22% | `run_plain_hippo_gemini_full100.py` | `results/zep/plain_hippo_gemini_full100.json` |
| PAT (orig prompt) | 36% | `pat_gemini.py` | `results/oracle_a_gemini/pat_*_results.json` |
| **OA2 (orig prompt)** | **55%** | `oracle_a_fact_level_origprompt.py` | `results/diagnostic/oracle_a_fact_level_origprompt_mh_results.json` |
| RPT-min (orig prompt) | 60% | `restructured_pat_min_gemini.py` | `results/oracle_a_gemini/rpt_min_*_results.json` |
| **NC origprompt（NEW）** | **60%** | `non_counterfactual_baseline_origprompt.py` | `results/diagnostic/non_counterfactual_baseline_origprompt_mh_results.json` |
| RPT (orig prompt) | 68% | `restructured_pat_gemini.py` | `results/oracle_a_gemini/rpt_*_results.json` |
| **Sim-OB chain-only (orig prompt, NEW)** | **97%** | `sim_ob_chain_only_origprompt.py` | `results/diagnostic/sim_ob_chain_only_origprompt_results.json` |

### 7.3 FC-SH EM landscape

LLM = Gemini 3.1 Flash-Lite，n=100

| Method | Modified prompt | Original prompt |
|---|:---:|:---:|
| A1 baseline | 96% | 77% |
| PAT | 97% | ~96% |
| **OA2 fact-level filter** | **98%** | **98%** |
| **NC（NEW）** | **97%** | **97%** |
| Sim-OB chain-only | 98% | — |

→ FC-SH 接近飽和，所有 method 落在 96–98%。**多跳特定問題只在 FC-MH 出現**。

### 7.4 ★ NC vs Sim-OB by num_hops（multi-hop retrieval 衰減曲線，paper-relevant）

| num_hops | A1 mod (with conflict) | NC mod | NC orig | Sim-OB orig | Sim-OB mod |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 2 | — | 90.2% (55/61) | 70.5% (43/61) | 95.1% (58/61) | 96.7% (59/61) |
| 3 | — | 70.8% (17/24) | 54.2% (13/24) | **100% (24/24)** | 100% (24/24) |
| **4** | — | **40.0% (6/15)** | **26.7% (4/15)** | **100% (15/15)** | 100% (15/15) |

→ **關鍵 evidence**：Sim-OB orig 3-hop / 4-hop 都 **100%**，但 NC orig 4-hop 只 26.7%。**LLM 多跳 reasoning 在乾淨 chain 上完全沒問題，4-hop 在 6k retrieval 下崩到 26.7% 全部來自 retrieval / context 限制**，與 conflict 無關。這是 paper 主張「multi-hop retrieval 是獨立、嚴重瓶頸」的直接量化證據。

### 7.5 NC by n_conflict（修正後的衝突跳數，現在每個都 resolved）

| n_conflict | NC modified | NC origprompt |
|:---:|:---:|:---:|
| 1 | 90.9% (30/33) | 66.7% (22/33) |
| 2 | 81.2% (39/48) | 64.6% (31/48) |
| 3 | 47.1% (8/17) | 41.2% (7/17) |
| 4 | 50.0% (1/2) | 0.0% (0/2) |

### 7.6 Trailer effect across context cleanliness（SESSION §4.5.2 + NC + Sim-OB NEW）

| Method | Orig prompt | Modified prompt | Trailer Δ |
|---|:---:|:---:|:---:|
| A1（very noisy + conflict） | 20% | 23% | +3 pp |
| PAT（mid-noisy + soft label） | 36% | 48% | +12 pp |
| **NC（cleaner，no conflict + heavy removal）** | **60%** | **78%** | **+18 pp** |
| OA2（cleanest，chain conflict 清乾淨 + 6k 完整） | 55% | 83% | +28 pp |
| **Sim-OB（cleanest possible，only chain）** | **97%** | **98%** | **+1 pp（saturation）** |

→ **Inverted-U with cleanliness**：trailer 在 mid-clean 級別最有效（OA2 +28 pp），太髒（A1 +3）或太乾淨（Sim-OB +1）都效應小。OA2 之後 trailer 邊際效應 saturate — 這是 paper 對 trailer scope 的限定 evidence。

### 7.7 Production system baselines（跨 method）

| Method | LLM | FC-SH | FC-MH | Doc / Script |
|---|---|:---:|:---:|---|
| Plain HippoRAG-v2 (chunk=512) | GPT-4o-mini | 69% | 11% | step1a |
| Plain HippoRAG-v2 (chunk=512) | Gemini 3.1 FL (orig prompt) | 77% | 22% | session_context |
| Plain HippoRAG-v2 (chunk=512) | Gemini 3.1 FL (modified prompt) | 96% | 23% | A1 modified |
| **Zep OOB** | GPT-4o-mini | 70% | 25% | [zep_mechanism_deep_dive](results/oracle_a/zep_mechanism_deep_dive.md) |
| **Zep × Gemini inference**（NEW 2026-05-02） | Gemini 3.1 FL | **79%** | **8%** | [experiments/2026-05-02.../zep_gemini_*_results.json](experiments/2026-05-02_mem0_zep_gemini_full100/results/) |
| **Mem0 OOB**（vector mode）| GPT-4o-mini | 15% | 1% | [mem0_deep_analysis](results/oracle_a/mem0_deep_analysis.md) |
| **Mem0 customized × Gemini**（NEW 2026-05-02） | Gemini 3.1 FL | **77%** | **43%** | [experiments/2026-05-02.../mem0_gemini_*_results.json](experiments/2026-05-02_mem0_zep_gemini_full100/results/) |
| Mem0-graph (Neo4j) | — | **待跑** | **待跑** | (Phase 0 sprint Step 1 audit blocker check) |

→ **Zep 25% > HippoRAG 11%（GPT）** 但 Zep 的 detection 只 ~50% per-hop 觸發；Mem0 因 `FACT_RETRIEVAL_PROMPT` 拒收 FC 知識所以幾乎全錯。

### 7.8 Detection audit（Zep-format event-level，hop-level for MH）

**FC-SH**:

| | total invalidations | correct | wrong | false_positive | unique correct / has_pair | P | R | F1 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Mem0 customized × Gemini | 251 | 65 | 0 | 186 | 33/74 | 25.9% | 44.6% | **32.8%** |
| Zep × Gemini (sampled) | 64 | 18 | 7 | 39 | 18/74 | 28.1% | 24.3% | **26.1%** |
| Zep × GPT (existing) | 48 | 20 | **25** | 2 | 20/74 | 41.7% | 27.0% | **32.7%** |

**FC-MH (hop-level)**:

| | total invalidations | correct | wrong | false_positive | unique correct / has_pair | P | R | F1 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Mem0 customized × Gemini | 251 | 133 | 0 | 118 | 67/188 | 53.0% | 35.6% | **42.6%** |
| Zep × Gemini (sampled) | 78 | 65 | 7 | 6 | 65/188 | 83.3% | 34.6% | **48.9%** |
| Zep × GPT (existing) | 67 | 59 | 3 | 4 | 59/188 | 88.1% | 31.4% | **46.3%** |

→ 三系統 FC-MH F1 都 < 50%，都遠低於 OA2 oracle 100%。Mem0 wrong-direction 都是 0（structural ingest order，無 world-knowledge bias）；Zep × GPT SH 25/48 個方向反錯（counterfactual bias），Zep × Gemini SH 改善至 7。

### 7.9 ★ Detection × Answer Correspondence（rigor check）

每題依 chain has_pair hop 偵測狀況分組，看答對率：

| 系統 / Task | All detected EM | Partial EM | No detection EM | No has_pair EM | Det × Ans 差異 |
|---|:---:|:---:|:---:|:---:|:---:|
| Mem0 SH | **91% (30/33)** | — | 56% (23/41) | 92% (24/26) | +35 pp ✓ |
| Mem0 MH | **77% (20/26)** | 42% (14/33) | 22% (9/41) | — | +55 pp（all vs none）✓ monotonic |
| Zep × Gemini SH | 89% (16/18) | — | 68% (38/56) | 96% (25/26) | +21 pp |
| **Zep × Gemini MH** | **0% (0/8)** | 6% (1/18) | 9.5% (7/74) | — | **−9 pp**（反例！）|
| Zep × GPT SH FULL | 67% (6/9) | — | 59% (38/65) | 100% (26/26) | +8 pp |

→ **Mem0 是 detection-bottleneck**（Spec mode C）；**Zep MH 是 propagation-bottleneck**（Spec mode A，detection 全對也 0% EM）；**整體 paper baseline 兩種 mode 都存在**（Spec mode B）。詳見 [experiments/2026-05-02.../README.md §4.5](experiments/2026-05-02_mem0_zep_gemini_full100/README.md#45--detection--answer-correspondencerigor-check)。

### 7.10 Mem0 OOB fact extraction（no L1 mod，confirms baseline broken）

| | n chunks | n with extracted facts | total facts | Source |
|---|:---:|:---:|:---:|---|
| Mem0 OOB GPT FC-SH | 12 | **0** | **0** | `outputs/rag_retrieved/Structure_rag_mem0/.../ingestion_context_0.jsonl` |
| Mem0 OOB GPT FC-MH | 12 | **0** | **0** | 同上 |
| Mem0 L1 mod × Gemini smoke | 12 | 12 | ~448 | [experiments/2026-04-30.../mem0_l1_smoke_results.json](experiments/2026-04-30_mem0_zep_baseline_setup/results/mem0_l1_smoke_results.json) |

---

## 8. Glossary（縮寫）

| 縮寫 | 全名 | 說明 |
|---|---|---|
| FC-SH / FC-MH | FactConsolidation Single-Hop / Multi-Hop | 100 題 conflict resolution 任務 |
| OA1 | Oracle A v1 | passage-level filter（粗）— 已 supersede |
| **OA2** | Oracle A v2 | fact-level surgical filter — paper Layer 1 universal target |
| PAT | Passage-level Annotation Tag | 軟標籤 `[CURRENT/OUTDATED FACT]` |
| RPT | Restructured Passage Tag | Section A/B + MUST 強指令（FC-overfit） |
| RPT-min | RPT minus MUST | 只有 inline section labels |
| Sim-OB | Simulated Oracle B | chain-only context（absolute ceiling） |
| Sim-OB-grad | Sim-OB gradient noise | 加 k ∈ {10,50,100,200,455} distractors |
| **NC** | Non-counterfactual baseline | 移除全部 chain olds（chain + non-chain）— NEW 2026-04-29 |
| Modified prompt | A1/B/Sim-OB/OA2 modified | 加 `Intermediate answers: [a, b, c]` trailer |
| Original prompt | RPT/PAT/OA1/NC origprompt | 不加 trailer 的 vanilla HippoRAG prompt |
| H1–H5 | Working hypotheses | Visibility / Signal / Trust gap / Multiplicative / Chain mis-anchor |

---

## 9. Common Confusions / 常見困惑點

| 看到 X 會以為 Y，但其實是 Z | 解法 |
|---|---|
| `results/zep/` 名稱是 zep 但裡面有 smoke_test 與 plain_hippo 結果 | 路徑歷史遺留；**真正 zep 機制資料在 `results/zep/{sh,mh}_zep_mechanism.json`，audit 在 `results/oracle_a/zep_*_invalidation_audit*.json`** |
| `results/oracle_a/` 名稱是 oracle_a 但有 7 個 zep_*.md + 2 個 mem0_*.md | 命名延伸自最早的 OA1 探索；現在它實際上是「method deep-dive 報告集中地」 |
| OA2 有兩個版本 (modified 83% vs orig 55%) | 不同 inference prompt — 詳見 SESSION §5.5 prompt rigor caveat |
| Sim-OB 98% 與 Task B 87% / per-hop 94.5% 哪個是真 ceiling | Sim-OB 移除 6k 噪音 + 衝突；B 拆 single-hop 但保留 6k；兩者測不同維度 |
| `next_phase_design_space.md` 與 `fc_mh_research_overview.md` 哪個看 | **看 overview**；next_phase 已被 supersede |
| 「FC-MH 20%」「FC-MH 22%」「FC-MH 23%」哪個對 | 都對，只是 prompt 條件不同：20% gemini orig / 22% gemini orig 不同 run / 23% gemini modified；§7.1/§7.2 有對照 |
| `fc_mh_hypotheses.md` 還是 overview §2 講 H1–H5 | overview §2 是濃縮版，hypotheses doc 是完整版（含嚴謹度審計） |

---

## 10. 已知未做 / Open Experiments

| 待做 | 來源 | 預估成本 |
|---|---|---|
| ~~Sim-OB original prompt~~ | ✓ 已完成 (97%) | — |
| Zep + Mem0 用 Gemini 重跑（fair compare with 9 oracles） | overview §9 Phase 1 | ~30 min |
| Zep edge invalidation precision/recall on MH + Gemini | overview §9 Phase 1.2 | 中等 |
| Mem0 customization（改 `custom_fact_extraction_prompt`） | overview §9 Phase 1.3 | 中等 |
| Imperfect detection robustness（OA2 加 noise，r ∈ {0.6, 0.8, 1.0}） | overview §9 Phase 2 | 中等 |
| C2 = 0A + Step 5 RM extend（method paper baseline） | brainstorm §7 Phase α | 中等 |
| C4 = 0A + 1D + 2C forward chaining（method paper main） | brainstorm §7 Phase β | 高 |
| 32k / 64k / 262k context 擴展 | overview §9 Phase 5 | 高 |

---

## 11. Memory References

外部 memory 引用本目錄的檔案：

| Memory file | 引用 |
|---|---|
| `~/.claude/projects/-home-yhchiang/memory/reference_fc_mh_diagnostic.md` | 入口指向 `fc_mh_research_overview.md` |
| `~/.claude/projects/-home-yhchiang/memory/MEMORY.md` | INDEX 指向 reference_fc_mh_diagnostic |

**若以後做 Option B 資料夾重組，這兩處連帶要 update**。

---

*最後更新：2026-04-29*
*下次有新實驗加進來時，記得在 §3 補新 series + §6 補新數字 + §9 把待做項目移過來*
