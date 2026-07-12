# 6k Weak-Backbone Case Study — qid-level pipeline trace (gemma3 1B/4B/12B/27B, GX10)

> **目的**:對 6k weak-backbone regime 挑 canonical qid 做**逐階段 pipeline trace**,說明每個 backbone 各自錯/對在哪一步。格式類比 Mac 的 [`case_studies_64k.md`](case_studies_64k.md),但**軸不同**:Mac 64k 是**跨 method**(ours/mem0/Zep @ gpt-4o-mini);本檔是**跨 backbone**(同一 method=`ours_struct`,gemma 1B→27B)。
> **關鍵前提**:GX10 是 **per-backbone gemma extraction**(見 [`weak_model_6k_analysis.md`](weak_model_6k_analysis.md) §前提)→ 每個 backbone 的 **P1 extraction 步驟本身就是變因**,因此本檔的 trace **必含 P1 extraction 這一格**(Mac 端 gpt-4o-mini 抽取固定,不需要)。
> **每個 case 的 trace 鏈**:question → gt_new/gt_old → **該 backbone P1 extraction** → store/retrieved → (S,P)+argmax → pool(memories_str,reader 實際看到)→ answer LLM response → EM。
> **資料**:`p1_caches__gemma3-{s}/extraction_cache_p1_6k.json`(P1)、`outputs/rag_retrieved/Structure_rag_gemma3-{s}-…_unified_struct/…/query_{qid}_*.json`(pool/response)、`…unified_struct__gemma3-{s}/…results.json`(EM)。

---

## 0. 一句話結論:失敗沿 backbone 逐格「往後推」

同一題,失敗點隨 backbone 變強而**沿 pipeline 往後移**——這正是 per-backbone extraction 的 signature:

| backbone | 主要失敗點 | 機制 |
| :--- | :--- | :--- |
| **1B** | **P1 抽取**(漏 new / 措辭不一致)+ **reader** | 抽不到 gt_new,或抽到但 new/old 措辭不一致 → (S,P) 分桶未併;且 reader 常吐非答案(echo prompt)|
| **4B** | **P1 抽取**(漏 new) | 抽取覆蓋率仍不足,常只抽到舊版 → pool 只有 old |
| **12B** | (幾乎不失敗) | 兩版抽取**措辭一致** → 同 (S,P) → argmax 取新 → pool 乾淨 → reader 抄對 |
| **27B** | **reader override**(Mode C) | pool 一樣乾淨,但 reader 用世界知識**否決** pool、答真實舊值 |

**對 core claim 的意涵**:12B 起「抽取一致性」達標,mechanical (S,P)+argmax 就把 KU 解對(無需 query-time LLM);weak 端(1B/4B)的失分是**抽取軸**(能力),strong 端(27B)的失分是**reader override**(與 KU 方法正交)。**中段 12B 是最乾淨的「decomposed simple task 可行」證據**。

---

## 1. Canonical case 對照表(3 qid × 4 backbone,method=ours_struct)

| qid | 問題 | GT_new(反事實)| GT_old(世界真值)| 1B | 4B | 12B | 27B |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **19** | Who is the CEO of Microsoft? | **Steve Jobs** | Satya Nadella | 答`Current Time…`(reader 崩)✗ **W2+W3** | 答`Satya Nadella`✗ **W1 漏抽** | 答`Steve Jobs`✅ | 答`Satya Nadella`✗ **C override** |
| **57** | Who is Elvis Presley married to? | **Charles the Bold** | Priscilla Presley | 答`Current Time…`✗ **W1+W3** | 答`Priscilla Presley`✗ **W1→世界知識** | 答`Charles the Bold`✅ | 答`Priscilla Presley`✗ **C override** |
| **14** | Who is the author of Sidereus Nuncius? | **Samuel Beckett** | Galileo Galilei | 答`Galileo Galilei`✗ **W1 漏抽 new** | 答`Samuel Beckett`✅ | 答`Samuel Beckett`✅ | 答`Samuel Beckett`✅(**未** override)|

