# FC-SH 6k Weak-Model Analysis (gemma3 1b/4b/12b/27b, GX10)

> **本檔取代** [`weak_model_case_study.md`](weak_model_case_study.md) 的頭條指標(舊檔用 standalone Resolution + 舊 matcher;其機制段落 [三關卡漏斗、"一致性 not 正確性"] 仍為有效 backing)。
> **分析結構(定案)**:① E2E Acc 看整體(客觀,全 backbone)→ ② 說明 1b/4b 為何**不能**用 cross-tab(附證據)→ ③ 12b/27b 才做 cross-tab 歸因觀察。
> **資料**:`outputs/…__gemma3-{s}/…/results.json`(EM,全 N=100 已驗證,排除 smoke 檔)、`analysis/results/sh_6k_RUN_gt.json`、[`pool_acc_crosstab_gemma_6k.md`](pool_acc_crosstab_gemma_6k.md)(matcher v4)。

---

## ⚠️ 前提:GX10 弱模型實驗是 per-backbone gemma extraction

GX10 matrix wrapper 設 `MEM0_TRIPLE_MODEL=gemma3:$SIZE`,**每個 backbone 用自己的 gemma 做 P1 抽取**(各自 cache `analysis/results/p1_caches__gemma3-{s}/`),**非**共用 gpt-4o-mini。這與 Mac 端「backbone=gpt-4o-mini 做整條 pipeline」一致 —— **backbone = 做整條 pipeline(抽取+解析+作答)的那個模型**。

含意:
- ✅ **同一 backbone 內、方法之間的比較是公平的**(struct / no_p5 / p3_only / b 在同一 size 都用同一份該 size 的 extraction)→ paper 主 claim「結構化 KU 解析 vs LLM-judgment KU 解析」靠這個 **within-backbone gap**,extraction 已被控制。
- ⚠️ **跨 backbone 趨勢**同時反映抽取品質 + 解析品質(誠實的「整條 pipeline 跑在弱模型上」)。
- ⚠️ **弱模型抽取會退化**(見 §2)→ 這是可入 paper 的誠實證據,但也讓 cross-tab 在 1b/4b 失效。

---

## § 1  E2E Exact-Match(客觀頭條,全 backbone 有效)

主指標 = FC-SH `has_pair` 官方 **substring-EM**(有 old/new 對照的 KU 主戰場,分母 74);括號附 overall(/100)。全 N=100 驗證。**2026-07-11 canonical migration**(strict → MABench 官方 `substring_exact_match`;數字經 `rescore_canonical.py` 驗證)。

| Method | 1b | 4b | 12b | 27b | 隔離的變因 |
| :-- | :-: | :-: | :-: | :-: | :-- |
| **ours_struct** ((S,P)+argmax, no query-LLM) | **32**/52 | **54**/79 | **73**/99 | 71/97 | 結構化 KU(determ.)|
| **ours_no_p5** (struct + P3 LLM grouping) | 27/44 | 54/79 | 73/99 | **73**/99 | +P3 identity grouping |
| ours_p3_only (P3 over top-100, no (S,P)) | 8/27 | 26/50 | 46/72 | 33/59 | 去掉 (S,P) 結構鍵 |
| (b) mem0+P1 (write-time destructive) | 0/5 | 0/11 | 44/64 | 37/54 | write-time commit |
| (a) vanilla mem0 (native extract+destr.) | — | 0/11 | 32/53 | 29/45 | +native 抽取 |
| Zep (decoupled write-time graph) | 20/29 | 18/32 | 43/58 | 42/62 | decoupled write-time |

**觀察(對應 paper 主 claim)**:
1. **ours(struct / no_p5)在每個 backbone 都主導**;所有 write-time baseline(b / vanilla / Zep)在弱端崩得最重 → 「KU 是 query-time 問題」的 backbone-gap 證據:backbone 越弱、gap 越大。
2. **write-time destructive 在 1b/4b 直接歸零**(b=0/0、vanilla=0):mem0 的 update-LLM 在弱模型上產不出正確 schema(1b 回音 "Name is John" 範例、store 近乎空),**一旦 write-time 誤刪即不可逆** → 這正是 paper 在批的機制,在弱模型上以最極端形式出現。
3. **p3_only(拿掉 (S,P)、純 LLM grouping)在弱端崩**(8/27 vs struct 32/54):對 top-100 一次判 identity 對弱模型 intractable → **反向確立 structural pre-routing 的必要性**。
4. **P3 是 capability-gated**:no_p5 − struct 的 has_pair Δ = 1b **−5**(P3 反害)、4b/12b **0**(中性,structural 已足)、27b **+2**(P3 微幫)。弱模型上加 LLM 判斷是 liability,強模型上才是 asset。
5. **官方 SubEM 下 27B「dip」幾乎消失**:strict-EM 的 no_p5 27b=70、struct=65(has_pair),官方 SubEM 為 **73 / 71**(no_p5 與 12B 齊平)。原 dip 多為 verbose-correct 被 strict 冤枉,**真 override 殘留 struct 2、no_p5 1 題**(見 §3)。
6. **has_pair < overall**:has_pair 是 KU 衝突題,難度高於整體;gap 在 has_pair 上更清楚。

---

## § 2  為什麼 1b/4b **不能**用 cross-tab(附證據)

cross-tab 的 pool-state 軸靠 **matcher v4 把「抽出來的 fact 表面」對到 GT 表面**。在 per-backbone gemma extraction 下,**弱模型(1b/4b)抽出的 fact 字面偏離 GT** → matcher false-negative → `old_only/neither`(NEW-absent)桶被灌水,**分不清「抽取真的丟了 NEW」還是「matcher 對不上 gemma 的措辭」**。三項證據:

| 證據 | 1b | 4b | 12b | 27b |
| :-- | :-: | :-: | :-: | :-: |
| store 內事實數(max ordinal 簽章) | ~370 | ~370 | ~450 | ~450 |
| retrieved top-100 與 27b 重疊 | **5**/100 | **82**/100 | 99/100 | 100(基準)|
| 單 chunk 抽取數(`af9a27ef`) | 31 | — | — | 38 |

- **若 extraction 是 held-fixed,四個 backbone 的 store 應 ~100% 重疊**(12b∩27b=99 即證)。1b=5、4b=82 的落差**全來自弱模型抽取覆蓋率/措辭差異**,非資料汙染。
- 具體:chunk `af9a27ef` gemma-1b 抽 31 facts、gemma-27b 抽 38(1b 漏掉 "quarterback→American football"、"Frank Zappa died in Los Angeles" 等)。
- **結論**:1b/4b 的 pool-state 分類不可信 → **改用 §1 的 E2E EM(客觀)+ case-study 錯誤模式**。舊 case study 的機制分析已指出 1b/4b 主錯因 = **抽取 recall + subject 抽反**(把會變的值當 subject),與此處「弱模型抽取退化」完全一致 → 兩條證據互相佐證。

> 一句話:**1b/4b 的失分主要是「抽取軸」(弱模型抽不全/抽歪),不是「解析軸」**;而 matcher 無法在弱模型的措辭上可靠標記 pool,所以我們只用客觀 EM + 舉例,不硬套 cross-tab。

---

## § 3  12b/27b 的 cross-tab 歸因觀察(可信:抽取對齊 GT、pool-missing=0)

12b/27b 的 gemma 抽取措辭對齊 GT(store 與 27b 99–100% 重疊、cross-tab `pool-missing=0`)→ pool-state 可信。逐格(matcher v4,Acc = 官方 **substring-EM**,N=74):

| method | backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM |
| :-- | :-- | :-: | :-: | :-: | :-: | :-: |
| struct | 12b | **60/0** | 13/1 | 0/0 | 0/0 | 73 |
| struct | 27b | 58/**2** | 13/1 | 0/0 | 0/0 | 71 |
| no_p5 | 27b | 61/**1** | 12/0 | 0/0 | 0/0 | 73 |
| p3_only | 12b | 5/0 | 41/**28** | 0/0 | 0/0 | 46 |
| p3_only | 27b | 15/0 | 18/**41** | 0/0 | 0/0 | 33 |

**三個嚴謹論述:**

1. **struct 在強端把 pool 清乾淨**:12b/27b 的 `old_only=neither=0`(NEW 從不缺席)、`new_only` 主導(60 / 58)。結構化 (S,P)+argmax **確實把 KU 解析對** —— 這是「structural 是 workhorse」的直接證據,且**不倚賴 answer LLM 從混雜 pool 挑對**。

2. **struct 12b→27b 的 EM 微降(73→71)是 reader override,不是方法退步**:兩者 pool 一樣乾淨(old/neither=0),差別純在 `new_only ✗` = **2**(27b)vs **0**(12b)—— 27b 拿到「只含新版」的乾淨 pool,卻用參數先驗吐**舊值**(qid 19/57)。**官方 SubEM 下 override 已縮至 2 題**(strict-EM 的 7 題有 5 題其實是 verbose-correct 被 strict 冤枉);override 是 reader 特性,與 KU 方法正交。

3. **P3 在強端修 override**:no_p5 27b 的 `new_only ✗` 從 struct 的 2 降到 **1**,且把部分 `both` 收斂成 `new_only`(61 vs 58)→ EM 71→73。**P3 identity grouping 在強 backbone 上收緊 pool、壓制 override**(呼應 §1 觀察 4 的 capability-gate;官方 SubEM 下 override 本已小,P3 淨效益隨之縮至 +2pp)。

4. **p3_only 的崩,機制看得見 = 「卡在 both」**:12b 有 **69/74** 停在 `both`(41+28)、27b **59/74** 停在 `both`(18+41),`new_only` 只 5 / 15 → LLM grouping **沒把 new/old 併掉、pool 仍混**,reader 只能猜(27b 在 both 裡更常答舊,✗41)。→ 去掉 (S,P) 後 LLM 對 top-100 判 identity 失效,pool 無法乾淨。

**小結(接 paper 主 claim)**:強端可信 cross-tab 顯示 —— (i) 結構化 KU 把 pool 清乾淨(new_only 主導、NEW 不缺席);(ii) 唯一殘餘失分是 27b reader override,而 P3 能部分修;(iii) 拿掉 (S,P) 的 p3_only 因「卡在 both」而崩。三者共同支撐「**KU 是 query-time 問題,structural (S,P)+temporal 是 backbone-robust 的骨幹;LLM-judgment 在弱模型上崩**」。

---

## 附:與其他檔的關係

- **E2E 主表(跨機器)**:[`fc_sh_has_pair_main_table.md`](fc_sh_has_pair_main_table.md)(Mac gpt-4o-mini/gpt-4.1-mini)+ 本檔(GX10 gemma)合成 backbone-gap 敘事。
- **機制 backing**(仍有效,忽略其 standalone-Resolution 頭條):[`weak_model_case_study.md`](weak_model_case_study.md) 的三關卡漏斗、"一致性 not 正確性"、6k ordinal-tie、p3_only confound 診斷。
- **資源(時間/RAM)**:`docs/handoff/gx10_run_log.csv`(size_vram 1.3/5.5/11.2/21.1 GB、peak-sys 12/16/21/31 GB)。
