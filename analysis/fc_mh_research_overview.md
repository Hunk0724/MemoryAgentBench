# FC-MH 多跳事實鞏固研究 — 整合總覽

> 整合日期：2026-04-29
> 統整來源：
> - [SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md) — 9 個 oracle 實驗、敘事與發現
> - [fc_mh_hypotheses.md](fc_mh_hypotheses.md) — 5 個 working hypotheses (H1–H5) + 嚴謹度審計
> - [next_phase_design_space.md](next_phase_design_space.md) — 從 HippoRAG-v2 出發的 conflict detection design map
>
> 本檔目的：把上述三份的核心結論收斂成一份可獨立讀懂的研究總覽。原始三份保留作為深挖細節的索引；如需 raw data、prompt 對照、實驗腳本，請依各節指引回去查。

---

## 0. Executive Summary — 研究框架與本次進度

### 0.1 整體方法架構（兩階段）

我們把「memory-augmented agent 處理知識更新」拆成兩個獨立 phase：

| 階段 | 任務 | 對應 design space 維度 |
|---|---|---|
| **Phase 1: Write-time detection** | 在記憶寫入 / KG 構建時，偵測「哪個 fact 是新的、哪個是舊的、哪個 supersede 哪個」 | (A) Detection accuracy（§7） |
| **Phase 2: Query-time handling** | 拿到 query 時，根據 Phase 1 的標記，決定怎麼把新舊知識傳給 LLM 做 inference | (B) Info-packaging（§6：filter / annotation / hybrid） |

**核心 thesis**：FC-MH 這種 multi-hop knowledge update 任務，需要 Phase 1 + Phase 2 都做對才能解；過去 production 系統（Zep / Mem0 / HippoRAG-v2）沒人同時做好這兩件事。

### 0.2 基準線數字（perfect Phase 1 條件下，Phase 2 不同設計的上限）

| 條件 | FC-MH EM (orig prompt) | FC-MH EM (modified prompt) | 角色 |
|---|:---:|:---:|---|
| A1 baseline（top-10 retrieved + 6k 噪音，無 detection） | 20% | **23%** | **Floor** |
| NC non-counterfactual（無衝突，全 olds 移除） | **60%** | **78%** | "noise-only" reference (NEW) |
| OA2 retrieval-time fact-level filter（perfect detection） | **55%** | **83%** | Layer 1 / Layer 2 target |
| RPT（perfect detection + Section A/B + MUST，FC-overfit） | 68% | — | Reference ceiling，**不可部署** |
| Sim-OB chain-only（零噪音零衝突） | **97%** | **98%** | **Absolute ceiling**（純 LLM multi-hop 能力上限） |

**Bottom line**：
- Universal claim：**OA2 retrieval-filter 不改 prompt 即可 +35 pp on FC-MH**（20 → 55% orig / 23 → 83% modified），對 summarization / Recsys 等所有 4 類 memory task transparent
- QA-task add-on：trailer 對 OA2 多 +28 pp（55 → 83%），對 Sim-OB 只 +1 pp（saturation），trailer effect inverted-U with cleanliness
- Filter > soft annotation (PAT) 在所有 prompt 條件下成立（+19 ~ +35 pp on MH）
- **LLM 純多跳推理不是瓶頸（Sim-OB 97-98%）**；剩下的 noise loss 在 vanilla regime 下達 37 pp，與 conflict loss 40 pp 同等重要（詳見 §0.3）

### 0.3 本次進度（已完成）

**A. Phase 2 上限測試**（假設 Phase 1 perfect 條件下，Phase 2 不同 channel 能跑多高）
9 個 oracle 實驗（§3）用 MQuAKE GT 模擬 perfect detection，量化：
- Filter route (OA2)：23% → 55% (orig prompt) / 83% (modified prompt)
- Annotation route (PAT / RPT-min / RPT)：36% / 60% / 68%
- Pure-LLM ceiling (Sim-OB)：97% (orig) / 98% (modified)

**B. FC-MH 難解原因診斷** — 5 個 working hypotheses H1–H5（§2）解釋「就算只看 LLM-side，為什麼 multi-hop 比 single-hop 崩這麼多」。

**C. Non-counterfactual baseline + Sim-OB origprompt（advisor 0422 建議，2026-04-29 NEW）**
拆分「conflict handling loss」與「6k retrieval noise loss」。NC 移除全部 chain olds（chain + non-chain），保留多跳結構。Sim-OB 改用 vanilla HippoRAG prompt 補完 origprompt regime。

兩個 prompt regime 的完整 decomposition：

| Regime | A1 | NC | Sim-OB | Conflict loss | 6k noise loss | Total |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Modified prompt | 23% | 78% | 98% | 55 pp (73%) | 20 pp (27%) | 75 pp |
| **Original prompt (vanilla)** | **20%** | **60%** | **97%** | **40 pp (52%)** | **37 pp (48%)** | **77 pp** |

→ **Modified regime 下 conflict 是主因（73%）；vanilla regime 下兩者幾乎平分**。先前研究偏 modified prompt 結果，使「conflict 是主因」這個 framing 過度傾斜。

**Per num_hops 衰減（NC orig vs Sim-OB orig）— paper main evidence**：

| num_hops | NC orig (with 6k noise) | Sim-OB orig (chain only) |
|:---:|:---:|:---:|
| 2 | 70.5% | 95.1% |
| 3 | 54.2% | **100%** |
| 4 | **26.7%** | **100%** |

→ **Sim-OB orig 在 3-hop / 4-hop 都 100%** ⇒ LLM 多跳 reasoning 在乾淨 chain 上完全沒問題；NC orig 4-hop 26.7% **全部來自 retrieval / context 限制，與 conflict 無關**。是 paper「multi-hop retrieval 是獨立、嚴重瓶頸」的直接量化證據。

### 0.4 下一步（待做）

