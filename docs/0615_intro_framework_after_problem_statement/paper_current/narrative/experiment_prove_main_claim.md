# 4. Experiments — 以「證明主張」為骨架的設計藍圖(design blueprint)

> **這份是什麼**:不同於 [`experiment.md`](experiment.md)(已被現有結果填滿、以「我們跑了什麼」組織),本檔以**論文主張的邏輯結構**組織 ——「主張 → 該設計什麼實驗 → 預測的證據形狀 → 什麼結果會推翻它」。**刻意 outcome-agnostic**:數字一律留 `[待填]`,重點在**實驗該長什麼樣、為何非這樣不可**。等設計定稿,再把 [`experiment.md`](experiment.md) 的實測填進對應欄位。
> **對接**:定稿 abstract(主張:忠實寫入 + query-time 解析;優勢隨 backbone 越弱越大、越強收斂;受限部署為主場)。
> **寫作原則**:每個 claim ↔ 一個實驗 ↔ 一個可證偽條件;圖表遵循 [`../style_rules_tables_figures_writing.md`](../style_rules_tables_figures_writing.md)(有趨勢用 line、無趨勢用 table、黑白可辨、caption 三段論 what/observation/implication)。

---

## 4.1 主張 → 實驗對應(claim-to-experiment map)

論文主張拆成一個**正面**與兩個**必須背書的反面**。這張表是全章的地圖:每一列是一個 claim,對應唯一一個實驗與唯一一個「怎樣算輸」。

| # | 主張(claim) | 承載實驗 | 預測的證據形狀 | 可證偽條件(what falsifies it) |
|:--|:--|:--|:--|:--|
| **C0** | KU 的可靠度對 backbone 的**敏感度**,取決於「決策由誰、在何時做」 | §4.3 主實驗(KU 策略 × backbone 交互作用) | 確定性線對 backbone **平**;LLM 線**斜、弱端崩** | 確定性線也隨 backbone 崩 → 主張倒 |
| **C1** | 是「**決策去 LLM 化**」買到 robustness,不是光「延到 query-time」 | §4.3 內的 minimal-pair(query×LLM vs query×det) | query×LLM **斜**、query×det **平** | 兩者都平 → 結構貢獻不成立 |
| **C2** | write-time 的錯是**不可逆**(正確版根本不在庫) | §4.4 L0/L1/L2 分層 | write-time 失分集中在 **L0**;query-time 失分集中在 **L1** | write-time 失分主要在 L1 → 「不可逆」倒 |
| **U1** | 方法**適用範圍有邊界**:僅限可由時序判定的結構化衝突 | §4.5 邊界覆蓋率 + case study | 殘差型(keep-all/回退/破碎)佔比明確、ours 於其上不適用 | 殘差型佔大宗 → 方法適用性存疑(誠實揭露) |
| **U3** | 代價是**記憶庫單調增長**及其 query-time 成本 | §4.6 增長/成本分析 + bloat probe | 庫大小/檢索成本隨事實數上升;庫髒對非-KU 檢索的影響量化 | 成本爆炸到不可部署 → 受限部署定位受損 |

> **§4.7 明確不主張的事(scope-out)**:ours 不是通用記憶系統;「在通用記憶任務上比輸」不是 finding,是我們宣告的 scope 的定義性後果,故**不以其他記憶任務做正面比較實驗**(理由見 §4.7)。

---

## 4.2 Setup(由主張反推的必要條件,非由手上資料反推)

### 4.2.1 Task & Datasets — 資料集的**強制條件**

KU 任務的評測資料,必須同時滿足(否則主實驗無法成立):

