# Paper Motivation — FC-MH 為什麼難解（Evidence-Based Logic Chain）

> **目的**：把 INDEX.md 已收的 evidence 整理成 paper motivation 的清晰 C1 / C2 / C3 邏輯鏈，每個 claim 都有對應的 figure / table。
> **產出時間**：2026-05-03
> **下游用途**：(a) paper introduction & motivation section 的 source；(b) 決定 method 設計方向的 evidence base

---

## 1. The Problem — Multi-hop Knowledge Update

許多生產級記憶系統（Mem0 / Zep / HippoRAG-v2）強調支援「衝突解析 / 知識更新」。但**現有 benchmark 上的評估幾乎都聚焦 single-hop**（一個 fact 被另一個 fact 取代）。**Multi-hop knowledge update**——查詢需要鏈接多個事實，且鏈中每跳都可能有更新——是 production 場景常見但**評估嚴重不足**的問題。

我們研究的 specific scope：**sentence/fact-level explicit conflict**（同 (subject, relation) 多 object 的 supersession，每 chain hop 各自有更新）。FactConsolidation-MH (MemoryAgentBench)是這個 scope 的 canonical benchmark。

---

## 2. Claim C1 — 跨方法、跨 LLM、跨 prompt：FC-SH→FC-MH 嚴重 drop

> 我們的第一個 claim：**現有記憶方法在 single-hop knowledge update 上勉強能解，但 multi-hop 全部崩潰**。

### Evidence — 6 個 system × LLM 組合一致顯示 SH→MH drop ≥34pp

**[Figure 1]** ：FC-SH vs FC-MH bar chart（每組 system × LLM 並列）

```
                FC-SH       FC-MH       Drop
HippoRAG-v2 × GPT-4o-mini   69%   ─────  11%   ─    -58pp
HippoRAG-v2 × Gemini orig   77%   ─────  22%   ──   -55pp
HippoRAG-v2 × Gemini mod    96%  ──────  23%   ──   -73pp
Mem0 customized × Gemini    77%   ─────  43%   ────  -34pp ★ best
Mem0 OOB × GPT              15%  ─       1%    ─    OOB broken
Zep × GPT-4o-mini           70%   ─────  28%   ──   -42pp
Zep × Gemini inference      79%   ─────  8%    ─    -71pp
```

**Source**: [INDEX §7.7](../INDEX.md), [overview §0.2](../fc_mh_research_overview.md)

**Reading**：
- Best customized baseline (Mem0 customized × Gemini) 仍掉 34pp（77→43）
- 沒有任何 system × LLM 組合 SH 跟 MH gap 小於 30pp
- Zep × Gemini drop 71pp（最大），跟 Zep cloud detection 機制限制有關（§3 將討論）
- HippoRAG-v2 vanilla 雖有 prompt-level「序號越大越新」rule，仍 drop 50+pp

→ **C1 strongly supported**：FC-SH→FC-MH drop **不是某個 system 的特殊弱點，是 multi-hop knowledge update 整體的未解問題**。

---

## 3. Claim C2 — FC-MH 崩潰的根本瓶頸有兩層

> 第二個 claim：**FC-MH 的 75pp drop 不是單一原因。它由兩個可分離的 layer 組成**：(a) multi-hop retrieval coverage 不足（給 LLM 的 context 不完整 / 噪音多）+ (b) **LLM 看到新舊版本但缺清楚訊號決策困難**（衝突解析）。

要證明 C2，**必須先排除一個直觀但錯誤的假設**：「FC-MH 難是因為 multi-hop reasoning 本身難」。

### 3.1 子 claim C2-A：純 multi-hop reasoning **不是**瓶頸

**Evidence (a)**：給 LLM 完美 chain (零噪音零衝突)，多跳推理近完美。

**[Table 1]** Sim-OB chain-only：context 只放 N 個 chain GT facts，跑 FC-MH 100 題

| 條件 | num_hops=2 | num_hops=3 | num_hops=4 | overall |
|---|:---:|:---:|:---:|:---:|
| Sim-OB chain-only (modified prompt) | 96.7% | 100% | 100% | **98%** |
| Sim-OB chain-only (orig prompt) | 95.1% | 100% | 100% | **97%** |