**C. Related work gap 確認**（Phase 1 主張的 evidence，§9 Phase 1）
- 重跑 Zep + Mem0 用 Gemini 3.1 Flash-Lite fair compare
- 量化 Zep edge invalidation precision/recall vs MQuAKE GT
- 量化 Mem0 fact extraction recall on FC
- → 要的證據：**production 系統 detection precision/recall 都不到 100% 且 E2E EM 顯著低於 OA2 oracle ceiling**，這就是 paper main motivation 的 gap

**D. 我們的 Phase 1 設計**（補 gap，§9 Phase 4）
從 HippoRAG-v2 出發加 detection layer，候選方向 D1–D5（§7）。設計時要對應 Phase 2 的 robustness 曲線（§9 Phase 2 的 imperfect-detection ablation）。

### 0.5 方法論 Caveat — Probing prompt 引入的 confound

本次進度的最大方法論弱點：我們大量使用 modified prompt（intermediate trailer `[hop1, hop2, hop3]`）+ (A)/(B)/(C) 三條件來「強迫 LLM 暴露 reasoning」，藉此驗證 H1–H5。但這引入三個 confound：

1. **Modified prompt 本身就是 intervention**（trailer 給 OA2 +28 pp，§5.2 軸 2）
2. **(A) 條件強制結構化輸出可能改變 attention 分配**（HippoRAG (A) EM 從 6.7% 跌到 0% 是證據）
3. **(B) 條件有 rationalization 風險**（事後合理化編出沒實際發生的推理；§8.5）

→ 我們觀察到的「LLM-side 行為」是 probing 結果，不是真實黑盒 inference 的內部 state
→ H1 LLM-side recall 量化是 upper bound；H2 與 H1 confound；H3 機制不確定（§2.4）

### 0.6 解法 — Prospective Hypothesis-Driven Design

下一階段不再用 probing prompt 觀察 reasoning trace（confound 太多），改成「實驗前寫死預測值，實驗中保持 inference prompt 不動」：

```
假設 H_i  ──►  設計 Phase 1 方法 M_i  ──►  寫死 EM 預測值
                                                 │
                                       (不動 inference prompt)
                                                 ▼
                                       跑 M_i → 比較實際 vs 預測
```

具體 4 步驟（以 D1 補 H1 為例）：

1. **把假設翻成可預測數字**：H1（visibility 是瓶頸）+ OA2 oracle 55%（perfect detection）→ 預測「D1 detection precision = P 時，EM ≈ 22% + P × (55% − 22%)」
2. **用跟 baseline 完全一樣的 inference prompt 跑 D1**（只動 retrieval / Phase 1，不動 LLM 端）
3. **比較實際 EM vs 預測 EM**：
   - 對 → H1 + D1 設計都正確
   - 錯 → 拆解：detection precision 沒達標 vs H1 不是真瓶頸
4. **不論結果如何都更新假設與下個方法**

三個好處：
1. 預測值在實驗前寫死 → 沒有 post-hoc rationalization 風險
2. 不需要改 inference prompt → 黑盒一致，沒有 probing-induced behavior change
3. 不同方法的 EM 在同 prompt 條件下對齊 → 避免「gain 來自方法還是來自 prompt 工程」的質疑

→ 最終 paper main result table 會是「**同 prompt 條件下，不同 Phase 1 / Phase 2 組合的 EM**」。

**核心 reframe**：我們沒有「解決」FC-MH，而是 (1) 把問題從「LLM 該怎麼 reason」reframe 成「Phase 1 detection × Phase 2 packaging」雙階段設計問題，(2) 用 9 個 oracle 把 Phase 2 上限釘出來、讓 production 系統能對照定位，(3) 接下來用 prospective design 驗證 Phase 1 設計能多接近 oracle。

---

## 1. 背景 Context

### 1.1 專案與資料集
- **專案**：[MemoryAgentBench](../README.md) — 評估 memory-augmented agents 的 benchmark，涵蓋 4 類任務：
  - Conflict_Resolution（FC）
  - Accurate_Retrieval（EventQA, LongMemEval, Ruler）
  - Long_Range_Understanding（Detective_QA, InfBench_sum 含 summarization）
  - Test_Time_Learning（Recsys, ICL）
- **本研究焦點**：`Conflict_Resolution / FactConsolidation`
  - **FC-SH** = single-hop, 100 題
  - **FC-MH** = multi-hop (2/3/4-hop), 100 題
  - 知識來源：MQuAKE-CF（`/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json`）
  - 知識庫：6k tokens、455 numbered facts；每題 chain 中某些 hop 同時存在「新事實 (GT)」與「舊事實 (old)」
  - 規則：「序號越大越新越正確」

### 1.2 環境
- HippoRAG-v2（NV-Embed-v2 retrieval + KG + PPR rerank）
- Gemini 3.1 Flash-Lite preview（via Vertex AI, location=global）
- chunk_size=512, top-k=10, 6k context, 455 facts
- Conda envs：`hipporag_env`（HippoRAG retrieval）、`MABench`（non-RAG agents）
- Vertex API：`GOOGLE_CLOUD_PROJECT=fc-mh-494213, LOCATION=global`

### 1.3 既有 baseline
| 系統 | LLM | FC-SH | FC-MH |
|---|---|:---:|:---:|
| HippoRAG-v2 + chunk_size=512 | GPT-4o-mini | 69% | 11% |
| HippoRAG-v2 + chunk_size=512 | Gemini 3.1 Flash-Lite | 77% | 20% |

---

## 2. Working Hypotheses — H1–H5

> 5 個假設拆解 LLM 在 FC-MH 失敗的根因，每個對應一個 design 方向。
> 詳細證據、confound、嚴謹度審計見 [fc_mh_hypotheses.md](fc_mh_hypotheses.md)。

### 2.1 假設總覽

