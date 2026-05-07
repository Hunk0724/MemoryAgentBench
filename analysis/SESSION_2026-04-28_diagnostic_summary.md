# FC-MH Multi-hop Diagnostic Session — 完整紀錄與三大發現

> Session 日期: 2026-04-28
> 對話者: 使用者 + Claude (Opus 4.7 1M context)
> 目的: 為另一個 Claude Code instance / 未來繼續者提供完整 context,可獨立讀懂並接續工作
> 產出 doc: `analysis/diagnostic_methodology.md` (方法論) + `analysis/diagnostic_findings.md` (數字結果) + 本檔 (敘事與框架)

---

## ★ Session 真正的 Contribution (用這個 framing 跟人說)

**我們做的 9 個 oracle 實驗實際上是在量化 「detection 結果 → inference 端」的不同 information channel 各自能達到多高的上限。**

每個 method 對應一種「把 detection 資訊送給 LLM」的方式 (= channel):

| Channel 類型 | 真實系統範例 | 我們對應的 oracle 實驗 | FC-MH 上限 |
|---|---|---|:---:|
| 零 detection | (無記憶系統) | A1 baseline | 20% |
| **強 filter** (delete 舊知識) | **Mem0** | OA2 fact-level removal | 55% (原 prompt) |
| 強 filter + reasoning trailer | (Mem0 + COT prompt) | OA2 + intermediate trailer | 83% |
| **soft annotation** (timestamp/label) | **Zep** | PAT (`[CURRENT/OUTDATED FACT]`) | 36%~48% |
| 結構 annotation + 強指令 | (production 少見) | RPT (Section A/B partition) | 68% |
| 完美 chain context (理論上限) | 不存在 | Sim-OB (chain-only) | 98% |

**Trade-off 兩條 dimension**:
- **資訊強度 (filter > strong annotation > soft annotation > 無)** → 上限越高
- **Reversibility (annotation > filter)** → filter 不可逆, 對 historical / counterfactual queries 失效

**Channel-orthogonal 乘數: Reasoning scaffold prompt (intermediate trailer)**
- filter + trailer: +28 pp synergy
- annotation + trailer: +12 pp synergy
- baseline + trailer: +3 pp
- (但 scope 限於 QA-style tasks)

**研究價值**: 這個 session 不是「找到了一個好方法」, 而是**建立了 detection-to-inference channel 設計空間的 oracle benchmark**。任何未來實作 conflict detection algorithm 都可以對照這個 benchmark 看自己的 channel 設計距離 oracle 上限多遠。同時 Zep / Mem0 等 production 系統可以被 plot 在這個 spectrum 上做位置定位。

詳細結果見 §4.5。

## 0. 快速理解 (Read this first)

**這個 session 在做什麼**: 用 oracle (perfect conflict detection) 把 FC-MH 任務的上下限釘出來,量化「inference-time intervention 上限」 vs 「retrieval-time filter 上限」, 為下一步研究方向 (paper framing) 提供量化證據。

> ⚠️ **CRITICAL UPDATE (2026-04-28 後段)**: 原本 §4 的 framing 假設了 modified prompt (`Intermediate answers: [...]` trailer 要求) 對所有方法影響相同,但實測 OA2 用原 HippoRAG prompt 跑出來 **MH 只有 55%, 不是 83%** — 28 pp 差距完全來自 prompt 變更。同時 **RPT/RPT-min 實質是 FC-task-overfit prompt** (有 `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]` 等 FC-specific 結構), 對非 FC 任務不可部署。**修正後的 framing 在 §4.5**, 詳細 prompt rigor caveat 在 §5.5。

**Bottom line (再修正後 — 分 deployability layer)**:

MemoryAgentBench 涵蓋 4 類任務 (FC, Accurate_Retrieval, Long_Range_Understanding 含 summarization, Test_Time_Learning), 一個 production memory 系統需要服務全部, 因此 prompt 改動的部署性要分層:

| Layer | 方法 | FC-MH | 適用範圍 |
|---|---|:---:|---|
| **Layer 1 (Universal)** | OA2 retrieval-time filter (不改 prompt) | **55%** | 所有 4 類 memory task |
| Layer 2 (QA add-on) | + intermediate trailer | 83% | QA-style tasks 才能加 (排除 summarization/Recsys) |
| Layer 3 (Conflict add-on) | + PAT soft labels (graceful) | (未組合測) | conflict tasks 才有效 |
| (Reference ceiling, 不可部署) | RPT FC-overfit | 68% | 僅作 in-context FC-aware oracle 上限 |

