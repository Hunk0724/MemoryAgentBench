# From Overview to Component — method 章節的漸進敘述結構

> 用途:整理 method(論文 + slide)該**怎麼一層一層講** —— 從 overview 的核心理念,逐步下沉到各 module/component 的設計與 prompt。
> 配套:prompt 原文與現役實作清單見 [`current_ours_method_pipeline_and_prompts.md`](../paper_draft&materials/current_ours_method_pipeline_and_prompts.md);戰場定位見 [`ku_taxonomy_and_scope_zh.md`](../paper_draft&materials/ku_taxonomy_and_scope_zh.md)。
> 建立 2026-06-27。

---

## 0. 讀者/聽眾進入 method 時的已知狀態

從 intro 他們只知道一個**高層 framework**:
> **Conservative Writes + Query-Time KU Resolution** —— KU 是 query-time 的問題,不是 write-time 的提交。

method 章節的任務 = 把這個理念**逐步具體化**,但**不要一開頭就丟細節**。原則:**每個 component 都應讀起來像「理念的必然結果」,而不是工程選擇。**

---

## Layer 0 — Method Overview(開頭只講到這)

對應圖:[`introduction_framework_abstract`](introduction_framework_abstract.drawio)(高層)/ [`Methodology_ours_Overview`](Methodology_ours_Overview.drawio)(具體)。

用 overview 層的語言把端到端講一遍,**每個 module 一句話、不進細節**:

**寫入期(new info →):**
- **Storage**:新資訊進來後,抽取記憶,**確保 LLM 把事實忠實保留進來**(不在此判斷對錯、不解衝突)。
- **Update**:對每個抽取出的事實做**結構化提取** —— 取成 **triple (subject, predicate, object)** 形式。
- **(理念)** 寫入只做保守、非破壞的保留:**全版本留存**,不去重、不覆蓋、不刪除。

**查詢期(query →):**
- **Retrieval**:檢索候選 → 找出「同一事實的不同版本」(identity grouping)→ 判該組衝突型別 → **確定性地取最新版**(temporal resolution)。
- **Inference**:用解析後的記憶答題。

> overview 的關鍵訊息只有一個:**「誰是權威」由 query-time 的確定性步驟決定,寫入期什麼都不破壞。** 其餘全部延後。

---

## Layer 1 — 延後到各 component 才講的細節(overview 不提)

把這些**從 overview 拿掉**,留到對應 module 小節再展開(避免一開頭資訊過載):

| 細節 | 屬於哪個 component | 何時講 |
|---|---|---|
| 存**個人 + 世界**事實 | Storage(抽取) | 3.x Storage:且註明這是對 vector 線 personal-only 限制的**對齊**(非賣點;Zep 本就通用) |
| **只對 User 端**抽取、assistant 只當 context | Storage | 3.x Storage:source-based selectivity、backbone-independent |
| **忠實、不 fact-check、不合併衝突值** | Storage | 3.x Storage:這是 conservative write 在抽取端的實現 |
| triple 的 subject/predicate/object **怎麼選** | Update(triple extract) | 3.x Update:見下方 §C |
| **不做 predicate/subject canonicalization**、null-encouraged | Update | 3.x Update:schema-free 取捨 + 下游 LLM grouping 救援 |
| (S,P) routing(structural vs dynamic pool) | Retrieval | 3.x Retrieval |
| identity grouping / conflict-type(P5)/ ordinal argmax | Retrieval | 3.x Retrieval |
| raw-question 檢索、subject fallback、cache | Retrieval / Update | 各自 component + 工程註記 |

---

## Component rationale(逐一補；先補 Triple extract)

### C. Update — Triple extract:prompt 設計的理由

> 現役 prompt:`methods/phase0_triple_extractor.py: TRIPLE_EXTRACTION_PROMPT`(全文見 current 檔 P2)。
> **一句話定位**:triple 不是為了建知識圖譜,而是把「一條事實」轉成「**(槽位 key, 值)**」—— 讓**同一事實的不同版本落在同一個 `(subject, predicate)`**,query-time 才能分群 + 取最新。

