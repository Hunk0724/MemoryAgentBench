# FC-SH 64k 非正常案例 deep-dive + 6k→32k→64k 結構性證據

> ### ⚠️ 2026-06-08 方法學精修(read first)
> 本檔的 write-time A-WT bucket(resolved / H1-miss / H2-refuse / same-chunk)是「**逐 update 事件**」分類,**≠ 最終 store 狀態 ≠ QA 對錯**。實測(6k 擴充 QA)event-bucket 失敗對中約 28% 最終 store 其實乾淨(被後續 chunk 清成 new_only → QA 答對,如 Figaro)。**事件數字作為 write-time 描述不變**;但要主張「QA 失敗」須用**最終 store 狀態(old_only/both)**。本檔 §C 的 query 逐案 trace 已是 final-state(直接追 update_decision 到最終),不受影響;受影響的是 §A/§E 的 A-WT 聚合「事件」數不可直接讀成 QA 失敗率。詳見 [02 頂部](02_fc_sh_6k_failure_deepdive.md)/[05](05_expanded_eval_set.md)。

> **用途**:64k 版逐案 trace(對應 [02](02_fc_sh_6k_failure_deepdive.md) 之於 6k、[03](03_fc_sh_32k_failure_deepdive.md) 之於 32k),並把證據延伸到第三個長度點。
> **資料**:`logs/sh_64k_l2`(L2+frozen cache,vector text-embedding-004,temp=0)。
> **⚠️ 重大設定差異(confound,務必先讀)**:64k 的 **ingestion update LLM 與答題 LLM 皆用 `thinking_level="minimal"`**(因 High thinking 在 64k 造成本機累積 OOM crash 於 chunk 37);**6k/32k 當時跑的是 High thinking**。→ **64k 的 write-time 指標(resolved/H1/H2)與 6k/32k 不可直接並列做趨勢**,詳見 §E。答題端 `generation_max_length=256`(6k/32k 當時=10)→ 64k **無截斷空輸出**。
> write-time 用 `mh_64k_FULLPAIRS_gt`(1691 in-store 對,query-independent);SH query 用 `sh_64k_RUN_gt.json`(本 run 自己的 queries,100 題,66 has_pair)。
> **⚠️ FC-SH queries 隨長度不同**(6k≠32k≠64k),benchmark-defect 題號也不同(32k 是 qid8/9;**64k 是 qid18/20**)。

---

## 摘要(先說結論,含誠實 caveat)

1. **64k 真實 EM 天花板 = 96%**(無截斷;nominal EM 94%,+2 benchmark 答案鍵瑕疵 qid18/20 mem0 其實答對)。100 題只有 **4 個真 mem0 失敗**。
2. **4 個真失敗全部收斂到同一結構根因**(R1 候選鍵控錯誤 + R2 update 不可逆裁決),**無一例外、無隨機 artifact**:
   - 1 個衝突題:qid32(**A4** cross-fact 污染)。
   - 3 個**單一事實題(無衝突)**:qid76(update LLM **靜默漏掉** new fact)、qid77(**A4**)、qid87(**近重複碰撞**)。
3. **新發現(強化主張)**:連「無衝突的單一事實」都會被同一機制摧毀 —— 只要候選池混入**同實體異關係**或**近重複表面字串**的反事實 fact。即結構失敗**不限於衝突解決**,而是「embedding 鍵控的候選池 + 不可逆 update」這組設計在任何 fact 上都可能毀損正確記憶。qid76 更揭露一個**新子模式**:候選池過大(n_cand=156)時 update LLM **直接把某 new fact 從輸出省略**(既非 ADD 也非 NONE)。
4. **誠實 caveat(關鍵)**:64k resolved **95.6% > 32k 93.1%**,是**非單調的回升**。這幾乎確定是 **minimal-thinking confound**(minimal 讓 H2-refuse 由 3.4%→1.3%),**不是「池更大反而更好」**。→ **乾淨的 6k→32k→64k 趨勢必須把 6k/32k 用 minimal 重跑後才成立**。在那之前,64k 不可與 6k/32k 並列宣稱「持續惡化」。

---

## A. write-time 結構性問題(核心證據,1691 in-store 對,query-independent)

