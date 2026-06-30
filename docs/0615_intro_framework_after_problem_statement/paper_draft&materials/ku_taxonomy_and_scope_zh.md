# KU 分類與戰場定位 — 我們處理的是哪一種知識更新問題

> 定錨筆記(2026-06-23;**2026-06-24 修訂** §5/§6:extraction 從「正交前提」改為
> 「保守寫入 commitment 的一部分」+ 單一統一抽取器 + source-based 機制)。以四個
> benchmark 的 paper + eval code 證據,確立我們的架構針對哪一種 KU 問題、為什麼、
> 以及什麼明確不在範圍內。作為 methodology / experiment / 口試的論述定錨。
> 對應 memory:`project_ku_taxonomy_battlefield`。
> (英文版 `ku_taxonomy_and_scope.md` **尚未同步本次 §5/§6 修訂**。)

---

## 0. 一段話結論

KU 文獻**不是單一問題**。我們調查的四個 benchmark,「knowledge update」依**權威值如何被決定**分成兩類:

- **Bucket (B) — 隱式 recency /「newer-wins」**:演變中事實的權威值 = 它**最新的權威主張**。(FC、LongMemEval、BEAM)
- **Bucket (A) — 使用者明確更正**:權威值由明確更正言語行為決定(「我說錯了,更正」);**recency 不會贏**(後續同屬性的提及可能是雜訊)。(MemBench)

**我們的戰場是 Bucket (B)。** 我們的兩個結構性 commitment —— *保守寫入*(保留全版本、不做跨筆 LLM 判斷)+ *query-time temporal resolution*(在 query 相關的版本中以 recency 取 argmax)—— 正是 Bucket (B) 的標準解。四個主流 benchmark 有三個落在這裡。

---

## 1. 分類與證據