| # | 假設 | Claim | 可信度 | 設計方向 |
|:---:|---|---|:---:|---|
| H1 | **Candidate Visibility** | LLM 無法可靠列舉 retrieval 中的候選事實 | 🟢 STRONG | Inline marker（強制候選並列在 prompt 文字層） |
| H2 | **Signal Comprehension** | 隱式 signal（serial / date_range）被 LLM 不一致理解 | 🟡 MODERATE-STRONG | Explicit signal label per fact |
| H3 | **World-Knowledge Override** | 看到候選後，世界知識仍可能壓過「use newer」規則 | 🟡 MODERATE | 強指令 MUST NOT use OUTDATED |
| H4 | **Multiplicative Compounding** | per-hop 弱點透過鏈乘法放大 | 🟢 描述性 / 🟡 因果 | Per-hop 100% 覆蓋 |
| H5 | **Chain Mis-anchor / Bail-out** | hop N+1 找不到下游時退回 hop N 舊鏈 | 🔴 WEAK | Chain-aware 約束（備用） |

### 2.2 三條關鍵 evidence

- **H1 STRONG**：inline marker 把 LLM-side GT recall 從 plain 62.7% → RPT 98.3%（+36 pp on n=59 has_pair hops, gemini-FL）
- **H2/H3 confound 警告**：PAT → RPT-min 的 +24 pp 同時改變 visibility (H1) 與 explicitness (H2)，沒做 clean ablation；RPT vs RPT-min 的 +8 pp 可能是 override，也可能是 LLM 自我過濾不列 OUTDATED（RPT Both-listed 67.8% < RPT-min 83.1%）
- **H4 描述性 STRONG**：1c→2c→3c→4c plain hippo EM = 30%/2%/0%/0% (gpt)、39%/23%/6%/0% (zep)；多跳乘法模型 0.6^N 與觀察吻合

### 2.3 假設與 SESSION 修正後 evidence 的對應

| 假設 | RPT ladder evidence | SESSION oracle evidence（更強） |
|---|---|---|
| H1 | RPT-min 60% (inline marker) − plain 22% = +38 pp | OA2 fact-level filter 直接從 retrieval 移除舊事實 → 23 → 55% (orig) / 83% (modified)，**不依賴 LLM 識別 marker** |
| H2 | PAT 36% → RPT-min 60% = +24 pp 從 explicit marker | 同上（filter 路線完全跳過 signal 問題） |
| H3 | RPT-min → RPT = +8 pp 從 MUST | **強化** — Sim-OB 98% vs RPT 68% 顯示 ~32% 機率即使看到 `[OUTDATED]` + `DO NOT USE` 仍採信舊事實，trust gap 是 hard ceiling |
| H4 | SH 68.5% / MH 8.5% gap | Sim-OB-grad noise gradient（PPR-nearby k=100 處從 90% 突崩到 61%）量化 noise tolerance 曲線 |
| H5 | q6 case + 1/30 expanded | 證據未強化，不列 main hypothesis |

### 2.4 設計方向 ≠ 假設證實

| 假設 | 可作為設計起點 | 因果機制已被驗證 |
|---|:---:|:---:|
| H1 Candidate Visibility | ✅ | ✅ STRONG |
| H2 Signal Comprehension | ✅ | 🟡 與 H1 confound |
| H3 World-Knowledge Override | ✅ 可試 | 🟡 機制不確定（override vs enumeration filter） |
| H4 Multiplicative Compounding | ✅ | 🟢 描述性 / 🟡 因果 |
| H5 Chain Mis-anchor | ⚠️ 備用 | 🔴 WEAK |

---

## 3. 9 個 Oracle 診斷實驗

> 完整方法論：[diagnostic_methodology.md](diagnostic_methodology.md)
> 完整數據：[diagnostic_findings.md](diagnostic_findings.md)
> 原始 JSON：`analysis/results/diagnostic/`

### 3.1 實驗清單

| # | 實驗 | 操作 | FC-MH 結果 | 角色 |
|---|---|---|:---:|---|
| 0 | Parse 既有 baseline Thought | 從 baseline output 抽 per-hop trace | 失敗 | 排除零成本選項 |
| **A1** | Modified-prompt baseline | system prompt 加 `Intermediate answers: [...]` + one-shot 重跑 100 | **23.0%** | 重建 fair-compare baseline |
| **A2** | Per-hop diagnosis | 從 A1 抽 per-hop 預測對齊 MQuAKE per-hop GT | 91% 首錯在 conflict hop / 71% older_fact / 69% 在 hop 0 | 失敗 hop 屬性歸因 |
| **B** | Hop-by-hop ablation | 每 hop 當 standalone FC-SH | per-hop **94.5%**, all-pass **87%** | Single-hop ceiling + chain 干擾 |
| **Sim-OB** | Chain-only context | context = 僅 chain 的 N 個 current facts | **98.0%** | 純 chain reasoning ceiling |
| **Sim-OB-grad** | Noise gradient | chain + k ∈ {10, 50, 100, 200, 455} distractors × {random, ppr-nearby} | PPR-nearby k=100 處從 90% 突崩到 61% | Noise tolerance 曲線 |
| **C** | 移除非 chain old facts | 6k 全集移除其他題目的 old facts | **42.0%** | Query-irrelevant conflict 是否有害 |
| **OA2** | Oracle A v2 (fact-level filter) | passage 內 surgical 移除 `{old_seq}. <fact>` 那一行 | **83.0%** (modified) / **55%** (orig prompt) | full-100 perfect-filter ceiling |
| **PAT modified** | PAT + intermediate trailer | soft `[CURRENT/OUTDATED FACT]` 標籤 + trailer | 48% | Annotation route + trailer cell |

### 3.2 完整 Floor → Ceiling 拆解（full 100 同 denominator）

