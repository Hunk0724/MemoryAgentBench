# FC-SH 32k 非正常案例 deep-dive + 6k→32k 結構性證據

> ### ⚠️ 2026-06-08 方法學精修(read first)
> write-time fate(H1-miss / H2-refuse / resolved / same-chunk)是「**逐 update 事件**」分類,**≠ 最終 store 狀態 ≠ QA 對錯**。某些 event-failed 對在後續 chunk 被清成 new_only(最終乾淨、QA 答對);某些 event-resolved 也可能後續再被破壞。**事件統計數字不變**,但 QA 相關的「失敗對」須改用**最終 store 狀態(old_only / both = 真未解決)**。詳見 [02 頂部](02_fc_sh_6k_failure_deepdive.md) 與 [05](05_expanded_eval_set.md)。

> **用途**:32k 版的逐案 trace(對應 [02](02_fc_sh_6k_failure_deepdive.md) 之於 6k),並彙整 6k→32k 的**結構性問題證據**(支撐研究主張)。
> **資料**:mh/sh_32k_l2(L2+cache,vector,temp=0,**但答題曾跑 High thinking**→空輸出 artifact)。write-time 用 `mh_32k_FULLPAIRS_gt`(837 in-store 對,query-independent);SH query 用 `sh_32k_RUN_gt.json`(該 run 自己的 queries)。
> ⚠️ FC-SH queries **隨長度不同**(6k≠32k),勿用 6k GT 套 32k。

---

## ⚠️ 2026-06-05 修正與深化(逐案 trace Layer A + candidate_pool 後的更正)

> 觸發:重檢 5 BAD-SUP 的歸因是否成立、A4 是否其實是 A1 的下游。腳本 [scripts/trace_badsup_cases.py](scripts/trace_badsup_cases.py)(逐案)+ [scripts/a4_contamination_audit.py](scripts/a4_contamination_audit.py)(全域 837 對)。**初版本檔有兩處需更正,結論方向不變但歸因更乾淨。**