- Universal claim (寫進 paper 為通用方法): **OA2 alone 給 +35 pp on FC-MH** without 任何 prompt overhead, 對其他任務 transparent
- QA-task claim: + trailer 額外 +28 pp, 但要 task routing 才能用 (不能放 universal default)
- Filter > Soft annotation (PAT) 在所有 prompt 條件成立 (+19~+35 pp)
- LLM 純 multi-hop reasoning 不是瓶頸 (Sim-OB 98%)

---

## 1. 背景 Context (給沒看過前情的 reader)

### 1.1 專案與資料集
- **專案**: [MemoryAgentBench](../README.md) — 評估 memory-augmented agents 的 benchmark
- **本 session 焦點任務**: `Conflict_Resolution / FactConsolidation`
  - **FC-SH** = single-hop, 100 題
  - **FC-MH** = multi-hop (2/3/4-hop), 100 題
  - 知識來源: MQuAKE-CF (`/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json`)
  - 知識庫格式: 6k tokens 中含 455 個 numbered facts, 每題的 chain 中某些 hop 同時存在「新事實 (GT)」與「舊事實 (old)」
  - LLM 的任務: 在 prompt 中已告知「序號越大越新越正確」的規則下,正確回答多跳問題

### 1.2 此 session 之前的 baseline
| 系統 | LLM | FC-SH | FC-MH |
|---|---|:---:|:---:|
| HippoRAG-v2 + chunk_size=512 | GPT-4o-mini | 69.0% | 11.0% |
| HippoRAG-v2 + chunk_size=512 | Gemini 3.1 Flash-Lite | 77.0% | 20.0% |

詳細分析見:
- [`session_context.md`](session_context.md) — 2026-04-16 之前的研究脈絡
- [`step1a_methodology.md`](step1a_methodology.md) — 衝突跳數 vs Acc 完整分析
- [`step1a_sh_summary.md`](step1a_sh_summary.md) — FC-SH 結果摘要

### 1.3 已嘗試的 inference-time intervention (在本 session 之前)
| 方法 | 描述 | FC-SH (subset 64) | FC-MH (subset 66) |
|---|---|:---:|:---:|
| Vanilla | 原 HippoRAG prompt | 67.2% | 27.3% |
| PAT | passage 內加 `[CURRENT FACT]` / `[OUTDATED FACT]` 標記 | 71.9% | 42.4% |
| Oracle A v1 (passage-level) | 移除含 chain old facts 的整個 passage | 96.9% | 63.6% |
| RPT-min | inline `[SECTION A/B]` 標籤 + fact annotation | (未取數) | 69.7% |
| RPT | 完整結構重組 + Section A/B 區分 + 強指令 | 100% | 80.3% |

完整 prompt 對照: [`prompts_comparison.md`](prompts_comparison.md)
詳細實驗報告: [`results/oracle_a/oracle_a_report.md`](results/oracle_a/oracle_a_report.md)
**注意**: subset = 排除「new/old 同 passage」等題目,僅 64/66 題可跑,**denominator 與 full 100 不同**。

### 1.4 環境設置
- HippoRAG-v2 (NV-Embed-v2 retrieval + KG + PPR rerank)
- Gemini 3.1 Flash-Lite preview (via Vertex AI, location=global)
- chunk_size=512, top-k=10, 6k context (455 facts)
- `conda env: hipporag_env` for HippoRAG retrieval, `MABench` for non-RAG agents
- Vertex API config: `GOOGLE_CLOUD_PROJECT=fc-mh-494213, LOCATION=global`

---

## 2. Session 研究問題

> Multi-hop KU 真正難在哪?
> baseline 23%, Sim-OB 98%, 中間的 75pp gap 由什麼貢獻? Conflict 解析失敗 vs Multi-hop chain accumulation error?

具體拆解問題:
1. failure 主要來自 conflict hop 還是 clean hop?
2. 把 hop 拆成 single-hop 跑, 是否本來就能解?
3. 純 multi-hop reasoning 在零噪音下表現如何?
4. 噪音與 conflict 各自的傷害量化?

---

## 3. Session 期間執行的所有實驗

完整方法論: [`diagnostic_methodology.md`](diagnostic_methodology.md)
完整數據: [`diagnostic_findings.md`](diagnostic_findings.md)
原始 JSON: `analysis/results/diagnostic/`

### 七 + 一個 oracle 實驗

