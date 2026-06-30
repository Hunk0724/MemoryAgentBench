# Conflict Resolution in Incremental Memory — Main Framing & Evidence

> **一句話主張**：增量記憶系統在 ingestion 時用「一次 LLM call 直接決定不可逆 store 操作」來解衝突，會在 query 之前就把正確版本毀掉/留錯；我們把 update component **解耦成「LLM 只判斷衝突類型 + deterministic 執行 + 盡量保留資訊」**，讓正確版本至少**先進得了記憶庫**，衝突消歧延到 query pipeline。FC-SH 上（同 backbone gpt-4o-mini）EM **37→80（6k）、51→66（32k）、52→53（64k）**；三長度都把失敗模式從「寫入層不可逆毀損（98/93/81%）」翻轉到下游，**64k 增益收斂揭示 scale 的兩個新瓶頸（檢索飽和 + 累積誤刪）——兩者正是 Phase 2（soft supersession + query-time 消歧）的設計對象**。
>
> 本文只放**論述需要的結果/表**；完整實作、方法論漏斗、所有數字見 [conflict_resolution_main_design.md](conflict_resolution_main_design.md)（§14 實作、§15 方法論、§16 證據、§18 future work）。

---

## 1. Background — mem0 在 FC 任務上的 pipeline 與最終 benchmark prompt

### 1.1 FC（FactConsolidation）任務設計＝衝突風格
- 輸入是一串**帶序號的事實**（`[1] …`、`[57] …`），**序號越大＝越新**。
- 同一個 `(entity, attribute)` 會有多個版本，新版本邏輯上**覆蓋**舊版本（反事實覆蓋，如某國首都 Aville→Bville）。
- query 要求模型答「**最新版本**」，而非檢索到的任意版本。
→ FC 是「記憶庫衝突處理」最乾淨的壓力測試：政策明確（最大序號勝）、可逐題歸因。

### 1.2 mem0 跑在 FC 的 pipeline（記憶方法的流程）
```
INGESTION（每個 chunk = 一次 memory.add()）
  1. Extraction：從 chunk 抽出原子事實（序號在此被剝離）
  2. Candidate ：每個新 fact → cosine top-5 既有記憶（池化去重）
  3. Update    ：所有新 fact + 池化候選 → 一次 LLM call（DEFAULT_UPDATE_MEMORY_PROMPT）
                 → 輸出 ADD / UPDATE / DELETE / NONE → **destructive 寫入 store**
QUERY（每個 query）
  4. Retrieval ：query → cosine top-100
  5. Assembly  ：把記憶拼成「- mem」清單
  6. Inference ：送進答題 LLM
```

### 1.3 最終 benchmark inference prompt（也解釋了 FC 的衝突風格）
- **system**：`You are a helpful AI. Answer ... based on query and memories.` + 檢索到的記憶清單（`- …`，**無序號**）。
- **user**：FC 知識管理模板（規則寫明「**序號較大者為最新、據此解衝突**」）+ 問題 + Current Time。
- **內建矛盾**：模板假設「知識池帶序號」，但 store 內的記憶**早在 extraction 就被剝掉序號** → 規則對 mem0 形同失效。此矛盾是原始 MABench 內建（非我們製造）。

---

## 2. Past method 的結構性缺點（在 pipeline 的哪一步）+ 數據佐證

### 2.1 缺點都集中在 pipeline 的 **Step 3（Update component）**
mem0 的 `DEFAULT_UPDATE_MEMORY_PROMPT` 在 ingestion 時，對「新 fact × top-5 候選」**一次 LLM call 直接輸出 store 操作**，四個結構性問題：
1. **三件事綁在一個 call**：衝突偵測 + 解析 + 寫入動作 全由 LLM 一次決定並 **commit 成不可逆操作** → 任一環節錯，store 永久污染。
2. **無時序訊號**：prompt 從不知「誰較新」（序號在 Step 1 已被剝離）。
3. **操作空間迫使 commit**：ADD/UPDATE/DELETE/NONE 四選一，**沒有「不確定」** → 沒把握也得選，選錯不可逆。
4. （L1 抽取偏個資化；我們用 frozen cache 控制掉，非主訴。）

### 2.2 數據佐證（FC-SH **6k / 32k / 64k**，gpt-4o-mini；只取論述需要的表）

> 分析順序＝逐級漏斗：**(0) 總體有多差 → (a) 答錯的題在檢索層看到什麼 → (b) 為什麼檢索不到 → (c)(d) update component 的具體錯誤機制**。每級分母都標明 m/n。

**(0) 總體表現：記憶系統本身就是失分主因**
每個長度共 **100 題**，依 GT 分兩種題型：**conflict-pair**（題目對應一組新舊衝突事實，須答新版；74/65/66 題）與 **single-fact**（單一事實，無衝突；26/35/34 題）。