**錯誤模式(擴充 Mac taxonomy 至 weak-backbone)**:
- **W1. Extraction miss** — 該 backbone P1 沒抽到 gt_new(甚至 gt_old)→ fact 從未進 store。(1B/4B 主因)
- **W2. Extraction inconsistency → (S,P) split** — new/old 抽成不同措辭 → 不同 (S,P) key → 未併群 → pool 留兩版。
- **W3. Reader garbage** — 1B 即使有 pool 仍產非答案(echo prompt timestamp)。
- **C. World-knowledge override** — 27B 忽略乾淨 pool、答世界真值(= Mac Mode C,但這裡是**強 local model**)。

---

## 2. Case 詳 trace

### Case 19 — Microsoft CEO(**一題四機制**,最 canonical)

- **Question**:Who is the chief executive officer of Microsoft?
- **GT_new**:`The CEO of Microsoft is Steve Jobs.`(gt_seq=188)/ **GT_old**:`…Satya Nadella.`(old_seq=85)→ new 較晚,argmax(ord) 邏輯上該取 new。

| backbone | **P1 extraction(該 backbone 抽出的 subject facts)** | pool(memories_str,reader 看到)| response | EM |
| :--- | :--- | :--- | :--- | :---: |
| **1B** | `Satya Nadella is the Chief Executive Officer of Microsoft.` + `The chief executive officer of Microsoft is Steve Jobs.` ← **兩版措辭不一致** | 兩版**都在**(Steve Jobs + Satya Nadella)| `Current Time: 2026-…`(**非答案**)| ✗ |
| **4B** | `The chief executive officer of Microsoft is Satya Nadella` ← **只抽到舊版** | 只有 Satya Nadella | `Satya Nadella` | ✗ |
| **12B** | `…Microsoft is Satya Nadella` + `…Microsoft is Steve Jobs` ← **兩版措辭一致** | **只有 Steve Jobs**(argmax 取新、old 濾掉)| `Steve Jobs` | ✅ |
| **27B** | 同 12B(兩版一致)| **只有 Steve Jobs**(pool 一樣乾淨)| `Satya Nadella` | ✗ |

**判讀**:
- **1B = W2+W3**:P1 把兩版抽成不同 predicate 結構(`is the Chief Executive Officer of X` vs `The chief executive officer of X is`)→ (S,P) 分兩桶、沒併 → pool 留兩版;且 reader 吐 timestamp(生成能力不足)。
- **4B = W1**:P1 只抽到舊版 → pool 根本沒 gt_new → reader 只能答舊。**這是 per-backbone extraction 的直接後果**(4B 抽取覆蓋率不足)。
- **12B = 成功**:兩版抽取**措辭一致** → 同 (S,P) → mechanical argmax 取 seq 大者(Steve Jobs)→ pool 乾淨 → reader 抄對。**注意:12B 不需要「知道」誰是 CEO,只需要抽取一致 → 這就是 "decomposed simple task" 的意義。**
- **27B = C override**:pool 與 12B **完全相同**(只有 Steve Jobs),但 27B reader 用世界知識否決,答真實 CEO Satya Nadella。**失分純在 reader,與 KU 方法無關**(對照 [`F_crosstab_1227_6k`](../figures/F_crosstab_1227_6k.png) 的 override 桶)。

### Case 57 — Elvis 的配偶(override + 弱端抽取雙失)

- **Question**:Who is Elvis Presley married to? **GT_new**:`…Charles the Bold.`(139)/ **GT_old**:`…Priscilla Presley.`(120)

| backbone | P1 extraction(subject facts)| pool | response | EM |
| :--- | :--- | :--- | :--- | :---: |
| **1B** | `Elvis Presley is married to Priscilla Presley.` ← **漏 gt_new** | 只有 Priscilla | `Current Time:…` | ✗ |
| **4B** | (無婚姻 fact,只有 `Viva Las Vegas was performed by Elvis`)← **new/old 皆漏** | 無婚姻 fact | `Priscilla Presley`(**世界知識 fallback**)| ✗ |
| **12B** | `…married to Priscilla Presley` + `…married to Charles the Bold`(一致)| **只有 Charles the Bold** | `Charles the Bold` | ✅ |
| **27B** | 同 12B | **只有 Charles the Bold** | `Priscilla Presley` | ✗ |