| # | 實驗 | 操作 | FC-MH 結果 (n=100 unless noted) | 角色 |
|---|---|---|:---:|---|
| 0 | Parse 既有 baseline Thought | 嘗試從 baseline output 抽 per-hop trace | 失敗 (output 已被 split('Answer:') 截掉) | 排除零成本選項 |
| **A1** | Modified-prompt vanilla baseline | system prompt 加 `Intermediate answers: [...]` 要求 + one-shot 示範,重跑全 100 | **23.0%** | 重建 fair-compare baseline |
| **A2** | Per-hop diagnosis | 從 A1 抽 per-hop 預測對齊 MQuAKE per-hop GT | 91% 首錯在 conflict hop / 71% older_fact / 69% 在 hop 0 | 失敗 hop 屬性歸因 |
| **B** | Hop-by-hop ablation | 每 hop 當 standalone FC-SH (full HippoRAG retrieval + inference) | per-hop **94.5%**, all-pass **87%** | Single-hop ceiling + chain 干擾量化 |
| **Sim-OB** | Chain-only context | context = 僅 chain 的 N 個 current facts | **98.0%** | 純 chain reasoning ceiling |
| **Sim-OB-grad** | Noise gradient | chain + k ∈ {10, 50, 100, 200, 455} distractors × {random, ppr-nearby} | PPR-nearby k=100 處從 90% 突崩到 61% | Noise tolerance 曲線 |
| **C** | 移除非 chain old facts | 6k 全集移除其他題目的 old facts (僅留該題自己的 conflict pairs) | **42.0%** | Query-irrelevant conflict 是否有害 |
| **OA2** | **Oracle A v2 (fact-level filter)** | passage 內 surgical 移除 `{old_seq}. <fact>` 那一行,跑全 100 (vs OA1 v1 passage-level + subset) | **83.0%** (FC-SH 98.0%) | full-100 perfect-filter ceiling |

每個實驗的腳本:
- `analysis/a1_modified_prompt_baseline.py`
- `analysis/a2_per_hop_diagnosis.py`
- `analysis/b_hop_by_hop_ablation.py`
- `analysis/sim_ob_chain_only.py`
- `analysis/sim_ob_grad_noise.py`
- `analysis/c_no_distractor_conflicts.py`
- `analysis/oracle_a_fact_level.py`

統合 summary script: `analysis/diagnostic_summary.py` (跑此腳本 → 產 `results/diagnostic/diagnostic_summary.txt`)

---

## 4. 三大發現 (Session Conclusion)

> ⚠️ §4.1–4.4 是早期 framing,假設了 modified prompt 對所有方法影響相同。
> 修正後的 framing 在 §4.5 (基於 prompt rigor 後的 apples-to-apples 對比),
> 並考慮 method deployability (FC-agnostic vs FC-overfit)。
> Reader 若沒時間, 直接看 §4.5。


### 發現 1 — 釘出三條基準線: Floor / Ceiling / Target

| 條件 | EM | 角色 |
|---|:---:|---|
| A1 baseline (沒做 detection,top-10 retrieved + 6k 噪音) | **23%** | **Floor** |
| Sim-OB (chain-only,零噪音零衝突) | **98%** | **Absolute ceiling** (LLM 純能力上限) |
| OA2 fact-level filter (perfect detection + retrieval filter) | **83%** | **Practical target** (filter pipeline 上限) |
| RPT (perfect detection + inference annotation) | **68%** | Inference-only target |

**含意**:
- 75pp 的 floor → ceiling gap 中,**60 pp 靠 perfect conflict detection + filter 取得**
- 剩下 15 pp 是 retrieval 噪音 + entity confusion,跟 conflict 本身無關 (Sim-OB-grad 與 B 已分離出這部分)
- LLM 純 multi-hop reasoning **完全不是瓶頸** (98%)

完整拆解 (full 100 同 denominator):

| 階段 | EM | Δ | 機制 |
|---|:---:|:---:|---|
| A1 baseline | 23% | — | top-10 retrieved + 6k noisy |
| C (移除非 chain olds) | 42% | **+19 pp** | query-irrelevant conflicts |
| **OA2 (移除 chain olds)** | **83%** | **+41 pp** | **query-relevant conflicts ← 最大頭** |
| Sim-OB (零噪音零衝突) | 98% | +15 pp | retrieval 雜訊 / entity confusion |

### 發現 2 — Inference-time 工程的邊際收益遞減

