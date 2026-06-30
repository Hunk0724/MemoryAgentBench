# §5.4 Mechanism Analysis — 機制章草稿(2026-06-30)

> ⚠️ **數字為 PROVISIONAL(暫定)**:來自本機演進過程的既有結果,**論文最終須由穩定機器在定版統一 pipeline + 同一設定下重跑全矩陣取代**(見 `experiment_chapter_draft.md` 頂部與 `docs/handoff/EXPERIMENT_RUNLIST.md`)。本章敘事與因果鏈結構為主、數字為佔位。
>
> **狀態**:draft,可直接進論文 experiment 章。證據來自已 committed 資料(`analysis/results/phase0/*.json`、`figures_current/F_*.{png,pdf}`、`paper_tables_and_figures.md`、`experiment_results.md`);**因果鏈結構穩固,但數字待 unified re-run 取代**。
> **設定**:FC-SH;backbone gpt-4o-mini、temperature 0、**single deterministic run**(故圖無 error bar);metric = exact_match(DRQA normalize + ==,**非 LLM judge**)。LongMemEval / 262k 的對應分析待補(見 outline §5.3 / 缺口)。
> **數據出處**:E-L0/E-rec/E-L1/E-L1L2 → `paper_tables_and_figures.md:37-71`、`F_bank_recall`/`F_recoverable`/`F_L1_state_pie`/`F_ours_L1L2_pie`;E-ceiling → `F_em_vs_ceiling`、`figure_captions.md:17-18`;E4 → `e4_state_to_em.py` / `state_eval_current.json` / `F_state_to_em`;error-mode → `experiment_results.md:64-93`。

---

## 5.4 機制分析:為什麼有效

前兩節(§5.2 主結果、§5.3 LongMemEval)顯示 ours 在 knowledge-update 題上跨 40× context length 維持平緩(has_pair EM 92/86/91/88%),而依賴 full-context 或 write-time 更新的方法隨規模惡化。本節回答**為什麼**:我們沿一條確定性因果鏈,把「答對」逐層拆解到可量測的中間狀態——

$$\text{L0(記憶庫狀態)}\;\rightarrow\;\text{L1(檢索態 top-100)}\;\rightarrow\;\text{L2(解析後 final context)}\;\rightarrow\;\text{EM}$$

每一層皆以**衝突事實的「新版本是否仍可得」**為量測量(以 HF 原文 serial 對應 recency 的 ground truth 比對),且全程 deterministic、不經 LLM judge。結論先行:**答對率幾乎完全由 L2 的最終 context 狀態決定,而最終狀態能否收斂成「只剩新版」,在破壞性 baseline 是 write-time 就已被封死,在 ours 則由「保守寫入 + query-time 解析」兩步達成。**

### 5.4.1 Write-time 不可逆性:損失發生在寫入,而非檢索(E-L0)

我們先掃描**整個記憶庫**(非 top-k 檢索),量測衝突事實的新版本是否仍存在於 store 中(L0 bank GT-recall)。

| 方法 | 6k | 32k | 64k | 262k | 庫大小(facts) |
|---|---:|---:|---:|---:|---|
| **ours**(保守寫入) | **100** | **98** | **95** | **92** | 455 → 18,324(隨長度增長) |
| mem0 + ours storage(破壞性更新) | 51 | 49 | 41 | —* | 219 / 1,162 / 2,076(刪除後縮水) |
| native mem0 | 0 | 0 | 0 | 0 | 0(FC 上幾乎抽不到事實) |

<sub>*破壞性 baseline 的 262k 為 prohibitive run(殘缺,排除)。Zep 不納入此診斷:其非破壞性的 raw-episode 儲存幾乎保留全版本,記憶庫恆為 both,無 write-time 毀損可測(見 §5.4.3 註)。</sub>

**殺手論證(L0 == L1)**:破壞性 baseline 的 **bank-level recall(L0,掃整庫)與 retrieved-level recall(L1,top-100)在每一個長度上完全相等**。若損失是檢索造成,L0 應 > L1(庫裡有、但沒檢索到);兩者相等,直接證明**正解的遺失發生在 write-time——記憶庫本身就已經沒有新版**,而非下游檢索。一旦 write-time 的破壞性 knowledge-update 誤判,即不可逆,任何下游 retrieval / resolution 都無法挽回。相對地,ours 的保守寫入讓記憶庫幾乎完整保有新版(92–100%)。這是論文主張①(faithful / 不在 write-time commit)的直接證據(圖 `F_bank_recall`)。

對應地,以「新版仍可救率」(both + new_only @ L1,佔 has_pair %)量測(圖 `F_recoverable`):ours **100/98/95/92%**、破壞性 mem0+P1 **51/49/41%**、vanilla **0%**——破壞性更新在 write-time 即永久丟掉約一半新版。

### 5.4.2 Query-time 解析的價值:把 both 收斂成 new_only(E-L1→L2)

對 ours 而言,檢索後(L1)幾乎總是 **both**(新舊版本皆在 top-100,92–100%);真正的 knowledge-update 發生在 query-time:經 identity grouping →(S,P)結構 + LLM 分群 → 3-way conflict-type 分類 → 確定性 temporal resolution 後,final context(L2)**大多收斂為 new_only**:

| | 6k | 32k | 64k | 262k |
|---|---:|---:|---:|---:|
| L1 both(新舊皆檢索到) | 100 | 98 | 95 | 92 |
| **L2 new_only(只留新版)** | **70** | **85** | **86** | **79** |

