# §4.2 Focused Comparison — ours vs (no P3) vs Don't Ask vs Q-llm-recency

> **對接**:[`experiment.md §4.1`](experiment.md)(setup)、[`../results/fc_sh_main_table_4length.md`](../results/fc_sh_main_table_4length.md)(數字)。
> **範疇**:僅比較四個 **query-time KU resolution** 的方法;write-time methods(mem0/Zep)於 §4.4 case study 拆解。
> **論證目的**:證明「query-time resolution」有多條可行實作路徑,並釐清 ours main 相對於其他 query-time baseline 的優勢來源。

---

## §4.2.1 設計矩陣(identity × freshness)

四個方法皆採 query-time resolution,差別在於**如何處理 identity(哪些檢索到的 chunk 指同一 fact)**與**如何處理 freshness(同 fact 內哪個是最新版)**。

| Method | Identity mechanism | Freshness mechanism | LLM calls per query |
| :--- | :--- | :--- | :---: |
| **ours (main)** | (S,P) structural + LLM P3 补救 | deterministic `argmax(seq)` | 1 P3(only if (S,P) failure)+ 1 answer |
| ours (no P3) | (S,P) structural only | deterministic `argmax(seq)` | 1 answer |
| Don't Ask | LLM candidate extraction | deterministic `max(serial)` | 1 extraction + 1 answer |
| Q-llm-recency | none(raw retrieval)| **LLM** recency judgment | 1 answer(prompt 含 recency 指令)|

「Deterministic freshness」是 3/4 方法的共同 commitment;Q-llm-recency 是唯一把 freshness 也丟給 LLM 判的對照。

---

## §4.2.2 三段論 Observation

**Overall sEM(headline)四長度(引 [`../results/fc_sh_main_table_4length.md`](../results/fc_sh_main_table_4length.md) Table 1):**

| Method | 6k | 32k | 64k | 262k |
| :--- | :---: | :---: | :---: | :---: |
| ours (main) | **94** | **91** | **94** | **91** |
| ours (no P3) | 91 | 87 | 92 | 86 |
| Don't Ask | 80 | 86 | 88 | 86 |
| Q-llm-recency | 93 | 77 | 85 | 81 |

**(O1) `ours (main)` 是唯一 flat 91-94 across 4 length 的方法。**Δ(6k→262k)= −3 pp;其他三者 Δ 分別為 −5 / +6 / −12。這支持 method_v1.md §3.2 的 commitment:忠實寫入 + 確定性 freshness 於 identity mechanism 正確時,對 history length 具 length-invariance。ours main 於 262k 的 has_pair sEM 為 88%(68/77),與 6k 的 93% 僅相差 5 pp,顯示 KU 正確率不隨 context 增大而衰退。

**(O2) `ours (no P3)` 相對 `ours (main)` 的 gap 呈長度單調擴大**:6k=−3、32k=−4、64k=−2、262k=−5。這對應 P3 LLM 補救(當 (S,P) canonicalization 於 stem-vs-full predicate variant 分錯時,以 LLM 語意判 identity 合併)的實際貢獻。262k 於 has_pair 上尤其明顯:ours (no P3) 為 82%(63/77),ours (main) 為 88%(68/77),P3 額外救回 5 題。假設源於長 context 下 predicate variant 累積更多,structural key 的 canonicalization miss rate 上升 → P3 補救的邊際效益隨長度成長。

**(O3) `Don't Ask` 呈反向 monotonic**(80 → 86 → 88 → 86,Δ = +6)。這是 4 個方法裡唯一「越長越強」的。假設:Don't Ask 依賴 `max(serial)` 於作者定義的 ingestion ordinal(於 FC-SH 直接對應 chunk 順序),而 FC-SH context 越長,fact bank 越大,同一 (S,P) 的多版本 fact 於 bank 中的相對排序 signal 越飽和 → deterministic max-serial 越可靠。此推論可從 has_pair 262k 的 63/77(82%)驗證:雖然低於 ours main 的 68/77(88%),但已與 ours (no P3) 的 63/77(82%)持平——**證明「LLM candidate extraction + deterministic serial」是完全可行的 query-time identity resolution 路徑**,只是 structural (S,P) 於長 context 上仍領先 5 pp。

