# FC-SH 4-Method Error-Mode Diagnosis(query-time family,per-qid,2026-07-13)

> **對接**:[`fc_sh_main_table_4length.md`](fc_sh_main_table_4length.md)(headline 數字)、[`../narrative/experiment_4_2_focused_comparison.md`](../narrative/experiment_4_2_focused_comparison.md)(aggregate Δ 拆解)。
> **本檔定位**:把 §4.2 focused comparison 的 aggregate Δ **下沉到 per-qid**,回答四個問題 — (1) ours(no P3) 錯誤模式、(2) Don't Ask 錯誤模式、(3) Q-llm-recency 錯誤模式、(4) ours(main) 相對 ours(no P3) 補救了哪些題 + ours(main) 自身殘餘錯誤模式。**填補 experiment.md §4.4 目前缺的 query-time 家族 case study**(現有 §4.4 只拆 mem0/Zep/backbone)。
> **數據來源(READ-ONLY,無 API)**:`scratchpad/diag_4method.py` 直接沿用 `analysis/rescore_canonical.py` 的官方 `official_subem` 逐 qid 重算 4 method × 4 length 的既存 output 檔;per-qid 正誤加總**逐格吻合** [`fc_sh_main_table_4length.md`](fc_sh_main_table_4length.md) Table 1/2(sanity 見文末)。gpt-4o-mini backbone,temp 0,single run。
> **分析範疇**:has_pair 子集(74 / 65 / 66 / 77),KU 實際發生處,唯一能定義 gt_new/gt_old 對照。

---

## 0. Sanity — per-qid 加總 == canonical 主表

| Method | 6k | 32k | 64k | 262k | has_pair(6/32/64/262)|
|:--|:-:|:-:|:-:|:-:|:--|
| ours (main) | 94/100 | 91/100 | 94/100 | 91/100 | 69·57·60·68 |
| ours (no P3)| 91/100 | 87/100 | 92/100 | 86/100 | 67·53·58·63 |
| Q-llm-recency| 93/100 | 77/100 | 85/100 | 81/100 | 67·42·51·58 |
| Don't Ask | 80/100 | 86/100 | 88/100 | 86/100 | 54·51·54·63 |

全數逐格等於 [`fc_sh_main_table_4length.md`](fc_sh_main_table_4length.md)(overall Table 1 + has_pair Table 2)→ 下列 per-qid 歸因與主表同源、可直接引用。

---

## 1. ours (no P3) 錯誤模式 — **(S,P) canonicalization miss**

ours(no P3)= (S,P) structural grouping + `argmax(seq)`,**無 P3 LLM 補救**。has_pair wrong-set:

| Length | wrong qids | 全部「答成 gt_OLD」? | 其中 P3-可補救(main 修對)| 其中殘餘(main 也錯)|
|:--|:--|:-:|:--|:--|
| 6k | 30·33·48·58·66·70·81 (7)| ✅ 7/7 | **58·66·81** | 30·33·48·70 |
| 32k| 2·3·8·9·27·32·51·65·68·81·87·94 (12)| ✅ 12/12 | **2·3·65·68·81·87·94** | 8·9·27·32·51 |
| 64k| 0·8·18·20·85·86·91·97 (8)| 7/8 | **8·18·97** | 0·20·85·86·91 |
| 262k| 8·12·19·24·33·40·49·57·65·67·80·86·93·98 (14)| 11/14 | **12·24·40·57·65·93·98** | 8·19·33·49·67·80·86 |

**機制**(canonical trace,6k):

| qid | Q | gt_new(seq)| gt_old(seq)| no P3 答 | 診斷 |
|:-:|:--|:--|:--|:--|:--|
| 58 | Who performed Hermione Granger? | Kylie Minogue(425)| Emma Watson(413)| **Emma Watson** ❌ | new/old 被抽成 stem-vs-full predicate → 分不同 (S,P) 桶 → argmax 從未比對 → pool 留兩版 → reader 取世界先驗舊值 |
| 66 | What work does Stephen McNeil do? | journalist(320)| politician(152)| **Politician** ❌ | 同上(subject/predicate variant 未併群)|
| 81 | Head of state in Soviet Union? | Elizabeth II(365)| Mikhail Gorbachev(159)| **Gorbachev** ❌ | 同上 |

