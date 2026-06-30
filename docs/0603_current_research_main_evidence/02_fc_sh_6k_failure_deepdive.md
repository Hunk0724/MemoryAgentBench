# FC-SH 6k 非正常案例 deep-dive — 逐題 trace 與結構性問題

> ### ⚠️ 2026-06-08 方法學精修(read first)— event-bucket ≠ final-store ≠ QA
> 本檔(及 03/04)的 write-time fate(**H1-miss / H2-refuse / resolved / same-chunk**)是「**逐 update 事件**」分類,**不等於最終 store 狀態,也不等於 QA 對錯**。實測(6k 擴充 QA):18 個 event-bucket 失敗對中,**5 對最終 store 其實乾淨(new_only)→ QA 答對**(例:Figaro 舊版「作者=Beaumarchais」在 chunk8 被「Beaumarchais 出生於 Paris」A4 污染抹掉,chunk10 才加入新版「Thomas Kyd」→ awt 在 chunk10 標 H1-miss,但最終只剩新版)。
> → **事件統計數字不變(作為 write-time 事件描述正確)**,但 **QA 相關的「失敗對」須用最終 store 狀態(old_only / both = 真未解決)**,見 [05](05_expanded_eval_set.md)/擴充 QA。6k 對照:resolved 組 QA EM 97.9% vs 真未解決(old_only+both,13 對)EM 38.5%。

> **用途**:把所有「非單純成功」的具體題目逐一 trace（query → write-time → retrieval → inference），抓出**結構性問題**。配合 [01_mem0_fc_setup_and_results.md](01_mem0_fc_setup_and_results.md)(結果總表)。
> **建立**:2026-06-04　**資料**:mh/sh_6k_l2(L2 + frozen cache,vector,temp=0)。
> **⚠️ 兩個要先排除的非結構性 artifact**:
> - (a) **inference prompt「answer ... rather than the real facts in real world」**:benchmark 自帶,會在新舊都在時把模型推向反事實(影響 STALE 的"成功")。
> - (b) **gemini-3.1-flash-lite thinking 非確定性**:G3 無法真正關 thinking(`thinking_level=minimal` 也只是減量),`_answer_with_client` 漏設 thinking_config → 答題曾跑 **High thinking** → 偶發空輸出(`resp.text=None`,finish_reason=STOP)。temp=0 **不保證**確定。**這使單 trial EM 有雜訊**。見 [[project_gemini3_thinking_determinism]]。

---

## A. 結構性問題（真正的發現,撇除 artifact）

### A1 ★ same-chunk 衝突解決失敗(主因)
**現象**:衝突對的新舊兩版落在**同一個 chunk** 時,mem0 無法正確解決。
**根因(架構)**:update 只能對「已寫入 store 的候選(=先前 chunk)」做 UPDATE/DELETE。同 chunk 的新 fact 還沒寫入、**沒有合法 candidate id**。當兩個衝突新 fact 同在一 chunk,LLM 想 link 它們就只能瞎掰 id,或乾脆省略一版。
**三種觀察到的行為(對結構相同的情況,結果卻不一致 = 任意性)**:

| 行為 | 例(qid) | write-time 實際 | 結果 |
|---|---|---|---|
| (i) UPDATE 但 hallucinated-id | **qid42** Hines Ward | ch0(候選池=0): ADD `wide receiver`(世界); **UPDATE `cornerback` id='36'** → 空池無此 id → apply 丟棄 | 反事實 DROPPED → 答舊(wide receiver) ❌ |
| (ii) NONE 省略一版 | **qid34** Christianity / **qid52** | ADD `Jerusalem`(世界); `Taipei`(反事實)**完全無 event** | 反事實 DROPPED → 答舊 ❌ |
| (ii') NONE 省略,但**留下反事實** | **qid28**(Mantler)/**qid38**(France)/**qid69**(Canadair) | ADD 反事實(post-punk/Harare/Tucson); 世界版**無 event** | 只剩反事實 → 答對 ✅(但靠運氣方向對) |
| (iii) 兩版都 ADD | **qid12**(Parish)/**qid31**(Heinkel)/**qid57**(Elvis) | ADD 世界 + ADD 反事實 | STALE(都在); inference 靠 artifact(a)選反事實 → 答對 ✅(脆弱) |

→ **關鍵**:同 chunk 內「保留哪版/丟哪版/留兩版」基本是**任意的**(部分受 thinking 非確定影響)。答對與否取決於**剛好保留了反事實**(qid28/38/69)或 STALE 時 inference 剛好選反事實(qid12/31/57),**不是系統正確解決**。SH 6k 受 same-chunk 影響的題:失敗 qid34/42/52,脆弱成功 qid12/28/31/38/57/69。

### A2 cross-chunk write-time H2-refuse(qid7)
**現象**:候選 retrieval 成功,但 LLM **拒絕**把世界事實覆蓋成反事實。
**trace(qid7,Q: quarterback 的運動?gt=Muay Thai,old=American football)**:
- ch0: ADD `quarterback ... American football`(世界,seq31)。
- ch1(Muay Thai/seq50 進來): candidate top-5 **rank1 = American football,score 0.902**(候選 retrieval 成功,H1 過)。
- update: **UPDATE id=17 把 American football → American football(prev==new,no-op!)** + Muay Thai 給 NONE。
- → LLM 看到衝突、候選在手,卻 **no-op 更新(保留世界)+ 丟反事實**。
**retrieval/inference**:American football 留在 DB → 被檢索 → 答 American football ❌。
→ 這是 **write-time 的參數知識覆蓋(H2)**,cross-chunk、candidate 可用,純粹 LLM 不願寫反事實。**與 A1 的架構失敗不同**(A1 是想做卻做不到;A2 是能做卻不做)。

### A3 inference cross-fact 混淆(qid1)
**現象**:記憶正確、檢索到正解,但 inference 抓了**另一條共用主詞的 fact 的 object**。
**trace(qid1,Q: Nobuhiro Watsuki famous for?gt=The Fairly OddParents)**:
- write-time/ingestion: 正常(winner STORED, old SUPERSEDED)。
- retrieval: **rank0 = 正解 `Watsuki is famous for The Fairly OddParents`**; rank10 = `Vito Corleone was created by Nobuhiro Watsuki`(另一條 Watsuki 的 fact)。
- inference: 答 **`Vito Corleone`** ❌ — 把「famous for」與「created by」搞混,抓了共用主詞 Watsuki 的另一 fact 的 object。
→ **用了記憶但讀錯 fact**(同主詞不同關係的混淆)。非參數覆蓋、非隨機。

---

## B. 非結構性 / artifact 案例（需與 A 分開看）

### B1 thinking 非確定空輸出(qid66/89/97)
- 原始 run: `output=''`(High thinking,`resp.text=None`,completion_tokens=6=只有 thought 無答案)。
- **重跑(同 prompt,temp=0)**: finish_reason=**STOP**(非 safety/recitation), **非空**: qid89→`Washington, D.C.`(對)、qid97→`Charles Frederick...`(對)、qid66→`Chairperson of Congolese Party of Labour`(仍錯,cross-fact 類)。
- → **空輸出 = thinking model 偶發無答案文字,非真失敗**(qid89/97 其實答得出)。是 backbone 非確定性,非衝突解決問題。

### B2 STALE「成功」靠 benchmark prompt(qid12/31/57)
- 新舊都在 DB、都被檢索,模型答反事實(Elvis 娶 Charles the Bold 等明顯反現實)。
- 機制假設(n=3): prompt「answer ... **rather than the real facts in real world**」在無序號可用時推向反事實。
- → **write-time 其實沒解決(both present)**,靠 benchmark prompt 湊巧答對。歸入 A1(iii)。

---

## C. 全非正常案例彙整(SH 6k,8 失敗 + 6 脆弱成功)

| qid | 類別 | write-time | retrieval | inference | 結構問題 |
|---|---|---|---|---|---|
| 42 | FAIL | same-chunk UPDATE hallucinated-id 丟反事實 | 只取到舊 | 答舊 wide receiver | **A1** |
| 34/52 | FAIL | same-chunk NONE 省略反事實 | 只取到舊 | 答舊 | **A1** |
| 7 | FAIL | cross-chunk no-op update + 丟反事實 | 取到舊(rank1) | 答舊 American football | **A2** |
| 1 | FAIL | 正常 | 取到正解(rank0) | cross-fact 混淆答 Vito Corleone | **A3** |
| 66/89/97 | FAIL | 正常 | 取到正解 | 空輸出(thinking) | B1(artifact) |
| 28/38/69 | 脆弱成功 | same-chunk NONE 省略,**剛好留反事實** | 取到新 | 答新 | A1(任意) |
| 12/31/57 | 脆弱成功 | same-chunk 兩版都 ADD(STALE) | 都取到 | 靠 prompt 選反事實 | A1(iii)+B2 |

→ **結構性問題排序**: **A1 same-chunk(影響 9 題:3 失敗 + 6 脆弱)** > A2 cross-chunk H2-refuse(1) > A3 cross-fact 混淆(1)。其餘為 thinking artifact(3)。