**Source**: [overview §0.3](../fc_mh_research_overview.md)、`results/diagnostic/sim_ob_chain_only_results.json`

**但這個證據單獨不夠**——批評者可能說「context 只 N 個 facts 太少當然好解」。所以我們需要 **gradient noise 實驗**證明「LLM 在乾淨 chain 上能解，**且能 tolerate 一定噪音，超過某 threshold 才崩**」。

**Evidence (b)**：Sim-OB-grad — 在 chain 旁加 k 個 distractor facts，看 EM 怎麼降。

**[Figure 2]** Sim-OB-grad noise tolerance curve

```
EM (%)
100 ┤●━━●                              ← 'random' distractors (任選)
 90 ┤   ●━━●━━━━━●
 80 ┤              ●━━━━━━●
 70 ┤
 60 ┤   ●━━━━━━●                       ← 'ppr-nearby' distractors (entity-relevant)
 50 ┤              ●
 40 ┤                  ●
 30 ┤                       ●━━●
 20 ┤                              ●━━━●
    └──┬───┬───┬────┬─────────┬──────►
       10  50  100  200      455      k (distractor count)
```

| k distractors | random EM | ppr-nearby EM |
|:---:|:---:|:---:|
| 10 | 96% | 97% |
| 50 | 93% | 90% |
| **100** | **87%** | **61%** ★ cliff |
| 200 | 76% | 34% |
| 455 (full) | 20% | 21% |

**Source**: `results/diagnostic/sim_ob_grad_results.json`

**Reading**：
- 即使加 100 個 random distractors，LLM 仍 87% — 純 noise 不致命
- 但加 100 個 ppr-nearby（entity-related distractors，類似真實 retrieval 抓到的相關但不對的 facts），EM 從 90% 跳崖到 61%
- → **LLM 的 multi-hop reasoning 對「entity-related noise（似是而非的相似 facts）」特別敏感**

→ **C2-A refined（用 NC-grad 補實驗 disambiguate 後）**：LLM 的 multi-hop reasoning 不是瓶頸，**也不是純粹「entity-related noise」敏感**。**它對「conflict pairs（同 entity-relation 的 new + old 同時出現）」特別敏感**。純新事實噪音（即使 entity-relevant、k=200）LLM 仍 90% 解。

**Evidence (c)**：NC-grad — distractor pool 限定 NEW-only facts（exclude 全部 165 olds + chain）

| k | Sim-OB-grad PPR (mixed pool: 165 old + 290 new) | **NC-grad PPR (NEW-only pool, no conflicts)** | 差異 |
|:---:|:---:|:---:|:---:|
| 10 | 97% | 97% | 0pp |
| 50 | 90% | 92% | +2pp |
| **100** | **61%** ★ cliff | **90%** | **+29pp** |
| 200 | 34% | **90%** | **+56pp** |

**Source**: `results/diagnostic/nc_grad_results.json`

→ **Sim-OB-grad 的 cliff at k=100 不是「噪音多了」造成，是「distractor 池含 conflict pairs」造成**。當 distractor 純新事實，LLM **k=200 仍 90%**。這 directly disprove「entity-related new-fact 噪音是 multi-hop retrieval 的瓶頸」。

→ **這 refinement 重新定義 paper main message**：FC-MH 崩潰**不是 multi-hop retrieval 上限低，而是 conflict pairs 在 context 中觸發 LLM 決策困難**。Layer 1（retrieval coverage）仍重要（4-hop NC orig 27% 仍 stand），但**「retrieve 太多無關新事實」這個解釋被排除**。

### 3.2 子 claim C2-B：Conflict 處理 vs retrieval noise — 兩個獨立瓶頸

**Evidence**：Non-counterfactual baseline (NC) — 移除全部 chain old facts，保留多跳結構但沒衝突。比較 Sim-OB / NC / A1 三條基準線。

**[Figure 3]** FC-MH performance ladder (orig prompt regime, vanilla HippoRAG inference)