| 方法（同 backbone gpt-4o-mini, temp 0）| 6k | 32k | 64k |
|---|---|---|---|
| LCA：全 context 直接餵，**無記憶系統**（天花板）| 86/100 | 75/100 | 65/100 |
| **vanilla mem0**（經 ingestion 寫入記憶庫再檢索）| **37/100** | **51/100** | **52/100** |
| 差距（= 經過記憶系統的代價）| **−49** | **−24** | **−13** |

→ 同一顆 LLM：資訊完整給它（LCA）能答 86/75/65，**經過 mem0 的 ingestion 後掉到 37/51/52**——失分不在模型能力，在記憶系統把資訊弄丟/弄錯。（64k 起 LCA 自身也因長 context 衰退。）

再按題型拆 vanilla 的失分（m/n = 答對/該題型總數）：
| vanilla | 6k | 32k | 64k |
|---|---|---|---|
| conflict-pair | **23/74（31%）** | **24/65（37%）** | **29/66（44%）** |
| single-fact | 14/26（54%）| 27/35（77%）| 23/34（68%）|

→ **重災區是 conflict-pair**（恰好是 update component 要處理衝突的題型）。以下逐級追問：這些答錯的 conflict-pair 題，到底錯在哪一層？

**(a) 答錯 ⟺ 需要的新版沒被檢索到**（vanilla，retrieval-state × Acc，m/n）
把**全部** conflict-pair 題（74/65/66 題）按「query 時 top-100 是否撈到新版/舊版」分四桶（四桶加總＝74/65/66），看各桶答對率：
| 檢索狀態 | 6k | 32k | 64k |
|---|---|---|---|
| new_only（檢到新）| 21/21 | 22/22 | 20/21 |
| both | 2/3 | 2/2 | 6/6 |
| old_only（只檢到舊）| **0/21** | **0/19** | **0/14** |
| neither（都沒檢到）| **0/29** | **0/22** | 3/25 |
| （single-fact：fact_in / fact_out）| 13/13、1/13 | 21/22、6/13 | 19/19、4/15 |
→ 三個長度一致：新版進 top-100 → ~100%；old_only/neither → ~0%。**問題不在答題，在於新版根本沒進可檢索狀態。**（64k neither 3/25 為參數知識/巧合命中，屬雜訊。）

**(b) 為什麼新版不可檢索？81–98% 是 Step 3 把 store 寫壞**（vanilla conflict-pair 答錯題成因）
| 成因 | 6k（錯51）| 32k（錯41）| 64k（錯37）|
|---|---|---|---|
| old_only（留舊、新沒進）| 21 | 19 | 16 |
| neither D0 純 omission | 12 | 5 | 3 |
| neither D1 舊刪+新沒進 | 15 | 10 | 8 |
| neither D2 新被摧毀 | 2 | 4 | 3 |
| 下游 R/Z（檢索/答題）| 1 | 3 | 7 |
| **→ write-time（update component 寫壞 store）** | **50/51 = 98%** | **38/41 = 93%** | **30/37 = 81%** |

→ **claim 扣合（跨長度成立）**：vanilla 衝突失敗 **81–98% 發生在 ingestion 的 update component**，不是檢索、不是答題（下游比例隨 store 變大緩升，屬正交的檢索飽和）。過去方法「聽起來合理」的結構缺點，數據證實就是主因。

> **分類方法（嚴謹性）**：對每個答錯題依優先序判定 `new∈top-100？→Z；new∈final store？→R；old∈final store？→old_only；否則依「曾否入庫」分 D2/D1/D0`——if/elif 構造保證互斥窮盡（加總=51/41 ✓）。final store 由 `ingestion_context_0.jsonl`（實際 applied 事件，非 LLM 原始輸出）逐事件 replay 重建；並以獨立的 query-time top-100 dump 交叉驗證 store 狀態（6k 74/74 一致；32k 62/65，3 題差異恰為 R 的定義本身）。機制層另由候選池 log（old_only 85–94% 衝突可見）與逐事件 trace（D1 87–90% 經 DELETE）獨立佐證。詳 design doc §15。

**(c) 主軸鐵證：write-time 失敗中，壓倒性是「衝突可見卻沒解」而非候選沒撈到**
把 §2.2(b) 的 old_only 再切一刀——看「新 fact 的 top-5 候選**有沒有撈到對應的舊版**」（撈到＝衝突攤在 update component 面前）：
| | 6k | 32k | 64k |
|---|---|---|---|
| old_only 總數 | 21 | 19 | 16 |
| **VISIBLE：舊版在候選裡、update 卻沒判 UPDATE（留舊丟新）** | **18/21 = 85%** | **18/19 = 94%** | **16/16 = 100%** |
| INVISIBLE：舊版沒撈到（候選/檢索問題，正交，非主訴）| 3（皆 same-chunk）| 1 | 0 |