| 階段 | EM | Δ | 機制 |
|---|:---:|:---:|---|
| A1 baseline | 23% | — | top-10 retrieved + 6k noisy |
| C（移除非 chain olds） | 42% | **+19 pp** | query-irrelevant conflicts |
| **OA2（移除 chain olds + modified prompt）** | **83%** | **+41 pp** | **query-relevant conflicts ← 最大頭** |
| Sim-OB（零噪音零衝突） | 98% | +15 pp | retrieval 雜訊 / entity confusion |

**邊際收益遞減（inference-time prompt engineering）**：

| 投入 | 方法 | EM | 邊際 Δ |
|---|---|:---:|:---:|
| 0 | A1 vanilla | 23% | — |
| 軟標籤 | PAT (`[CURRENT/OUTDATED]`) | 36% | +13 |
| 結構區分 | RPT-min (inline section labels) | 60% | +24 |
| 完整重組 | RPT (Section A/B + MUST "DO NOT USE B") | 68% | +8 |
| **不留 old** | **OA2 (filter)** | **83%** | **+15** |

→ inference-time prompt engineering 在 RPT 處邊際收益已 saturate；最後 +15 pp 無法靠 prompt 取得 → 只能把「conflict 解析責任」從 LLM 移走（move detection upstream）。

### 3.3 重跑指南

```bash
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# Resume-safe；自動跳過已完成 query
conda run -n hipporag_env python analysis/oracle_a_fact_level.py
conda run -n hipporag_env python analysis/sim_ob_chain_only.py

# Task B 需 HippoRAG retrieval
HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface \
  conda run -n hipporag_env python analysis/b_hop_by_hop_ablation.py

# 統合 summary
python analysis/diagnostic_summary.py
```

---

## 4. Channel Design Space — 核心貢獻

### 4.1 兩個正交維度

| 維度 | 含義 | 失敗會出現在 |
|---|---|---|
| **(A) Detection accuracy** | 寫入 / 檢索時辨識「哪個 fact 是 CURRENT、哪個是 OUTDATED」的準確度 | 如果 detection 錯，後續 inference 拿到錯誤訊號；Zep SH 14 個 misfired counterfactual 是案例 |
| **(B) Info-packaging strategy** | detection 結果怎麼傳遞給 inference LLM | 如果訊號形式 LLM 不採信（Zep date_range 0% 識別），detection 再準也沒用 |

兩個維度都做到極致才能達到 ceiling；單做一邊有 cap。

### 4.2 Channel spectrum（production methods + oracles 對照）

| Channel 類型 | 真實系統範例 | 我們的 oracle 對應 | FC-MH EM (gemini) |
|---|---|---|:---:|
| 零 detection | （無記憶系統） | A1 baseline modified | **23%** ← Floor |
| **強 filter**（delete 舊知識） | **Mem0** OOB（被 prompt-rejected） | OA2 fact-level（原 prompt） | **55%** ← Layer 1 universal |
| 強 filter + reasoning trailer | （Mem0 + COT prompt） | OA2 + intermediate trailer | **83%** ← Layer 2 QA-only |
| **soft annotation**（timestamp/label） | **Zep** | PAT (`[CURRENT/OUTDATED FACT]`) | **36–48%** |
| 結構 annotation + 強指令 | （production 少見） | RPT-min（inline section labels） | **60%** |
| 結構重組 + DO NOT USE 強指令 | （FC-overfit, 不可部署） | RPT（Section A/B partition） | **68%** ← in-context FC-aware oracle |
| 完美 chain context（理論上限） | **不存在** | Sim-OB chain-only | **98%** ← Absolute ceiling |

**兩條 trade-off dimension**：
- **資訊強度**：filter > strong annotation > soft annotation > 無 → 上限越高
- **Reversibility**：annotation > filter → filter 不可逆，對 historical / counterfactual queries 失效

**Channel-orthogonal 乘數：Reasoning scaffold prompt（intermediate trailer）**
- filter + trailer：**+28 pp synergy**（55 → 83%）
- annotation + trailer：**+12 pp synergy**（36 → 48%）
- baseline + trailer：**+3 pp**（20 → 23%）
- → trailer 的 effect 隨 context cleanliness monotonically scale，**只在 context 足夠乾淨時 unlock chain reasoning 能力**

### 4.3 Production system 在 spectrum 上的位置

| 方法 | (A) Detection 設計 | (B) Info-packaging | FC-MH EM | 主要限制 |
|---|---|---|:---:|---|
| **HippoRAG-v2** | ❌ 無顯式 detection，LLM 自推 | passages with seq numbers + FC 序號規則 prompt | 11% (gpt) / 22% (gemini, orig) | LLM 自推訊號失敗（H1+H2） |
| **Zep** | LLM extractor entity-edge supersession，標 `invalid_at` | edges 帶 `(valid_at - invalid_at)` + nodes summary "conflicts with" + episodes 原文 | 25% (gpt；gemini 待補) | detection ~50% per-hop 觸發；date range LLM 0% 識別；trust gap |
| **Mem0**（OOB） | LLM ADD/UPDATE/DELETE 真刪除舊 fact | retrieved memories（已過濾） | 1% (FC OOB) | `FACT_RETRIEVAL_PROMPT` 只抽 personal，FC 知識被拒；customize 後可能改善 |
| **RPT/RPT-min**（oracle） | 用 MQuAKE GT（perfect detection assumed） | `[CURRENT/OUTDATED FACT]` inline + section A/B + MUST | 68% / 60% (gemini) | **FC-overfit，不可部署**；真實場景無 perfect detection |
| **OA2**（oracle） | 用 MQuAKE GT（perfect detection assumed） | retrieval-time fact-level 移除舊 fact，**不改 prompt** | 55% (orig) / 83% (modified) | **Layer 1 universal**：不依賴 prompt，可放進多任務 system |