1. **衝突密集**:同 `(subject, relation)` 在對話中出現 ≥2 個 object、時間序已知 → 才有 KU 可做、可判「當前版」。
2. **recency ground truth + 字面 exact-match**:免 LLM judge。**這是硬條件** —— 我們正在測弱 backbone,若用 LLM 當 judge,judge 本身即為一條 backbone-quality confound,污染主實驗。
3. **兩種 flavor(拆 world-prior confound)**:
   - **(a) world-conflicting**(counterfactual;新版與模型參數知識牴觸)
   - **(b) no-prior / personal**(模型對特定實體無先驗)
   - 用途:若只在 (a) 上看到 write-time 弱端崩,reviewer 會說「是**反事實內容**觸發 LLM 抗拒,不是 backbone 弱」。只有 (b) 上仍見同樣交互作用,才把「backbone 能力」與「內容 world-prior」分開。
4. **可調事實規模 / context 長度**(次要壓力軸):顯示 write-time 不可逆 damage 隨事實數累積;非主軸。

| Dataset | flavor | 角色 |
|:--|:--|:--|
| KU-benchmark A(conflict-dense, exact-match) | world-conflicting | 主實驗主場 |
| KU-benchmark B(personal fact) | no-prior | §4.5 confound 拆解、跨資料重驗 |

### 4.2.2 Method 軸 —— 一條「LLM 判斷離 query 有多遠」的階梯

baseline 的職責不是「找幾個 SOTA 來比」,而是**每個都固定其他一切、只動一個設計動作**。

**先做一個 taxonomy 修正**:mem0 與 Zep **都是 write-time 的 LLM 判斷** —— mem0 破壞性覆寫、Zep 標時間戳,兩者「怎麼提交」不同,但「由 LLM、在 query 之前、盲判」這件事相同。intro 的 coupled / decoupled 差異屬「**提交方式**」的次要軸,不是「**誰在何時判斷**」的主要軸。因此**不存在真正的 write-time × 確定性 cell**(確定性只出現在 Zep 的提交機制,判斷本身仍是 LLM)—— 我們**不設 W-det**,也全篇不用「裁決」一詞,統一為「判斷 / 決策」。

主要軸因此是一條**三階梯**(LLM 判斷離 query 越來越近、越來越可回復):

| 代號 | KU 判斷:何時 × 由誰 | 對應真實系統 | 該階隔離的設計動作 |
|:--|:--|:--|:--|
| **W-llm** | write-time × LLM(盲判、提交即定) | mem0(破壞性)、Zep(標時間戳)兩變體 | 基準:query 之前的 LLM 判斷 |
| **Q-llm** | query-time × LLM 判新舊 | **ours 把時序 argmax 換成 LLM**(自製 minimal-pair) | ← **query-time 化**(對比 W-llm) |
| **Q-det** | query-time × 確定性(結構配對 + 時序 argmax) | **ours** | ← **決策去 LLM 化**(對比 Q-llm) |
| *(ref-1)* | keep-all、檢索兩版直接丟 reader | trivial query-time | 「結構化 resolution」相對「丟給 reader 自己挑」的價值 |
| *(ref-2)* | 無記憶架構(full-context reader) | long-context | ceiling / floor 參考線 |

> **兩個設計動作各由一段階梯乾淨隔離**:`W-llm → Q-llm` 隔離「query-time 化」(帶來可回復 + query-aware);`Q-llm → Q-det` 隔離「決策去 LLM 化」(帶來 backbone-invariant)。
> **mem0 與 Zep 同屬 W-llm、卻落在不同失效層**(對接 §4.2.5 / §4.4):mem0 破壞性 → 錯在 **L0**(正確版沒了);Zep 非破壞性、版本都在(L0 過)→ 錯在**寫入時標籤品質**,顯化為 reader 讀時間戳的 **L1**。這個「同是 write-time LLM 判斷、卻落在不同層」本身就是好證據:**write-time 的病灶不是提交方式,而是判斷發生在 query 之前**。
> **為何 Q-llm 不能省**:沒有它,無法證明是**確定性**(而非光 query-time)在買 robustness → C1 落空。多數論文只比 W-llm 系統就宣稱贏,無法排除「query-time 本身就夠」。

### 4.2.3 Backbone 光譜 —— 軸的語意是「判斷力」,backbone 只是 proxy