> **這就是主軸最該展示的一刀**：old_only 失敗**85–100%（隨長度遞增至全部）是「update component 明明看得到衝突、卻沒做 UPDATE」**的**純衝突解析判斷失敗**，不是候選沒撈到。
> （old_only 已隱含「沒 UPDATE」：若 vanilla 把舊版 UPDATE 成新版，store 就會是 new_only 而非 old_only。）
> 例：qid25「Tang 首都」舊版 Chang'an 就在候選池、新版 Beaumont 也在，update LLM 卻判 **NONE** → 留舊丟新。**這批正是 U5 餵同一份候選 + ordinal 後能解掉的**（§4）。
> 成因對應 §2.1：無時序訊號（不知 Beaumont 較新）+ 耦合單次 commit + 預設保守不動。

**(d) D1 的機制驗證：「該 UPDATE 卻 DELETE」**（`scripts/neither_mechanism.py`，逐事件 replay）
| neither 子類的移除方式 | 6k | 32k | 64k |
|---|---|---|---|
| D1 **via DELETE**（舊版被 DELETE、新版沒進）| **13/15** | **9/10** | **9/9** |
| D1 via UPDATE_overwrite（舊版被改寫成無關文字）| 2/15 | 1/10 | 0 |
| D2 新版被摧毀（以 DELETE 為主）| 2 | 4 | 4 |

> 與 old_only 合起來，**vanilla 的兩大衝突失敗就是同一個錯的兩面**：正確動作都是 `UPDATE old→new`，但 LLM 直接出操作時——
> **old_only = 錯選 NONE**（保守不動，留舊丟新）；**D1 = 錯選 DELETE**（毀舊、又沒存新）。
> 操作空間 {ADD/UPDATE/DELETE/NONE} 四選一、一次 commit、不可逆 → 任一誤選都讓正確版本永遠進不了庫。這正是 §2.1 結構缺點 #1/#3 的逐案實證。

---

## 3. Insight & Main Design

### 3.1 從缺點導出的 insight
- LLM 的能力是「**判斷衝突類型**」，不是「決定 store 操作」——一旦判出類型，操作是 mechanical 的，不該讓 LLM 自由 commit。
- 不可逆毀損的根因是「**在不知未來 query、且不可逆的前提下盲裁**」→ 與其在 ingestion 賭一個操作，不如**先保住資訊**，把衝突消歧**延到 query 時**（那時知道問哪個 slot）。
- 缺「誰新誰舊」的客觀依據 → 補一個**通用時序訊號**。

### 3.2 設計（仍在 pipeline 的 Step 3，加上 storage 帶時序）
| 機制問題（§2.1）| U5 對策 |
|---|---|
| 耦合 + 不可逆 commit | **解耦**：LLM 只輸出六類關係（NO_RELATION/DUPLICATE/ENRICHMENT/COEXIST/SUPERSEDE/UNCERTAIN）+ reason；**Python deterministic** 把類型映射成操作 → 錯誤被限制在 *misclassification* 而非 *misexecution* |
| 無時序訊號 | **ordinal**（ingestion 順序的單調整數，**存進 payload＝持久化時間戳**）。**精確角色（雙證據）**：write-time 它是惰性的——(i) 候選恆比 new 舊（0 例外）使 SUPERSEDE case (c) 的「ordinal 較大」恆真、零鑑別力；(ii) LLM 的 SUPERSEDE reason 引用時序僅 **0%/0%/2%**（6k/32k/64k），實際靠「同屬性互斥+矛盾」（case b，引用 77–84%）。**裁決力在 query-time 兌現**——top-100 內版本對等、無角色不對稱，ordinal 是唯一時序訊號（vanilla 連這個都丟掉）。故設計陳述：**write-time stamp、query-time use**；prompt case (c) 為 vestigial。|
| 強制 commit 無「不確定」| 分類含 **UNCERTAIN / COEXIST**，保守時保留兩版而非誤刪 |
| query 前就毀掉正解 | **盡量保留資訊**：除非 DUPLICATE，新 fact 一律 ADD → 失敗模式從「資料毀損（不可逆）」降級成「兩版並存（可救）」 |

### 3.2b 核心設計一頁表：Conflict classification → Deterministic operation

> **The LLM judges WHAT the relation is. The code decides WHAT TO DO.**