| 投入 | 方法 | EM (full 100) | 邊際 Δ |
|---|---|:---:|:---:|
| 0 | A1 vanilla | 23% | — |
| 軟標籤 | PAT (`[CURRENT/OUTDATED]` label) | 36% | +13 |
| 結構區分 | RPT-min (inline section labels) | 60% | +24 |
| 完整重組 | RPT (Section A/B + 強指令 "DO NOT USE B") | 68% | +8 |
| **不留 old** | **OA2 (filter)** | **83%** | **+15** |

**含意**:
- inference-time prompt engineering 在 RPT 處邊際收益已 saturate
- 最後 +15 pp 無法靠 prompt 取得 → **只能靠把「conflict 解析責任」從 LLM 移走 (move detection upstream)**
- LLM 即使看到 `[OUTDATED FACT]` 標記與 `DO NOT USE Section B` 指令,仍有 ~32% 機率採信舊事實 — **trust gap 是 hard ceiling**

### 發現 3 — Paper 應主張的研究方向 (待 §4.5 修正)

| 投入方向 | 上限 (perfect detection) | 工程難度 | 推薦度 |
|---|:---:|:---:|:---:|
| Inference-time prompt 改進 | 68% (RPT) | 高 (RPT prompt 已很複雜) | ⚠️ 邊際遞減 |
| **Write/retrieval-time conflict detection + filter** | **83%** | 取決於 detection 演算法 | ✅ 上限最高 |
| 純 chain reasoning 改進 (e.g. CoT 加強) | ~0 pp 收益 | 不必要 | ❌ Sim-OB 已 98% |

**核心 reframe (early version, 待 §4.5 修正)**:
> 我們沒有真的「解決」FC-MH, 只是把問題從**「LLM 該怎麼 reason」重新 frame 成「retrieval-time / write-time 該怎麼做 conflict detection」**, 並用 oracle 證明這個 reframe 是值得的 (上限提升 +15~60 pp, 看比較對象)。

### 發現 4 (修正) — Method Deployability + 二軸 framing

#### 4.5.1 Deployability classification — 三層 (refined for multi-task memory system)

MemoryAgentBench 涵蓋 **4 類任務**: Conflict_Resolution (FC), Accurate_Retrieval (EventQA, LongMemEval, Ruler), Long_Range_Understanding (Detective_QA, InfBench_sum 含 summarization), Test_Time_Learning (Recsys, ICL)。一個 production memory 系統需要服務全部, 因此 prompt 改動的部署性要分層判斷:

| Method | Layer | 部署性 | 對其他任務類別的影響 |
|---|:---:|:---:|---|
| **A1 vanilla** (原 HippoRAG prompt) | 1 | ✓ Universal | 跟原 HippoRAG 完全一樣, 對所有任務無影響 |
| **OA2 fact-level filter** (不改 prompt) | 1 | ✓ Universal | retrieval-time intervention, 完全不改 prompt → 對所有任務 transparent |
| **A1 / OA2 / PAT + intermediate trailer** | 2 | △ QA-only | 對 entity-answer QA (FC/EventQA/Detective_QA) 無害~有益, 但對 summarization 會強迫 `[bullet1, bullet2]` 破壞 long-form, 對 Recsys/ICL 不適用 |
| **PAT** (soft labels only) | 3 | △ Conflict-only graceful | label 是 conditional, 沒衝突時不出現 → 對其他任務退化為 vanilla, 但仍是 conflict-task 假設 |
| **RPT-min** | 4 | ✗ FC-overfit | 強制 `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]` 結構, non-FC 任務 prompt 會誤導 |
| **RPT** | 4 | ✗ 重度 FC-overfit | `== SECTION A: USE THESE ==` 結構重組, 對 non-FC 任務不可部署 |

**關鍵 distinction**:
- Layer 1 (Universal): OA2 vanilla 是**真正可放進多任務 memory system 的 default 干預**, 因為它完全不動 prompt (純 retrieval-time fact 移除)
- Layer 2 (QA plugin): intermediate trailer **不是** universal — 它假設 task 輸出是 entity list, 對 summarization / Recsys 不適用。要做 task routing 才能加這個 trailer
- Layer 3-4 (Conflict-specific): PAT/RPT 假設有 conflict 結構 → 在 non-FC 任務不該啟用

→ **Paper 主張要分層**: universal default = OA2 vanilla, QA-task add-on = + trailer, conflict-task add-on = + PAT graceful labels。**RPT/RPT-min 不是 method recommendation, 只是 "FC-aware oracle" in-context 上限參考。**