- **跨 ≥3 個 model family**(輕量 → 前沿),證明是 capability 效應而非某家怪癖。**這是 reviewer 最會打的點**:只有一兩個 family,審稿人會質疑「趨勢是 Gemma/GPT 的家族特性,不是普遍的 capability 效應」。建議在光譜上納入 **Qwen2.5、Llama-3.x、Mistral** 至少各一 size(與現有 Gemma3 / GPT 對齊 size 帶),讓「越弱越崩」在**多個獨立 family** 上重現。
  - **現況(2026-07-08)**:只有 **Gemma3 + GPT 兩 family** → 缺口,見 §4.8。
- **必須涵蓋論文定位的受限部署真實區間**(真正的小/便宜模型),不能只在窄帶掃。
- **把 proxy 坐實**:額外量一個中介量 —— 該 backbone **單獨做 KU 決策的正確率** —— 顯示它確實隨 backbone 變化,證明「backbone 真的在移動決策品質」,而非移動了別的東西。

### 4.2.4 Controls —— 主實驗效力全取決於這裡 hold 得住

| 控制項 | 做法 | 若不控制,會被歸因到 |
|:--|:--|:--|
| **抽取(extraction)** | 能注入的 method(mem0)吃**同一份**抽好的 fact;不能注入的(Zep cloud)**改以量測其抽取 GT recall** 證明抽取非其瓶頸(見下註) | 「你們是抽取差異在贏」 |
| **檢索 / embedding** | **單一 online API embedder,跨全部 method 與全部 backbone 固定**;同 top-K | retrieval recall |
| **★ Reader** | **固定為強模型**,backbone 只掃在「KU 決策」那一步 | 「弱 reader 讀不動」≠「弱 backbone 做不了 KU」,兩者不可混 |
| **答題 prompt / 溫度** | 全 method 對稱、temp 0 | 「贏在答題 prompt」 |

> **註 — embedding 為受控干擾變因,非變因重點(對接設計反思 point 4)**:檢索品質不是本文主張的變因,故對**所有 backbone(含 local weak model)一律用同一顆強 API embedder**,以移除 embedding 品質這條混淆。此舉不破壞 on-device 定位:embedding model 本身極小、裝置端可獨立跑,實驗用 API embedder 屬**受控簡化**而非部署障礙 —— 論文誠實一句帶過即可。
>
> **註 — 抽取控制的不對稱(對接 point 5)**:mem0 可注入 ours 的抽取 cache → 抽取 held-fixed,乾淨。**Zep cloud 閉源、無法注入**,故改測「Zep 自身抽取是否 recall 到兩版 GT」:若 recall 高,則 Zep 的 KU 失敗歸因於**寫入時判斷(標籤)**而非抽取,對比仍成立。**唯有當抽取確證為 Zep 瓶頸時**,才需自架開源 graphiti 對齊抽取(工程成本高,列 future work);否則**優先以現有 Zep cloud 結果呈現**。此不對稱本身即誠實揭露。

> **兩個版本、各證一件事**:
> - **(主,科學)reader-fixed**:reader 固定強模型,只壓 KU 決策步 → 乾淨隔離「去 LLM 化買 robustness」。
> - **(輔,生態)all-weak**:整條 pipeline 同一弱模型 → deployment-realistic,但混了 reader 退化,只作補充,不承載 C0/C1。

### 4.2.5 Metrics —— 巢狀三層,才能定位「在哪一步斷」

每個(method × backbone)格子報三層,而非只報 E2E:

| 層 | 定義 | 抓什麼 |
|:--|:--|:--|
| **L0 — present** | 正確(當前)版是否還在庫/pool 裡 | write-time 的**不可逆丟失** |
| **L1 — selected** | 在庫的前提下,是否被選出/浮到 reader 面前 | **query-time resolution 決策**本身 |
| **L2 — E2E** | 最終答對(含 reader) | 加上下游 reader |

主評分 = exact-match(無 LLM judge);單次 deterministic(temp 0)。