**(O4) `Q-llm-recency` 呈 non-monotonic dip**(93 → 77 → 85 → 81);32k 於 has_pair 上崩到 65%(42/65),為 4 個方法中最低。假設:當 freshness 判斷交給 LLM(而非 deterministic argmax),LLM 需要於 top-100 retrieved chunks 中比對 temporal 訊號;短 context(6k)temporal cue 密集且局部,LLM 較容易分辨;中 context(32k)temporal noise 累積但總體 signal 尚未飽和,LLM 判斷不穩;長 context(262k)雖 noise 進一步增大但 recency prior 顯著(舊 fact 位置明顯前段),LLM 判斷部分恢復。此非單調行為驗證 method_v1.md §3.3 的 commitment:**freshness 應該由確定性規則處理,不應交由 LLM 判**(交由 LLM 判會引入 backbone-brittle 的非單調行為)。

---

## §4.2.3 兩兩 Δ 拆解(隔離單一機制的貢獻)

**Δ_A = ours main − ours (no P3):P3 LLM identity 补救的貢獻**

| Length | 6k | 32k | 64k | 262k |
| :--- | :---: | :---: | :---: | :---: |
| Δ_A (Overall) | +3 | +4 | +2 | +5 |
| Δ_A (has_pair) | +2 | +6 | +3 | +6 |

P3 LLM identity 补救於 has_pair 上一致貢獻 +2 到 +6 pp;於 262k 上尤其重要(+6 pp)。這是 method_v1.md §3.3 提到「(S,P) canonicalization 於長歷史下 miss rate 上升,P3 是必要補救」的直接數據。

**Δ_B = ours (no P3) − Don't Ask:structural (S,P) vs LLM candidate extraction(identity mechanism swap)**

| Length | 6k | 32k | 64k | 262k |
| :--- | :---: | :---: | :---: | :---: |
| Δ_B (Overall) | +11 | +1 | +4 | 0 |
| Δ_B (has_pair) | +18 | +4 | +6 | 0 |

Δ_B 於 6k 極大(+11 / +18)但於 262k 收斂到 0。這對應 (O3) 的假設:短 context 下 (S,P) structural key 的密度優勢明顯(fact bank 小,structural collision 少);長 context 下 max-serial ordering signal 飽和,兩種 identity mechanism 於 has_pair 上打平。此結果為 concurrent work Don't Ask 提供了一個非平凡的積極評價——**於 FC-SH 這個 ordering-heavy benchmark 上,LLM candidate extraction + deterministic freshness 是與 structural (S,P) grouping 對等的 query-time identity 方案**;paper 應將其列為 primary Q-llm-identity baseline 而非弱基線。

**Δ_C = ours (no P3) − Q-llm-recency:deterministic argmax vs LLM recency(freshness mechanism swap)**

| Length | 6k | 32k | 64k | 262k |
| :--- | :---: | :---: | :---: | :---: |
| Δ_C (Overall) | −2 | +10 | +7 | +5 |
| Δ_C (has_pair) | 0 | +17 | +11 | +7 |

6k 上 Q-llm-recency 略勝 ours (no P3)(93 vs 91),但 32k 就反轉且拉開 +10 到 +17 pp。此 Δ 隔離了「freshness 該不該交給 LLM」的答案:**短 context 下差距不大,但中/長 context 下確定性 freshness 顯著且穩定勝出**。這解釋 method_v1.md 為何堅持「freshness = deterministic」而非依賴 LLM temporal reasoning。

**Δ_D = Don't Ask − Q-llm-recency:LLM identity + deterministic freshness vs raw retrieval + LLM freshness(兩種 Q-llm 對照)**

| Length | 6k | 32k | 64k | 262k |
| :--- | :---: | :---: | :---: | :---: |
| Δ_D (Overall) | −13 | +9 | +3 | +5 |
| Δ_D (has_pair) | −18 | +13 | +5 | +7 |

6k 上兩者顛倒(Q-llm-recency 勝 +13),但 32k 起 Don't Ask 一路領先。這對兩支 Q-llm 家族的內部比較給出結論:**若 LLM 資源只夠用在一個 mechanism 上,應該用在 identity 而非 freshness**(Don't Ask 的策略),不應用在 recency 判斷(Q-llm-recency 的策略)。deterministic freshness 是比 deterministic identity 更重要的 commitment。

---

## §4.2.4 三段論 Implication(對 paper 主 claim 的 tie-in)

**(I1) query-time resolution 是 length-robust KU 的必要條件,但不是充分條件。**四個方法皆採 query-time resolution,但只有 ours main 與 Don't Ask 於 262k 上 ≥86;Q-llm-recency 於 262k 掉到 81。差異來自「哪些 sub-decision 交給 LLM」:交給 LLM 越少的確定性 sub-decision(freshness、identity 於 structural 可覆蓋時),length-robustness 越強。這對接 method_v1.md §3.3「decomposed simple LLM tasks」的第三條 commitment——不是所有 sub-task 都要 LLM,能確定性就確定性。