**結論**:ours(no P3) 的 **100%(6k/32k)/ ~88%(64k/262k)失敗都是「答成 gt_OLD」**,且成因單一 = **(S,P) canonicalization miss**(new/old 因 predicate stem-vs-full 或 subject 碎裂被分到不同結構桶,`argmax(seq)` 無從在桶內比對兩版,pool 保留兩版,answer template 無 recency steer → reader 默認世界先驗舊值)。這正是 P3 存在的理由(§3)。**這是 experiment.md §4.4 taxonomy 的 Mode A/B 在 query-time 家族的定量落地**。

---

## 2. Don't Ask 錯誤模式 — **LLM candidate-extraction 塌成單一候選(world-prior extraction leak)**

Don't Ask = vector top-100 檢索 → LLM extract candidates → `max(serial)`。逐 row 帶 `n_candidates` / `chosen_serial`,可直接讀失敗根因:

| Length | dont wrong | **`n_candidates==1`**(抽取只留一版)| 扣掉 D-flag 後的 ncand==1 佔比 |
|:--|:-:|:--|:--|
| 6k | 20 | **20 (100%)** | 20/20 = **100%** |
| 32k| 14 | 11 | 11/12 = **92%** |
| 64k| 12 | 10 | 10/10 = **100%** |
| 262k| 14 | 10 | 10/12 = **83%** |

**機制**(canonical trace):

| qid·L | gt_new(seq)| gt_old(seq)| dont 答 | chosen_serial · ncand | 診斷 |
|:-:|:--|:--|:--|:--|:--|
| 6k·14 | Samuel Beckett(401)| Galileo Galilei(124)| **Galileo** ❌ | 124 · **1** | LLM 只把「Galileo」抽為候選(世界先驗名字);Beckett 版雖在 top-100 檢索內卻沒被 extract → `max(serial)` 對單一候選 trivially 回舊值 |
| 6k·57 | Charles the Bold(139)| Priscilla Presley(120)| **Priscilla** ❌ | 120 · **1** | 同上(Elvis 配偶世界先驗極強)|
| 64k·48| Old Turkic(3145)| Dutch(1598)| **Dutch** ❌ | 1598 · **1** | 同上(荷蘭官方語言先驗)|

**結論**:Don't Ask 的失敗**不是 freshness(max-serial)出錯**,而是**上游 LLM candidate-extraction 把反事實新版漏掉、只留世界先驗舊版為唯一候選**(`ncand==1`,`chosen≈old_seq`)→ `max(serial)` 只能回舊值。這解釋 §4.2 (O3)「越長越強」:context 越長 → fact bank 越大、同 (S,P) 多版本在 bank 中越飽和 → extract 越常抓到 ≥2 候選(ncand==1 佔比 100%→83%)→ Don't Ask 從 80 升到 86-88。**這是 concurrent work Don't Ask 的結構性弱點:把 identity 交給 LLM extraction,在 dense-fact / 強世界先驗題上會 leak**;ours 的 (S,P) 結構鍵免疫(忠實寫入全版本,不靠 LLM 選候選)。

> **⚠ serial 對位 caveat**:Don't Ask 的 `chosen_serial` 與 mquake `gt_seq/old_seq` 為**近似同源**但非逐位相等(同一 fact 常在鄰近 ordinal 有 duplicate,Don't Ask 取其一)→ 本節**只用 `n_candidates` 與「答成 gt_OLD 表面」兩個 robust 訊號**,不做 fine-grained serial 比對。

---

## 3. Q-llm-recency 錯誤模式 — **把 freshness 交給 LLM → 回退到世界先驗舊值**

Q-llm-recency = raw retrieval(**與 ours 同 store**)+ ordinal-prefixed pool + LLM 判 recency(no grouping、no argmax)。

| Length | qrec wrong | 答成 gt_OLD | **freshness-only-fail**(qrec 錯、但 no P3 同 store 對)|
|:--|:-:|:--|:--|
| 6k | 7 | 7/7 (100%)| 7 |
| 32k| **23** | 22/23 (96%)| **14** |
| 64k| 15 | 15/15 (100%)| 10 |
| 262k| 19 | 18/19 (95%)| 11 |

「freshness-only-fail」= **同一 store、no P3 用 `argmax(seq)` 判對、但 Q-llm-recency 用 LLM 判 recency 判錯**的題 → 隔離出「把 freshness 委給 LLM」的淨代價。

**機制**(canonical trace,32k;這些題 ours main/no P3 皆✅):