> **關鍵:兩派的「KU 決策」落在不同層,不是三派都平均有 L0/L1 兩個獨立失分點(對接設計反思 point 1)。**
> - **write-time 派**:判斷在寫入 pipeline 跑完時就定形,**結果直接由 L0 讀出**(正確版還在不在庫)。L0 一旦失敗,L1 無意義 —— 選不出不存在的版本。故 L0 是 write-time 陣營的**主要鑑別軸**。
> - **query-time 派(ours 與 Q-llm)**:因忠實寫入,**L0 幾乎恆過**;真正的 KU 決策發生在 **L1**(從在庫候選裡選/併出當前版)。故 L1 是 query-time 陣營的**主要鑑別軸**。
> - 這個「決策落在哪一層」的不對稱,**正是 C2『write-time 錯在不可逆的 L0、query-time 錯在可回復的 L1』的量化形式**。(Zep 為 write-time 判斷但非破壞性 → L0 過、失分顯化於 L1,是這條不對稱的變體,見 §4.4。)

---

## 4.3 主實驗 —— KU 策略 × backbone 交互作用(承載 C0、C1)

### 4.3.1 設計

固定 §4.2.4 全部控制,把 §4.2.2 的 method 階梯 × §4.2.3 的 backbone 光譜跑滿,依變數取 L1(resolution 正確率;E2E 於 §4.4 展開)。**這張圖是全章頭條**。

### 4.3.2 呈現(figure spec)

**Figure 1**(line chart,x = backbone 判斷力弱→強,y = KU 正確率 %;每 method 一條線;黑白以 marker/linestyle 區分):

> **Figure 1. KU 正確率 × backbone,依決策策略分線。**
> *(What)* 固定抽取/檢索/reader,唯一變動為 backbone 判斷力(≥2 family)與 KU 策略(W-llm / Q-llm / Q-det = ours)。
> *(Observation,**預測**)* Q-det(ours)對 backbone **近乎水平**;W-llm 與 Q-llm **隨 backbone 增強上升、弱端崩**;故 gap(ours − baseline)於弱端最大、強端收斂。
> *(Implication)* KU 可靠度對 backbone 的敏感度由「決策是否經 LLM」決定 → 去 LLM 化提供 backbone-invariant 的地板。
> *(縮寫)* det = deterministic resolution;llm = LLM-judged resolution;W/Q = write-/query-time。

### 4.3.3 預測簽名(schematic,非實測)

以符號表達「形狀」;數字待 §4.3.4 填。`→` 讀作「隨 backbone 由弱到強」。

| Method | 弱 backbone | 中 | 強 backbone | 對 backbone 的斜率 |
|:--|:--|:--|:--|:--|
| **Q-det(ours)** | 高(極弱端可能微降) | 高 | 高 | **相對平緩**(斜率遠小於 LLM 線) |
| Q-llm | 低 | 中 | 高 | ↑ 明顯 |
| W-llm | **崩(≈地板)** | 中 | 高 | ↑ 陡 |
| gap = ours − W-llm | **最大** | 中 | ≈0 或反轉 | ↓(收斂) |

> **⚠ 承重點是「相對斜率」不是「絕對水平」**:主張要守得住,Q-det 的預測應寫成「**斜率遠小於 LLM 線**」,而非「完全水平 / near-invariant」。**Q-det 在極弱端(如 1B/4B)出現小幅下滑是正常且預期的** —— 其來源是**抽取品質與 reader 退化**(該 backbone 連結構化抽取都做不乾淨),**而非 KU 決策本身崩**。這條由 §4.2.5 的 L0/L1 分層 + §4.2.4 reader-fixed 控制隔離:KU 決策的正確性(L1)應遠比 W-llm/Q-llm 平,殘餘的極弱端下滑歸因於抽取(L0 前)與 reader(L2),非確定性 resolution。