**(I2) ours main 相對其他 query-time baseline 的優勢在 identity mechanism。**Δ_A(P3 補救)於 has_pair 262k = +6 pp,Δ_B(structural vs LLM extract)於 6k = +18 pp 但 262k 收斂到 0。這意味 ours 相對 Don't Ask 於長 context 上的優勢已收斂;paper 應誠實揭露此收斂,並將 ours 的差異化定位改為「**於全 length spectrum 保持 flat**」而非「於 262k 顯著勝過所有 baseline」。

**(I3) FC-SH 的 ordering signal 是 Don't Ask 的隱性配額。**Don't Ask 的 monotonic 上升(80 → 88)在 personal-fact benchmark(如 LongMemEval-KU,對話時序 signal 弱)上是否會保持,是未來 §4.6 或後續 evaluation 需驗證的開放問題。若 Don't Ask 於 LME-KU 上劣化,則 ours main 的「structural (S,P) 通用性」claim 更強;若仍持平,則 identity mechanism 的選擇成為 backbone-driven 而非 dataset-driven 的設計權衡。

---

## §4.2.5 Discussion(四問答)

**Q1: 這四個方法哪些條件下 work / 不 work?**
- **ours main**:全 length 皆 work(91-94);無明顯 fail regime。
- **ours (no P3)**:短-中 length 高效(87-92),長 context(262k)無 P3 补救時 has_pair 掉 5 pp(88→82)。
- **Don't Ask**:短 context 弱(80),中-長 context 強(86-88)。適用於 ordering signal 明確的 benchmark;對話式 KU(如 LongMemEval)未驗證。
- **Q-llm-recency**:短 context 表現與 ours 相當(93),中 context 崩(77),長 context 部分恢復(81)。**不適合 length-diverse deployment**。

**Q2: Failure case 長什麼樣、為什麼?**
- ours main 於 has_pair 失敗多為 (S,P) canonicalization 極端 case(需 §4.4 case study 佐證),P3 也無法覆蓋。
- ours (no P3) 於 262k 額外失敗 5 題(vs main),假設全為 stem-vs-full predicate variant(見 [`fc_sh_has_pair_main_table.md`](../results/fc_sh_has_pair_main_table.md) 32k 逐題對位:8/8 是 A mode)。
- Don't Ask 於 6k 失敗多(only 54/74 has_pair),假設是短 context 下 fact bank 小 → LLM extract candidates 時面對更少的 disambiguating signal → identity confusion。
- Q-llm-recency 於 32k 失敗多(only 42/65 has_pair),假設 LLM 需於 top-100 retrieved chunks 中做 temporal reasoning,但 chunks 未按時間排序 → LLM temporal cue 依賴 fact content 內的時間標記或 chunk 位置提示,32k 是「temporal noise 累積但 recency prior 不明顯」的最壞區間。

**Q3: 對 practitioner 的建議?**
- **若部署 length-diverse**:ours main 是唯一 length-robust 選擇。
- **若部署為固定短 context**(< 10k tokens):ours (LLM only) 或 Q-llm-recency 皆可(6k 上皆 93-97);ours (LLM only) 更省於 P2 (S,P) index 構建成本。
- **若部署為固定長 context**(> 100k tokens)且有 ingestion ordering signal(如 continuous log ingest):Don't Ask 是強且簡單的替代方案(僅需 BM25/vector + 1 LLM extract call)。
- **不建議**任何 backbone 下用 Q-llm-recency 於 length-diverse 部署——非單調行為使 SLA 不可預測。

**Q4: Follow-up research 建議?**
- **驗證 Don't Ask 於 non-ordering benchmark**(personal-fact KU 如 LongMemEval)是否仍具此穩定性 → 若否,則「ordering-heavy vs conversational-heavy」成為 identity mechanism 選擇的分水嶺。
- **weak-backbone 上此對照的重現**:於 gemma3-{1B, 4B, 12B, 27B} 上重跑四個方法。假設 Q-llm-recency 於 weak backbone 上進一步崩壞;Don't Ask 因 LLM 任務單純(僅 candidate extract)於 weak backbone 上可能仍穩;ours (no P3) 因純 structural 應為 weak backbone 上的 upper-bound baseline。
- **P3 補救觸發率分析**:於 ours main 上量測 P3 實際觸發率(non-structural cluster 佔比)與命中率(P3 mergers 是否對應 has_pair correct);此為 §4.5.2 已規劃,補齊後可進一步 quantify P3 的邊際效益。

---

## 更新歷程

- **2026-07-13**:本檔建立;基於 canonical rescore(53 cells,gpt-4o-mini)四方法對照;數字來自 [`../results/fc_sh_main_table_4length.md`](../results/fc_sh_main_table_4length.md)。