**修正 1 — 5 BAD-SUP = 2 benchmark 答案鍵瑕疵(qid8/9)+ 3 A4(qid87/95/98):**(2026-06-05 二次深查,**benchmark-only 確認、不靠 MQuAKE**)
- **qid8/qid9 是 benchmark 自己的答案鍵與其宣告規則矛盾,不是 mem0 失敗,也不是 MQuAKE 對應錯**。直接讀 benchmark 原始 item(`ai-hyz/MemoryAgentBench` Conflict_Resolution idx5,**context md5 與我們的完全一致**):
  - Q8「Which city did Noel Pemberton Billing work in?」答案鍵 = **London**;但同 context 有 `707. London` **和** `1929. Washington, D.C.`(同主詞同關係)。Q9 答案鍵 = **Rome**;context 有 `1291. Rome` 和 `2016. Watertown`。
  - benchmark 的 prompt 模板([utils/templates.py:81](../../utils/templates.py#L81) rag_agent)**白紙黑字**:「newer fact has larger serial number ... find the newest fact with larger serial number」。→ 按規則 Q8 該答 **Washington D.C.(seq1929,較大)**,但答案鍵標 London(seq707,較小)→ **答案鍵直接違反 benchmark 自己的規則**。
  - **mem0 按 ingestion 順序保留大序號(Washington D.C./Watertown)正是 rule-compliant**;是 benchmark 答案鍵自相矛盾去懲罰正確的衝突解決 → **非 mem0 失敗,從分母剔除**。
- **全 100 SH 僅 qid8/9 兩題**有此瑕疵(腳本 [scripts/benchmark_rule_consistency.py](scripts/benchmark_rule_consistency.py),benchmark-only):**65 題為衝突題,63 題答案=最大序號(規則自洽),僅 2 題答案=較小序號**。→ 孤立瑕疵,非系統性誤解。
- ⚠️ **write-time FULLPAIRS denominator 未受影響**:write-time 把大序號當 winner(與規則一致),(707,1929) winner=1929 標 **resolved 成功**;每個 FULLPAIRS pair 都是單一 requested_rewrite 的 old/new(within-case)→ A1/A2/A4 的 837 對計數乾淨。矛盾只在 **query 端答案鍵**。
- qid87/95/98 才是真 A4(gt 為大序號該留,被同主詞/同受詞**不同關係** fact over-fire 覆蓋)。
- (成因註:這 2 題的答案鍵取了**真實世界事實**(London/Rome,較小序號),context 裡同 slot 又有另一筆反事實編輯(較大序號)→ 答案鍵建構時誤取真實版而非編輯版。腳本 [scripts/collision_detect.py](scripts/collision_detect.py) 為純 context 版偵測,結論一致。)

**修正 2 — A4 ≠ A1 的下游(使用者假設「A4 是否因 A1 才覆蓋無關 fact」的答案:否):**
全部 3 個被 query 的 A4(qid87/95/98)+ 全域 16 個 A4 污染中 **13/16**,被覆蓋的 gt **在污染者的 top-5 候選裡(rank 1–3)**。即候選檢索**成功取到 gt**,失敗在 **update LLM 主動把「同主詞/同受詞、不同關係」的候選誤判成衝突而 UPDATE 覆蓋(over-fire)**。→ **A4 是 Component 3(update-decision)失敗,與 A1(Component 2 candidate-miss)機制上不同**。

| qid | gt(被毀) | 污染者(同實體、異關係) | gt 在污染者 top-5 |
|---|---|---|---|
| 87 | Natalie Portman 宗教 | Natalie Portman **married** Benjamin Millepied | rank2 (0.813) |
| 95 | Henri Grégoire 公民 India | Henri Grégoire **religion** Christianity | rank2 (0.837) |
| 98 | South Korea 元首 Mauro Carlesse | South Korea **capital** Seoul | rank3 (0.799) |

**深化 — A1 與 A4 是同一根因的兩面(比「4 條獨立路徑」更站得住):**
> vector 候選檢索按「**關係模板相似度 + 實體重疊**」排序,而非「**(主詞, 關係) 槽位身分**」。
> - **A1**:真正同槽位的舊版被「同關係不同主詞」干擾項擠**出** top-5 → miss → 兩版都 ADD。
> - **A4**:「同主詞/同受詞不同關係」的 fact 被擠**進** top-5 → 不可逆 LLM 裁決挑中它覆蓋 → 無關 fact 被毀。
>
> 兩者皆源於「embedding 相似度 ≠ 槽位身分」+「LLM 對錯誤鍵控的候選集做不可逆 ADD/UPDATE/DELETE」。A2(拒覆蓋反事實)才是獨立第三軸(參數知識),A3(same-chunk)是架構軸。

**修正 3 — A1/A2 不負責解釋這 10 個 QA 失敗(兩軸不可混):**
10 個 SH-query 失敗逐一歸因:**2 benchmark 答案鍵瑕疵(qid8/9,非 mem0,見修正 1)**+ 3 A4(qid87/95/98)+ 3 空輸出 thinking artifact(qid7/33/51)+ 2 cross-fact inference(qid23/64)。→ **真正可歸因 mem0 衝突解決的 query 失敗 = 3(全 A4)**。**A1(H1-miss)與 A2(H2-refuse)一個都沒造成 QA 失敗** — 它們在 837 對裡各 29/28 例 write-time 退化,但**這批 100 題 SH query 沒抽樣到**(抽到時剛好被乾淨解決)。
- **正確框架 = 兩條互補但分開的軸**:(軸1)write-time 退化(query-independent 837 對:A1/A2/A4 隨 scale 上升)= 主張的乾淨證據;(軸2)query-time 端到端(100 題:只有 A4 傳導 + benchmark 反常 + inference)。**A1/A2/A3 是 write-time 退化的必要證據,不負責解釋 10 個 QA 失敗。**

**附帶 — 32k 脆弱成功 = 0(對比 6k 的 6 個):** 57 個 has_pair 答對題全部乾淨 SUPERSEDED,無 old 洩漏/STALE/反常蒙對。6k 脆弱成功來自 same-chunk 任意性,32k same-chunk 占比 10%→1.6% 故消失(掃描 [logs/sh_32k_conditional.json](logs/sh_32k_conditional.json))。

---

## A. write-time 結構性問題(核心證據,837 in-store 對)

A-WT 32k: resolved **93.1%**(6k 98.6%)/ **H1-miss 29**(6k 1)/ **H2-refuse 28**(6k 1)/ same-chunk 13。

### A1' Candidate-retrieval crowd-out(H1-miss,32k 主因之一,1→29)★
**component**: ingestion 第 2 步「每個 new fact 取 cosine top-5 既有記憶」。
**問題**: store 變大後,**同關係類型(capital-of / sport / university)不同主詞的 fact 大量存在**,embedding 對「關係型態」的相似度蓋過「主詞匹配」→ 真正的同主詞舊版被擠出 top-5 → update LLM 根本沒看到舊版 → 只 ADD 新版,衝突未解(新舊並存)。
**具體例**:
- winner=`The capital of Japan is Bondi Junction`;真夥伴 `The capital of Japan is **Tokyo**` 不在 top-5。top-5 反而是 `capital of Australia is Canberra`(0.831)、`capital of Israel is Jerusalem`(0.773)、`capital of Italy is Rome`(0.773)——全是「capital of X」別的主詞。
- winner=`goaltender ... pesäpallo`;真夥伴 `goaltender ... ice hockey` 不在;top-5 全是別的「X associated with sport Y」。
- winner=`William Shakespeare educated University of Oxford`;真夥伴 King Edward VI School 不在;top-5 全是別的「university where X」。
→ **這是「池過大」在 candidate retrieval 的直接體現,且隨長度單調惡化**。

### A2 Write-time H2-refuse(LLM 拒絕用反事實覆蓋世界事實,1→28)★
**component**: ingestion 第 3 步 update LLM 判 event。
**問題**: 舊版**已在候選池且 rank1**,LLM 卻不發 UPDATE(或發 no-op),保留世界事實、丟反事實。
**具體例**(舊版 rank1,LLM 不覆蓋):
- winner=`Maksim Chmerkovskiy married Johann Adolph Hasse`;loser=`...married Peta Murgatroyd`(rank1,**0.917**)→ 拒覆蓋。
- winner=`Boston founded by Ramu Yalamanchi`;loser=`...John Winthrop`(rank1,0.791)→ 拒。
- winner=`The Normal Heart created in Nazi Germany`;loser=`...United States of America`(rank1,0.911)→ 拒。
→ candidate 取得成功(rank1 高分),純粹 **LLM 不願寫反事實**=參數知識覆蓋。**能做卻不做**。

### A3 same-chunk(6k 主因,32k 退居次要)
32k same-chunk 僅 13(占 1.6%,6k 占 10%):新舊版本在大 context 更分散,較少落同 chunk。機制同 [02](02_fc_sh_6k_failure_deepdive.md) A1(UPDATE-hallucinated-id / NONE 省略 / 兩版都 ADD,任意)。

### A4 ★ Cross-fact 污染(update 覆蓋到無關 fact,6k 2→32k 16)
> ⚠️ **見頂部 2026-06-05 修正**:A4 = **update LLM over-fire**(候選取到 gt 卻仍覆蓋它),**非 A1 下游**;且 qid8 應移出 A4(是 benchmark 反常)。

**component**: ingestion 第 3 步 update LLM(候選檢索成功,LLM 自己誤判)。
**問題**: update LLM 對候選池判 UPDATE 時,**把某 fact 的槽位覆蓋成另一條「同主詞/同受詞、不同關係」fact 的內容**(entity confusion)→ 原 fact(含反事實)被「superseded」成錯內容,**正確 fact 被摧毀**。被毀的 gt 通常**就在污染者 top-5(rank 1–3)**,故失敗在 update 判斷,非候選 miss。
**具體例(32k SH BAD-SUP,真 A4)**:
- gt `Natalie Portman 宗教 interdenom.`(seq1583)被覆蓋成 `Natalie Portman is married to Benjamin Millepied`(同主詞、異關係;gt 在污染者 top5 rank2)。
- gt `Henri Grégoire 公民 India`(seq1454)被覆蓋成 `Henri Grégoire ... religion Christianity`(同主詞、異關係;rank2)。
- gt `South Korea 元首 Mauro Carlesse`(seq324)被覆蓋成 `The capital of South Korea is Seoul`(共用受詞 South Korea、異關係;rank3)。
→ 全域 **16 例**(6k 僅 2);其中 13/16 gt 在污染者 top5。32k 直接造成 **3 個 SH 失敗**(qid87/95/98)→ **隨 scale 放大**。(qid8 經實查為 benchmark 反常,非 A4,見頂部修正。)

---

## B. FC-SH 32k query 失敗逐案(10 個,EM 90%)

### B1 write-time 傳導(5,BAD-SUP)— **2 dataset 碰撞 + 3 A4**(2026-06-05 二次深查)
trace gt fact 被誰覆蓋(`who_superseded`,逐案實查 Layer A + MQuAKE-CF 來源):
| qid | gt seq vs old | 被覆蓋成 | gt 在污染者 top5 | 對應結構問題 |
|---|---|---|---|---|
| qid8 | 707, slot 有更大 1929 | `1929. ...Washington D.C.`(同主詞同關係,更大序號) | rank1 (0.916) | **benchmark 答案鍵瑕疵**(答案=較小序號 London,違反 largest-serial 規則),**非 mem0 失敗** |
| qid9 | 1291, slot 有更大 2016 | `2016. ...Papal States is Watertown`(更大序號) | rank1 (0.918) | **benchmark 答案鍵瑕疵** |
| qid87 | 1583 > old 112 | `Natalie Portman is **married** to Benjamin Millepied`(異關係) | rank2 (0.813) | **A4**(update over-fire) |
| qid95 | 1454 > old 1398 | `Henri Grégoire **religion** Christianity`(異關係) | rank2 (0.837) | **A4** |
| qid98 | 324 > old 21 | `The **capital** of South Korea is Seoul`(共用受詞、異關係) | rank3 (0.799) | **A4** |
→ **5 BAD-SUP = 2 benchmark 答案鍵瑕疵(qid8/9,從 mem0 分母剔除)+ 3 A4(qid87/95/98,真 mem0 write-time 失敗)**。瑕疵題:同 (主詞,關係) 在 context 有更大序號的編輯版,benchmark 答案鍵卻標較小序號的真實事實 → 違反其自宣告的 largest-serial 規則,**mem0 保留大序號反而 rule-compliant**(benchmark-only 確認,見頂部修正 1)。A4 題:候選取到 gt 卻被 update LLM over-fire 覆蓋。**A1/A2 不在這 10 個失敗內**(見頂部修正 3)。

### B2 inference 失敗(5,CORRECT-ingestion,記憶其實正確)
| qid | gt(反事實) | 模型答 | 性質 |
|---|---|---|---|
| qid7 | Montanus of Phrygia | '' | **空輸出**(thinking artifact) |
| qid33 | Washington, D.C. | '' | 空輸出 |
| qid51 | Roch Marc...Kaboré | '' | 空輸出 |
| qid23 | Charlie Hebdo | 'The Birth of Tragedy' | **cross-fact 混淆**(答了別條 fact) |
| qid64 | Neuromancer | 'Pattern Recognition' | cross-fact(同作者 Gibson 另一作品) |

→ 3 空輸出(thinking artifact,非結構)+ 2 cross-fact 混淆(A3-inference,6k 也有,持續)。

---

## C. 6k→32k 結構性證據彙整(對研究主張)

| 結構問題 | component | 6k | 32k | 趨勢 |
|---|---|---|---|---|
| **A1 H1-miss** crowd-out | candidate retrieval(top-5)| 1 | **29** | 隨池放大 ★ |
| **A2 H2-refuse** | update LLM(判斷)| 1 | **28** | 放大 ★ |
| **A4 cross-fact 污染** | update LLM(over-fire 覆蓋)| 2(全域)| **16 全域 / 3 SH**(qid87/95/98)| 放大 ★ |
| A3 same-chunk 架構 | extraction+update | 16(10%)| 13(1.6%)| 占比降(版本分散)|
| (inference cross-fact 混淆)| inference(讀取)| 有 | 有(qid23/64)| 持續 |
| resolved 率 | — | 98.6% | 93.1% | 退化 |

> **根因統整(2026-06-05 修正,取代「4 條獨立路徑」)**:write-time 結構失敗收斂到 **2 個根因 + 2 軸**:
> - **根因 R1 = 候選檢索鍵控錯誤**(embedding 按關係模板/實體重疊排序 ≠ (主詞,關係) 槽位身分)。**A1 與 A4 是 R1 的兩面**:A1 把真舊版擠**出**(→ miss → 兩版 ADD);A4 把同實體異關係 fact 擠**進** → LLM over-fire 覆蓋(→ 無關 fact 被毀)。
> - **根因 R2 = update LLM 不可逆裁決品質**:A2(拒用反事實覆蓋,參數知識)。
> - **架構軸 A3**:same-chunk 新 fact 無合法候選 id(mem0 實作層,占比隨 scale 降)。
> A1/A2/A4 皆隨 scale 放大。**注意 A4 非 A1 下游**:13/16 污染中 gt 在污染者 top5,失敗在 update 判斷而非候選 miss。

**支撐主張的點**:
1. **不可逆性**:write-time 一旦解錯(丟反事實/over-fire 覆蓋),query **無法回復**(32k 的 3 A4 題、6k 的 4 題皆無解)。這正是「破壞性衝突解決」的代價。(qid8/9 是 benchmark 答案鍵瑕疵、非 mem0 失敗,已剔除。)
2. **結構性失敗收斂到 2 根因**(R1 候選鍵控錯誤 → A1+A4;R2 LLM 不可逆裁決 → A2),都在 6k 出現、32k 放大,**非獨立 artifact**。
3. **單調惡化**:resolved 98.6→93.1,A1/A2 各 1→~28-29,A4 全域 2→16。
4. **兩軸分開**:write-time 退化(query-independent 837 對)是主證據;query-time 10 失敗僅 A4(3)傳導,A1/A2 未被此 query 抽樣。勿用 10 失敗反推「A1/A2 不重要」。

**誠實 caveat(需 64k 釐清)**:
- 6k resolved 98.6%、32k 仍 93.1% → 目前證據是「**隨 scale 結構性退化**」,**非小尺度就 systematic failure**。「systematic/普遍」需 64k(甚至 262k)顯示**持續惡化趨勢**才站得住。
- **空輸出 = generation-budget 截斷 artifact(非 thinking 隨機,非衝突解決)**(2026-06-05 controlled re-trial 釐清,見 §D):3 空輸出(qid7/33/51)在 `generation_max_length=10` 下**確定性**空(3/3 trial);放大 max_tokens→**三題全答出完全正確答案**。→ EM 數字被截斷壓低,真實 EM 天花板 **93%**;**write-time 指標(resolved/H1/H2,query-independent)才是乾淨證據**。
- 若 64k 仍 ~90% resolved,則「systematic failure」框架偏弱,應改框為「**特定結構條件(高關係密度 / counterfactual)下的可預測退化**」。

---

## D. ★ 完整逐題分類 + 空輸出 re-trial(6k §C 等級,2026-06-05)

> 腳本:分類 [scripts/sh_full_classify.py](scripts/sh_full_classify.py)、re-trial [scripts/retrial_empty_outputs.py](scripts/retrial_empty_outputs.py)。資料 sh_32k_l2 + 本 run retrieval/results。

### D.1 全 100 題互斥分類(總和=100,nominal EM=90)

| 類別 | n | 說明 |
|---|---|---|
| ✅ single-correct | 33 | no_pair 單一事實,答對 |
| ✅ clean-resolved | 57 | has_pair,winner STORED + old 消失,答 winner |
| **FRAGILE(脆弱成功)** | **0** | **無 STALE / 無 same-chunk 蒙對 / 無 leak-but-correct**(對比 6k 的 6 個;32k same-chunk 占比崩到 1.6% 故消失) |
| ❌ benchmark-defect | 2 | qid8/9(答案鍵違反 largest-serial 規則,非 mem0,§修正1) |
| ❌ FAIL-A4(真 mem0 write-time) | 3 | qid87/95/98(winner 被同實體異關係 fact over-fire 覆蓋) |
| ❌ FAIL-inference cross-fact | 2 | qid23/64(winner 乾淨檢索到,答題 LLM 讀錯同主詞另一條 fact) |
| ❌ artifact 截斷空輸出 | 3 | qid7/33/51(max_tokens=10 截斷,模型其實答對,見 D.2) |

→ **真正可歸因 mem0 的 query 失敗 = 5**:3 write-time(A4)+ 2 inference(cross-fact)。其餘 5 = 2 benchmark 瑕疵 + 3 generation artifact,**皆非 mem0**。

### D.2 空輸出 re-trial(qid7/33/51)— 確定是 generation-budget 截斷,非失敗

精準重放 stored inference prompt(`system_prompt + "\n\n" + user_message`),同 Vertex Gemini call:

| qid | gt_answer | 同設定 max_tok=10 ×3 | 放大 max_tok=2048 | 判定 |
|---|---|---|---|---|
| 7 | Montanus of Phrygia | `''` ×3(MAX_TOKENS,thought_tok=0)| **`Montanus of Phrygia` ✓**(STOP)| 截斷 artifact,**正解被壓抑** |
| 33 | Washington, D.C. | `''` ×3 | **`Washington, D.C.` ✓** | 同上 |
| 51 | Roch Marc Christian Kaboré | `''` ×3 | **`Roch Marc Christian Kaboré` ✓** | 同上 |

- **根因更正**:不是「thinking 非確定性」(thought_tok=**0**、同設定 3/3 **確定性**空),而是 **benchmark `generation_max_length=10` 對此模型太小** → 較長答案(≥~5-6 token)在 10-token 上限下回空。所有方法(LCA/RAG/mem0)共用此 config → **跨方法比較公平,但絕對 EM 被壓低**。
- **真實 EM 天花板 = 93%**(90 + qid7/33/51 修正)。**EM 不該當主證據**,write-time 指標才乾淨。
- 對照:qid23/64 放大 budget **仍穩定輸出相同錯答**(STOP)→ **真 cross-fact inference 混淆**,非截斷。

### D.3 真 mem0 失敗的 5 題逐案(structure 映射)

| qid | gt(反事實) | 機制 | 階段/結構 |
|---|---|---|---|
| 87 | Natalie Portman 宗教 interdenom. | winner 被 `Natalie Portman married Benjamin Millepied` over-fire 覆蓋(gt 在污染者 top5 rank2)| **A4** write-time(update over-fire,R1)|
| 95 | Henri Grégoire 公民 India | winner 被 `Henri Grégoire religion Christianity` 覆蓋(rank2)| **A4** write-time |
| 98 | South Korea 元首 Mauro Carlesse | winner 被 `capital of South Korea is Seoul` 覆蓋(rank3)| **A4** write-time |
| 23 | Stephen Crane famous for Charlie Hebdo | winner 乾淨檢索到 rank0,LLM 答 `The Birth of Tragedy`(同主詞另一條)| **inference cross-fact**(R-inf,非 write-time)|
| 64 | William Gibson famous for Neuromancer | winner rank0,LLM 答 `Pattern Recognition`(Gibson 另一作品)| **inference cross-fact** |

→ **write-time 衝突解決失敗 = 3(全 A4);inference 層失敗 = 2**。與 §C 兩軸框架一致:A1/A2 的 write-time 退化(29/28 例)未被這 100 題抽樣到,query 端只有 A4 傳導。

### D.4 write-time 操作面(即便多數題未對應 ingestion 錯誤,仍盤點)

100 題對應的 winner fact write-time 命運:**STORED(clean)90 + SUPERSEDED(A4 over-fire)3 + benchmark-defect 的 winner 由 ingestion 順序正確保留大序號(2,但 benchmark 答案標小序號)**。其餘無 DROPPED / same-chunk 落在被 query 的 winner 上 → **被 query 到的衝突對,write-time 幾乎全乾淨解決(僅 3 A4 例外)**,印證「32k write-time 對 SH-query 的衝擊集中在 A4,A1/A2 退化主要發生在未被 query 的 pair」。