**兩條 claim 的讀法**:
- **C0** 讀「ours 斜率遠小於 W-llm」。
- **C1** 讀「**Q-llm 也斜、只有 Q-det 相對平**」→ 證明是**確定性**、不是光 query-time。

### 4.3.4 結果(留空)

**Table 1**(row = method,col = backbone tier;cell = L1 正確率;bold 每 col 最佳):

| Method | tier-1(輕量) | tier-2 | … | tier-k(前沿) |
|:--|--:|--:|--:|--:|
| Q-det(ours) | `[待填]` | `[待填]` | | `[待填]` |
| Q-llm | `[待填]` | | | |
| W-llm · mem0(破壞性) | `[待填]` | | | |
| W-llm · Zep(標時間戳) | `[待填]` | | | |

### 4.3.5 可證偽(pre-registered)

- 若 **Q-det 也隨 backbone 崩** → C0 倒(robustness 另有來源)。
- 若 **Q-llm 對 backbone 也平** → C1 倒(光 query-time 就夠,結構貢獻不成立)。
- 若 gap **不隨 backbone 收斂**(強端仍大)→ abstract 的 backbone-conditional 定位需重寫。

---

## 4.4 機制定位 —— L0/L1/L2 分層歸因(承載 C2)

同一批 run,拆三層 DV,回答「每個方法在 backbone 變弱時**於哪一步斷**」。

**Table 2**(以一個代表性 tier;row = method,col = L0/L1/L2):

| Method | L0 present | L1 selected | L2 E2E | KU 決策落點 / 失分處 |
|:--|--:|--:|--:|:--|
| Q-det(ours) | `[待填]` | `[待填]` | `[待填]` | 決策在 **L1**;殘量 = reader/邊界(§4.5) |
| Q-llm | `[待填]` | `[待填]` | `[待填]` | 決策在 **L1**;失分 = 選錯版(版本仍在 → **可逆**) |
| W-llm · mem0(破壞性) | `[待填]` | —(L0 過時 store 已乾淨,L1 近乎 trivial;L0 失敗則 L1 無意義) | `[待填]` | 決策在 **L0**;失分 = 正確版沒了(**不可逆**) |
| W-llm · Zep(標時間戳) | `[待填]` | `[待填]` | `[待填]` | L0 過、決策 = 寫入時標籤;失分顯化於 **L1**(reader 讀不出時序) |

> **Observation(預測)**:破壞性 write-time(mem0)的失分在 **L0** 就發生(庫裡沒有正確版);query-time(ours / Q-llm)L0 恆過、失分止於 **L1**(版本在、只是這次沒選對,下次可重判);Zep 雖非破壞性(L0 過),但寫入時標籤盲判 → 失分落在 reader 端的 **L1**。
> **Implication**:**L0 vs L1 的落點差**是 C2「write-time 判斷不可逆」的直接證據,也解釋為何強 backbone 能救 write-time 的 L0 錯(以後不再刪錯)、卻救不回已被刪的版本;而 query-time 派的 L1 錯天生只影響當下這一題。

---

## 4.5 Trade-off I(**必做**)—— KU 內部邊界的覆蓋率(承載 U1)

> **定位**:這不是附錄的誠實,而是**主張的可證偽底面**。主實驗證「確定性 argmax + 結構配對在弱 backbone 撐得住」,審稿人立刻會問「最新 ≠ 一定對」「三元組不乾淨怎麼配對」。此節正面回答:**方法適用在什麼分佈上。**

### 4.5.1 把 case study 升級為「覆蓋率聲明」

先對 benchmark 的每個衝突,依**兩個假設**分類,量化各型佔比 —— 這把軼事變成 scope:

**Table 3 覆蓋率 schema**(留空;分母 = 全 has-conflict 題):