| Relation (LLM judges) | Definition (when to use) | Operation (code executes) | Store effect |
|---|---|---|---|
| **NO_RELATION** | The two facts are about different things — the retrieved candidate was a false match. | ADD new | old kept, new added |
| **DUPLICATE** | The new fact says the same thing as the existing one, nothing extra. | DROP new (no-op) | store unchanged |
| **ENRICHMENT** | The new fact adds detail to the existing one, **without** contradicting it. | ADD merged fact + DELETE old | one richer fact replaces old |
| **COEXIST** | Both facts can be true at the same time (multi-valued attribute, e.g. "likes X"). **Default when unsure.** | ADD new | old and new both kept |
| **SUPERSEDE** | The new fact replaces the old one — same single-valued attribute, mutually exclusive values, and newer (larger ordinal) or an explicit correction signal. | ADD new + **DELETE old** | new replaces old |
| **UNCERTAIN** | Cannot decide confidently. A **valid and encouraged** answer — never guess SUPERSEDE. | ADD new | old and new both kept (recoverable later) |

**Three rules the table encodes：**
1. **LLM never outputs operations** — only a relation + one-sentence reason. The relation→operation mapping is fixed code, so a wrong judgement is a *misclassification*, never a *misexecution*.
2. **DELETE has exactly one gate**：only SUPERSEDE / ENRICHMENT can remove anything, and SUPERSEDE needs evidence（correction signal ∨ single-valued attribute ∨ larger ordinal + mutual exclusivity — ordinal alone is never enough）。
3. **Every "not sure" path keeps both versions**（COEXIST / UNCERTAIN / NO_RELATION → ADD）：a wrong conservative call costs **redundancy**（query-time can still resolve）；it never costs **information loss**。
> Phase 1：DELETE is physical（irreversible）。Phase 2（future）：soft supersession — mark old as `superseded` instead of deleting，making rule 2 fully reversible。

### 3.3 本質
> **核心 = 解耦 update component LLM 的職責（判斷而非操作）+ 盡量讓資訊存得進記憶庫**；至於「新舊並存時挑哪個」的衝突消歧，**留到 query pipeline 再處理**——但前提是**正解至少先存在於記憶庫、檢索得到**，不會像過去在檢索前就消失。

> **Phase 1 範圍（誠實標註）**：目前 ordinal **只用於衝突判斷**，SUPERSEDE 仍是**物理刪除**（重用 vanilla 原語、不可逆）。soft supersession（可逆標記）、ordinal 去 FC-specific 措辭、non-FC 範例、ordinal on/off ablation 均列 **future work**（見 design doc §18）。

---

## 4. Results（FC-SH **6k / 32k / 64k**，gpt-4o-mini；唯一變量 = update component）

> 三方法皆為自跑 matched run（vanilla 6k 與 09 的 37% 逐字吻合；32k/64k 與 09 有漂移：51 vs 62、52 vs 45，LCA 64k 65 vs 62 → 證明必須比自跑 baseline）。詳見 design doc §16。

### 4.1 總體 + 分題型 EM（含 LCA 天花板）
| 方法 | 6k overall | 6k CP | 6k SF | 32k overall | 32k CP | 32k SF | 64k overall | 64k CP | 64k SF |
|---|---|---|---|---|---|---|---|---|---|
| LCA（全 context，無記憶系統，天花板）| 86/100 | — | — | 75/100 | — | — | 65/100 | — | — |
| vanilla mem0 | 37/100 | 23/74 | 14/26 | 51/100 | 24/65 | 27/35 | 52/100 | 29/66 | 23/34 |
| **ours(U5)** | **80/100** | **56/74** | **24/26** | **66/100** | **38/65** | **28/35** | **53/100** | **34/66** | **19/34** |

- LCA = 同 backbone、temp 0、全 context 直接餵（無 ingestion 損耗），界定「資訊零損失」時答題層的上限——64k 它自己也衰退到 65。
- 讀法：vanilla 與天花板差 **−49/−24/−13pp**；ours 收斂到 **−6/−9/−12pp**。**EM 增益隨長度收斂：+43 → +15 → +1**——原因見 §4.2/§4.5：write-time 修復的增益，在 64k 被「檢索飽和 R + 並存消歧 Z + 累積誤刪」吃掉（其中 SF 還倒退 23→19，正是飽和的直接代價）。

### 4.2 ★ 失敗模式翻轉（呼應 §2.2 的 claim，跨長度成立；但下游代價隨長度成長）
| 成因 | 6k van（錯51）| 6k ours（錯18）| 32k van（錯41）| 32k ours（錯27）| 64k van（錯37）| 64k ours（錯32）|
|---|---|---|---|---|---|---|
| write-time（update 寫壞 store）| **50 = 98%** | **3 = 17%** | **38 = 93%** | **12 = 44%** | **30 = 81%** | **14 = 44%** |
| 下游 R+Z（檢索/答題）| 1 | **15 = 83%**（Z15）| 3 | **15 = 56%**（Z10+R5）| 7（R6+Z1）| **18 = 56%**（**R12**+Z6）|