#### 4.5.2 修正後的二軸 framing (FC-agnostic only)

研究主張的兩個獨立軸:

**軸 1: Conflict handling 策略 (FC-agnostic)**

| 同 prompt 條件 | A1 baseline | PAT (soft label) | OA2 (filter) | Filter Δ vs PAT |
|---|:---:|:---:|:---:|:---:|
| 原 prompt FC-MH | 20% | 36% | **55%** | **+19 pp** |
| modified prompt FC-MH | 23% | 48% | **83%** | **+35 pp** |
| 原 prompt FC-SH | 77% | ~96% | **98%** | +2 pp |
| modified prompt FC-SH | 96% | 97% | **98%** | +1 pp |

→ **OA2 filter > PAT soft label 在所有 prompt 條件下都成立** (FC-MH: +19~+35 pp; FC-SH 都飽和近 100% 差距很小)。modified prompt 下差距 widens, 因 filter + trailer synergy 比 annotation + trailer 強。

**軸 2: Reasoning scaffold prompt (intermediate trailer, FC-agnostic)**

| Method | 原 prompt MH | + intermediate trailer MH | Δ |
|---|:---:|:---:|:---:|
| A1 baseline (very noisy context) | 20% | 23% | +3 pp |
| PAT soft label (still noisy, labeled) | 36% | **48%** | **+12 pp** |
| OA2 filter (clean context) | 55% | **83%** | **+28 pp** |

→ **Trailer effect 隨 context cleanliness monotonically scale**: very-noisy +3 pp, mid-noisy +12 pp, clean +28 pp。Reasoning trailer 是 reasoning scaffold, 只在 context 足夠乾淨時才能 unlock chain navigation 能力。原因驗證: OA2 原 prompt 失敗分析顯示 45 個錯題中過半 Thought 是 0 字, LLM 直接回 `Answer:` 跳過推理 — trailer 強迫 chain decomposition。

**兩軸可疊加 → 23% baseline → 83% (filter + trailer), 差距 60 pp。但這 60 pp 中:**
- 純 filter (OA2 vs A1, 同原 prompt): +35 pp
- 純 trailer (A1 modified vs orig): +3 pp
- 兩者 interaction (filter + trailer 額外 lift): +22 pp
- 總計 60 pp

→ Trailer 與 filter 有 **synergy** (clean context unlocks structured reasoning),不是純疊加。

#### 4.5.3 修正後對 paper 的研究方向主張 — 分層

**Layer 1 (Universal, 適用全部 4 類 memory tasks):**
- **OA2 retrieval-time fact-level filter** → A1 baseline 20% → 55% on MH (+35 pp), 77% → 98% on SH (+21 pp)
- 這是**真正可寫進 paper 的「multi-task production recommendation」**, 因為它不改 prompt, 對 summarization/Recsys 等非 QA 任務 transparent

**Layer 2 (QA-task add-on, 適用 entity-answer QA 任務 ≈ FC/EventQA/Detective_QA, 但不適用 summarization/Recsys):**
- **+ intermediate trailer** 在 OA2 上 → 55% → 83% (+28 pp)
- 必須做 task routing, 只在 QA 子任務啟用; 不能放進 universal default prompt
- 注意**對 noisier context 影響小** (PAT+trailer 36→48% 只 +12pp; A1+trailer 只 +3pp), trailer × clean-context 才有 synergy

**Layer 3 (Conflict-task add-on, soft-deploy graceful):**
- **PAT soft labels** 在 OA2 上 (未測, 但理論上 PAT 與 OA2 不衝突 — 一個是 retrieval-time filter 的舊 fact, 一個是 inference-time mark 的新 fact)
- 在無 conflict 任務 graceful 退化為 vanilla, 但仍是 FC-assumption

**FC-aware in-context 上限 (不可部署, 僅作 reference)**:
- RPT 68% — 結構重組強制 Section A/B, 在非 FC 任務不可放; 但作為「假設知道任務是 FC 時 in-context 能做到的最強」是有用的科學基準

#### 4.5.4 修正後 paper 主張的 5 個結論