| 衝突型 | recency 即正解? | 三元組結構乾淨? | ours 適用 | 佔比 `[待填]` |
|:--|:--:|:--:|:--:|--:|
| 單值 × 時序更新(canonical KU) | ✓ | ✓ | **✓ 適用** | `[待填]` |
| 多值 / keep-all(如 hobbies、去過的城市) | ✗(該全留) | ✓ | ✗ | `[待填]` |
| 回退 / 修正(舊值才是當前) | ✗(非最新) | ✓ | ✗ | `[待填]` |
| 有效區間型(valid-interval,需區間判斷) | ✗ | ✓ | ✗ | `[待填]` |
| 三元組破碎(subject 分裂 / predicate stem 不一致) | ✓ | ✗ | △(結構配對失敗,靠 LLM 補救) | `[待填]` |

> **Observation(要講出的一句)**:ours 明確適用於「單值 × recency 可判定 × 結構乾淨」佔比 `[待填]%` 的衝突;殘差 `[待填]%` 屬 keep-all / 回退 / 區間型,**本方法的確定性 argmax 依設計無法處理**,此為 scope 邊界。

### 4.5.2 Case study 協定

對每個殘差型挑 1–2 個 canonical 題,拉完整 trace(question → 兩版 GT → 檢索候選 → 結構分群 → argmax 選誰 → 為何錯),說明**是機制假設不成立、而非實作 bug**。

- **keep-all 型**:argmax 壓掉了本該共存的版本。
- **回退型**:argmax 選了最新、但正解是較早值。
- **破碎型**:結構配對把同一事實分到不同 (S,P) 桶 → 沒併群。

### 4.5.3 為何這是**必做**而非可選

覆蓋率 + case 讓 reader 知道你的方法**在什麼分佈上成立、你也知道不成立在哪**。這比任何額外資料集更能建立信任,且幾乎免費(用既有標註)。**沒有這節,主實驗的正面結論是懸空的**(argmax 假設未被審視)。

---

## 4.6 Trade-off II(**分析**)—— 忠實寫入 / 單調增長的代價(承載 U3)

> **定位**:這是 ours **設計上必然**付出、且**背書得起來**的代價。以分析呈現,不搶主實驗頭條。

### 4.6.1 候選 recall —— 跨派共享的「找候選」子步驟(對接設計反思 point 3)

**先釐清一個共享因子,以鞏固主實驗的歸因**:兩派都有一個「**找候選**」子步驟,只是發生時機不同 ——

| 派別 | 「找候選」發生在 | 該步的 GT recall 定義 | miss 的後果 |
|:--|:--|:--|:--|
| write-time(mem0/Zep) | **新 fact 寫入時**,檢索既有記憶找「可能的舊版」 | 新 fact 進來時,是否撈到該事實的既有版本當候選 | miss → 沒 UPDATE 機會(可能兩版並存,或漏判) |
| query-time(ours) | **query 檢索時**,找與 query 相關的候選記憶 | query 時,是否撈到含兩版衝突的記憶 | miss → 這次無法解析(但版本仍在庫,可回復) |

**Table 4a — 跨派候選 GT recall**(留空):

| 派別 / 步驟 | 候選 GT recall `[待填]` |
|:--|--:|
| write-time 新-fact 候選(mem0/Zep) | `[待填]` |
| query-time query 候選(ours) | `[待填]` |

> *(用途 1,歸因)* 若兩派候選 recall **相當**,則主實驗的 E2E 差距**不能**歸因到「誰找候選找得好」,只能歸因到**找到之後的決策**(= 本文變因)→ 鞏固 C0/C1。
> *(用途 2,接 U3)* 候選 recall **隨記憶庫增長而退化**是**三派共享**難題;但 ours 因忠實寫入 + 永不壓縮,庫成長最快、於長 context **付得最兇** —— 這條退化曲線即 §4.6.2 的成本主軸。

### 4.6.2 增長與成本曲線

**Figure 2**(line;x = 已 ingest 事實數 / context 長度,y 雙軸:記憶庫大小、query-time 檢索+分群成本;可疊 §4.6.1 的 ours 候選 recall 退化線):