**觀察**：
- Zep 走 soft annotation channel（B 維度的 strategy B2，對應 PAT 上限 36–48%）
- Mem0 走 strong filter channel（B 維度的 strategy B1，對應 OA2 上限 55–83%）
- RPT 走 structured annotation channel（B 維度的 strategy B3-4，FC-overfit 不可部署）
- **OA2 oracle 對應的「strong filter without prompt change」是 production 推薦最強路線**（Layer 1 universal）

---

## 5. Deployability 分層 + 二軸 framing

### 5.1 Method deployability — 4 層

MemoryAgentBench 涵蓋 4 類任務，一個 production memory 系統需要服務全部，因此 prompt 改動必須分層判斷：

| Method | Layer | 部署性 | 對其他任務的影響 |
|---|:---:|:---:|---|
| A1 vanilla（原 HippoRAG prompt） | 1 | ✓ Universal | 跟原 HippoRAG 完全一樣 |
| **OA2 fact-level filter**（不改 prompt） | 1 | ✓ Universal | retrieval-time intervention，對所有任務 transparent |
| A1 / OA2 / PAT + intermediate trailer | 2 | △ QA-only | 對 entity-answer QA 有益，但對 summarization 強迫 `[bullet1, bullet2]` 破壞 long-form，對 Recsys/ICL 不適用 |
| PAT（soft labels only） | 3 | △ Conflict-only graceful | label 是 conditional，沒衝突時退化為 vanilla |
| RPT-min | 4 | ✗ FC-overfit | 強制 `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]`，non-FC 任務 prompt 會誤導 |
| RPT | 4 | ✗ 重度 FC-overfit | `== SECTION A: USE THESE ==` 結構重組，不可部署 |

### 5.2 二軸 framing（FC-agnostic only）

**軸 1：Conflict handling 策略**

| 同 prompt 條件 | A1 | PAT | OA2 | Filter Δ vs PAT |
|---|:---:|:---:|:---:|:---:|
| 原 prompt FC-MH | 20% | 36% | **55%** | **+19 pp** |
| modified prompt FC-MH | 23% | 48% | **83%** | **+35 pp** |
| 原 prompt FC-SH | 77% | ~96% | **98%** | +2 pp |
| modified prompt FC-SH | 96% | 97% | **98%** | +1 pp |

→ **filter > soft annotation 在所有 prompt 條件下都成立**。

**軸 2：Reasoning scaffold prompt（intermediate trailer）**

| Method | 原 prompt MH | + trailer MH | Δ |
|---|:---:|:---:|:---:|
| A1（very noisy） | 20% | 23% | +3 pp |
| PAT（mid-noisy, labeled） | 36% | **48%** | **+12 pp** |
| OA2（clean context） | 55% | **83%** | **+28 pp** |

→ trailer effect 隨 context cleanliness monotonically scale。原因驗證：OA2 原 prompt 失敗分析顯示 45 個錯題中過半 Thought 是 0 字，trailer 強迫 chain decomposition。

**兩軸可疊加**：23% → 83%（filter + trailer），差距 60 pp 拆解：
- 純 filter（OA2 vs A1，同原 prompt）：+35 pp
- 純 trailer（A1 modified vs orig）：+3 pp
- 兩者 interaction：+22 pp
- → trailer 與 filter 有 **synergy**，不是純疊加

### 5.3 修正後 paper 主張的 5 個結論

1. **Universal recommendation = OA2 vanilla**（Layer 1）→ 給 +35 pp on FC-MH 不影響其他任務
2. **QA-task add-on（trailer）gives extra +28 pp on filter** but is **NOT universally deployable** — paper 要明確 scope 為 QA-style tasks
3. **Filter > soft annotation (PAT)** 在所有 prompt 條件下都成立 → +19 ~ +35 pp on MH
4. **RPT (68%) 不是 method recommendation**，是 in-context FC-aware oracle 的 reference ceiling
5. **Reasoning scaffold prompt (trailer) 對 context cleanliness monotonic** → 純 reasoning prompt 工程的邊際收益取決於 conflict / noise 處理是否到位

---

## 6. (B) Info-packaging 設計選擇空間

假設 (A) 已經有某個 detection 機制，detection 結果有四種傳給 inference 的方式：

### B1 — Filter at retrieval（Mem0 / OA2 路線）
```
detect → 標 OUTDATED → 從 retrieval 過濾掉 → LLM 只看 CURRENT
```
| 優點 | 缺點 |
|---|---|
| LLM 不可能誤用 OUTDATED（根本沒看到） | 完全依賴 detection 準確度，detection 錯 = 答案錯 |
| Inference prompt 不需特殊設計，可保留 HippoRAG-v2 通用性 | 失去「兩版本都看見讓 LLM 自己判斷」的容錯彈性 |
| 對 (B) 維度的 H1/H2/H3 完全規避 | detection misfire 災難放大（SH counterfactual 14 案例） |

### B2 — Show all + temporal signal（Zep 路線）
```
detect → 雙版本都保留，加時間訊號 → LLM 看到全部、自行用訊號選
```
| 優點 | 缺點 |
|---|---|
| Detection 即使部分錯，LLM 仍可能從 raw context 自救 | LLM 對隱式 signal 識別率低（date 0%、序號 33-46%） |
| 保留 historical context，適合「這 entity 的歷史 X」類問題 | 訊號太多反而困惑 LLM |
| 沒丟訊息，後續 method 可改進 | 即使 detection 100%，LLM-side 仍受 H1/H2/H3 拖累 |

### B3 — Show all + explicit marker + soft instruction（中庸路線）
```
detect → 雙版本都保留，但用顯式 marker（類 RPT）+ 適度而非 overfit 的指令
```
| 優點 | 缺點 |
|---|---|
| 結合 B1「LLM 不必 infer signal」+ B2「保留全部資訊」 | marker 太強 → overfit；太弱 → LLM 仍用世界知識 |
| 可比 RPT 設計得更通用，不依賴「序號越大越新」這個假設 | 需要 dataset 標 CURRENT vs OUTDATED 的訊號形式適用各任務 |