| qid | Q | gt_new(seq)| gt_old(seq)| qrec 答 | 診斷 |
|:-:|:--|:--|:--|:--|:--|
| 17 | Who is Charles Darwin married to? | Amala Paul(1896)| Emma Darwin(591)| **Emma Darwin** ❌ | LLM 無視「larger serial = newer」,選語意熟悉的真實配偶 |
| 47 | Continent of San Francisco? | Africa(1659)| North America(85)| **North America** ❌ | 同上(地理先驗)|
| 20 | Tony Parker 位置? | shooting guard(1797)| point guard(1647)| **Point guard** ❌ | 兩版 ordinal 接近 → LLM ordinal parsing 更易翻車 |

**結論**:Q-llm-recency 的失敗 **95-100% 是「答成 gt_OLD」**;根因 = **LLM 被要求在 flat ordinal pool 上判 recency 時,傾向回退到語意熟悉(世界先驗)的舊值、而非嚴格 follow max-ordinal 規則**。這在 32k 最嚴重(23 wrong / freshness-only-fail 14),對應 §4.2 (O4) non-monotonic dip 的 qid 級證據。**直接證成 method_v1 §3.3 commitment:freshness 必須確定性、不可委給 LLM**(委給 LLM 引入 backbone-brittle 的世界先驗回退)。

---

## 4. ours(main) 補救了哪些題 + ours(main) 殘餘錯誤模式

### 4a. P3 補救 vs 迴歸(ours main − ours no P3,同 store)

| Length | **P3 RESCUE**(no P3 錯→main 對)| P3 REGRESS(main 錯、no P3 對)| net | has_pair |
|:--|:--|:--|:-:|:--|
| 6k | **58·66·81** (+3)| 5 (−1)| **+2** | 67→69 |
| 32k| **2·3·65·68·81·87·94** (+7)| 16·46·70 (−3)| **+4** | 53→57 |
| 64k| **8·18·97** (+3)| 40 (−1)| **+2** | 58→60 |
| 262k| **12·24·40·57·65·93·98** (+7)| 18·77 (−2)| **+5** | 63→68 |

**補救機制**(qid 58/66/81):P3 LLM identity grouping 把 (S,P) 碎裂的 new/old 併回同群 → `argmax(seq)` 取較晚 ordinal 的新版 → pool 乾淨只留新版 → reader 抄對。**淨值於全 4 length 皆正**(+2/+4/+2/+5),且**長 context 邊際效益最大**(262k +5),對應 §4.2.3 Δ_A 隨長度成長(predicate variant 於長歷史累積更多 → canonicalization miss rate 升 → P3 補救空間變大)。

**迴歸機制**(qid 5 Marriage of Figaro:no P3 對 Thomas Kyd → main 錯 Beaumarchais):P3 於此題 over-merge / 引導 pool 保留舊版,reader 退回世界先驗。**這是 P3 的成本項**,但每長度僅 1-3 題,遠小於補救(§4.5.3 已據此把 P3 定位為 capability-gated add-on)。

### 4b. ours(main) 殘餘錯誤模式分解

歸因規則:**D-flag** = benchmark 反轉(`gt_seq < old_seq`,argmax 邏輯上不可能對);**READER-override** = main 答舊 **且** Q-llm-recency(同 store,無 grouping)也答舊(同一 reader 兩條路徑都被世界先驗俘虜);**STRUCT-frag / P3-regress** = main 錯但 qrec(同 store,無 grouping)對 →(S,P) grouping 反而害了它。

| Length | main wrong | D-flag(benchmark)| STRUCT-frag / P3-regress(方法)| READER-override(reader 先驗)| other |
|:--|:-:|:--|:--|:--|:--|
| 6k | 5 | — | 5·30·33·48·70 (5)| — | — |
| 32k| 8 | 8·9 (2)| 16·46·70 (3)| 27·32·51 (3)| — |
| 64k| 6 | 20 (1)| — | 0·85·86·91 (4)| 40 (1)|
| 262k| 9 | 8·49·80 (3)| 19·33·77 (3)| 18·86 (2)| 67 (1)|

**canonical trace**:

- **D-flag**(64k·20 Great Britain 洲別 gt_new Europe seq2374 < gt_old Asia seq2468):四方法全錯,`argmax(seq)` 邏輯上不可能對 → **benchmark 標註缺陷,與 method 正交**(§4.4.5;64k 2/66、262k 3/77 ≈ 3-4%)。
- **STRUCT-frag**(6k·30 baseball 產地 gt_new Japan;main/no P3 答 USA,qrec 答 Japan):同 store,ours 的 (S,P) 把 baseball-created-in 碎裂 → 兩版都留 → ours answer template 無 recency steer → reader 退回世界先驗 USA;qrec 的 ordinal-prefixed pool 有 recency steer → reader 取 Japan。**short context(6k)ours-main 殘餘錯誤 100% 屬此類**(P2 canonicalization / P3 mis-merge),非 reader override。
- **READER-override**(64k·85 Reese Witherspoon 之子 gt_new James Badge Dale;main/no P3/qrec 全答 Ava Phillippe 真實女兒):同 store 兩條 query-time 路徑的 reader **都**被強世界先驗俘虜 → 純 reader 特性,KU pipeline 已把新版送進 pool,失分在 answer LLM(§4.4.7 selective override 的 gpt-4o-mini 鏡像)。**長 context(64k/262k)ours-main 殘餘錯誤主體轉為 reader override**。

**結論(ours main 責任邊界)**:ours(main)殘餘失分沿長度**從「方法(結構碎裂)」漂移到「reader(世界先驗)」再加「benchmark(D-flag)」**——三者中**只有 STRUCT-frag / P3-regress 是 KU 方法自身可修的**(重寫 GROUPING_PROMPT / 改進 P2 canonicalization),reader override 與 D-flag 皆與 KU 解析正交。這與 §4.4.6/§4.7「失敗沿 pipeline 往後推」的 backbone 版陳述,在**長度軸**上得到平行印證。

---

## 5. 一頁式總結(四方法錯誤模式對照)

| 方法 | 失敗「答成 gt_OLD」比例 | **唯一主導根因** | 隨長度趨勢 | 是否 KU-方法可修 |
|:--|:--|:--|:--|:--|
| **ours (main)** | short:結構碎裂;long:reader override | 依長度漂移(§4b)| 全長 flat 91-94 | 部分(結構碎裂可修;reader/D-flag 正交)|
| **ours (no P3)** | ~88-100% | **(S,P) canonicalization miss** | flat-ish;P3 gap 隨長度張 | ✅ 由 P3 補救 |
| **Q-llm-recency** | 95-100% | **LLM 判 freshness 回退世界先驗** | 32k 最壞(non-monotonic)| ✗(改回 argmax 才修)|
| **Don't Ask** | ~85-100% | **LLM extract 塌成單一候選(world-prior leak)** | 越長越強(bank 飽和)| ✗(改用結構鍵才修)|

**跨方法一句話**:四個 query-time 方法的失敗**幾乎全是「回退到世界先驗舊值」**,但**發生的 pipeline 位置不同** — Don't Ask 在 LLM extract(識別)、Q-llm-recency 在 LLM recency(取新)、ours(no P3)在 (S,P) 結構碎裂、ours(main)把前三者的識別問題用「忠實寫入全版本 + 結構鍵 + P3 補救 + 確定性 argmax」逐一 dodge,殘餘只剩 reader 先驗與 benchmark D-flag(皆與 KU 解析正交)。

---

---

# Diagnostic 1 — P3 觸發率(structural pool vs dynamic pool routing)

> **方法**:offline (S,P)-merge proxy(`attribute_sp_merge` 同款 L0/L1/L2 normalization,讀 `triple_cache_{L}.json` gpt-4o-mini P1 store + `sh_{L}_RUN_gt.json`)。對每 has_pair query,找出 gt_new / gt_old 的抽取 triple,判其 (S,P) 是否同鍵:**同鍵 → structural pool(argmax 解)**;**異鍵 → dynamic pool(P3 LLM grouping 解)**;**gt_new 未抽到 → new_missing(P2 extraction miss)**。
> **⚠ proxy 偏差(誠實揭露)**:proxy 用**全 store** 找最可能同鍵的 pair,會**低估** dynamic 佔比(sanity:proxy 標 structural 但實測 main≠noP3 的 P3-active qid = 6k 1、32k 5、64k 1)→ 真 dynamic 佔比略高於下表。**趨勢(structural↓ / dynamic↑ 隨長度)為 robust**。**262k**:無 `triple_cache_262k` / `RUN_gt_262k` → 需 store re-query(**approval-gated,PENDING**)。