1. **Universal recommendation = OA2 vanilla** (Layer 1) → 給 +35 pp on FC-MH 不影響其他任務類型
2. **QA-task add-on (trailer) gives extra +28 pp on filter** but is **NOT universally deployable** — paper 要明確 scope 為 QA-style tasks
3. **Filter > soft annotation (PAT)** 在所有 prompt 條件下都成立 → +19~+35 pp on MH
4. **RPT (68%) 不是 method recommendation**, 是 in-context FC-aware oracle 的 reference ceiling
5. **Reasoning scaffold prompt (trailer) 對 context cleanliness monotonic** → 純 reasoning prompt 工程的邊際收益取決於 conflict / noise 處理是否到位

---

## 5. 重要 Caveat

### 5.1 全部 oracle 都用 MQuAKE GT 作為「perfect detection」
- OA2 / C / Sim-OB 假設我們完美知道哪些是 old / new / chain-relevant
- 實務 write-time / retrieval-time detection 不會完美
- **下一步必做的 ablation**: imperfect detection robustness — 對 OA2 加人為 noise (隨機保留 r% 的 chain old, r ∈ {1.0, 0.8, 0.6, 0.4, 0.2, 0.0}), 跑同樣的 RPT 對照, 看曲線交叉點。本 session 因 user 暫停而未做。

### 5.2 OA1 → OA2 的 24 pp 提升是「演算法 fix」而非「filter 本質改進」
詳見 [`diagnostic_findings.md`](diagnostic_findings.md) §1。
- v1 (passage-level): 63.6% on subset 66
- v2 (fact-level): 87.9% on same subset 66 / 83.0% on full 100
- 拆解: **3 pp 來自 v1 cross-hop subset filter bug** (qid 13, 22 連 chain GT 也誤殺), **21 pp 來自 passage 粒度太粗連帶丟 supporting facts**
- **Implication**: chunk_size=512 下 passage-level filter 幾乎不可能避免 supporting context 損失,fact-level surgical excision 是必要的

### 5.3 prompt 改變會顯著改變 LLM 行為
A1 用 modified prompt (要求 `Intermediate answers: [...]` trailer) 後, FC-SH 從原 baseline 77% 跳到 96%。所有 A1/B/Sim-OB/Sim-OB-grad/C/OA2 都用 modified prompt → 對齊 baseline 才公平。

### 5.5 Prompt rigor — 早期 framing 的關鍵失誤
本 session 早期 framing (§4.1–4.4) 在 fair-comparison 上有兩個問題:

**(a) Modified prompt 的影響被低估:** OA2 用 modified prompt 跑出 83% 但用原 prompt 只有 55% (`oracle_a_fact_level_origprompt_*.json`),純 prompt 變更 = +28 pp on MH。同樣 A1 modified (23%) vs orig (20%) 只差 +3 pp,差距集中在「context 乾淨時 trailer 才能發揮 chain reasoning scaffold」的 synergy。

**(b) RPT/RPT-min 是 FC-task-overfit 不該當 production baseline:** 它們的 prompt 強制 `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]` 結構, 對 non-FC 任務 prompt 會非常奇怪。記憶系統需要服務多種任務類型, 這類 prompt 不能部署。

修正方法:
1. **限定到 FC-agnostic 方法 (A1, PAT, OA2)** 才能稱「production 推薦」
2. **同 prompt 條件對齊**: 原 prompt 比較 vs 原 prompt, modified prompt 比較 vs modified prompt
3. **不要用「filter > annotation」這種粗略表述**, 應分二軸 (conflict handling × reasoning scaffold) 並標明 prompt 條件

詳見 §4.5。所有 A1/B/Sim-OB/Sim-OB-grad/C/原 OA2 都用 modified prompt — 故它們之間的對比 internally consistent, 但跟 RPT/PAT (原 prompt) 的對比要小心。 OA2 + 原 prompt 的補充實驗 (`oracle_a_fact_level_origprompt_*.json`) 已產出 fair comparison 數字。

### 5.4 Sim-OB-grad 的 PPR-nearby 噪音突崩點 (k=50→100) 跟 chunk_size 強相關
chunk_size=512 → 一個 chunk ~25 facts → top-10 retrieval ≈ 250 facts。當 k=100 時 distractor 數量已大於正常 retrieval 規模, 突崩可能反映 LLM context window 內某種「fact 數量閾值」, 應在不同 chunk_size 重複驗證。

---

## 6. 檔案索引 (對接者必看)