**判讀**:1B/4B = **W1 抽取漏**(4B 連 old 都沒抽到 → pool 空 → reader fallback 世界知識,恰好是真實配偶);12B 一致抽取 → 乾淨 pool → 對;27B = **C override**(乾淨 pool 說 Charles the Bold,27B 答真實配偶 Priscilla)。**這題把「弱端抽取失敗」與「強端 override」放在同一問句上對照。**

### Case 14 — Sidereus Nuncius 作者(乾淨的 1B 抽取失敗 + 27B **未** override)

- **Question**:Who is the author of Sidereus Nuncius? **GT_new**:`…Samuel Beckett.`(401)/ **GT_old**:`…Galileo Galilei.`(124,= 真實作者)

| backbone | P1 extraction(subject facts)| pool | response | EM |
| :--- | :--- | :--- | :--- | :---: |
| **1B** | `The author of Sidereus Nuncius is Galileo Galilei.` ← **只抽到舊版** | 只有 Galileo | `Galileo Galilei` | ✗ |
| **4B** | `…is Samuel Beckett` ← **恰只抽到新版** | 只有 Samuel Beckett | `Samuel Beckett` | ✅ |
| **12B / 27B** | 兩版一致 | **只有 Samuel Beckett** | `Samuel Beckett` | ✅ |

**判讀**:
- **1B = W1 乾淨範例**:P1 只抽到舊版 Galileo(gt_new 從未進 store)→ pool=old_only → 答舊。**這正是 §2 為何 1B/4B 不能用 cross-tab 的機制:pool 的 `old_only` 是抽取漏,不是解析錯**。
- **4B**:巧合只抽到新版 → 對(抽取不全但方向對)。
- **27B 這題「未」override**(答 Samuel Beckett,採用 pool)→ **override 不是必然**:Microsoft CEO / Elvis 配偶 27B 有強世界先驗 → override;Sidereus Nuncius 作者的反事實編輯先驗較弱 → 採用 pool。**override 率取決於 answer LLM 對該題世界先驗的強度**,這也解釋為何 27B override 只有少數題(官方 substring-EM 下 struct 2/74、no_p5 1/74;非全崩)。

---

## 3. Takeaways(接 paper §5 case narrative)

1. **失敗點沿 backbone 往後推**(W1 抽取 → W2 (S,P) split → 成功 → C override),是 per-backbone gemma extraction 的直接可視化。**弱端天花板 = 抽取(能力),強端天花板 = reader override(先驗)**,兩者都與 query-time KU **方法本身**正交。
2. **12B 的成功機制是「一致性 not 正確性」**:reader 不需知道正解,只需 P1 把 new/old 抽成同一 (S,P) → mechanical argmax 解 KU。這精確兌現 intro 的 "decomposed **simple** tasks for weak model"。
3. **27B override 有選擇性且量小**(官方 substring-EM:struct 2/74、no_p5 1/74;strict-EM 的 7/4 有多數是 verbose-correct 被 strict 冤枉):世界先驗強的題(CEO、名人配偶)才 override,弱先驗題(冷門反事實)採用 pool → 對照 Mac 64k gpt-4o-mini 的 Mode C,**override 是 answer-LLM 通性、非 local-model 特有**,strong backbone(gpt-4.1-mini)未必能救。
4. **與 cross-tab 一致**:本 trace 的 27B「乾淨 pool + override」= [`F_crosstab_1227_6k`](../figures/F_crosstab_1227_6k.png) 的 `new_only ✗` 桶(官方 substring-EM:struct 2 → no_p5 1);1B/4B 的抽取漏 = 為何其 pool-state 不可信、只能用 E2E+此 case study。

---

## 附:與其他檔關係
- **格式對照**:[`case_studies_64k.md`](case_studies_64k.md)(Mac,跨 method @ gpt-4o-mini)。
- **上層分析**:[`weak_model_6k_analysis.md`](weak_model_6k_analysis.md)(E2E + cross-tab)。
- **機制 backing**:[`weak_model_case_study.md`](weak_model_case_study.md)(三關卡漏斗、"一致性 not 正確性" 統計版)。
- **重跑**:trace 資料由 `p1_caches__gemma3-{s}/` + `outputs/rag_retrieved/Structure_rag_gemma3-{s}-…_unified_struct/` 直接讀,無需 API。