(原始題數:6k 52/74、32k 55/65、64k 57/66、262k 61/77。)綠(both)→ 藍(new_only)的轉換**量化了「將 KU 延遲到 query-time」的價值**(圖 `F_ours_L1L2_pie`)。關鍵對比:**這是破壞性 baseline 結構上做不到的**——它在 write-time 已刪掉一版,L1 根本沒有 both 可供解析。

### 5.4.3 兩道關卡:recall ceiling 與 inference(E-ceiling)

答對需同時通過兩關:(i)**新版必須存在於最終 answer context**(recall ceiling,決定上限);(ii)**模型要能據此答對**(inference)。圖 `F_em_vs_ceiling` 以實際 EM(實線)對 recall ceiling(虛線;ours 取 query-time 解析後的 L2,無 query-time 解析的 mem0 系取 L1)作圖:

- **破壞性 mem0+P1 的 EM 幾乎貼著自身 ceiling(~41–51%)** → 它已逼近自身上限,瓶頸在 **ceiling**(write-time 破壞使新版不在 context),而非 inference;
- **ours 的 ceiling 高(87–100%)且 EM 逼近之** → 同時做到「保守寫入撐高 ceiling」與「query-time 解析逼近 ceiling」。

換言之,破壞性 baseline 的低 ceiling 在 write-time 即已封死,再強的 inference 也無法越過;ours 把上限與達成率兩端同時拉高。(native mem0 因 ceiling 與 EM 皆 ~0、不具資訊量,不列入此圖。)

### 5.4.4 最終狀態決定答對:閉環(E4)

把所有方法 × 長度的 has_pair 題依**最終 context 狀態**池化,對 EM 作圖(`F_state_to_em`):

| 最終 context 狀態 | EM |
|---|---:|
| **new_only**(只剩新版) | **287 / 302 = 95%** |
| both(新舊並存) | 39 / 59 = 66% |
| old_only(只剩舊版) | 1 / 46 = 2% |
| neither(兩版皆無) | 20 / 362 = 6% |

**答對率幾乎完全由最終狀態決定**:new_only → 95%,其餘皆低。這使整條因果鏈閉環——**整場遊戲就是「把 final context 收斂成 new_only」**:ours 靠保守寫入(撐高 ceiling、新版可救)+ query-time 解析(把 both 收斂成 new_only)達成;破壞性 baseline 卡在 old_only / neither 而不可逆。閉環:E-L0(write-time 可救)→ E-rec → E-L1 → E-L1L2 → E4。

### 5.4.5 誤差歸因:retrieval 不是瓶頸,殘餘錯誤在下游(error-mode)

最後檢視 ours 自身的殘餘錯誤,從 per-query 檢索/解析 JSON 直接歸因並核對 HF 原文 serial:

| 長度 | has_pair EM | 檢索可救率(D1) | (S,P) same_sp | benchmark 標註錯(排除) | 真 method 錯 | winnable has_pair |
|---|---:|---:|---:|---:|---|---:|
| 6k | 92% | **100%** | 66% | 0 | 6(全 old_not_dropped) | 92% |
| 32k | 86% | 98% | 66% | 2(q8/q9) | 7(5 分群 + 2 answer) | 89% |
| 64k | 91% | 95% | 68% | 1(q20) | 5(1 分群 + 4 answer) | 92% |

**三個長度的「檢索造成答錯」皆 = 0**:每題答錯時 GT_new 都已在 top-100,錯在下游。raw-question 檢索下 retrieval 不是瓶頸(可救率 100→98→95%,at-scale 僅微降)。真正的 method 錯只有兩種:

1. **`old_not_dropped`**(主因於 6k/32k):新舊兩版都檢索到,但(S,P)未 canonicalize → 沒分到同群 → 沒丟舊 → context 留新舊兩版混淆答題。根因是 ~1/3 的 GT 配對因 predicate/subject 表述不一致而(S,P) key 不同(例如 `is associated with` vs `…the sport of`),只能靠 LLM grouping 補。
2. **`answer-LLM`**(64k 起為主,4/5):context 已乾淨仍答錯,屬 backbone 能力,長 context 下變多。

此外 benchmark 標註錯(gold = 較小 serial、違反 FC newer-wins 規則)0/2/1 題,孤立且排除後 **winnable has_pair = 92/89/92%**。temporal key 經 HF 原文核對正確(FC 池按 serial 排序、chunk-ordinal 正確對應 recency,無 inversion)。

> **小結**:殘餘錯誤集中在 **(S,P) canonicalization**(唯一主要 lever)與 backbone answer 能力,**都不在記憶/檢索層**——進一步佐證「KU 的瓶頸已從 write-time 搬到 query-time 的下游處理」。

### 5.4.6 本節結論

機制分析顯示:knowledge-update 的成敗可化約為「final context 是否收斂成 new_only」這一個確定性狀態(E4:new_only → 95% EM)。破壞性 write-time 更新在記憶庫層即不可逆地丟失新版(E-L0 的 L0==L1),把 ceiling 封死在 ~50%(E-ceiling),下游無從挽回;ours 以**保守寫入撐高 ceiling**、再以 **query-time 解析把 both 收斂成 new_only**(E-L1→L2),且其殘餘錯誤已不在記憶/檢索層(error-mode 的 retrieval-caused = 0)。這正是論文核心主張——**KU 應是 query-time 問題,而非 write-time 的不可逆 commitment**——的機制層證據。