| Benchmark | 論文任務名 | Bucket | 殺手級證據(paper) |
|---|---|---|---|
| **FC**(MemoryAgentBench) | *Selective Forgetting*(FC-SH/MH) | **(B) recency** | 「newer facts have larger serial numbers… **finding the newest fact**」;「**prioritize later information**」。MQuAKE 反事實改寫,**無更正標記**。論文把 explicit-negation(Policy B)當 ablation 測,**反而更差**(−4.5)→ recency 才是設計。 |
| **LongMemEval** | *Knowledge Update (KU)* | **(B) recency** | 同屬性兩筆**各自標日期**的主張;問句「**my most recent / last**」;judge:「correct as long as **the updated answer** is the required answer」。無「我說錯了」。 |
| **BEAM** | *Knowledge / Information Update* | **(B) recency** | original→update 配對;更新**刻意隱式**(「embed new value in narrative, **don't state 'X is now Y'**」);問句問「**most recent version rather than outdated**」並**移除所有變更線索** → 逼模型靠 recency 推。 |
| **MemBench** | *Knowledge-updating*(Factual Memory) | **(A) 明確更正** | 「**I just realized I need to correct myself**—only lasts for one day」,gold=被更正值。**全文無 newer-wins**;code 顯示更正後還有同屬性雜訊 → recency 會答錯。 |

證據兼具 **paper 層**(上述定義/引文)與 **code 層**(eval harness 檢視,見 §3)。

---

## 2. Bucket (B) 內部細分 → 我們的主結果 vs 泛化

recency 的「給法」不同,決定主結果與泛化:

- **FC = 外顯化 / 工程化 recency**:recency 以 **serial number** 明確給出(「序號越大越新」)。我們的 **per-chunk `ordinal`** 直接對應,且計分為 **substring-EM**(最嚴)。→ **乾淨、受控的主結果。**
- **LongMemEval / BEAM = 自然化 recency**:只有 timestamp / turn 順序(BEAM 還拔掉線索);**LLM-judge** 計分;真實多 session 對話。→ **泛化** —— 同一機制更難、更真實的測試(temporal resolution 必須**推斷** recency,而非讀序號)。

---

## 3. Eval 協定事實(嚴謹性 — 受測系統實際看到什麼)

逐一從各 benchmark 的 eval code 驗證。兩件事最關鍵:(a)**沒有任何 benchmark 把結構化 fact store 交給記憶方法** —— 從 raw NL 抽取是普世的;(b)**計分與 truth 定義各不同**。

| Benchmark | 餵給 SUT 的 ingestion | Oracle-only(執行時拿不到) | 計分 | 「truth」機制 |
|---|---|---|---|---|
| FC | 編號 NL 事實清單(分塊) | gold answer | **SubEM** | 最大序號 |
| LongMemEval | 一整塊**串接**、依日期排序、帶 role 的 transcript(或 RAG top-k) | `has_answer`(剝除)、`answer_session_ids` | **LLM-judge** | 靜態 gold=最新值 + judge prompt |
| BEAM | 逐 turn role/content stream(長文 tail-prune 或 RAG) | `user_messages.json`、`time_anchor`(丟棄)、rubric、`source_chat_ids` | **LLM-judge vs rubric** | rubric=更新值 |
| MemBench | **真・逐 turn streaming**,一步一 turn | `(rel,attr,value)`、`target_step_id`、`choices`、`ground_truth` | **多選 EM** | 明確更正 turn |

需收回的早期過頭話(經 code 檢視修正):
- ❌「從資料結構讀權威子集」—— SUT 只看到 raw NL turns(+ 有就帶 role/time)。`(rel,attr,value)` 與 `user_messages.json` 都是 **oracle-only**,執行時拿來抽取=作弊。
- ❌「BEAM 分離 `user_messages` = 背書 user-authoritative」—— 那是生成 pipeline 產物,絕非執行輸入,**不可引用**。
- ❌「truth = 時間最新,普世成立」—— **MemBench 違反**(truth=明確更正;後續提及是雜訊)。

---

## 4. 為何「保留全版本」是*必要*而非方便(最強論證)

即使在純 newer-wins 下,記憶也必須**保留歷史**,因為**同一個 store 還要回答歷史查詢**:

- LongMemEval 與 BEAM **同時包含** *knowledge-update*(問**當前**值 → 取最新)**與** *temporal-reasoning*(問**過去 / 某時點**值 → 需要舊版本)。LongMemEval 各有 **133 題 KU、133 題 temporal-reasoning**。
- **破壞性 write-time consolidation**(覆蓋成最新)**會毀掉歷史 → temporal-reasoning 直接無解。**

因此:**寫入階段保留全版本,把「取哪個版本」推遲到 query-time,policy 依問題而定**(KU 取最新;temporal 取指定時點)。這是架構最深的存在理由,且由 benchmark 自身的能力題型分布背書 —— 不只靠 KU 任務。

---

## 5. Scope 聲明(in / out)

**介面前提:** 輸入是 **role-attributed 對話流(user/assistant)+ 原子顆粒度**。三 benchmark 都滿足(§6 驗證)。

**範圍內(我們的貢獻):**
- **Bucket (B) 隱式 recency KU**。
- 兩個結構性 commitment:
  - **保守寫入**:用**單一統一抽取器**忠實捕捉使用者主張的事實(個人 + 反事實世界)、**保留全版本**、不跨筆 LLM 判斷。**「忠實存入」是這個 commitment 的一部分,不是正交前提**(修正自舊版,見 §6)。
  - **query-time KU 解析**:`(S,P)` + LLM fallback 做 identity grouping;**temporal argmax**;functional vs multi-valued guard。
- 推論期契約:**記憶對 LLM 參數知識具權威性**(讓被信任的使用者反事實能覆蓋模型)。
- **Additive ablation(兩 delta 皆我們的)**:(a) stock mem0(native) →(b) **+ 忠實存入**(統一抽取器、仍破壞性寫) →(c) **Ours**(+ 保守寫入 + query-time 解析)。**(a)→(b)= 忠實存入貢獻;(b)→(c)= 解析貢獻。** 同一 benchmark 內 (b)/(c) 抽取相同 → apples-to-apples;(a) 為誠實 out-of-box。
- 評估:**FC 主結果**(外顯 recency、SubEM、受控);**LongMemEval + BEAM 泛化**(自然 recency、judge、真實對話)。

**範圍外(明文標出,不藏):**
- **Bucket (A) 明確更正 KU(MemBench)**:temporal-argmax 會答錯(truth ≠ 最新)→ **future work:correction-aware resolver**。佐證 keep-all + **可插拔** query-time 解析是正確通用設計。
- **「答案在 assistant turn」的題型**(如 single-session-assistant):因我們存 **user 主張**而出界 → 題型 scope,揭露即可(minor)。
- **抽取的 NLP 品質本身**:我們固定用同一套統一抽取器,**接受並分析**其跨 dataset 的 recall 落差(那是泛化發現),不為單一 dataset 調 prompt。

---

## 6. 統一抽取器 —— 保守寫入 commitment 的一部分(修正:不再當「正交前提」)

> 決策脈絡:起點是「放寬 native 讓它也抽世界事實」(broadened-native,FC ≈100%)。中途一度退成「extraction 正交、各 benchmark 換抽取」,**但那會讓『我們的方法』變成多套 config、削弱泛化 claim**。**最終收斂**:設計**單一、改進自 native 的抽取器**,跨所有 dataset 用同一套;**「忠實存入」OWN 進保守寫入 commitment(非正交)**;只剩「從髒文字抽乾淨原子 fact 的 NLP 品質」算正交工具問題。

**從 mem0 native 的四處 de-overfit 改動**(錨定 native,皆 domain-neutral):

| # | 改動 | 原則 |
|---|---|---|
| 1 | **解除「只存個人」限制**(Personal→Memory Organizer;允許關於自己**或世界**的事實),**不列舉屬性** | 存 delta(移除舊版 FC 形狀的屬性列舉 = overfit) |
| 2 | **Faithfulness**:逐字轉錄、矛盾也不更正、不查真 | 忠實於 user(KU 核心) |
| 3 | **保留 native 的 selectivity**(寒暄/問句→空);few-shots domain-neutral | 不存噪音 |
| 4 | **Source-based specificity**:存 **user 主張**;assistant turn 只當 context,不存其建議/知識 | 不存 LLM 已知噪音 |

**移除**(因 overfit / 預設文字內容):舊「list 逐項、忽略編號」規則(atomicity 已能拆);舊「世界知識屬性列舉」。

**機制:靠 source(user/assistant),不靠 backbone 自我知識**
- **knowledge-delta 是「為什麼」(justification);「怎麼做」靠 source** —— 使用者主張 ≈ delta,assistant 鋪陳 ≈ LLM 自知識複述。
- **不**靠「LLM 判斷自己是否已知」:那**不可靠(幻覺自信)+ backbone-dependent**(會殺掉「通用框架」claim)。role 標籤明寫 → **可靠、backbone-independent**。

**介面前提 + benchmark 驗證**(role-attributed 對話輸入):
- LongMemEval:`"{}: {}".format(role, content)`(run_generation.py:329);BEAM:`USER:/ASSISTANT:`(long_term_memory_methods.py:303–352);FC:`<User>…<Assistant>…`(templates.py:8)。三者都帶 role。
- **LongMemEval 官方 harness 本身就有「只取 user turn」模式**(run_generation.py 多處 `if x['role']=='user'`,執行期、非 oracle)→ 「user-asserted 儲存」有 **field-precedent**。(注意:這與 §3 收回的 BEAM `user_messages.json`(oracle 生成產物)不同。)
- **損失評估**:FC 全部事實在 `<User>` turn → **零損失**;KU 答案在 user turn → 保留;丟的是 assistant 噪音。

**接受並分析落差**:同一套抽取器跨 dataset,FC 與對話各自可能有 recall 落差 —— 那個落差**本身是泛化發現,要回報**,不為單一 dataset 調 prompt。**chunk_size 維持 512。**

Code:`methods/mem0_fc_prompt_fix.py`(**待改寫為統一抽取器**;旗標 `use_broadened_native_prompt`);舊 broadened-native / L2 保留供對照與重現。**狀態:prompt 改寫 + FC/KU smoke test 通過後,才逐步更新其餘 writing_draft 並上 benchmark。**

---

## 7. 修正後的統一抽象(SUT 視角)

> 記憶方法收到一段**長 NL 歷史**,其中某些 `(entity, attribute)` 的值**隨時間被重新主張為不同值**。任務是在 query 時回傳被查事實的**當前權威值** —— 其中「權威」對 Bucket (B) 是 **recency**、對 Bucket (A) 是**明確更正**。**沒有 benchmark 把結構化 `(entity, attribute, value, time)` store 交給方法;從 NL 抽取是內在的。**

我們的架構在 Bucket (B) 體制下提供這個 store 的**正確讀寫紀律**:append-only 寫入 + query-time 取最新值解析,對抗領域慣用的 write-time 破壞性覆蓋。

---

## 8. 開放線索(追蹤,不阻塞)

- 多值(非 functional)屬性:同 `(S,P)` 須 **COEXIST** 而非 argmax —— `phase2` 已有 guard 雛形;寫成 retrieval module 的有界精修。
- 262k 規模:真正瓶頸是**逐筆序列 embedding**(≈ #facts,與 chunk size 無關),**不是** chunk 數 —— `chunk_size=4096` **解決不了**還傷 recall。槓桿 = **batch embeddings**。(chunk 維持 512。)
- 大 chunk 下 ordinal 顆粒度:登記為假設(舊+新落同 chunk → 平手)。chunk=512 時 non-issue;真要推大有解(chunk 內次序)。不未遇先催。
- 跨系統 baseline(Zep、LightMem — clone 於 `~/LightMem`)與 FC-MH:future。