### 本 session 產出
| 檔案 | 內容 |
|---|---|
| [`SESSION_2026-04-28_diagnostic_summary.md`](SESSION_2026-04-28_diagnostic_summary.md) | **本檔** — session 敘事與發現 (含 §4.5 修正後 framing) |
| [`diagnostic_methodology.md`](diagnostic_methodology.md) | 七個實驗的方法論 (modified prompt 部分) |
| [`diagnostic_findings.md`](diagnostic_findings.md) | 完整數據 + paper-framing (含 prompt rigor 修正) |
| `a1_modified_prompt_baseline.py` 等 7 支 .py | 可重跑腳本 (modified prompt 系列) |
| `oracle_a_fact_level_origprompt.py` | OA2 + 原 HippoRAG prompt (fair compare 用) |
| `pat_modified_prompt.py` | PAT + intermediate trailer (missing cell 補完) |
| `oa2_thought_error_analysis.py` | OA2 原 prompt 剩餘錯誤的 Thought 分析 |
| `results/diagnostic/*.json` | Raw outputs (per-question) |
| `results/diagnostic/diagnostic_summary.txt` | 自動生成的對比表 |
| `results/diagnostic/oa2_remaining_errors_analysis.{json,txt}` | OA2 原 prompt 剩餘錯誤分類 |

### 此 session 之前的相關 docs
| 檔案 | 內容 |
|---|---|
| [`session_context.md`](session_context.md) | 2026-04-16 之前的研究脈絡 (FC-SH/FC-MH 失敗根因 Step 1A) |
| [`step1a_methodology.md`](step1a_methodology.md) | 衝突跳數 vs Acc 方法論 |
| [`step1a_sh_summary.md`](step1a_sh_summary.md) | FC-SH 結果摘要 + Oracle 預期 |
| [`prompts_comparison.md`](prompts_comparison.md) | vanilla / OA / PAT / RPT / RPT-min prompt 對照 |
| [`results/oracle_a/oracle_a_report.md`](results/oracle_a/oracle_a_report.md) | Oracle A v1 GPT-4o-mini 完整報告 |
| `results/mh_512_mquake_analysis.json` | FC-MH 100 題 per-hop GT/old/conflict_type 分析 (本 session 大量引用) |
| `results/sh_512_mquake_analysis.json` | FC-SH 同上 |
| `results/oracle_a_gemini/*.json` | OA1 / PAT / RPT / RPT-min 在 Gemini 上的 results |

### 重跑指南 (對接者快速上手)
```bash
cd /home/yhchiang/MemoryAgentBench

# 環境變數 (Vertex AI)
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# 跑某個 oracle 實驗 (resume-safe;會跳過已完成 query)
conda run -n hipporag_env python analysis/oracle_a_fact_level.py
conda run -n hipporag_env python analysis/sim_ob_chain_only.py
# Task B 需要 HippoRAG retrieval, 加 HF_HOME:
HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface \
  conda run -n hipporag_env python analysis/b_hop_by_hop_ablation.py

# 跑統合 summary
python analysis/diagnostic_summary.py
```

---

## 7. 已知未做事項 (Open follow-ups) — 按 channel framing 排序

### 7.A — Production system baselines on channel spectrum (★ 最高優先)

把 Zep / Mem0 放上我們建立的 oracle benchmark, 讓它們成為真實系統 baseline。現有 GPT-4o-mini 結果不能跟我們的 Gemini oracles 直接比, 必須補 Gemini 版本。

| # | 待做 | 為何重要 |
|---|---|---|
| **A1** | **重跑 Zep + Mem0 用 Gemini 3.1 Flash-Lite** (現有是 GPT-4o-mini) | LLM 一致才能跟 9 個 Gemini oracles fair compare; 現有 Zep 70% / Mem0 15% on FC-SH 都是 GPT 數字 |
| **A2** | Zep edge invalidation precision/recall vs MQuAKE GT | 量化 Zep 的 conflict detection 精度; 已在 [`zep_mechanism_deep_dive.md`](results/oracle_a/zep_mechanism_deep_dive.md) 部分做過 (correct 7 / wrong 14 / none 52 on FC-SH 100), 需要 MH + Gemini 版本 |
| **A3** | Mem0 fact extraction recall (FC 上 detection 為什麼失效) | 已知 Mem0 `FACT_RETRIEVAL_PROMPT` 只抽 personal preferences, FC 知識被 filter 掉 → 對 production 系統「什麼樣的 detection 對 FC 有效」有 negative example value |
| **A4** | 實際送進 LLM 的 inference prompt 結構盤點 | Zep: timestamp + abstract + raw; Mem0: vector retrieval 結果。對照我們的 PAT/RPT,量化「資訊密度」 |
| **A5** | End-to-end (Zep/Mem0) vs oracle (channel ceiling) gap | 這個 gap = detection 改進的潛力空間, 是 paper 的核心 motivation |