> **定義（以「新版正解」為主詞）**：**Z** ＝ 新版**有進**該題 top-100（LLM 看得到）卻仍答錯——多發生在 both（新舊同進、挑了舊）；**R** ＝ 新版**在 final store** 但**沒進** top-100（在庫沒檢到＝飽和）。判定優先序 Z→R→store 狀態，見 §2.2(b) 註腳。
>
> **U5 在三個長度都把 write-time corruption 大幅壓低（98→17、93→44、81→44），失敗模式一致翻轉到下游**。但下游的組成隨長度變化：6k 殘留幾乎全是 Z（並存消歧），64k 變成 **R 主導（12/32）＝檢索飽和**——always-ADD 讓 store 變大，正解在庫卻擠不進 top-100（SF 同步受害：fact_out 15→18）。**結論：write-time 解掉之後，query-pipeline（消歧 + 飽和處理）從「可選的下一步」變成「scale 的必要條件」。**

### 4.3 store 層 wins/losses（final-store 狀態轉移 vanilla→ours）
```
6k (n=74)                       32k (n=65)                      64k (n=66)
van\ours  new both old nei      van\ours  new both old nei      van\ours  new both old nei
new_only   13   8    0   0      new_only   12   8    2   3      new_only   19   1    1   6
old_only    9  10    1   1      old_only    4  11    2   2      old_only    6   7    2   1
neither    19   9    0   1      neither     8   8    0   3      neither     7   7    2   1
both        1   2    0   0      both        1   0    1   0      both        3   2    0   1
```
- 修好（old_only/neither → new 進庫）：6k **47 對**、32k 31 對、64k 27 對——三長度都大量修復。
- **破壞性退步 `new_only→old_only/neither`：0 → 5 → 7**＝Phase-1 物理刪除的累積暴露（64k 另有 D2=6）→ soft supersession 從「加分項」變成「必要」。
- 共同代價 `new_only→both`（8/8/1）：新仍在、舊也留 → 答題層負擔（屬「可救」的並存，非毀損）。

### 4.4 機制與舉例（matched re-run 的事件分布）
- update 事件對比：vanilla **NONE 655（6k）/ 6029（32k）**（大量不作為＝留舊）vs U5 主動 **SUPERSEDE 101（6k）/ 507（32k）**（DELETE舊+ADD新）。
- U5 32k relations：COEXIST 813 / SUPERSEDE 507 / DUPLICATE 228 / ENRICHMENT 64 / NO_RELATION 43 / UNCERTAIN 1。
- 代表案例 qid25「Tang Empire 首都 Chang'an→Beaumont」：vanilla 對舊版判 NONE → old_only → 答 Chang'an ✗；U5 判 SUPERSEDE → store 只剩 Beaumont（FC 正解）。

### 4.5 隨長度趨勢（6k / 32k / 64k）
| 指標 | 6k | 32k | 64k |
|---|---|---|---|
| EM：vanilla → ours | 37 → **80**（+43）| 51 → **66**（+15）| 52 → **53**（**+1**）|
| conflict-pair EM | 23/74 → 56/74 | 24/65 → 38/65 | 29/66 → 34/66 |
| single-fact EM | 14/26 → 24/26 | 27/35 → 28/35 | 23/34 → **19/34（倒退）** |
| write-time corruption（vanilla → ours）| 98% → **17%** | 93% → **44%** | 81% → **44%** |
| store 層破壞性退步 `new_only→old_only/neither` | **0** | **5** | **7** |
| 檢索飽和 R（在庫沒進 top-100，ours）| 0 | 5 | **12** |

（全部自跑 matched run；與 09 的漂移：vanilla 32k 51 vs 62、64k 52 vs 45、LCA 64k 65 vs 62。）

**趨勢解讀（誠實）**：
1. **主軸 claim 隨長度更強**：vanilla 的 write-time corruption 一直是失敗主因（98/93/81%），且 old_only「衝突可見卻沒解」85%→94%→**100%**；U5 在三長度都把 corruption 壓到 17/44/44%，修復 47/31/27 對。**write-time 解耦設計的有效性跨長度成立。**
2. **但 EM 增益收斂（+43→+15→+1），因為兩個 scale 代價把 write-time 增益吃掉**：
   - **檢索飽和 R（0→5→12）+ SF 倒退（fact_out 15→18）**：always-ADD 讓 store 變大，正解在庫卻擠不進 top-100——「保留資訊」的直接代價，**這不是反證，而是把問題從『不可逆毀損（無解）』換成『檢索飽和（可解）』**。
   - **累積誤刪（0→5→7；D2 6 例）**：chunk 越多，Phase-1 物理 DELETE 被一次 over-SUPERSEDE 毀掉正解的累積機率越高。