> **觀察**：RPT 的 +8pp from MUST 一部分可能來自 LLM 自我過濾不列 OUTDATED（Both-listed 67.8% < RPT-min 83.1%）—— 這意味「marker + 弱指令」也可能達到接近 RPT 的效果，且 generalization 更好。

### B4 — 混合：filter for sure cases + show-with-marker for uncertain
```
detect → 信心高的 OUTDATED 直接 filter；信心低的雙版本 + marker
```
兩個世界的 best：detection 高信心時走 B1（filter，效率最高）；低信心時走 B3（保留資訊讓 LLM 判斷）。需要 detection 機制提供 confidence score。

---

## 7. (A) Detection accuracy 設計選擇空間

> ⚠️ **2026-04-29 update**：D1–D5 是 generic detection 機制清單，不是 multi-hop-specific 設計。真正能 fill「過去沒人做多跳衝突機制」gap 的方法設計（M1–M5：versioned KG + chain-aware retrieval + per-hop subgraph context）整理在 [method_design_brainstorm.md](method_design_brainstorm.md)。本節保留作為 D1–D5 generic 偵測選項的清單。

從 HippoRAG-v2 出發加 detection 層的可選方向：

| 方向 | 描述 | 偵測什麼觸發衝突 | 預期準確度 | 主要限制 |
|---|---|---|:---:|---|
| **D1** Structural at ingestion | KG 抽 triple 時，同 (s, r) 多 object 即觸發衝突，以 ingest order 為 currency proxy（類 Zep） | 純 structural，無需 LLM | 中（FC 上 100%，其他 dataset 不一定） | FC artifact: ingest order = recency，在 LongMemEval 等真實 conversational data 上會失效 |
| D2 Embedding-based at retrieval | retrieve 時對 top-k chunk 做 (s, r) 相似性匹配 | retrieval-time，不依賴 ingest order | 中-低 | 仍需 currency signal |
| D3 LLM-as-detector at ingestion | ingestion 時 LLM 判斷新 fact 是否 supersede 既有（類 Mem0 ADD/UPDATE/DELETE） | LLM-driven，可加 confidence | 中-高 | 每次 ingest 都呼叫 LLM 成本高；對 counterfactual 仍可能誤判 |
| D4 LLM-as-detector at retrieval | retrieval 完成、inference 之前，中介 LLM 看 top-k 並標 CURRENT/OUTDATED | inference-time，完全 LLM-driven | 中-高 | 增加 inference latency；同 backbone 時可能繼承 bias |
| D5 Structural + LLM 混合 | structural 找候選 + LLM 確認 + 標 confidence | 兩階段，平衡速度與準確度 | 高 | 最複雜；但分階段較好 debug |

→ **從 D1 開始最便宜**：用 ingest order 做 supersession，對 FC 100% 準；但對真實 conversational data 會失效，要看 Phase 2 的 robustness 曲線決定值不值得做下去。

---

## 8. 重要 Caveats

### 8.1 全部 oracle 都用 MQuAKE GT 作為「perfect detection」
OA2 / C / Sim-OB 假設我們完美知道哪些是 old / new / chain-relevant；實務 detection 不會完美。**下一步必做的 ablation**：對 OA2 加人為 noise（隨機保留 r% 的 chain old，r ∈ {1.0, 0.8, 0.6, 0.4, 0.2, 0.0}），跑同樣的 PAT 對照看曲線交叉點 → Phase 2 核心。

### 8.2 OA1 → OA2 的 24 pp 提升是「演算法 fix」而非「filter 本質改進」
- v1 (passage-level): 63.6% on subset 66
- v2 (fact-level): 87.9% on same subset 66 / 83.0% on full 100
- 拆解：3 pp 來自 v1 cross-hop subset filter bug，21 pp 來自 passage 粒度太粗連帶丟 supporting facts
- **Implication**：chunk_size=512 下 passage-level filter 幾乎不可能避免 supporting context 損失，fact-level surgical excision 是必要的

### 8.3 Prompt rigor — 早期 framing 的關鍵失誤（很重要）
- **(a) Modified prompt 的影響被低估**：OA2 用 modified prompt 跑出 83% 但用原 prompt 只有 55%，純 prompt 變更 = +28 pp on MH
- **(b) RPT/RPT-min 是 FC-task-overfit 不該當 production baseline**：強制 `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]` 結構，記憶系統需服務多種任務類型，這類 prompt 不能部署

修正方法：
1. 限定到 FC-agnostic 方法（A1, PAT, OA2）才能稱「production 推薦」
2. 同 prompt 條件對齊比較
3. 不要用「filter > annotation」這種粗略表述，應分二軸並標明 prompt 條件

### 8.4 Sim-OB-grad 的 PPR-nearby 噪音突崩點 (k=50→100) 跟 chunk_size 強相關
chunk_size=512 → 一個 chunk ~25 facts → top-10 retrieval ≈ 250 facts。當 k=100 時 distractor 數量已大於正常 retrieval 規模，突崩可能反映 LLM context window 內某種「fact 數量閾值」，應在不同 chunk_size 重複驗證。

### 8.5 LLM 行為觀察的 confound
| 條件 | 觀察的是什麼 | 不是什麼 |
|---|---|---|
| (C) 純原 inference | 原 EM byte-equal；自發 Thought 中的推理線索 | LLM 內部完整推理；Zep prompt 抑制 Thought 後完全看不到 |
| (A) trace-first | 結構化推理痕跡可量化（candidate-recall, signal-cited） | **(A) 行為 ≠ (C) 自然 inference 行為**——強制結構可能改變 attention（HippoRAG (A) EM 從 6.7% 跌到 0% 是證據） |
| (B) post-hoc explain | 保留原 EM 同時得結構化解釋 | **rationalization 風險**——q5 (B) 列出 GT 但 (A) 沒列；可能事後合理化 |