> *(What)* 忠實寫入 + 永不刪 → 記憶庫隨事實數單調增長;KU 決策延到 query-time → 檢索/分群成本與候選 recall 退化亦隨庫大小惡化。
> *(Observation,預測)* 庫大小、query-time 成本隨事實數上升;候選 recall 隨庫變大而降。
> *(Implication)* 這是「保留全版本」的直接價格;ours 因永不壓縮在此軸**付得最兇**,誠實揭露。

### 4.6.3 Bloat probe —— U2 的唯一正確版本(有機制、非範疇比較)

**唯一**值得跑的「其他任務」對照:**同一個(膨脹的)記憶庫**上,回答**非-KU 問題**時,ours 會不會因庫髒(舊版當干擾)而輸給會壓縮的系統?

**Table 4**(留空):

| 讀取任務(同一 store) | ours(keep-all) | 會壓縮的系統 | Δ |
|:--|--:|--:|--:|
| 非-KU 檢索 / QA | `[待填]` | `[待填]` | `[待填]` |

> **Observation(要誠實面對)**:若 Δ 明顯為負 → keep-all 的確以「非-KU 檢索變差」為代價,據實揭露;若 Δ≈0 → 說明地板足夠、bloat 未實質傷害,強化定位。

---

## 4.7 我們**刻意不主張**的事(scope-out;預先擋掉 U2)

明文寫進論文,把「narrow method」的批評**轉為主動定位**:

- ours 是 **KU 特化元件**,非通用記憶系統。刪除/遺忘、壓縮、通用記憶管理**不在 scope**。
- 因此**不以其他通用記憶任務做正面 head-to-head** —— 在我們沒宣稱要做的事情上「比輸」,是 scope 的定義性後果,不是科學發現,且會稀釋貢獻、主動遞刀給 reviewer。
- 我們扛得住的代價只有兩條,且都已背書:**(U1)適用範圍限於可由時序判定的結構化衝突**(§4.5)、**(U3)記憶庫單調增長及其 query-time 成本**(§4.6)。abstract 的成本句應與此二者**逐字對齊**。

---

## 4.8 現有 coverage vs 主實驗缺口(2026-07-08 盤點)