A-WT 64k(minimal thinking):detectable **1678** / resolved **1604(95.6%)** / **H1-miss 53(3.2%)** / **H2-refuse 21(1.3%)** / same-chunk 13。
(腳本 `awt_writetime_audit.py`,結果 `logs/sh_64k_l2/awt_result.json`,gt==larger-seq 1691/1691。)

| 結構問題 | component | 數量(/1678 detectable) |
|---|---|---|
| **A1 H1-miss** crowd-out | candidate retrieval(top-5)| 53(3.2%)|
| **A2 H2-refuse** 拒覆蓋 | update LLM(判斷)| 21(1.3%)|
| same-chunk 架構盲區 | extraction+update | 13(從分母剔除)|
| resolved | — | 1604(95.6%)|

- **A1(H1-miss)機制同 32k**:store 達 ~4580 facts,同關係模板(capital-of / educated-at / citizen-of)不同主詞 fact 大量存在,embedding 對「關係型態」相似度蓋過「主詞匹配」→ 真同主詞舊版被擠出 top-5 → update LLM 沒看到舊版 → 兩版並存,衝突未解。**絕對數 53(6k=1,32k=29)**。
- **A2(H2-refuse)機制同 32k**:舊版已在候選且高 rank,update LLM 仍不發 UPDATE,保留世界事實丟反事實。**但 minimal thinking 下只剩 21(32k High=28,占比 3.4%→1.3%)** → 見 §E confound 討論:H2-refuse 對 thinking level 敏感。

---

## B. FC-SH 64k query 失敗逐案(6 個 nominal EM-wrong,EM 94%)

### B.0 先做 benchmark-only 規則自洽檢查(剔除答案鍵瑕疵)
腳本 `benchmark_rule_consistency.py`(arrow idx6 = sh_64k,**context 直讀 benchmark,不靠 MQuAKE**):
> covered 100/100;conflict(multi-version)questions **66**;answer==largest serial(規則自洽)**64**;**answer != largest serial(BENCHMARK DEFECT)2 → Q18、Q20**。

| qid | benchmark 答案鍵 | 同 slot 更大序號版本 | 判定 |
|---|---|---|---|
| **18** | `Tom Clancy`@**7** | `Torquato Tasso`@**1219** | **答案鍵違反 largest-serial 規則** |
| **20** | `Europe`@**2374** | `Asia`@**2468** | **答案鍵違反 largest-serial 規則** |

- mem0 在 qid18 輸出 **Torquato Tasso**、qid20 輸出 **Asia** —— 正是**較大序號(rule-compliant)**,卻被瑕疵答案鍵判 EM=wrong。**非 mem0 失敗,從分母剔除**(同 32k qid8/9 性質,只是題號因 query 隨長度不同而改變)。
- ⚠️ **`sh_full_classify.py` 預設帶 `--benchmark-defect 8,9` 是 32k 沿用值,對 64k 是錯的**;64k 正確瑕疵題 = **18,20**。已用 `benchmark_rule_consistency.py` 從 context 重新判定,本檔以此為準。
- 64k 無「mem0 蒙對瑕疵鍵」的情形(2 瑕疵題 mem0 都答 rule-correct、皆 EM=wrong)→ **94 個 EM-correct 全為規則自洽的真對**,EM 無被瑕疵鍵灌水。

### B.1 6 個 nominal 失敗的最終歸因

| qid | 題型 | nominal | 真實狀態 | 機制 / 階段 |
|---|---|---|---|---|
| 18 | 衝突 | wrong | **mem0 正確** | benchmark 答案鍵瑕疵(輸出 Torquato Tasso=大序號)|
| 20 | 衝突 | wrong | **mem0 正確** | benchmark 答案鍵瑕疵(輸出 Asia=大序號)|
| 32 | 衝突 | wrong | **真失敗** | **A4** write-time over-fire(R1+R2)|
| 76 | 單一(無衝突)| wrong | **真失敗** | **update LLM 靜默漏掉 new fact**(R2,大池)|
| 77 | 單一(無衝突)| wrong | **真失敗** | **A4** 同實體異關係覆蓋(R1+R2)|
| 87 | 單一(無衝突)| wrong | **真失敗** | **近重複碰撞**覆蓋(R1+R2)|

→ **真 mem0 失敗 = 4**(qid32/76/77/87);其中**衝突解決失敗 = 1**(qid32,A4),**單一事實毀損 = 3**(qid76/77/87)。**mem0 規則正確率 = 96/100**。