→ H1 LLM-side candidate-recall 是用 (A) 觀察的，**這是 upper bound**；真實 (C) inference 的 candidate visibility 可能更低。

### 8.6 其他
- 30 題 sample 不足以做穩健統計推論（95% CI 寬）
- gpt-4o-mini 在 temp=0 仍有 nondeterminism（q6 兩次 run 不同行為）
- Zep 因為內部 LLM 不可換，backbone-swap 實驗只能對 final inference 做

---

## 9. 下一階段優先順序（Phase 1–5）

### Phase 1 ★（最高優先）— Production system baselines on channel spectrum
把 Zep / Mem0 放上已建立的 oracle channel benchmark，讓它們成為真實系統 baseline。現有 GPT-4o-mini 結果不能跟我們的 Gemini oracles fair compare，必須補 Gemini 版本。

| # | 待做 | 為何重要 |
|---|---|---|
| 1.1 | **重跑 Zep + Mem0 用 Gemini 3.1 Flash-Lite** | LLM 一致才能跟 9 個 Gemini oracles fair compare |
| 1.2 | Zep edge invalidation precision/recall vs MQuAKE GT（MH + Gemini） | 量化 Zep detection 精度；[zep_mechanism_deep_dive.md](results/oracle_a/zep_mechanism_deep_dive.md) 已部分做過（SH:correct 7 / wrong 14 / none 52） |
| 1.3 | **Mem0 customization**（改 `custom_fact_extraction_prompt`） | 直接測 Strategy B1 (filter at write) 在 FC 上的真實表現 |
| 1.4 | 實際送進 LLM 的 inference prompt 結構盤點 | 對照我們的 PAT/RPT，量化「資訊密度」 |
| 1.5 | End-to-end gap analysis | Zep/Mem0 E2E EM vs oracle channel ceiling = detection 改進的潛力空間 |

### Phase 2 — Imperfect-detection robustness（從 oracle 推到 production claim 的橋樑）
- 對 OA2 加 imperfect detection 模擬：隨機保留 r% 的 chain old facts，r ∈ {1.0, 0.8, 0.6, 0.4, 0.2, 0.0}
- 對應 PAT 同曲線比較
- 找 OA2-filter 與 PAT-annotation 的 crossover point — 也就是 detection 多準時 filter 開始輸給 annotation
- **這是 paper 從「oracle ceiling」推到「production claim」的關鍵實驗**

### Phase 3 — Hybrid channel design
- **OA2 + PAT graceful labels 同時用**：retrieval-time filter 移除高信心舊事實，inference-time annotation 標記低信心 / 衝突未解的剩餘 facts
- 上限應介於 OA2(83%) 與 Sim-OB(98%) 之間
- 同時保留 Zep-style reversibility（historical queries 可從 graceful label 推回原版本）
- **最實用的 production design 候選**

### Phase 4 — 從 HippoRAG-v2 加 detection layer（method 設計）
按 §7 的 D1–D5 五個方向設計 real detection algorithm，對應 Phase 2 找到的 robustness 曲線位置：

| 方向 | 對應 oracle 上限 |
|---|:---:|
| D1 Structural at ingestion | OA2 filter 路線 |
| D2 Embedding-based at retrieval | filter 路線 |
| D3 LLM-as-detector at ingestion | 類 Mem0，可加 confidence |
| D4 LLM-as-detector at retrieval | inference-time |
| D5 Structural + LLM 混合 | 兩階段，適合 Phase 3 hybrid |

從 D1 開始最便宜；對 FC 100% 準但對真實 conversational data 會失效，要看 Phase 2 的 robustness 曲線決定。

### Phase 5 — Generalization
| # | 待做 |
|---|---|
| 5.1 | 擴展到 32k / 64k / 262k 對話歷史（目前全在 6k） |
| 5.2 | chunk_size=4096 重做（本 session 全用 chunk=512；Sim-OB-grad 噪音閾值與 fact-level vs passage-level 差距可能改變） |
| 5.3 | 換 LLM（GPT-4o-mini / Claude / 更大 LLM）看結論可推廣性 |
| 5.4 | 驗證 trailer 對 non-QA 任務（InfBench_sum）的負面影響 — 強化 paper Layer 2 scoping argument |

---

## 10. 開放問題

1. **Mem0 customize 後是否能解 FC？** Detection misfire 比例如何？（Phase 1.3）
2. **Strategy B1 (filter) vs B2 (annotation) 在 imperfect detection 下的 crossover 點在哪？**（Phase 2）
3. **D1 ingest-order proxy 在非 FC 任務上會崩到什麼程度？** 需要 LongMemEval 或類似真實 temporal data 驗證（Phase 4-5）
4. **「per-hop 100% 覆蓋」在 detection 不完美時要怎麼辦？** 部分覆蓋是否仍能 close 大部分 EM gap？（Phase 2 ablation）
5. **Counterfactual robustness 是 detection 維度還是 inference 維度的問題？** RPT vs OA2 在 SH 14 案例上的對比能回答（Phase 1.2 + Phase 2）
6. **Hybrid filter + annotation（Phase 3）的實際 EM 是介於 83% 與 98% 之間，還是會因 design conflict 反而變差？**

---

## 11. 檔案索引與重跑指南

### 主要 docs（本檔之外）

| 檔案 | 內容 | 何時看 |
|---|---|---|
| [SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md) | session 完整敘事 + 9 個 oracle 細節 | 想看完整實驗故事與 prompt rigor 修正過程 |
| [fc_mh_hypotheses.md](fc_mh_hypotheses.md) | H1–H5 working hypotheses + 嚴謹度審計 | 想看每個假設的證據強度、confound、設計方向 |
| [next_phase_design_space.md](next_phase_design_space.md) | 下一階段 design space 地圖 | 想看 (A)×(B) 維度與 D1–D5 detection 方向的細節 |
| [diagnostic_methodology.md](diagnostic_methodology.md) | 7 個實驗的方法論（modified prompt 部分） | 想重跑或檢查實驗設定 |
| [diagnostic_findings.md](diagnostic_findings.md) | 完整數據 + paper-framing（含 prompt rigor 修正） | 想看 raw 數字、per-question 失敗分析 |