3. **→ Phase 2 的設計從「可選」變成「scale 必要」——但要成套，不是單放一個 status 欄位**：
   - **關鍵釐清**：若 retrieval 硬過濾 `status=superseded`，被誤標的正解一樣檢索不到——**對誤刪題，「標記+硬過濾」的 EM 結局＝物理刪除**。soft supersession 的價值必須由 **query-time 政策**兌現：(i) 檢索到勝者時**連帶附上其 supersession 鏈**（"X (current, ord 57); previously Y (ord 1)"）→ 同時做消歧與誤標保險；(ii) active 結果衝突/低信心時 fallback 撈 superseded 層；(iii) 離線可審計修復。
   - **修正（2026-06-13）**：「過濾 superseded 解飽和」對 Phase-1 baseline **不成立**——Phase 1 已物理刪除被取代版本（64k 刪 1140 條後 active store 仍 2934，top-100 僅覆蓋 3.4%），飽和發生在已修剪的庫上；soft 標記＋過濾只是維持同樣的 active 集合。**真正打 R 的是 supersession 鏈擴展**：query 措辭常更貼近舊版 → 舊版被檢回時沿 `superseded_by` 自動拉進新版，舊版從干擾項變成指向正解的路標。輔以 active 集 dedup 與 diversity 檢索。
   - **§4.8 B2 揭露 soft supersession 蓋不到的洞**：退步題裡「誤判 DUPLICATE → 新版被 drop」（32k 4、64k 5）**比 over-SUPERSEDE（2、4）更多**——被 drop 的新版**從未入庫**，標記救不了。對策＝把 DUPLICATE 的 drop 也改成 deterministic 守門（僅在文字/embedding 近同一時才 drop，否則 ADD）。
   - 殘餘 both（Z）由 query-time ordinal 消歧處理。→ 三個殘餘失敗源頭（R / 誤刪+誤dup / Z）各有對應且互相咬合的設計。

### 4.6 跨方法公平比較的指標：conflict-pair 的最終 vectorDB 狀態分布
> 為什麼選它：此指標定義在 **store 內容的最終狀態**（new/old 是否存在），**與操作種類無關**——vanilla 有四種操作、ours 只有 ADD/DELETE，但「正確版本最後在不在庫」對兩者同樣可判，**op-agnostic、跨方法公平**。它也是 QA 的真相上游（§2.2(a)：new 不在庫 ⇒ 必錯）。

| conflict-pair 最終 store 狀態 | 6k van | 6k **ours** | 32k van | 32k **ours** | 64k van | 64k **ours** |
|---|---|---|---|---|---|---|
| new_only（✓ 衝突乾淨解決）| 21 | **42** | 25 | **25** | 27 | **35** |
| both（新舊並存，可救）| 3 | 29 | 2 | 27 | 6 | 17 |
| old_only（✗ 留舊丟新）| 21 | **1** | 19 | **5** | 16 | **5** |
| neither（✗ 全毀）| 29 | **2** | 19 | **8** | 17 | **9** |
| （n = conflict pairs）| 74 | 74 | 65 | 65 | 66 | 66 |

→ 一張表看 wins/losses：**「正確版本在庫」（new_only+both）vanilla 24/74、27/65、33/66 → ours 71/74、52/65、52/66**；ours 的代價是 both 變多 + 64k 起在庫≠檢得到（R），消歧與飽和留給 query pipeline（§4.5 解讀 3）。

### 4.7 答題 LLM 實際看到什麼：top-100 檢索狀態分布（vanilla vs ours）
> §4.6 是 store 真相；這張是 **query 當下 top-100 的可見狀態**——兩者的差距＝檢索飽和。各桶附答對率（m/n）。

| 檢索狀態 | 6k van | 6k ours | 32k van | 32k ours | 64k van | 64k ours |
|---|---|---|---|---|---|---|
| new_only | 21（21/21）| **42**（41/42）| 22（22/22）| 22（21/22）| 21（20/21）| **28**（27/28）|
| both | 3（2/3）| 29（15/29）| 2（2/2）| 25（16/25）| 6（6/6）| 12（7/12）|
| old_only | 21（0/21）| **0** | 19（0/19）| 7（0/7）| 14（0/14）| 5（0/5）|
| neither | 29（0/29）| 3（0/3）| 22（0/22）| 11（1/11）| 25（3/25）| **21**（0/21）|

