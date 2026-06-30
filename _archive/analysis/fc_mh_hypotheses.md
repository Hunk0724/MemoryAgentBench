# FC-MH 多跳知識更新難解的假設集 — 設計方向地圖

> 目的:把目前 smoke test 與量化分析的觀察(可能是 local、非全面)收斂成 5 個明確假設。每個假設指定**證據強度**、**對應的 HippoRAG-v2-based 改進方向**、**未來實驗如何驗證**。
>
> 注意:本文是「working hypotheses」,目的是提供未來方法設計的 testable 起點,而非 paper 的最終 claim。每個假設都需要更大樣本與 ablation 驗證。

---

## 假設總覽

| # | 假設名稱 | 核心 claim | 證據強度 | 對應改進方向 |
|:---:|---|---|:---:|---|
| H1 | **Candidate Visibility** | LLM 無法可靠列舉 retrieval 中的候選事實 | 強 | inline marker(強制候選並列在 prompt 文字層) |
| H2 | **Signal Comprehension** | 隱式 signal(serial / date range)被 LLM 不一致理解 | 強 | 顯式 signal label(直接綁在 fact 上) |
| H3 | **World-Knowledge Override** | 即使候選都看到,世界知識仍壓過 conflict 規則 | 中 | 強指令(MUST NOT use OUTDATED) |
| H4 | **Multi-hop Multiplicative Compounding** | per-hop 弱點透過多跳鏈乘法放大 | 強 | 每跳都施加 H1+H2+H3,而非僅最後 hop |
| H5 | **Chain Mis-anchor / Bail-out** | hop N+1 查找不順時退回 hop N 的舊鏈 | 弱 | chain-aware 約束(不能 abandon current chain) |

---

## H1 — Candidate Visibility Hypothesis

### Claim

> LLM 在原 inference prompt 條件下,**無法可靠地列舉 retrieval-side 已提供的候選事實**。即使被診斷指令強制要求「list ALL matching facts」,LLM 仍漏掉 25–60% 的 has_pair hops 的 GT 或 Old fact 。

### 證據

| 來源 | 觀察 |
|---|---|
| smoke_test_findings.md §5.1 | gpt-4o-mini:LLM-side Both-listed 25.4% vs retrieval 100%(差 75pp) |
| smoke_test_findings.md §5.1 | gemini-FL:Both-listed 61.0%(差 39pp,仍嚴重) |
| q14 Hippo (A) 範例 | retrieval 含 Emmerson Mnangagwa(GT)+ Elizabeth II,LLM 僅列 Elizabeth II |
| q5 Zep (A) vs (B) | (A) 不列 Wilhelm II 的 universities;(B) 事後被問才列出 |

### 設計方向

**Direction A:Inline candidate marking** — 在 prompt 文字層強制把每個衝突對的兩版本並列,標上顯式 marker(如 `[CURRENT FACT]` 與 `[OUTDATED FACT]`)。剝奪 LLM 「不去看」的選項。

對應的具體實作 = 我們的 RPT 設計第一個 component。

### 未來實驗

| 實驗 | 預期結果(若 H1 成立) |
|---|---|
| 對同 30 題跑「只加 inline marker、不加 MUST 指令」的版本 | LLM-side Both-listed 接近 100%(因為 marker 直接在文字中) |
| 對 100 題 MH RPT vs RPT-min(差別在 MUST 強度) | RPT-min 應已大幅改善 candidate-recall;EM 也大幅升 |
| 量化 hop-level candidate-recall × EM 相關性 | 強正相關(r > 0.6) |

---

## H2 — Signal Comprehension Hypothesis

### Claim

> 即使 retrieval 中嵌入了 conflict-resolution signal(序號、Zep date_range、HippoRAG passage 順序),**LLM 不一致地理解這些 signal**。LLM 自報的 signal 使用率在 33–46% (serial-number),0% (date-range);50%+ 自報 "signal: none / fallback"。

### 證據

| 來源 | 觀察 |
|---|---|
| smoke_test_findings.md §5.2 | gpt-4o-mini:33% 自報 serial,61% 自報 none/fallback |
| smoke_test_findings.md §5.2 | gemini:46% serial,52% none/fallback;**沒有任何 hop 自報 date-range** |
| §13.2 | Zep 在 LLM 認知層面 invalid_at 訊號 0% 被識別 |
| smoke v1 q1 | LLM 自稱 "selected by larger serial number" 但 FACTS section 沒有序號(hallucinate) |

### 設計方向

**Direction B:Explicit signal label per fact** — 不讓 LLM infer 哪個事實是 newer。直接把 signal 編成 token-level marker 與 fact 並列,如 `<CURRENT> fact_text </CURRENT>` vs `<OUTDATED> fact_text </OUTDATED>`。LLM 不需要 reason,只需要遵循 marker。

對應 RPT 的第二個 component。

### 未來實驗