以主實驗(§4.3 ladder × §4.2.3 family × §4.2.5 L0/L1/L2)為準,對照 canonical 現況([`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md)、[`../narrative_experiment_evidence/COVERAGE.md`](../narrative_experiment_evidence/COVERAGE.md))。

### 4.8.1 ladder 對映(現有 method → 藍圖 arm)

| 藍圖 arm | 現有對應 method | 狀態 |
|:--|:--|:--|
| **W-llm · mem0** | (b) mem0+P1(held-fixed extraction) | ✅ 全 tier / mid 三長度 |
| **W-llm · Zep** | Zep(k=10) | ✅(但抽取未控 → 需 §4.2.4 點5 的 GT-recall 量測) |
| **Q-det(純確定性)** | `ours (struct)` = struct+argmax | ✅ 6-tier@6k、4o 三長度、4.1@64k |
| Q-det + 最小 LLM(identity 補救) | `ours (main)` = struct+P3+argmax（**論文主 method**) | ✅ |
| **Q-llm · LLM 做 identity** | `ours (p3-only)` = P3+argmax(無結構) | ✅ ← 已提供「LLM identity 弱端崩」的 C1 訊號(1B=9%、4B=35%) |
| **Q-llm · LLM 做 recency** | **無** | 🔴 **缺**(見 §4.8.2 #2) |
| ref-1 keep-all | 無獨立 arm(可用 Zep additive 桶近似) | 🟡 |
| ref-2 long-context | LCA | ✅ mid tier |

### 4.8.2 三大缺口(按主實驗優先序)

1. 🔴 **family 只有 2 個(Gemma3 + GPT)** —— reviewer 最會打。need **Qwen2.5 / Llama-3.x / Mistral** 至少各一 size 上光譜,把「越弱越崩」在多個獨立 family 上重現。這是「capability 效應 vs family 怪癖」的 credibility 關卡(§4.2.3)。
2. 🔴 **Q-llm『LLM 做 recency』arm 缺** —— C1 目前**只由 `struct` vs `p3-only`(LLM 做 identity)承載**;abstract headline「LLM **全程不參與 recency** 裁決」這條**沒有直接對照**。補一個「把時序 argmax 換成 LLM 判新舊」的變體即可兌現。
   > **注**:此 arm 的失敗可能主要來自 **world-prior override**(LLM 看時間戳仍答世界真相舊值)而非 backbone 能力 → 於**強 backbone 也會崩**。這反而更強化「為何 recency 必須確定性」的論證(確定性 argmax 對 world-prior 免疫),是一個**加分**的對照而非純弱端故事。
   >
   > **設計對接(2026-07-11 確認)**:MemoryAgentBench origin 的 `utils/templates.py:81` 已內建 `factconsolidation.rag_agent` template,明列「Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number.」——**這就是 Q-llm-recency baseline 的自然接入點**。實作:top-K retrieval(同 ours 的 100)+ 每 fact 前綴 serial number(對應 raw dataset 格式)+ 一字不改用 origin `rag_agent` template + 走 `rag_agent` 分支(不進 mem0 handler)。**Origin 的 rag_agent template 目前未被任何 baseline 使用**,故補此 arm 同時填補 origin evaluation coverage 的 gap,並乾淨對接 experiment.md §M-3 的 fairness audit。
3. 🟡 **reader-fixed 隔離版缺**(現有全為 all-weak,backbone = 做整條 pipeline)——
   - **已部分被度量隔離**:L1 / pool-state 在 mid/strong(12B/27B/4o/4.1)可信 → KU 決策已與 reader 分離。
   - **缺口在最弱端**:1B/4B 的 pool-state matcher 不可信(抽取字面漂移)→ 只能報 L2(混 reader)。**補救**:最弱端補 reader-fixed run(reader 固定強模型),或以 case study 佐證「弱端下滑是抽取/reader 非 KU 決策」。

### 4.8.3 已足的部分(不擋主實驗)

- **backbone spectrum @6k**:W-llm(mem0 + Zep)vs Q-det(struct)vs 主 method(main)於 6-tier(1B→4.1-mini)齊 → C0 頭條可畫。
- **L0/L1 機制歸因**:pool-state cross-tab 於 4o 三長度 + 4.1@64k 齊(12B/27B 可信)→ C2 可證。
- **gap 收斂的誠實揭露**:main/mem0 × {4o, 4.1} × 3 長度齊 → 強端收斂/反轉可誠實呈現。

### 4.8.4 次要缺口(optional,列 future work)

weak-tier 長 context(32k/64k)、strong-tier 6k/32k ablation、Zep 抽取 GT-recall 量測(§4.2.4 點5)、FC-MH multi-hop。

---

## 附:與 [`experiment.md`](experiment.md) 的關係

| 本檔(blueprint) | experiment.md(已填) |
|:--|:--|
| 以 claim 邏輯組織、outcome-agnostic | 以「跑了什麼」組織、結果已填 |
| method 軸 = 拆 query-time/確定性的 minimal-pair 階梯 | 目前主要 ours vs mem0/Zep 三系統 |
| reader-fixed 為主、all-weak 為輔 | backbone = 做整條 pipeline 的模型(reader 隨 backbone 退化) |
| L0/L1/L2 分層為機制歸因主幹 | pool-state(≈L0)為主、單 backbone |
| U1 覆蓋率 = 必做主張底面;U3 = 分析;U2 = scope-out | case study 為誠實揭露、未升級為覆蓋率;無 U2 立場 |

> **落地建議**:本檔定稿後,把 experiment.md 既有實測**填入 §4.3.4 / §4.4 / §4.5.1 / §4.6 的留空欄位**;缺的格子(尤其 **Q-llm minimal-pair**、**reader-fixed 版**、**§4.5 覆蓋率量化**)即為下一步要補跑/補算的清單。
</content>
</invoke>