- 「新版可見」（new_only+both）：vanilla 24/24/27 → ours **71/47/40**——6k 近乎全可見；64k 雖 store 有 new 52/66，**可見只剩 40/66**，缺口 12＝飽和（R）。
- ours 的 neither-檢索 64k 高達 21，但 store 層 neither 只有 9 → **12 題正解在庫卻整題撈不到**——飽和已是 ours 在 64k 的第一大失因。

### 4.8 ★ 戰場回收與新增失敗（直接回答「過去的失敗戰場救回多少、又多輸了哪些」）

**B0：兩方法「各自的主戰場殘餘」對照**（各自 store 歸因下，old_only + D1 造成的答錯題數）：
| 主戰場失敗數（old_only + D1）| 6k | 32k | 64k |
|---|---|---|---|
| vanilla | **36**（21+15）| **29**（19+10）| **24**（16+8）|
| **ours** | **1**（1+0）| **5**（5+0）| **5**（5+0）|

- **主戰場殘餘 36→1、29→5、24→5**——這是 update component 改動「真實改進」最直接的一張表。
- **結構性事實：ours 的 D1 恆為 0**——非運氣，是 deterministic mapping 構造上消滅了這條路徑（DELETE 只能經 SUPERSEDE/ENRICHMENT 觸發、且必然同時 ADD 新版 →「刪舊又沒存新」不可能發生）。ours 殘餘的 old_only 全來自誤判 DUPLICATE 把新版 drop（見 B2）。
- （vanilla 在 B1 各類別答對率定義上＝0%——類別即從 vanilla 答錯題歸因而來，故 B1 直接列 ours 救回數。）

**B1：以 vanilla 的失敗成因為條件，看 ours 同題的結果**（救回/該類總數）：

| vanilla 失敗成因 | 6k | 32k | 64k |
|---|---|---|---|
| **old_only（該 UPDATE 卻 NONE）** | **13/21** | **9/19** | **9/16** |
| **D1（該 UPDATE 卻 DELETE）** | **13/15** | **9/10** | **4/8** |
| └ **主戰場小計（old_only+D1）** | **26/36 = 72%** | **18/29 = 62%** | **13/24 = 54%** |
| D0 純 omission（附帶）| 9/12 | 2/5 | 2/3 |
| D2 新被摧毀 | 2/2 | 3/4 | 1/3 |
| R 檢索飽和（正交，預期救不了）| — | **0/3** | **0/6** |
| Z 答題層 | 0/1 | — | 1/1 |

- **主戰場（old_only+D1）回收率 72%→62%→54%**：三長度都過半，但隨飽和遞減。
- **vanilla 的 R 題 ours 救回 0/9**——完美驗證「檢索飽和與 update component 正交」：我們只改 update，R 題就一題都救不動。歸因乾淨。

**B2：退步題（vanilla 對 → ours 錯），按 ours 的失敗成因**：

| ours 失敗成因 | 6k（退4）| 32k（退9）| 64k（退12）|
|---|---|---|---|
| Z（both 並存挑錯）| 4 | 3 | 2 |
| old_only / D0（**誤判 DUPLICATE → 新版被 drop**）| 0 | 4 | 5 |
| D2（**over-SUPERSEDE → 新版被誤刪**）| 0 | 2 | 4 |
| R（飽和）| 0 | 0 | 1 |

- 退步來源恰好就是 U5 僅有的兩個破壞性出口：**誤判 DUPLICATE（丟新）與 over-SUPERSEDE（刪新）**——皆為 misclassification 映射到 drop/delete。6k 全是可救的 Z；32k/64k 起破壞性誤判隨 chunk 數累積。
- 對帳：淨增益 = 救回 − 退步 = +33/+14/+5（與 CP EM 23→56、24→38、29→34 完全吻合）。

---

## 5. 主軸 ↔ 證據 總對應（audit）

> 研究主軸逐句拆解，每句對應到已有的實作/分析結果。✅=已有數據扣合；🔶=部分/誠實註記；⬜=future。