| prompt 規則 | 設計理由(為什麼) | 扣回的理念 |
|---|---|---|
| **subject = 事實所屬、更新時不變的實體;object = 會變的值(答案);predicate = 關係** | 這是**核心**:把 fact 拆成「**穩定槽位 (S,P)** + **可變值 (O)**」,讓新舊版本以相同 (S,P) 對齊 → 直接餵給 query-time 的 identity grouping + temporal argmax。沒有這個固定法,版本就不會碰在同一 key 上 | KU 顆粒 = (entity, attribute) 槽位;triple 是其結構化實現 |
| **名詞化關係拆解**:「the R of E is V」→ subject=E, predicate="has R", object=V | 否則 subject 會是長名詞片語、predicate 變成 "is",值被綁進 subject。拆解後 **subject 是乾淨命名實體**(更好對齊、更好比對),**答案被孤立成 object** | 乾淨槽位 → 版本對齊更穩 |
| **predicate 是短自然語言動詞片語;不映射固定詞表 / 不 canonicalize** | **刻意 schema-free**:(a) canonicalization 本身脆、且 backbone-dependent;(b) 不預設 ontology → **跨域可泛化**。代價(同事實不同 predicate 字串 = F2-split)**接受**,交給下游 LLM identity grouping 救 | schema-free 泛化 > 精確 key;對齊「抽取不完美、可接受」立場 |
| **subject/object 逐字、verbatim,不改寫** | 保留**實際答案字串**(供 substring-EM 計分 + 忠實儲存),不被正規化吃掉 | 忠實(conservative write 抽取端) |
| **代名詞:user/assistant→固定;可解析→解析;不可解析→null** | 解析指涉讓**同實體一致分群**;不確定就 null,避免錯誤分群 | precision-safe |
| **不分主題照抽(個人/偏好/世界知識)** | 一套抽取器同時吃 FC(世界)+ LongMemEval(個人) | 單一統一前端 → 撐泛化 |
| **反事實照抽、不對世界知識查核** | KU 要存反事實值(FC);不讓 LLM 的世界知識覆蓋 user 主張 | 忠實 / 記憶權威於參數知識 |
| **主觀狀態 / 複雜敘事 / 多事實 → null;null 合法且被鼓勵** | triple 只適合**乾淨單一主張**;硬塞 triple 給多事實/主觀句 → 壞 triple → 錯分群。寧可 null(落 subject fallback / dynamic pool,交給 LLM 路徑) | precision-safe:**不結構化 優於 錯誤結構化** |

**最重要的誠實點(要在 method 明講,預防審稿)**:
- Triple extract 是 **per-item、self-contained** —— 它**只結構化「每一條事實自己」,不對「跨筆事實」做任何衝突判斷**。所以它**不違反**「寫入期無跨筆 LLM 判斷」。
- 它的角色是 **enabler**:把事實整成可在 query-time 分群的形狀,從而**讓 KU 能被推遲到 query-time**。Update 模組的改動本質是「**把 mem0 的跨筆破壞性判斷,換成 per-item 的結構化**」。

---

## 對應關係(本檔 ↔ 其他檔)

- **prompt 原文 / 現役 vs 死碼** → [`current_ours_method_pipeline_and_prompts.md`](../paper_draft&materials/current_ours_method_pipeline_and_prompts.md)
- **顆粒度地基(為何 fact 顆粒、競品 code + paper 佐證)** → 待整合(見 session 討論:knowledge-editing triple + Mem0/Zep/LightMem)
- **flow 圖(可編輯源)** → `introduction_framework_abstract.drawio` / `Methodology_ours_Overview.drawio`

## 待補(下一個 component)
- [ ] B. Storage — 統一抽取器(P1)的設計理由(personal+world / 忠實 / user-only / source-based),已在 session 討論,待填本檔。
- [ ] D. Retrieval — routing + identity grouping(P3) + conflict-type(P5) + temporal argmax 的理由。
- [ ] mem0 選用理由段(載體、模組清晰、破壞性-主動更新代表;framework-agnostic 防守句)。