### 之前的相關 docs

| 檔案 | 內容 |
|---|---|
| [session_context.md](session_context.md) | 2026-04-16 之前的研究脈絡（FC-SH/FC-MH 失敗根因 Step 1A） |
| [step1a_methodology.md](step1a_methodology.md) | 衝突跳數 vs Acc 方法論 |
| [step1a_sh_summary.md](step1a_sh_summary.md) | FC-SH 結果摘要 + Oracle 預期 |
| [prompts_comparison.md](prompts_comparison.md) | vanilla / OA / PAT / RPT / RPT-min prompt 對照 |
| [results/oracle_a/oracle_a_report.md](results/oracle_a/oracle_a_report.md) | Oracle A v1 GPT-4o-mini 完整報告 |
| [results/oracle_a/zep_mechanism_deep_dive.md](results/oracle_a/zep_mechanism_deep_dive.md) | Zep edge invalidation 機制分析 |

### 實驗腳本與原始 JSON

| 檔案 | 用途 |
|---|---|
| `analysis/a1_modified_prompt_baseline.py` 等 7 支 .py | 可重跑腳本（modified prompt 系列） |
| `analysis/oracle_a_fact_level_origprompt.py` | OA2 + 原 HippoRAG prompt（fair compare 用） |
| `analysis/pat_modified_prompt.py` | PAT + intermediate trailer（missing cell 補完） |
| `analysis/oa2_thought_error_analysis.py` | OA2 原 prompt 剩餘錯誤的 Thought 分析 |
| `analysis/diagnostic_summary.py` | 統合 summary 產生器 |
| `results/diagnostic/*.json` | Raw outputs（per-question） |
| `results/diagnostic/diagnostic_summary.txt` | 自動生成的對比表 |
| `results/diagnostic/oa2_remaining_errors_analysis.{json,txt}` | OA2 原 prompt 剩餘錯誤分類 |
| `results/mh_512_mquake_analysis.json` | FC-MH 100 題 per-hop GT/old/conflict_type 分析 |
| `results/sh_512_mquake_analysis.json` | FC-SH 同上 |
| `results/oracle_a_gemini/*.json` | OA1 / PAT / RPT / RPT-min 在 Gemini 上的 results |

### 重跑指南

```bash
cd /home/yhchiang/MemoryAgentBench

# 環境變數（Vertex AI）
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# 跑某個 oracle 實驗（resume-safe；會跳過已完成 query）
conda run -n hipporag_env python analysis/oracle_a_fact_level.py
conda run -n hipporag_env python analysis/sim_ob_chain_only.py

# Task B 需要 HippoRAG retrieval，加 HF_HOME
HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface \
  conda run -n hipporag_env python analysis/b_hop_by_hop_ablation.py

# 跑統合 summary
python analysis/diagnostic_summary.py
```

---

## 12. 給接手 Claude / 對接者的提示

讀完本檔後，你應該知道：

1. **9 個 oracle 實驗組成 detection-to-inference channel benchmark**：A1（Floor 23%）/ C / Sim-OB（98% absolute ceiling）/ Sim-OB-grad / OA2（83% modified, 55% orig）/ PAT modified / RPT-min / RPT / B
2. **早期 §4.1–4.4 framing 不夠嚴謹** — modified prompt（intermediate trailer）對 OA2 給了 +28 pp 隱性 boost；正確 framing 在 SESSION §4.5 與本檔 §5
3. **OA1 (63.6% subset) → OA2 (83% full, modified) 的差距是演算法 fix，不是 ceiling 改變**（§8.2）
4. **RPT/RPT-min 是 FC-task-overfit，不能算 production-recommendable method** — 它們的 prompt 強制 `[SECTION A: ACTIVE/SUPERSEDED]` 結構，對 non-FC 任務不可部署
5. **正確的 paper 主張是「二軸獨立 + filter > soft annotation」**（§5.2）
6. **下一步預設答案**：Phase 2 imperfect-detection robustness ablation — 把 OA2 加人為 noise 看 degradation 曲線，跟 PAT 同曲線比較

如果使用者問「下一步做什麼」：**預設答案是 Phase 1 Zep/Mem0 Gemini 重跑 + Phase 2 imperfect-detection robustness**。
如果使用者問「結果在哪」：**指向 [diagnostic_findings.md](diagnostic_findings.md)**（含 prompt rigor 修正）；如果問「方法」：**指向 [diagnostic_methodology.md](diagnostic_methodology.md)**。

**警告 — 不要重複的常見錯誤**：
- 不要把不同 prompt 條件的數字直接比較（e.g. OA2-modified 83% vs RPT-orig 68%）— 這是 apples-to-oranges
- 不要把 RPT 當 production baseline — 它 FC-overfit，真實場景不可部署
- 不要重跑已完成實驗（resume-safe，直接讀 `results/diagnostic/*.json`）
- 不要刪 partial output 檔（resume 機制依賴它）

---

*整合日期：2026-04-29*
*來源：SESSION_2026-04-28_diagnostic_summary.md（2026-04-28）+ fc_mh_hypotheses.md（2026-04-28，2026-04-29 修正）+ next_phase_design_space.md（2026-04-28，2026-04-29 修正）*
*總 inference call 約：2750 次（A1 200 + B 254 + Sim-OB 100 + Sim-OB-grad 1000 + C 100 + OA2 modified 200 + OA2 origprompt 200 + PAT modified 200 + Thought analysis 0）*