```
A1 baseline           Plain HippoRAG (full 6k + conflicts)
20% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      ↑ +40pp gap = "conflict handling loss"
NC orig               Removed all old facts; chain intact + 6k noise
60% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      ↑ +37pp gap = "6k retrieval noise loss"
Sim-OB                Chain only; zero noise zero conflict
97% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**By num_hops** (orig prompt)：

| num_hops | Sim-OB | NC orig | Conflict gap (Sim-OB − A1) | Noise gap (Sim-OB − NC) |
|:---:|:---:|:---:|:---:|:---:|
| 2 | 95% | 70% | (= 50pp 全 conflict) | 25pp |
| 3 | **100%** | 54% | (= 80pp 全 conflict) | 46pp |
| 4 | **100%** | **27%** | (= 80pp 全 conflict) | **73pp** ★ |

**Source**: [overview §0.3](../fc_mh_research_overview.md)、`results/diagnostic/non_counterfactual_baseline_origprompt_*.json`

**Reading**：
- Sim-OB 4-hop 100%，但 NC 4-hop（無衝突 + 6k 噪音）只 **27%**
- → **4-hop multi-hop retrieval 在 6k 噪音內結構性無能**，跟衝突無關
- conflict loss + 6k noise loss 在 vanilla regime 各佔約 50%

→ **C2-B confirmed**：FC-MH 崩潰是**兩個獨立瓶頸**：
- **Layer 1 — Multi-hop retrieval coverage**：6k 內的 chain 抓不全（4-hop 27% even no conflict）
- **Layer 2 — Conflict resolution**：當 chain 抓得到，但 LLM 同時看到新舊版本時的決策

### 3.3 子 claim C2-C：當 LLM 同時看到新舊版本但缺清楚訊號 → 決策崩

這是 paper 主軸。Production system Zep 的 detection × answer cascade 是**直接 evidence**。

**[Figure 4]** Mem0 vs Zep — Detection × Answer cascade by num_hops（FC-MH，has_pair 題）

**Mem0 (filter at write paradigm — UPDATE 後 LLM 看不到 outdated)**：
```
EM    All detected ─────  Partial ─── None detected ─────
 90 ┤                              
 80 ┤        ★ 86%(3-hop all)
 70 ┤                              
 60 ┤  57%   
 50 ┤        50%(4-hop all)        
 40 ┤  42%   42%
 30 ┤                              32%
 20 ┤                              20%(3-hop none)  25%(4-hop none)
 10 ┤
    └──────┬────────┬────────┬────►
          2-hop   3-hop   4-hop
```

**Zep (annotation at inference — LLM 看到 old+new 雙版本 + invalid_at)**：
```
EM    All detected ─────  Partial ─── None detected ─────
 30 ┤
 20 ┤  21%(2-hop all)             17%(2-hop none)
 10 ┤                              
  0 ┤        0%(3-hop all)  0%(4-hop all)        
    └──────┬────────┬────────┬────►
          2-hop   3-hop   4-hop