| # | 主軸論述 | 證據 | 狀態 |
|---|---|---|---|
| 1 | 過去方法（mem0/LightMem 派）在 ingestion 用 LLM 直接輸出 ADD/UPDATE/DELETE/NONE 操作記憶庫解衝突 | §1.2 pipeline Step 3（DEFAULT_UPDATE_MEMORY_PROMPT 逐字、單 call、destructive）| ✅ |
| 2 | 這種不可逆解法，操作失敗 → 正確版本沒存入 | §2.2(b)：conflict-pair 答錯 98/93/81%（6k/32k/64k）是 write-time 寫壞 store | ✅ |
| 2a | └ 失敗型 1：**old_only ＝ 該 UPDATE 卻 NONE**（衝突可見仍不動）| §2.2(c)：old 在 new 的 top-5 候選中仍沒 UPDATE ＝ 85%/94%/**100%**（隨長度遞增）| ✅ |
| 2b | └ 失敗型 2：**D1 ＝ 該 UPDATE 卻 DELETE**（毀舊又沒存新）| §2.2(d)：D1 經 DELETE 移除 13/15、9/10、9/9 | ✅ |
| 2c | └ 連 ADD 都沒做（D0 omission）比例不低，但**非主軸**（已用 L2+frozen cache 排除抽取變因，仍發生 → 歸因 update LLM 能力 × 該 prompt）| §2.2(b)：D0 12/51、5/41、3/37；extraction leak=0（09 §6）| ✅（明示為附帶，不灌水）|
| 3 | query pipeline 因此拿不到正確版本 | §2.2(a)：old_only/neither 檢索狀態 → Acc ~0%（三長度一致）；new 檢到 → ~100% | ✅ |
| 4 | 我們的設計＝解耦（LLM 只判衝突類型，code 執行）+ ordinal 輔助 + 盡量保留資訊、只操作明確衝突 | §3.2 設計表；實作為 CONFLICT_CLASSIFICATION_PROMPT + deterministic mapping（design doc §14）| ✅ |
| 5 | 設計奏效：正確版本進得了庫、write-time corruption 三長度都大降、失敗模式翻轉 | §4.2 write-time 98→17、93→44、81→44%；§4.6「new 在庫」24→71、27→52、33→52；EM +43/+15/+1（64k 增益被下游吃掉，見 #5b）| ✅ |
| 5b | **scale 誠實面**：EM 增益隨長度收斂（+1 @64k），原因＝檢索飽和 R（0→5→12）+ 累積誤刪（0→5→7）+ SF 倒退（fact_out 15→18）| §4.5 趨勢解讀；**兩個瓶頸都有對應 Phase-2 設計（soft supersession 一石二鳥 + query-time 消歧）** | 🔶（已定位、未實作）|
| 6 | 跨方法公平指標 | §4.6 最終 vectorDB 狀態（op-agnostic，ours 只有 ADD/DELETE 也適用）+ EM + 漏斗成因（同一套定義跑兩方法）| ✅ |
| 7 | 泛化設計（非 FC-specific）| 🔶 prompt 設計上通用（六類關係、ordinal=ingestion 順序），但措辭去 FC 化 + non-FC 範例 + ordinal ablation 均列 future（design doc §18）| 🔶 |
| 8 | 不可逆的殘餘代價（Phase 1 仍物理刪除）| 🔶 §4.5：32k 出現 5 題 new_only→old_only/neither → soft supersession 動機 | 🔶（誠實註記）|
| 9 | query pipeline：對檢回 top-100 的剩餘衝突（both）做消歧 | ⬜ 未設計。現有數據已定位戰場：both bucket Acc 15/29（6k）、16/25（32k）| ⬜ future |

**Gap 清單（寫論文前要嘛補、要嘛明寫 limitation）**：
1. ⬜ **Phase 2（64k 後已升級為必要）**：soft supersession（status 標記 + 檢索過濾 superseded → 同時解可逆性與飽和）+ query-time 消歧（both/Z）。
2. ⬜ ordinal on/off ablation（已登記預測：write-time delta 小；裁決力在 query-time 兌現）。
3. ✅ 64k 已補完（LCA 65 / vanilla 52 / ours 53，全自跑 matched）；漂移紀錄：vanilla 32k 51 vs 09 62、64k 52 vs 45、LCA 64k 65 vs 62。
4. 🔶 「流派」claim（LightMem/Zep 同病）目前僅引文獻（LightMem ablation 附錄 K.2），無自跑數據。

---

## 附：論述↔證據 對應檢查（速查版）
| 論述環節 | 對應證據 | 來源 |
|---|---|---|
| FC 是衝突風格任務 | §1.1 + 最終 prompt 內建序號矛盾 | design doc §14/§1 |
| 過去缺點在 update component | §2.2(b) 98% write-time | funnel Stage 3/4 |
| **主軸：衝突可見卻沒解（NONE）** | **§2.2(c) old_only VISIBLE 85–94%** | oldonly_visibility.py |
| **主軸：該 UPDATE 卻 DELETE（D1）** | **§2.2(d) D1 via DELETE 87–90%** | neither_mechanism.py |
| 答錯=新版不可檢索（非答題問題）| §2.2(a) retrieval×Acc | funnel Stage 2 |
| 解耦+保留資訊有效 | §4.2 翻轉 + §4.3/4.6 store 狀態 | funnel + 轉移矩陣 |
| 殘留是 query 層消歧 | §4.2 inference Z + both bucket | funnel Stage 2/3 |