| 實驗 | 預期結果 |
|---|---|
| smoke test 加 RPT-min 條件 | LLM 自報的 signal 應該全部變成 "explicit marker"(0% 'none'/fallback') |
| 隱式 vs 顯式 signal 的 ablation:passage 序號 / date-range / explicit marker 三種 | EM 應該按 explicit > passage序號 > date-range 排序 |
| Hop-level conflict-detected rate | 顯式 marker 條件下接近 100% |

---

## H3 — World-Knowledge Override Hypothesis

### Claim

> 即使 LLM 列出 Both candidates 並識別到衝突,**世界知識 prior 仍可能壓過顯式的「use newer」規則**——尤其當 GT 是 MQuAKE-CF counterfactual(如 US 官方語言=德語、basketball 創於蘇聯)。

### 證據

| 來源 | 觀察 |
|---|---|
| smoke_test_findings.md §5.4 | 47% Hippo / 64% Zep 答錯題目中 LLM 至少一個 hop 列出 GT,但仍選 Old |
| gemini smoke test | Both-listed 61% → EM 40%(21pp gap = 看到了仍選錯) |
| zep_sh_summary §4.1 | SH 14 個 SUPERSESSION_MISFIRED 全部是 counterfactual,EM 7% (1/14) |
| §13.1 | SH MISFIRED 14 題 EM 7% vs HippoRAG 同 14 題 ~70%(機制誤導比沒機制更糟) |

### 設計方向

**Direction C:Strong override instruction** — 在 prompt 加 `MUST NOT use OUTDATED` 之類的硬指令,顯式要求 LLM **無視世界知識先驗**,只依照 marker 採用 CURRENT。

對應 RPT 的第三個 component(也是 RPT 與 RPT-min 唯一差別)。

### 未來實驗

| 實驗 | 預期結果 |
|---|---|
| RPT-min(只有 inline marker)vs RPT(marker + MUST) | RPT 應在 counterfactual subset 顯著高於 RPT-min |
| 把 30 題標 counterfactual-strength(GT 與世界知識的距離) | counterfactual 越強的題,RPT 比 RPT-min 提升越多 |
| 在 SH 14 misfired 題上跑 RPT | 若 H3 成立,RPT 應該把 EM 從 7% 拉到 ~80%+ |

> ⚠️ 這個假設證據強度為「中」,因為 H1+H2 也可能解釋同樣現象。RPT vs RPT-min 的 ablation 是分離 H3 的關鍵實驗。

---

## H4 — Multi-hop Multiplicative Compounding Hypothesis

### Claim

> H1+H2+H3 都是 **per-hop 級別的 LLM 弱點**,但多跳鏈把這些弱點以乘法效應放大。**SH vs MH 表現差距的根本原因不是「多跳本身難」,而是「同樣的 per-hop 弱點被多次串連起來,任一 hop 失誤就鏈路斷裂」**。

### 證據

| 來源 | 觀察 |
|---|---|
| §13.2 | 同樣「無訊號但兩者都看得到」狀態,SH 68.5% / MH 8.5%(60pp gap) |
| smoke gemini §5(我們剛跑的) | gemini 1c→2c→3c EM:56% → 36% → 33%(A 條件)、56% → 7% → 17%(C 條件) |
| zep_mh_summary §2 | 衝突跳數 1→2→3→4:39%→23%→6%→0%(Zep)、30%→2%→0%→0%(HippoRAG) |
| 多跳乘法模型 | per-hop ~60%,2-hop 36%、3-hop 22%、4-hop 13% — 跟觀察數值匹配 |

### 設計方向

**Direction D:Per-hop signal application** — H1/H2/H3 的修正必須**對每一個 has_pair hop 都生效**,而非只標 final answer 對應的事實。每個衝突對都有 `[CURRENT]/[OUTDATED]` marker。

> 這暗示了 RPT 的覆蓋率必須是 per-hop 100%,不能只標部分。Zep 之所以 +14pp 受限就是因為 invalid_at 只在 ~50% has_pair hops 觸發。

### 未來實驗

| 實驗 | 預期結果 |
|---|---|
| 把 100 題 MH 按 n_conflict_hops 分(1/2/3/4),測 RPT 對每組的提升 | 提升幅度應 2c > 1c(因為 2c 乘法效應更嚴重,固定後改善大) |
| ablation:只標 final-hop 衝突 vs 全 hop 標 | 全 hop 標應顯著優於只標 final |
| Hop-level chain-success 率(每 hop 是否成功 carry 正確 entity) | RPT 應在 chain-success 率上接近 1,plain HippoRAG 在 2c+ 多跳衰減 |

---

## H5 — Chain Mis-anchor / Bail-out Hypothesis

### Claim

> 當 LLM 在 hop N 選擇了新事實版本,但在 hop N+1 找不到對應的下游事實時,**LLM 會退回 hop N 的舊事實版本繼續查找**(bail-out),導致最終答案沿舊鏈推出。

### 證據

| 來源 | 觀察 |
|---|---|
| smoke v1 q6 (C) Thought | "Bernard Arnault has a larger serial number... However, no specific mention of his citizenship... I will refer to the earlier fact about Jack Dorsey" |
| smoke expanded(同 q6 第二次 run) | 沒有 bail-out 語言;LLM 直接答 Jack Dorsey 沒提 Bernard Arnault |
| 30 題 (C) 條件 bail-out 語言偵測 | 0–1/30(罕見)|

> ⚠️ 證據強度「弱」。bail-out 在 small sample 偶見,但在 30 題 expanded sample 中只有 1 例;更多時候 LLM 在 (C) 根本沒啟動衝突偵測,直接用世界知識答了(這比 bail-out 更悲觀)。

### 設計方向

**Direction E:Chain-aware constraint** — 在 prompt 強制 LLM 一旦選了 CURRENT,就必須在所有後續 hop 都使用 CURRENT 鏈。例如:「If you select a CURRENT fact for a hop, you MUST continue using CURRENT facts for all downstream hops, even if the next hop's lookup seems harder. Do NOT fall back to OUTDATED chain.」

### 未來實驗

| 實驗 | 預期結果 |
|---|---|
| 大樣本(100+ MH 題)bail-out 語言偵測,加更精準的 pattern | 看 bail-out 比例究竟有多少 |
| 在 RPT 加上 chain-coherence MUST 指令 ablation | 若 H5 成立,該 ablation 應在 2c+ 多跳子集多救 |
| 標 q6-style「new chain has missing downstream」題目 | 該子集 RPT-with-chain-MUST > RPT |

---

## 假設與 RPT 的對應地圖

```
H1 Candidate Visibility ─────► Inline marker [CURRENT]/[OUTDATED]
                              (RPT component 1)

H2 Signal Comprehension ─────► Explicit signal label per fact
                              (RPT component 2)

H3 World-Knowledge Override ─► MUST NOT use OUTDATED instruction
                              (RPT component 3, RPT-min vs RPT 唯一差別)

H4 Multiplicative Compounding ► Per-hop 100% coverage
                              (RPT 對所有 has_pair 對標 marker,Zep 只有 ~50%)

H5 Chain Mis-anchor ─────────► (尚未在 RPT 加入,future direction)
```

> RPT vs RPT-min 的實際結果:
> - SH: RPT 100%,RPT-min 待補
> - MH: RPT 68%,RPT-min 60% (Δ +8pp = MUST 指令對 MH 多救 8 題)
>
> 這個 Δ 對應 H3 的部分驗證:在 RPT-min 已修正 H1+H2 的條件下,MUST 指令再額外修正 H3,還有 +8pp 空間。

---

## 對 paper writing 的核心啟示

1. **不要把 FC-MH 當成「多跳推理」問題,而是「per-hop 弱點 × 多跳乘法」問題**——這對 problem framing 很重要,讓設計方向聚焦在 per-hop 修正而非設計新的 reasoning 架構
2. **H1+H2 是核心,H3 是 secondary,H4 是 multiplier**——RPT 的三個 component 對應不同層級的修正,缺一不可
3. **Zep 的不足對應 H1+H4**:Zep 只在 ~50% has_pair hops 提供 supersession 訊號(H4 違反),且 invalid_at 訊號 LLM 0% 識別(H2 違反)。RPT 在這兩點都做到 100%
4. **gpt-4o-mini vs gemini 行為差異是 paper 的 caveat**:H1/H2 嚴重程度 model-dependent,RPT 在小模型上的修正幅度可能更大

## Validation experiments — corrected with SESSION_2026-04-28_diagnostic_summary.md

> ⚠️ 本節在 2026-04-29 更新:採納 [SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md) 中更完整的 oracle benchmark(共 9 個 oracle 實驗,含 OA2 fact-level filter 與 Sim-OB chain-only)。原本只用 RPT ladder 推斷 inference-side ceiling,實際上**retrieval-time filter (OA2) 給出更高的 ceiling (83%)**,而 Sim-OB 顯示 LLM 純 multi-hop 能力 ceiling **是 98%**。

### 兩條獨立的設計 channel ladder(full 100 MH,gemini-FL)

| Channel 類型 | Oracle 實驗 | EM | 累積 Δ vs A1 baseline |
|---|---|:---:|:---:|
| **A1 baseline**(no detection)| modified prompt | 23% | — |
| **Filter route**(retrieval-time)| | | |
| OA2 fact-level filter(原 HippoRAG prompt) | OA2 origprompt | **55%** | +32 pp ← Layer 1 universal |
| OA2 + intermediate-trailer prompt(QA add-on) | OA2 modified | **83%** | +60 pp ← Layer 2 QA-only |
| **Annotation route**(inference-time)| | | |
| PAT(soft `[CURRENT/OUTDATED FACT]` 標籤)| PAT modified | 48% | +25 pp |
| RPT-min(inline `[SECTION A/B]` 標籤) | RPT-min | 60% | +37 pp |
| RPT(完整重組 + DO NOT USE B 強指令) | RPT | 68% | +45 pp ← FC-overfit reference,**不可部署** |
| **Pure-LLM ceiling**(零噪音零衝突)| Sim-OB chain-only | **98%** | +75 pp ← absolute ceiling |

> **核心修正觀察**:
> 1. **Filter > annotation 在所有 prompt 條件下都成立**:OA2(原 prompt)55% > RPT 68% 是不對的比較(不同 prompt);**同 modified prompt 對齊**:OA2 83% > RPT 68% +15pp;**同原 prompt 對齊**:OA2 55% > PAT 36% +19pp
> 2. **RPT/RPT-min 是 FC-task-overfit**(`[SECTION A: ACTIVE]`/`[SECTION B: SUPERSEDED]` 結構強制 FC schema),**不能當 production baseline**——只是 in-context FC-aware oracle 的 reference ceiling
> 3. **Sim-OB 98% 證明 LLM 純 multi-hop reasoning 不是瓶頸**——剩下的 15pp(83% → 98%)是 retrieval 噪音 + entity confusion,跟 conflict 無關

### 修正後的假設驗證對應

| 假設 | 原本 evidence(從 RPT ladder)| **SESSION doc 的更強 evidence** |
|---|---|---|
| H1 Candidate Visibility | RPT-min 60% (inline marker) - plain 22% = +38pp | **OA2 fact-level filter 直接從 retrieval 移除舊事實 → 23% → 55% (orig prompt) / 83% (modified) — 不依賴 LLM 識別 marker,效果比 marker 更好** |
| H2 Signal Comprehension | PAT 36% → RPT-min 60% = +24pp 從 marker 取代 implicit signal | 同上(filter 路線完全跳過 signal 問題)|
| **H3 World-Knowledge Override** | RPT-min → RPT = +8pp 從 MUST | **強化了 — SESSION §4.2:LLM 即使看到 `[OUTDATED FACT]` 標記 + `DO NOT USE Section B` 強指令,仍有 ~32% 機率採信舊事實 — trust gap 是 hard ceiling**(H3 從 MODERATE 升到 STRONG)|
| H4 Multiplicative Compounding | SH 68.5% / MH 8.5% gap | Sim-OB-grad noise gradient:PPR-nearby k=100 處從 90% 突崩到 61% — 量化 noise tolerance 曲線 |
| H5 Chain Mis-anchor | q6 case + 1/30 in expanded sample | SESSION doc 沒把這列為 main hypothesis(資料太弱)|

### 修正後最重要的 takeaway

| 路線 | EM ceiling | Production deployability |
|---|:---:|---|
| **OA2 retrieval-time filter(原 prompt)** | **55%** | ✅ **Layer 1 Universal** — 完全不改 prompt,對 summarization/Recsys 等所有任務 transparent |
| OA2 filter + intermediate trailer | 83% | △ Layer 2 — 只能加在 QA-style task |
| PAT soft annotation | 36-48% | △ Layer 3 — graceful but conflict-task assumption |
| **RPT** | 68% | ❌ Layer 4 — FC-overfit,不可部署 |
| Sim-OB(reference only) | 98% | ❌ 不存在 |

→ **Paper main claim 應該是**:**filter at retrieval (OA2) +35pp on FC-MH 不需任何 prompt overhead,is the production-ready universal recommendation**。RPT 只當作 in-context FC-aware oracle 的科學基準。

> 這個修正大幅改變了 hypothesis 文件的論述重心:**前面 5 個假設仍然是 paper 對「LLM 在 FC-MH 上失敗的根因」的合理拆解,但「修正方向」應該偏向 retrieval-time filter,而不是 inference-time prompt engineering**。

---

## (Original validation section — kept for historical context)

> 以下保留原本 2026-04-28 寫的 validation 段落,內容已被上面的修正版本取代。讀者請以上方表格為準。

### Backbone-swap baseline + design ladder (full 100 MH)

| Setup | EM | Δ |
|---|:---:|:---:|
| Plain HippoRAG-v2 + gpt-4o-mini | 11/100 | (baseline) |
| Plain HippoRAG-v2 + gemini-FL | 22/100 | +11 pp 從 backbone 本身 |
| PAT(lead instruction)+ gemini | 36/100 | +14 pp from PAT |
| RPT-min(inline marker)+ gemini | 60/100 | +24 pp 從 inline marker |
| RPT(marker + MUST)+ gemini | 68/100 | +8 pp 從 MUST 指令 |

### LLM-side candidate-recall 驗證(30 fair-condition targets,gemini-FL)

H1 預測:inline marker 應把 LLM-side candidate-recall 從 ~60% 拉到接近 100%。實測:

| Method | EM (C) | EM (A) | GT listed | Both listed |
|---|:---:|:---:|:---:|:---:|
| Plain HippoRAG | 23.3% | 40.0% | 62.7% | 61.0% |
| RPT-min(inline marker) | 60.0% | **90.0%** | **93.2%** | **83.1%** |
| RPT(marker + MUST) | 73.3% | **96.7%** | **98.3%** | 67.8% |

> **H1 強驗證**:GT listed 從 plain 62.7% → RPT 98.3%(+36 pp),inline marker 直接把 candidate visibility 拉到接近完美。
>
> **副發現**:RPT 的 Both-listed 67.8% < RPT-min 的 83.1%。MUST 指令讓 LLM 在 (A) 診斷時把 OUTDATED 從 candidates 中略掉(認為不該列),這是 enumeration behavior 的改變——RPT 的 +8pp 提升不單來自 reasoning,也來自 LLM 對 OUTDATED 的「忽略式 enumeration」。

### 三個假設的最終驗證狀態

| 假設 | 預驗證強度 | 驗證後強度 | 證據 |
|---|:---:|:---:|---|
| H1 Candidate Visibility | 強 | **✅ 確證** | inline marker 把 LLM-side GT recall 62.7% → 98.3%;EM +24 pp(RPT-min over plain) |
| H2 Signal Comprehension | 強 | **✅ 確證** | RPT-min 顯式 marker 取代隱式序號/date,EM 22 → 60(+38 pp 含 PAT);LLM 無需 infer signal |
| H3 World-Knowledge Override | 中 | **✅ 確證** | RPT (with MUST) over RPT-min: +8 pp,顯示「marker 顯示 GT 後仍需 MUST 才能壓過世界知識」 |
| H4 Multiplicative Compounding | 強 | ✅ 已暗示 | per-hop 100% marker 覆蓋是 RPT 的關鍵設計;Zep 只 ~50% 才止步 +14pp |
| H5 Chain Mis-anchor / Bail-out | 弱 | ⚠️ 仍未直接驗證 | 待大樣本與 chain-aware ablation |

### 對 paper main contribution 的對應

我們的設計三組件對應三個假設,每個都有 quantified ablation 證據:

```
22% (plain hippo + gemini, no design)
 │
 │  +24 pp 從 H1+H2 修正(inline marker:[CURRENT]/[OUTDATED])
 ▼
60% (RPT-min)
 │
 │  +8 pp 從 H3 修正(MUST 指令)
 ▼
68% (RPT)
```

剩下 32 pp gap 對應 H4(per-hop 覆蓋未達 100%)+ H5(chain mis-anchor 未顯式處理)+ unsolvable hard core(retrieval-side 真缺)。這是 future work 方向。

---

## 假設驗證嚴謹度審計(2026-04-28 honest audit)

每個 H 標示**實驗設定**、**直接 vs 間接證據**、**confound**、**可信度等級**、**作為設計方向的可用程度**。

可信度等級定義:
- 🟢 **STRONG**:有 full-scale paired ablation(n=100)+ 一致趨勢 + 機制可分離
- 🟡 **MODERATE**:有 ablation 但 n 小或機制有 confound
- 🟠 **WEAK**:小樣本 anecdotal,趨勢一致但無 ablation
- 🔴 **SUGGESTIVE**:單一案例或 pattern 觀察,未 systematically 測

---

### H1 — Candidate Visibility Hypothesis

| 項目 | 內容 |
|---|---|
| **實驗設定** | (1) Smoke (A) condition 強制 LLM 列 candidates,30 MH targets × 2 backbones (gpt, gemini)。 (2) Full 100q EM ladder (gemini): plain 22% → RPT-min 60%。 |
| **直接證據** | • LLM-side GT recall(n=59 has_pair hops, gemini-FL):plain 62.7% → RPT-min 93.2% → RPT 98.3%<br>• Full 100q EM:plain HippoRAG 22% → RPT-min 60%(+38pp 含 PAT 步驟)|
| **間接證據** | • q14 case:retrieval 確認有 GT 但 LLM (A) 條件下沒列出<br>• gpt-4o-mini Both-listed 25.4% vs gemini 61.0%(model-dependent severity) |
| **Confound** | • (A) 條件本身改變 LLM 行為 — 我們觀察的是「LLM 被要求 enumerate 時的行為」,不是「自然 inference 時的內部 attention」<br>• `fact_in_candidates` 用 substring match,可能漏 paraphrase<br>• EM jump 22→60 conflate H1 與 H2 |
| **可信度** | 🟢 **STRONG**(full 100q EM ablation 一致 + LLM-side recall 量化趨勢一致) |
| **作為設計方向** | ✅ 高信心可作為設計起點:**任何方法都應該確保候選事實在 prompt 文字層直接呈現,不依賴 LLM 自行 scan retrieval** |
| **要再強化 confidence 的實驗** | (a) (C) 條件下用其他方式量化 LLM 內部 attention(如 attention map 分析,但 gemini 不公開 weights);(b) 對 paraphrased fact 做 semantic similarity match 而非 substring,測 candidate-recall 是否仍 < 100% |

---

### H2 — Signal Comprehension Hypothesis

| 項目 | 內容 |
|---|---|
| **實驗設定** | (1) parse "Signal used:" field from (A) traces, n=46-59 has_pair hops。 (2) PAT(lead instruction)vs RPT-min(inline marker)full 100q EM 對比。 |
| **直接證據** | • LLM 自報 signal:0% date-range / 33% serial (gpt) / 46% serial (gemini) / 50%+ none/fallback<br>• Full 100q:PAT 36% → RPT-min 60% = **+24pp 從 explicit marker 取代 implicit serial rule** |
| **間接證據** | • smoke v1 q1:LLM 自稱用 "larger serial number" 但 FACTS 沒序號(hallucinate)<br>• Zep date_range 訊號 LLM 0% 識別 |
| **Confound** | • LLM self-report signal 是 introspection 結果,**不必然反映 LLM 真實使用的 signal**(q1 hallucinate 證實)<br>• PAT→RPT-min 的 +24pp **同時改變 visibility(H1)與 explicitness(H2)**,無法乾淨分離<br>• 沒做「保留 visibility、只變 explicitness」的 ablation |
| **可信度** | 🟡 **MODERATE-STRONG**(full 100q EM gain 真實但機制有 confound) |
| **作為設計方向** | ✅ 可作為設計起點:**explicit per-fact label > implicit/positional signal**——但 H1 與 H2 的 contribution 比例尚未分離 |
| **要再強化 confidence 的實驗** | clean ablation:在 prompt 中保留所有 has_pair 對的兩個版本(visibility 100%),只變 signal 形式(serial number-only / date-only / explicit marker),測 EM 差異——這才能分離 H2 |

---

### H3 — World-Knowledge Override Hypothesis

| 項目 | 內容 |
|---|---|
| **實驗設定** | RPT-min(inline marker only)vs RPT(marker + MUST instruction)full 100q gemini ablation。SH 14 SUPERSESSION_MISFIRED 子集分析。 |
| **直接證據** | • Full 100q MH:RPT-min 60% → RPT 68% = **+8pp from MUST 指令**<br>• SH 14 SUPERSESSION_MISFIRED 全部是 counterfactual,EM 7%(機制誤導比沒機制更糟)|
| **間接證據** | • Smoke 30q:答錯題目中 47% (Hippo) / 64% (Zep) 仍列出 GT 但選 Old<br>• gemini Both-listed 61% → EM 40%(看到了仍選錯 21pp)|
| **Confound** | • **RPT 改變 LLM enumeration behavior**:RPT Both-listed 67.8% < RPT-min 83.1% — MUST 可能透過「LLM 自我過濾不列 OUTDATED」起作用,而不是真的「克服世界知識先驗」<br>• +8pp 在 n=100 邊界,**沒做 McNemar paired test**<br>• 沒有 counterfactual-strength label,無法看「世界知識 prior 越強的題,RPT 提升是否越大」 |
| **可信度** | 🟡 **MODERATE**(EM gain 真實但機制詮釋有兩種可能,目前無法區分)|
| **作為設計方向** | ⚠️ 可試但要小心:**MUST 強指令確實有 +8pp 效果,但「為何有效」還不確定**——可能是 override 也可能是 enumeration filter |
| **要再強化 confidence 的實驗** | (a) McNemar 測 +8pp 顯著性;(b) 標 30 題 GT 為 counterfactual-strength 高/中/低,測 RPT vs RPT-min Δ 是否在「強 counterfactual」題目上更大;(c) 設計只變指令、不變 marker 的版本(marker + 弱指令 vs marker + 強指令)|

---

### H4 — Multiplicative Compounding Hypothesis

| 項目 | 內容 |
|---|---|
| **實驗設定** | (1) SH vs MH 同條件 EM 對比;(2) n_conflict cohort 分析(1c/2c/3c/4c);(3) Zep 50% per-hop trigger vs RPT 100% per-hop coverage 的差異對應 EM gap。 |
| **直接證據(描述性)** | • 同「無訊號但兩者都看得到」狀態,SH 68.5% / MH 8.5%(60pp gap)<br>• 1c→2c→3c→4c plain hippo EM:30%/2%/0%/0%(gpt) ;39%/23%/6%/0%(zep)<br>• 多跳乘法模型 0.6^N 與觀察值一致 |
| **間接證據** | Zep ~50% has_pair hops 觸發 supersession 訊號 vs RPT 100% per-hop 覆蓋,這跟 Zep +14pp vs RPT +46pp 的差距方向一致 |
| **Confound** | • **SH vs MH 是不同 dataset**(不同問題結構、不同 retrieval 難度),把差距全歸 multiplicative effect 是 confounded<br>• 「per-hop 100% 覆蓋是 RPT 關鍵」的 claim 沒有直接 ablation(沒做「only-final-hop marker」vs「all-hop marker」對比)|
| **可信度** | 🟢 **STRONG(描述性)** / 🟡 **MODERATE(因果性)** |
| **作為設計方向** | ✅ 描述性事實可信:**MH 衝突跳數越多,EM 越低,呈乘法形態**——任何方法設計都應對每個 hop 都施加修正,不能只標 final hop |
| **要再強化 confidence 的實驗** | ablation:(a) 「only final-hop marker」vs「all-hop marker」EM 對比;(b) 控制變因把 MH 1c 子集視為「等效 SH」,測同條件下 EM 差距是否消失 |

---

### H5 — Chain Mis-anchor / Bail-out Hypothesis

| 項目 | 內容 |
|---|---|
| **實驗設定** | regex pattern matching 在 30 (C) Thought blocks(gpt + gemini 兩 backbones,共 60 responses)。 |
| **直接證據** | smoke v1 q6 (gpt-4o-mini) 一個明確案例:"Bernard Arnault has a larger serial number... However, no specific mention of his citizenship... I will refer to the earlier fact about Jack Dorsey" |
| **間接證據** | 無 |
| **Confound** | • Expanded sample 完全沒看到(0/30 gpt + 1/30 gemini)<br>• gpt-4o-mini 在 temp=0 仍有 nondeterminism — 同 q6 兩次 run 不同行為,bail-out 偵測不可靠<br>• 我用的 regex pattern 太狹窄 |
| **可信度** | 🔴 **WEAK / SUGGESTIVE**(單一明確案例 + 大樣本中極罕見) |
| **作為設計方向** | ⚠️ **不建議當主要設計依據**——可作為「未來如果觀察到 chain-coherence 問題,有這個方向可試」的備用 |
| **要再強化 confidence 的實驗** | (a) 大樣本(200+)+ 更精準 pattern matching(包括「stops mentioning new fact」「reverts to」等更廣的語言模式);(b) 定義可量化的 chain-coherence metric:每個 hop 的 selected entity 是否屬於 CURRENT 鏈或 OUTDATED 鏈;(c) 在 RPT 加 chain-coherence MUST 指令做 ablation |

---

## 設計方向 ≠ 假設證實 — 重要區分

我們要保留「**作為設計嘗試的起點**」與「**已被驗證的因果機制**」的區別:

| 假設 | 可作為下一輪設計的起點 | 因果機制已被驗證 |
|---|:---:|:---:|
| H1 Candidate Visibility | ✅ | ✅ STRONG |
| H2 Signal Comprehension | ✅ | 🟡 MODERATE(與 H1 confound)|
| H3 World-Knowledge Override | ✅ 可試 | 🟡 MODERATE(機制不確定)|
| H4 Multiplicative Compounding | ✅ | 🟢 描述性 STRONG / 🟡 因果 MODERATE |
| H5 Chain Mis-anchor | ⚠️ 備用 | 🔴 WEAK |

**重點**:
- **H1+H4 是最可信的兩個假設**,任何後續方法都該確保「per-hop 100% 候選都顯式呈現」
- **H2 與 H3 雖然 EM ablation 顯示有效,但機制詮釋有 confound** —— 在設計方法時可以借用,但 paper 論述時要小心 not to overclaim
- **H5 目前只是 hint,不應當作主要 design driver**

## Methodological caveats — A/B/C 條件的 confound 釐清

我們用 A/B/C 三種 prompt 策略觀察 LLM reasoning,但每種都引入了自己的 confound:

| 條件 | 觀察的是什麼 | 不是什麼 |
|---|---|---|
| (C) 純原 inference | 原 EM byte-equal(若 temp=0 deterministic);LLM 自發 Thought 中的推理線索 | LLM 內部完整推理(只看到最終 verbalized 部分);Zep prompt 抑制 Thought 後就完全看不到 |
| (A) trace-first | 結構化推理痕跡可量化(candidate-recall, signal-cited)| **LLM 在 (A) 條件下的行為≠LLM 在 (C) 原條件下的行為**——強制結構可能改變 attention 分配;HippoRAG (A) EM 從 (C) 6.7% 跌到 0% 就是證據 |
| (B) post-hoc explain | 保留原 EM 同時得結構化解釋 | **rationalization 風險**——q5 已直接展示 LLM 在 (B) 列出 Wilhelm II 的 universities(包括 GT),但 (A) 沒列;LLM 可能事後合理化編出沒實際發生的推理 |

**這對假設驗證的意義**:
- H1 的 LLM-side candidate-recall 是用 (A) 觀察的,**這個值更接近「LLM 被要求列時能列多少」而非「LLM 自然 inference 時看到多少」**;前者是 upper bound
- 真實 (C) inference 的 candidate visibility 可能**更低**(LLM 自發 Thought 多半連 conflict 都沒提及,§5.3),這意味 H1 在 plain inference 條件下可能比量化的還更嚴重
- 因此「inline marker 補上 H1 缺口」的 EM 提升(+24pp)**已經是經過 (A) 條件 underestimate 的下界**

---

## Local-vs-global caveats

當前證據的 local 性質:

- 30 題 sample 不足以做穩健統計推論(95% CI 寬)
- gpt-4o-mini 在 temp=0 仍有 nondeterminism(q6 兩次 run 結果不同)
- 30 題的 GT counterfactual-strength 沒有 label(無法分離 H3 因素)
- Zep 因為內部 LLM 不可換,backbone-swap 實驗只能對 final inference 做
- (A) 診斷格式對 gpt 的負向干擾(EM 0/30)可能影響 LLM-side recall 觀察

下一步擴大驗證的 priority:

1. **HippoRAG plain inference 在 gemini 上跑全 100 題**,得 plain backbone-swap baseline EM,看是否 H1/H2 在 gemini 緩解後整體 EM 仍 < RPT
2. **跑 RPT-min/RPT 在同 30 題 smoke test 條件**,看 candidate-recall × EM 改善幅度,直接驗證 H1+H2
3. **標 30 題 counterfactual-strength**,測 H3 在不同強度子集的差異

---

*資料截止:2026-04-28(smoke test gpt-4o-mini + gemini-FL on 30 fair-condition MH targets)*

---

## Strategic pivot — LLM-reasoning 分析停在這裡(2026-04-28)

### 為什麼此路有 diminishing returns

1. **RPT / RPT-min 本身 overfit on FC**:強指令 + section A/B 分區 + `[CURRENT]/[OUTDATED]` marker 是針對「序號越大越新」這個 FC 規則設計的,**換到其他 memory benchmark(LongMemEval / RecSys 等)會傷害 HippoRAG-v2 的通用記憶能力**。把 RPT 當作 paper main contribution 在 generalization 上有風險。
2. **LLM 是黑盒,(A)/(B)/(C) 條件觀察的是 probing 結果,不是真實 internal state**:用診斷 prompt 強制 LLM 暴露 reasoning,得到的是「LLM 被要求列時能列多少」(upper bound);真實 (C) 條件下的 attention 我們其實沒辦法直接量化(model weights 不公開、attention map 對 cloud LLM 取不到)。
3. **gpt-4o-mini temp=0 nondeterminism** + **(A) 條件對 gpt 反而傷害 EM**(從 6.7% 跌到 0%)→ 即使我們做了大樣本量化,也很難確認觀察結果在「真實 inference 黑盒下」是否一致。
4. **驗證 framing 的最 rigorous plan(SH+MH × 100q × 2 conditions × 3 methods,~900 calls)會花掉大量時間,但對 paper main contribution 的決定性已經不高**——我們已經知道 RPT 有效、知道 H1 是核心、知道 inline marker + 強指令是 prompt-side 的天花板組合。

### 我們在此 session 學到的、值得保留的核心結論(2026-04-29 更新版)

不深挖的前提下,以下是 paper / 後續設計可以放心拿來用的結論:

1. **Per-hop 知識識別是 LLM-side 的核心瓶頸**(不是「conflict 特殊困難」、也不是「多跳推理本身難」)。多跳 EM 崩潰主要來自單一 hop 識別不可靠 × 鏈式乘法傳播。Sim-OB chain-only 98% 證明 LLM 純多跳能力不是問題。
2. **不同 channel 的 inference-side ceiling 不同**:OA2 retrieval-filter 55% (orig) / 83% (modified+trailer);RPT inference-marker 68%;Sim-OB chain-only 98%。**filter ceiling > annotation ceiling**(per SESSION §4.5)。
3. **Retrieval-time filter 是最 leveraged 的方向**:OA2 fact-level filter 不改 prompt 即可 +32pp on FC-MH(原 prompt 條件)。Inference-side annotation(PAT/RPT)邊際遞減,且 RPT 對 FC overfit 不可部署。
4. **「detection 越準 + 訊號傳遞給 inference 越清晰」是 channel design space 的兩個維度**。SESSION doc 把 9 個 oracle 實驗組成 detection-to-inference channel benchmark,production 系統(Zep/Mem0)可以 plot 在這個 spectrum 上做位置定位。
5. **Trust gap 是 hard ceiling**:LLM 即使看到顯式 `[OUTDATED FACT]` + `DO NOT USE` 仍有 ~32% 機率採信舊事實。意味 inference-side prompt engineering 在 RPT 已 saturate,剩下的 +15pp 必須靠把 conflict-resolution responsibility 從 LLM 移走(move detection upstream)。

### 為什麼 LLM-reasoning 分析仍有價值(沒白做)

- **量化了三條基準線**:Floor 23% / Annotation ceiling 68% (RPT) / Filter ceiling 83% (OA2 modified) / Pure LLM ceiling 98% (Sim-OB)。這給 detection-side 設計者一個明確的「應該往哪邊推」的地圖
- **identified Zep 的核心缺陷**:invalid_at 訊號 LLM 0% 識別、per-hop 觸發率只 50%——這對「我們設計自己的 detection 機制時要避免什麼」是直接 instruction
- **identified RPT 的 overfit 限制**:section A/B 結構 + MUST 指令對 FC 序號規則太特化,**不可放進 multi-task production memory system**——這明確排除一條設計路徑,讓我們聚焦在 retrieval-time intervention
- **identified Trust Gap**:即使 perfect annotation,LLM 仍有 ~32% 機率採信舊事實——意味著「移除 detection responsibility from LLM」(filter 路線)比「強化 LLM 對 detection signal 的信任」(annotation 路線)更可行

### 下一階段的核心問題:從 detection mechanism 重新出發

把焦點從「inference prompt 怎麼設計」轉到:

> 假設我們從 HippoRAG-v2 重新設計 conflict detection,**(A) 偵測準確度**與 **(B) 偵測結果如何傳遞給 inference** 兩個維度怎麼選擇與設計?