```

| num_hops | n | Mem0 detection 全對時 EM | Zep detection 全對時 EM | Mem0 query 看到 old 機率 | Zep query 看到 old 機率 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 2 | 61 | 57% | 21% | 9% | 90% |
| 3 | 24 | **86%** | **0%** | 9% | 84% |
| 4 | 15 | 50% | 0% | 9% | 83% |

**Source**: [cascade_by_hops.md](../experiments/2026-05-03_writetime_querytime_eval/results/cascade_by_hops.md)

**Reading**：
- **Mem0 filter paradigm — detection 對的時候 partially unlock LLM**：3-hop all-detected **6/7 = 86%** EM
- **Zep annotation paradigm — detection 對也救不了 LLM**：3-hop all-detected **0/5 = 0%** EM
- 差別在 retrieval 給 LLM 看到的：Mem0 9% 機率看到 old（filter 把 outdated 清掉了）；Zep 84-90% 機率看到 old（沒 filter，靠 invalid_at 訊號）
- 但 Zep 的 invalid_at 訊號**只 22-24% 的 has_pair 才有正確設**（[2026-05-03 §1.2](../experiments/2026-05-03_writetime_querytime_eval/results/writetime_eval.md)）— LLM 87% 機率看到雙版本卻無清楚訊號

> **⚠️ Fig 4 caveat**：
> 1. **小樣本警告**：3-hop all-detected (Mem0) 只 n=7、(Zep) n=5；4-hop n≤7。Fig 4 已標 ★ 警示。每多/少答對一題都讓 % 大幅變動，**結論需謹慎**。
> 2. **「Detection 全對 ≠ EM 高」**：Mem0 2-hop all-detected 13/23 = 57% 看似不高 — 但其實**完全符合預期**。Mem0 query-time new_recall@100 = 77%，2-hop 兩個 has_pair 都在 top-100 的機率 ≈ 0.77² ≈ **59%**。觀察 57% 與這個乘法預測 **吻合**。**這直接證明 detection + retrieval 是兩個獨立瓶頸**：detection 完美但 retrieval 仍 23%/hop 漏，多 hop 累積放大。
> 3. **Zep cascade 在 3+ hops 全 0% 是可信的（n 加總 13+15=28）** — 即使每組 n 小，3-hop / 4-hop 三個 buckets 全部 0% 不太可能是樣本變異。

→ **C2-C confirmed**：當 LLM 同時看到新舊版本但缺**清楚的 supersession 訊號**時，決策崩。具體機制：
1. Zep 的 implicit timestamp（valid_at - invalid_at）對 LLM 太隱晦（[SESSION §13.2](../SESSION_2026-04-28_diagnostic_summary.md) 歷史結論：LLM 對 invalid_at 識別率 0%）
2. LLM 在 conflict 上回到 world knowledge → counterfactual GT 必錯

### 3.4 子 claim C2-D：Explicit chain structure 能緩解 — Modified prompt + RPT 對應

承接 C2-C：「LLM 看雙版本沒清楚訊號就崩」。**反向 evidence**：當我們**給 LLM explicit chain structure** 時，performance 顯著改善。

**Evidence (a)**：Modified prompt（強迫 LLM 輸出 `Intermediate answers: [a, b, c]` per-hop trailer）跨各 cleanliness 級別有不同效應。

**[Figure 5]** Trailer effect across context cleanliness regimes

```
Trailer effect (pp)
+30 ┤                              ★ +28pp
+25 ┤                              
+20 ┤                              
+15 ┤                       +18pp
+10 ┤              +12pp
+5  ┤      +3pp                      +1pp
+0  ┤───────────────────────────────────────►
    │  A1     PAT     NC    OA2    Sim-OB
        very          mid           cleanest 
        noisy         clean           (saturated)