### 7.B — Method exploration

| # | 待做 | 為何重要 |
|---|---|---|
| B1 | **Hybrid channel: filter + annotation 組合** | OA2 + PAT graceful labels 同時用,上限應介於 OA2 與 Sim-OB 之間,同時保留 Zep-style reversibility. **最實用的 production design** |
| B2 | **Imperfect detection robustness** | 對 OA2 / PAT / RPT 加人為 noise 看 degradation 曲線。**paper 從「oracle ceiling」推到「production claim」的關鍵橋樑** |
| B3 | Zep-style timestamp annotation channel | 補 oracle 級的 timestamp 多層 annotation, 預期介於 PAT 與 RPT 之間, 給 Zep 在 spectrum 上的位置驗證 |

### 7.C — Generalization

| # | 待做 | 為何重要 |
|---|---|---|
| C1 | 擴展到 32k / 64k / 262k 對話歷史 | 本 session 全部在 6k 跑 |
| C2 | chunk_size=4096 下重做 (依 user 規劃在長 context 上改回 4096) | Sim-OB-grad 噪音閾值與 fact-level vs passage-level 差距可能改變 |
| C3 | 換 LLM (GPT-4o-mini / Claude / 更大 LLM) | 結論可推廣性 |
| C4 | 驗證 trailer 對 non-QA 任務 (InfBench_sum) 的負面影響 | 強化 paper 的 layer 2 scoping argument |

---

## 8. 給接手 Claude 的提示

讀完本檔後,你應該知道:
1. **這個 session 跑了 7 個 oracle 診斷實驗 + Oracle A v2 (modified + 原 prompt 兩版) + PAT + intermediate trailer (modified) — 共 9 個 inference 實驗 + 多個分析腳本**
2. **§4 早期 framing 不夠嚴謹** — modified prompt (intermediate trailer) 對 OA2 給了 +28 pp 隱性 boost,跟 PAT/RPT 比較不公平。**正確 framing 在 §4.5**
3. **OA1 (63.6% on subset) → OA2 (83% on full, modified) 的差距不是 ceiling 改變,是演算法 fix** (詳見 §5.2)
4. **RPT/RPT-min 是 FC-task-overfit, 不能算 production-recommendable method** — 它們的 prompt 強制 `[SECTION A: ACTIVE/SUPERSEDED]` 結構,對 non-FC 任務不可部署 (詳見 §4.5.1, §5.5)
5. **正確的 paper 主張是「二軸獨立 + filter > soft annotation」** — 詳見 §4.5
6. **下一步候選**: (a) imperfect-detection robustness ablation (§7.1), (b) 換 chunk_size / 換 LLM 確認可推廣性 (§7.3, §7.4), (c) 32k/64k/262k 擴展 (§7.2)

如果使用者問「下一步做什麼」: **預設答案是 imperfect-detection robustness ablation** — 把 OA2 加人為 noise (perfect detection 假設打破) 看 degradation 曲線, 跟 PAT 同曲線比較, 才能稱 production claim。

如果使用者問「結果在哪」: **指向 [`diagnostic_findings.md`](diagnostic_findings.md)** (含 prompt rigor 修正); 如果問「方法」: **指向 [`diagnostic_methodology.md`](diagnostic_methodology.md)** (主要是 modified prompt 系列方法論, 原 prompt 系列在 `oracle_a_fact_level_origprompt.py` 與 `pat_modified_prompt.py` 程式註解中)。

**警告 — 不要重複的常見錯誤**:
- 不要把不同 prompt 條件的數字直接比較 (e.g. OA2-modified 83% vs RPT-orig 68%) — 這是 apples-to-oranges
- 不要把 RPT 當 production baseline — 它 FC-overfit, 真實場景不可部署
- 不要重跑已完成實驗 (resume-safe, 直接讀 `results/diagnostic/*.json`)
- 不要刪 partial output 檔 (resume 機制依賴它)

---

*產出時間: 2026-04-28 (主要實驗) — 後段補 OA2 原 prompt + PAT modified prompt*
*Session 對話歷時: ~3-4 小時 (含背景 inference 等待)*
*總 inference call 約: 2750 次 (A1 200 + B 254 + Sim-OB 100 + Sim-OB-grad 1000 + C 100 + OA2 modified 200 + OA2 origprompt 200 + PAT modified 200 + Thought analysis 0)*