| Length | structural pool | dynamic pool(P3)| new_missing(P2 漏抽)| **struct 命中 ✓/✗** | **dynamic-P3 ✓/✗** |
|:--|:-:|:-:|:-:|:-:|:-:|
| 6k | 60/74 = **81%** | 10/74 = **14%** | 4 | **56 / 4** | **9 / 1**(90%)|
| 32k| 50/65 = **77%** | 14/65 = **22%** | 1 | **45 / 5** | **11 / 3**(79%)|
| 64k| 45/66 = **68%** | 21/66 = **32%** | 0 | **43 / 2** | **17 / 4**(81%)|
| 262k| ☐ PENDING(approval)| ☐ | ☐ | ☐ | ☐ |

**四象限拆分(main 判分)**:
- **structural 命中且 correct**:56 / 45 / 43(argmax 於同 (S,P) 群取最新版,pool 乾淨,reader 抄對)
- **structural 命中但 wrong**:4 / 5 / 2(pool 已隔離卻答錯 → **reader world-prior override 或 D-flag**,非 argmax 錯;見 Diagnostic 3 (e))
- **dynamic 觸發、P3 後 correct**:9 / 11 / 17(P3 把 (S,P) 碎裂的 new/old 併回同群 → argmax 取新)
- **dynamic 觸發、P3 後 wrong**:1 / 3 / 4(P3 未併或 mis-merge;見 Diagnostic 3 (b))

**三段論**:
- **(What)** structural pool 佔多數(68-81%),但**佔比隨長度單調下降**(81→77→68%),dynamic/P3 佔比**單調上升**(14→22→32%)。new_missing(P2 抽取漏 gt_new)隨長度**下降**(4→1→0,長 context 給 P2 更多抽對機會)。
- **(Where)** dynamic-pool 的 P3 in-bucket accuracy 穩定 79-90%;**dynamic-pool 佔比隨長度變大 → P3 承擔的題數變多**(10→14→21)→ 直接解釋 §4.2.3 **Δ_A(P3 貢獻)隨長度成長**(6k +2 → 262k +5):不是 P3 變準,而是**需要 P3 的題(predicate/subject variant)隨 context 累積變多**。
- **(Implication)** 兌現 method_v1 §3.3「LLM 補救僅在少數案例介入」:P3 只在 14-32% 的 query 上真正做識別工作,其餘 68-81% 由確定性 (S,P)+argmax 解決;且 P3 觸發區的正確率高(≥79%)。**Struct 是 backbone-invariant workhorse,P3 是隨長度邊際效益成長的窄任務 add-on。**

---

# Diagnostic 2 — union table:structural(no P3)vs LLM only(仿 Don't Ask §5.5)

> **對照**:ours(no P3)=（S,P) structural only vs ours(LLM only)= P3 identity grouping only(no struct)。兩者**同 store、同 argmax freshness**,只差 identity mechanism（結構 vs 純 LLM）。量化「structural 救了幾題 LLM-only 答錯的」。

| Length(has_pair)| 兩者都對 | **只有 structural 對** | 只有 LLM-only 對 | 兩者都錯 | structural 獨家救回 qids |
|:--|:-:|:-:|:-:|:-:|:--|
| 6k(74)| 67 | **0** | 4 | 3 | — |
| 32k(65)| 51 | **2** | 7 | 5 | 46·88 |
| 64k(66)| 55 | **3** | 3 | 5 | 5·37·47 |
| 262k(77)| 58 | **5** | 6 | 8 | **11·36·41·69·73** |

（overall-100 對照:only-struct 0/3/4/5、only-LLMonly 6/7/3/6 → struct 91/87/92/86 vs LLMonly 97/91/91/87,逐格吻合主表。）

**三段論**:
- **(What)** **「只有 structural 對」的題數隨長度單調成長 0 → 2 → 3 → 5**;於 6k structural **零獨家貢獻**(LLM-only 於短 context 嚴格支配 identity,對應 Table 1 LLM-only 97 > no P3 91),但到 262k structural **獨家救回 5 題** LLM-only 失手的長 context 題。
- **(Where)** LLM-only 相對 structural 的優勢**隨長度收斂**(6k +6pp → 262k +1pp,overall)。長 context 下 P3 LLM 面對更大 retrieved pool、更多 distractor → identity grouping 變不穩;而 (S,P) 結構鍵是 backbone/length-invariant → structural 於 262k 反成關鍵。
- **(Implication)** **兩 identity mechanism 互補、缺一不可**:ours(main)= struct ∪ P3,於每長度都取兩者聯集 → 94/91/94/91 高於任一單獨 ablation。**這就是 main 為何同時保留 struct 與 P3 的量化理由**:structural 的獨家貢獻在長 context 才浮現(0→5),P3 的獨家貢獻在短 context 最大(4→6);Table 1「structural 特別擅長 262k」在此逐題證實。