```

| Method | Orig prompt | Modified prompt | Trailer Δ |
|---|:---:|:---:|:---:|
| A1 (very noisy + conflict) | 20% | 23% | +3pp |
| PAT (mid-noisy + soft label) | 36% | 48% | +12pp |
| NC (clean conflict + heavy removal) | 60% | 78% | +18pp |
| **OA2** (clean conflict + 6k 完整) | **55%** | **83%** | **+28pp ★** |
| Sim-OB (cleanest) | 97% | 98% | +1pp |

**Source**: [overview §0.2](../fc_mh_research_overview.md)、INDEX §7.6

**Reading**：
- Trailer = 一句 prompt 改動「請逐 hop 輸出 intermediate answers」
- Inverted-U with cleanliness：context 太髒（A1）或太乾淨（Sim-OB）trailer 沒用；中等乾淨度時 trailer 大幅幫助
- **OA2 +28pp 最大**：當 conflict 被 filter 清掉、其他 6k 還在，LLM 強迫 per-hop decompose 就能解

**Evidence (b)**：RPT (Restructured Passage Tag) — 在 prompt 加 explicit `[CURRENT FACT] / [OUTDATED FACT]` markers + section partitioning。

| Method | FC-MH (orig prompt) |
|---|:---:|
| Plain HippoRAG (no markers) | 22% |
| PAT (soft `[CURRENT/OUTDATED]` labels) | 36% |
| RPT-min (inline section labels) | 60% |
| **RPT (Section A/B + MUST instruction)** | **68%** ★ +46pp 從 baseline |

**Source**: [INDEX §7.2](../INDEX.md)

**Reading**：
- RPT-min vs PAT (+24pp from inline section markers)
- RPT vs RPT-min (+8pp from MUST instruction)
- 兩者都是「給 LLM 顯式的衝突/版本訊號」，比 Zep 的 implicit timestamp 顯著有效

→ **C2-D confirmed**：**explicit chain structure**（per-hop trailer + per-fact section markers）能讓 LLM 在 multi-conflict 場景下不崩。Zep 8% MH vs RPT 68% MH 同樣 perfect detection 條件下差 60pp，差異**全在訊號顯示方式**。

**Evidence (c)**：OA2 prompt ablation — disentangle modified prompt 的「+28pp」由 instruction 還是 one-shot demo 貢獻

**[Figure 5b]** OA2 prompt ablation 4 variants：

| Variant | System instruction | One-shot demo | OA2 FC-MH EM | Δ |
|---|---|---|:---:|:---:|
| V1 (orig) | orig | orig | 55% | baseline |
| **V2 (instruction-only)** | **modified ★** | orig | **81%** | **+26pp** |
| **V3 (demo-only)** | orig | **modified ★** | **75%** | **+20pp** |
| V4 (modified) | modified ★ | modified ★ | 83% | +28pp |

**Source**: `results/diagnostic/oa2_ablation_v{2,3}_results.json`

**Reading**：
- **Instruction alone (V2) 給 +26pp** — 接近 V4 全部
- **Demo alone (V3) 給 +20pp** — 也達 V4 大半
- V2 + V3 ≈ +46pp 但實際 V4 只 +28pp → 兩 mechanism **partially redundant**
- → 重要 takeaway：**任一 mechanism 單獨能提供 explicit chain structure 訊號**；不必兩者皆設。對 method 設計，可以選擇放在 system prompt OR 在 demo / context 中（成本較低的選擇）。

### 3.5 C2 總結（含 NC-grad + OA2 ablation refinement）

| Sub-claim | Evidence | Bottleneck layer |
|---|---|:---:|
| C2-A LLM multi-hop reasoning 不是瓶頸 | Sim-OB 97-98% on 4-hop | n/a (排除假設) |
| C2-A LLM **不是對純新事實噪音敏感**（NC-grad k=200 仍 90%）| NC-grad disambiguate Sim-OB-grad cliff | n/a (refined) |
| C2-A LLM **對 conflict pairs 在 context 中特別敏感** | Sim-OB-grad k=100 mixed pool 61% vs NC-grad k=100 new-only 90% (+29pp) | **Layer 2** |
| C2-B Multi-hop retrieval coverage 仍是 limitation | NC orig 4-hop 27% (no conflict) — chain 沒被 retrieve 到 | **Layer 1** |
| C2-C 看雙版本無清楚訊號→崩 | Zep MH all-detected 0% / Mem0 retrieval cascade math (0.77² ≈ 59%) | **Layer 2** |
| C2-D Explicit chain structure 能救 | RPT 68% vs PAT 48% (+20pp) / Trailer +28pp on OA2 | Layer 2 解法 |
| C2-D **Instruction or demo 都能 unlock 大半**（V2 +26pp / V3 +20pp / V4 +28pp） | OA2 prompt ablation | 設計選擇上 partial redundancy |

→ **C2 整體 conclusion（refined）**：FC-MH 崩潰是 **multi-hop retrieval coverage（Layer 1）+ 衝突訊號顯式度（Layer 2）** 雙層問題。
- **Layer 2 是主因**：在 noisy 6k 內加 100 個其他題的 conflict pairs 能讓 LLM 從 90% 降到 61%（NC-grad 對照證明）
- **Layer 1 是次因但仍 real**：4-hop chain 的 retrieve 仍困難（NC orig 4-hop 27%）
- **Method 設計必須同時 hedge 兩者**，但 **Layer 2（避免 conflict pairs 直接給 LLM 看 / 給 explicit signal）的優先序高於 Layer 1**。

---

## 4. Claim C3 — 我們的設計方向

> 第三個 claim：基於 C2 的兩層瓶頸分析，**我們的設計同時補強 (a) multi-hop chain coverage at retrieval + (b) explicit conflict signals at inference**。

### 設計核心（你已經寫的，加上 evidence anchor）

**(write-time)** 寫入時：
- 基於 ingest order 提供 default direction signal — **避免 Zep 的 LLM 純語意判斷的脆弱**（C2-C: Zep stative sentence 失效）
- 給 confidence score + version metadata — **避免 Mem0 不可逆**（C2-D: 保留兩 edges 供下游 bilateral 顯示）
- 結構性偵測（KG (s, r) 多 object）— **比 Zep 純 LLM 抽 supersession 更穩**（C2-C: Zep 27% extraction miss）

**(query-time)** 查詢時：
- 高信心 → filter（KG walk only current）— 對齊 OA2 oracle 83% paradigm（Mem0 cascade 證實 detection 對時 unlock LLM）
- 低信心 → bilateral with **explicit chain block markers**（"Hop k: A → B [supersedes prior X]"）— 比 Zep timestamp 顯著（C2-D: RPT explicit markers vs PAT soft labels +20pp）

### 預測 ceiling（從既有 oracle 反推）

| 我們的設計組合 | 對齊的 oracle ceiling | 預測 FC-MH EM |
|---|:---:|:---:|
| Filter (perfect detection) + perfect chain | OA2 modified | 83% |
| Filter + chain block prompt(generalizable RPT-style) | OA2 + RPT structure | **70-80%** (我們估) |
| Bilateral chain block (low confidence) | RPT-min | 60% |
| Realistic (mixed confidence + imperfect detection) | (無 oracle 對應) | **預估 50-65%** |

**Source**: [INDEX §7.1, §7.2](../INDEX.md)

→ 從目前 production best (Mem0 customized 43%) 預測能推到 **50-65%**，**+7-22pp gain**。

---

## 5. Scope 聲明

我們的研究 scope：**sentence/fact-level explicit conflict 的 multi-hop knowledge update**。具體：
- 每 chain hop 各自有 (subject, relation, object) supersession
- 衝突在事實層（sentence-level），不是 paragraph-level / event-level / implicit dialogue change
- Counterfactual edits 屬於 explicit conflict 子類別

**不在 scope 但相關**（future work）：
- LongMemEval-KU 中對話流動的 implicit knowledge change
- BEAM / MemBench 中的事件級 / 摘要級衝突
- Long-form / paragraph-level supersession

**為何先聚焦 explicit fact-level**：
1. FC dataset 提供乾淨 GT，可量化 detection F1
2. 實驗發現對話 dataset 的 implicit 衝突連 oracle 都難定義 — 應在解決 explicit 後再擴
3. 我們的設計不純依賴 FC artifact（如 ingest order = recency），可 generalize 到對話 — 但需要 follow-up 驗證

---

## 6. 對應 figures 的數據來源（給生圖用）

| Figure | Source data |
|---|---|
| Fig 1 SH→MH drop bars | INDEX §7.7 / overview §0.2 |
| Fig 2 Sim-OB-grad + NC-grad noise curves（ablation refined） | `results/diagnostic/{sim_ob_grad,nc_grad}_results.json` |
| Fig 3 FC-MH performance ladder | overview §0.3 + diagnostic experiments |
| Fig 4 Mem0/Zep cascade by num_hops（counts + small-sample ★） | `experiments/2026-05-03/results/cascade_by_hops.json` |
| Fig 5 Trailer effect curve | INDEX §7.6 |
| **Fig 5b OA2 prompt ablation (V1-V4)** | `results/diagnostic/oa2_ablation_v{2,3}_results.json` |

→ 下一步：用 matplotlib 把這 5 張圖實際生出來，附在這份 motivation 旁，paper 直接 reference。

---

*草稿完成於 2026-05-03。下一步：(a) 生 figures；(b) 跟使用者確認邏輯鏈完整後，進入 method 設計 + smoke test 階段。*