---

## C. 4 個真失敗逐案 trace(component-precise,Layer A update_decision 實查)

### C.1 qid32 ★ A4 cross-fact 污染(唯一衝突解決失敗 —— 結構主張的乾淨範例)
**Q**:Which city did Martin Luther King Jr. die in?　**gt(反事實)**:St Leonards-on-Sea(seq2234)　**old**:Memphis(seq1313)。gt=較大序號,規則上該留。
**update_decision 逐事件**(同 MLK「died-in-city」槽位):
1. `UPDATE`:`MLK died in the city of Memphis` ← old_memory=`MLK is a citizen of United States of America`。**第一次跨關係覆蓋**:用 died-in-city 蓋掉 citizen-of(本該 ADD)。
2. `UPDATE id=161`:`MLK died in the city of St Leonards-on-Sea` ← old=`...Memphis`。✓ **正確**把 Memphis 更新成反事實 winner St Leonards。此刻 store 應持 St Leonards(答案正確)。
3. **`UPDATE id=102`:`MLK is a citizen of Vietnam` ← old_memory=`MLK died in the city of St Leonards-on-Sea`**。**致命**:update LLM 把**剛存對的 winner**(died-in-city 槽)覆蓋成**無關的 citizen-of 反事實**。
→ query 時「MLK 死於哪座城市」→ died-in-city 槽已被 citizen-of 內容佔據 → mem0 答「pool 無此資訊」。**正確反事實被不可逆 UPDATE 摧毀**。
- **機制**:embedding 候選池把「同主詞 MLK、異關係(citizen-of vs died-in-city)」當鄰居 → update LLM 把它們**誤判為同槽衝突**而 over-fire(**R1 鍵控錯誤 + R2 不可逆裁決**)。與 32k qid87/95/98 同型(同主詞/同受詞、異關係)。

### C.2 qid77 A4(單一事實,被同實體異關係反事實摧毀)
**Q**:Who is the author of Areopagitica?　**gt**:John Milton(seq2558,context 唯一、無衝突對)。
**trace**:
- extraction 把「Areopagitica 作者=Milton」**改寫合併**進 `John Milton is famous for Paradise Lost and Areopagitica`(`UPDATE id=40`,← `John Milton is famous for Paradise Lost`)。
- **`UPDATE id=13`:`John Milton is famous for Shakugan no Shana.` ← old=`John Milton is famous for Paradise Lost and Areopagitica`**。「Milton famous-for」槽被反事實 `Shakugan no Shana` 覆蓋 → Areopagitica 關聯**連帶消滅**。
→ query「Areopagitica 作者」→ pool 已無此關聯 → 答「無資訊」。
- **機制**:同 C.1(R1+R2),外加 extraction 把不同關係(authored-by vs famous-for)**摺進同一 famous-for 槽**,放大了被 over-fire 的暴露面。

### C.3 qid87 近重複碰撞(單一事實,被近重複表面字串覆蓋)
**Q**:Who performed Born This Way Ball?　**gt**:Lady Gaga(seq350,無衝突對)。
**trace**:`ADD id=141` 存入 `Born This Way Ball was performed by Lady Gaga`;後 **`UPDATE id=10`:`Born This Way was performed by Lady Gaga.` ← old=`Born This Way Ball was performed by Lady Gaga.`**。
→ update LLM 把 **`Born This Way`(歌曲)** 與 **`Born This Way Ball`(巡演)** 當同一槽,用前者覆蓋後者 → 巡演 fact 消失。query「Born This Way **Ball** 由誰演出」→ 只剩較泛的 `Born This Way` → 答「無資訊」。
- **機制**:R1 的另一面 —— 候選鍵控按**表面字串相似度**,把「Ball(巡演)/無 Ball(歌曲)」近重複視為同槽 → R2 不可逆覆蓋。