---

# Diagnostic 3 — ours(main) 30 個錯誤案例分類

> **範疇**:overall-100 wrong × 4 length = **30 題**(6k 6 + 32k 9 + 64k 6 + 262k 9)。
> **歸因規則(先 authoritative,後 proxy 細分)**:D-flag(`gt_seq<old_seq`)→(e);P3-regress(main 錯、no P3 對)→(b);同 store 的 Q-llm-recency 判對 → **方法問題**(grouping/argmax 輸給 raw+recency)→ 再用 (S,P) proxy 細分 (a)/(c);main 答舊且 qrec 也失手 →(e) reader override;非 has_pair 單版題答錯 →(e)。

| 類別 | 定義 | **n / 30** | qids |
|:--|:--|:-:|:--|
| **(a)** 單值 KU 但 **P2 抽錯 predicate**(同 subject、predicate 變體)| 方法可修 | **1** | 6k·30 |
| **(b)** 單值 KU 但 **P3 fallback 判斷錯**(over-merge / 未併,弄壞 no P3 本來對的)| 方法可修 | **7** | 6k·5;32k·16·46·70;64k·40;262k·18·77 |
| **(c)** 單值 KU 但 **(S,P) normalization / subject 碎裂**(struct 未併,raw+recency 卻對)| 方法可修 | **5** | 6k·33·48·70;262k·19·33 |
| **(d)** **超出方法適用範圍**(multi-valued / event / n-ary)| — | **0** | —(FC-SH 依建構皆單值反事實 → 無此類)|
| **(e)** **other** | 與 KU 解析正交 | **17** | ↓ |
| ‥ e1. reader world-prior override(pool 乾淨/兩路徑 reader 皆取舊)| reader 軸 | 8 | 32k·27·32·51;64k·0·85·86·91;262k·86 |
| ‥ e2. benchmark D-flag(`gt_seq<old_seq`,argmax 邏輯不可能對)| benchmark 軸 | 6 | 32k·8·9;64k·20;262k·8·49·80 |
| ‥ e3. non-has_pair / off-answer(單版題答錯或答非所問)| 其他 | 3 | 6k·79;32k·64;262k·67 |

**三段論**:
- **(What)** **方法自身可修(a+b+c)= 13/30 = 43%**;**與 KU 解析正交(e)= 17/30 = 57%**(reader 世界先驗 8 + benchmark D-flag 6 + non-KU 3)。可修部分**以 P3 mis-merge(7)與 (S,P) 碎裂(5)為主**,真正的 P2 predicate 抽取錯僅 **1**,**out-of-scope = 0**。
- **(Where)** 錯誤結構**隨長度漂移**:短 context(6k)可修方法錯佔多數(5/6);長 context(64k/262k)轉為 reader override + D-flag 主導(64k 5/6、262k 5/9 屬 e)。與 Diagnostic 1 的 routing 漂移、以及 experiment.md §4.4.6/§4.7「失敗沿 pipeline 往後推」一致。
- **(Implication)** **ours(main) 責任邊界內(KU 解析)的殘餘失分很小**:全 400 cell-query 中方法可修者僅 13 題,且最大宗是「P3 於強識別下過保守/過度合併」(b=7)——這正是 §4.4.3 GROUPING_PROMPT「Clustering is RARE」設計副作用,**改 prompt 即可回收**(future work)。reader override(8)與 D-flag(6)與 KU 方法正交,不應計入方法缺陷。**out-of-scope=0 證實 FC-SH 完全落在 method 的單值-KU scope 內**(multi-valued 場景留 LME §4.6)。

---

## 更新歷程
- **2026-07-13**:建檔;per-qid 診斷 4 method × 4 length,逐格吻合 canonical 主表;補 experiment.md §4.4 缺的 query-time 家族 case study。腳本 `scratchpad/diag_4method.py`(READ-ONLY,沿用 `rescore_canonical.official_subem`)。
- **2026-07-13(續)**:加 Diagnostic 1(structural/dynamic routing,offline (S,P) proxy,6k/32k/64k;262k pending approval)、Diagnostic 2(structural vs LLM-only union table)、Diagnostic 3(ours main 30 wrong 分類 a/b/c/d/e)。腳本 `scratchpad/diag123.py`(READ-ONLY,沿用 `attribute_sp_merge` normalization + `rescore_canonical.official_subem`;無 API/store/embedding)。