### C.4 qid76 ★ 新子模式:update LLM 在大池下靜默漏掉 new fact
**Q**:Which university was James Dashner educated at?　**gt**:Brigham Young University(seq4414,無衝突對)。
**trace**(`extraction.jsonl` + `update_decision.jsonl` 事件 #124):
- extraction **有**抽到 `The univeristy where James Dashner was educated is Brigham Young University`(cache 確認)→ 進到該 chunk 的 new-facts 清單(n_new=34)。
- 但該事件 `parsed_actions` **完全沒有這條 fact 的任何動作**(無 ADD / UPDATE / NONE),且 `hallucinated_ids=[]`。**n_candidates=156**。
→ update LLM 被餵了這條 new fact,卻在輸出時**直接省略**它 —— 既沒存、也沒拒。fact 靜默蒸發。query 時 pool 根本沒有 → 答「Not mentioned」。
- **機制**:這是 **R2 在大候選池下的退化** —— `n_candidates=156` + 34 條 new facts 一次塞給 update LLM,它**漏處理**部分 new facts。直接呼應「**池過大壓垮 update LLM**」假設,且是與 A1/A4 不同的**省略型**子模式。
- **對照空池病理**(00 早期訊號):空池也會幻覺 update;大池則會**漏 ADD**。兩端都顯示 update LLM 對候選集規模不 robust。

---

## D. 全 100 題互斥分類(總和=100,nominal EM=94)

| 類別 | n | 說明 |
|---|---|---|
| ✅ single-correct | 31 | no_pair 單一事實,答對 |
| ✅ clean-resolved | 63 | has_pair,衝突乾淨解決,答 winner(含 qid8/9 —— 32k 的瑕疵題在 64k 規則自洽)|
| ✅ benchmark-defect 但 mem0 rule-correct | 2 | **qid18/20**(輸出大序號=規則正確,被瑕疵鍵判 wrong)|
| ❌ FAIL-A4(write-time over-fire)| 2 | qid32(衝突)、qid77(單一)|
| ❌ FAIL-collision(近重複覆蓋)| 1 | qid87(單一)|
| ❌ FAIL-omission(大池漏 ADD)| 1 | qid76(單一)|

> 總和 31+63+2+2+1+1=100。EM 94 = single-correct 31 + clean-resolved 63。(`sh_full_classify.py --benchmark-defect 18,20` 分組:single-correct 31 / clean-resolved 63 / BENCHMARK-DEFECT 2 / FAIL-A4 1〔qid32,of≠None〕/ single-FAIL 3〔qid76/77/87〕;本表把 qid77 依機制歸 A4、qid87 歸碰撞、qid76 歸 omission,故 FAIL-A4 計 2。)

- **FRAGILE(脆弱成功)= 0**(同 32k;same-chunk 占比 0.8% 故無蒙對)。
- **真 mem0 失敗 = 4**(全部結構性,見 §C)。**A1(H1-miss)/A2(H2-refuse)一個都沒造成 query 失敗** —— 它們在 1678 對裡各 53/21 例 write-time 退化,但這 100 題 SH query 未抽樣到(抽到時剛好乾淨解決)。**與 6k/32k 同樣的「兩軸分開」現象**(write-time 退化 ≠ query 失敗集合)。

---

## E. 6k→32k→64k 彙整 + ⚠️ confound 誠實討論

### E.1 三點數據(原樣並列,但**標記不可直接比**)
| 指標 | 6k(High th.)| 32k(High th.)| 64k(**minimal th.**)|
|---|---|---|---|
| in-store 對(detect)| 161(145)| 837(824)| 1691(1678)|
| resolved | 98.6% | **93.1%** | **95.6%** ⚠️ |
| H1-miss | 0.7%(1)| 3.5%(29)| 3.2%(53)|
| H2-refuse | 0.7%(1)| 3.4%(28)| **1.3%(21)** ⚠️ |
| same-chunk 占比 | 10% | 1.6% | 0.8% |
| 真衝突解決失敗(query)| 4 | 3(A4)| **1**(A4 qid32)|
| 真單一事實毀損(query)| — | — | **3**(qid76/77/87)|

### E.2 ⚠️ confound:64k 的回升幾乎確定是 minimal-thinking artifact
- resolved **32k 93.1% → 64k 95.6%** 是**非單調回升**;若「池過大」單調惡化成立,64k 應 < 32k。
- 最可能解釋:**H2-refuse 對 thinking level 敏感**。High thinking 時 update LLM 更會「推理出世界事實」而拒寫反事實(H2-refuse 32k=3.4%);minimal thinking 削弱此傾向(64k=1.3%)→ 連帶推高 resolved。**這是 thinking 設定差異,不是 scale 效應**。
- **H1-miss 不受 thinking 影響**(純 embedding 檢索):6k 0.7% → 32k 3.5% → 64k 3.2%,**絕對數 1→29→53 單調上升**。H1-miss 才是**乾淨、跨設定可比**的「池過大」證據;resolved/H2-refuse 因 thinking confound **暫不可比**。

### E.3 必做(讓三點趨勢乾淨)
**把 6k/32k SH 用 `thinking_level="minimal"` + `generation_max_length=256` 重跑**,再重算 resolved/H1/H2,才能宣稱「6k→32k→64k 持續惡化」。在此之前:
- **可宣稱**:H1-miss 絕對數 1→29→53 單調上升(跨設定穩健),候選池 crowd-out 隨 scale 惡化。
- **不可宣稱**:resolved 隨 scale 單調下降(64k 數字受 minimal confound 污染)。

---

## F. 對研究主張的貢獻(64k 新增的論點)

支撐「ingestion-time 用 LLM 做不可逆衝突裁決,在 FC 下系統性失敗」:

1. **不可逆性(再次坐實)**:qid32 在 step 2 已**存對** winner,卻在 step 3 被同實體異關係 fact 不可逆覆蓋 → query 無法回復。「破壞性裁決」即便一度正確也會被後續 over-fire 毀掉。
2. **失敗範圍擴大(新)**:64k 顯示結構失敗**不限衝突題** —— 3/4 真失敗是**無衝突的單一事實**(qid76/77/87),被同實體異關係(A4)、近重複碰撞、大池漏 ADD 摧毀。即 R1+R2 這組設計在**任何** fact 上都有毀損風險,只要候選池混入鄰近反事實。**比「只在衝突題失敗」更普遍**。
3. **新子模式 omission(新)**:qid76 揭露 update LLM 在 `n_candidates=156` 時**直接漏處理 new fact**,是「池過大壓垮 Component-3」最直接的證據(非 miss、非 over-fire,而是**根本沒輸出**)。
4. **收斂到同根因**:64k 全部 4 真失敗 = R1(候選按關係模板/實體/表面重疊鍵控 ≠ 槽位身分)+ R2(不可逆 update,含 over-fire 與 omission)。**無隨機 artifact**(空輸出已由 max_tokens=256 消除)。

**誠實 caveat(對使用者要求「若證據不夠說服必須知道」的回應)**:
- **query 端 magnitude 偏弱**:64k 100 題只有 **4 個真失敗(4%)**,mem0 規則正確率 **96%**。單看 FC-SH query,64k 的 mem0「大致可用」,稱不上戲劇性 systematic failure。
- **主張的力量在 write-time 聚合 + 機制純度**,不在 query EM:1678 對裡 4.4% 非解決(H1+H2),且每個 query 失敗都能 component-precise 對到 R1/R2,**無一隨機**。這是「存在性與機制普遍性」的證據,**不是「多數 query 會失敗」的證據** —— 論文措辭應如此界定。
- **趨勢未閉合**:resolved 64k 回升是 minimal confound(§E.2),**6k/32k minimal 重跑前不得宣稱單調惡化**。目前唯一跨設定穩健的 scale 證據是 **H1-miss 絕對數 1→29→53**。
- 若 minimal 重跑後 6k/32k/64k resolved 仍 ~95%+ 平緩,則「systematic failure」框架應改為「**特定結構條件(高關係密度 + counterfactual)下、可 component 定位的可預測退化 + 不可逆毀損**」—— 仍是有力且更精確的主張。

---

## G. 產物與腳本(可重現)
- write-time:`logs/sh_64k_l2/awt_result.json`(`awt_writetime_audit.py`)。
- query 條件分解:`logs/sh_64k_conditional.json`(`sh_query_conditional.py`)。
- 逐題分類:`logs/sh_64k_full_classify.json`(`sh_full_classify.py`,**注意 `--benchmark-defect` 須改 18,20**)。
- 規則自洽:`benchmark_rule_consistency.py "<arrow>" 6 analysis/results/sh_64k_RUN_gt.json`。
- GT:`analysis/results/sh_64k_RUN_gt.json`(`build_sh_gt_for_run.py`,100 題/66 has_pair)、`mh_64k_FULLPAIRS_gt.json`(1691 對)、`extraction_cache_64k.json`(4580 facts)。
- 逐案 trace:`update_decision.jsonl` / `extraction.jsonl`(`MEM0_CAND_LOG_DIR=logs/sh_64k_l2`)。
