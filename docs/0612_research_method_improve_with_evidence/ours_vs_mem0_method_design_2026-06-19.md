# 我們的方法（U5 conflict resolution）vs mem0 — 只談方法設計：到底改了什麼

> 日期：2026-06-19
> 來源蒸餾自 [0612_research_method_improve_with_evidence/conflict_resolution_main_design.md](../0612_research_method_improve_with_evidence/conflict_resolution_main_design.md)
> **範圍：只談方法設計本身（改了哪個 component、怎麼改、為什麼）。實驗證據/漏斗分析/數字一律不在此檔。**
> baseline = mem0（Chhikara et al. 2025），評估子任務 = FactConsolidation（FC）。

---

## 0. 一句話

> **我們只替換 mem0 ingestion 的「update component」一個環節：把 L2 從「LLM 直接吐 ADD/UPDATE/DELETE/NONE 的破壞性裁決」換成「LLM 只做六類關係分類 + 確定性映射 + 非破壞 supersede」。extraction、候選檢索、單次 LLM call、batch 結構全部不動，由 flag 切換，vanilla 行為 bit-identical。**

---

## 1. mem0 原本的 update component（被我們替換的對象）

mem0 ingestion 每個 chunk 兩次 LLM call：
- **L1 抽取** `FACT_RETRIEVAL_PROMPT`：抽原子事實。
- **L2 更新** `DEFAULT_UPDATE_MEMORY_PROMPT`：對「新 fact × 既有 top-5」一次性裁決，輸出 `{ADD, UPDATE, DELETE, NONE}` 列表，並 **write-time commit 成破壞性操作**（UPDATE 原地覆寫、DELETE 硬刪）。

**我們指認的四個結構性缺點（只談設計）：**
1. **三件事綁在同一次 LLM call**：衝突偵測 + 衝突解析 + 寫入動作，全在 L2 一次 tool-call 完成並 commit。任一環節錯 → store 永久污染。
2. **沒有時序訊號**：L2 prompt 從未被告知「哪個 fact 較新」，序號在 L1 抽取就被剝離。
3. **操作空間迫使 commit**：`{ADD,UPDATE,DELETE,NONE}` 四選一，**沒有「我不確定」**；沒把握也得選，選錯不可逆。
4. **L1 抽取偏個資整理器**：傾向過濾世界知識類事實（此點我們用 frozen cache 控制，不在本次改動）。

---

## 2. 三個設計原則（我們改動的依據）

**(a) LLM 的能力是「判斷衝突類型」，不是「決定 store 操作」。**
把 LLM 角色從「決定 ADD/UPDATE/DELETE」收斂成「**分類六類關係 + 給 reason**」，操作交給 deterministic mapping。
→ LLM 的錯被限制在 *misclassification*，而非 *misexecution*。

**(b) 操作必須 information-preserving，新資訊永遠進得了 store。**
**任何 fact 都會被 ADD**（除非分類為完全 DUPLICATE）；舊的 conflicting fact 只被標 `status=superseded`，**非物理刪除**。
→ 即使 LLM 判錯，失敗模式從「資料毀損（不可逆）」變成「兩版本並存（可救）」——差別是 categorical 的。

**(c) Ordinal = universal temporal signal。**
用 ingestion order 給每筆 fact 一個單調遞增整數（大者為新），不依賴 FC 特定序號。LLM 分類時把 ordinal 當 SUPERSEDE 的 evidence（但須搭配 mutual exclusivity，單獨 ordinal 不足以觸發）。

> 合起來定義 U5 的形狀：**LLM 只分類，deterministic 只執行，操作只 ADD 跟 supersede。**

---

## 3. 改了什麼：逐點 diff（mem0 → ours）

| 環節 | mem0（vanilla） | ours（U5） | 改動性質 |
|---|---|---|---|
| **L2 prompt** | `DEFAULT_UPDATE_MEMORY_PROMPT`：吐 `{ADD,UPDATE,DELETE,NONE}` | `CONFLICT_CLASSIFICATION_PROMPT`：吐 6 類關係 + reason（**不吐操作**） | **替換** |
| **LLM 角色** | 偵測+解析+寫入動作 三合一 | **只分類關係** | 解耦 |
| **操作決定** | LLM 自由發揮 | **deterministic mapping**（見 §4） | 新增 |
| **時序** | 無 | **ordinal**（write-time stamp） | 新增 |
| **不確定** | 無（被迫四選一） | **UNCERTAIN / COEXIST 預設** | 新增 |
| **舊衝突 fact** | UPDATE 覆寫 / DELETE 硬刪 | **soft supersede**（標 `status`，不物理刪） | 改為非破壞 |
| **新 fact** | 可能被 DELETE/被覆寫掉 | **一律 ADD**（除非 DUPLICATE） | 改為保留 |
| **extraction / 候選檢索 top-5 / 單次 call / batch** | — | **完全不動**（以隔離 update component） | 不變 |
| **觸發** | — | config flag / env，預設 vanilla，**bit-identical** | 不變 |

**不動的東西（重要——為了乾淨歸因）**：`agent.py`、inference prompt 組裝、`conversation_creator.py`、評分邏輯、L1 抽取、候選池大小（固定 top-5 對齊 mem0）、單一 LLM call 與 batch 結構。

---

## 4. 六類關係 → 操作的 deterministic mapping

LLM 只輸出 relation，系統機械映射（**LLM 完全不碰操作名**）：

| relation（LLM 判斷） | deterministic 操作 | 破壞性？ |
|---|---|---|
| NO_RELATION | 只 ADD 新 | 非破壞 |
| DUPLICATE | drop 新（no-op） | 非破壞 |
| ENRICHMENT | ADD merged_text + supersede 舊 | 非破壞（soft 版） |
| COEXIST | 只 ADD 新（兩者並存） | 非破壞 |
| SUPERSEDE | ADD 新 + supersede 舊 | 非破壞（soft 版） |
| UNCERTAIN | 只 ADD 新（保守保留） | 非破壞 |

關係類別與 SUPERSEDE 的證據門檻（correction signal / 單值屬性 / ordinal+互斥）逐字定義見 0612 doc §4 的 `CONFLICT_CLASSIFICATION_PROMPT`。

---

## 5. Phase 1 as-built vs 設計（誠實標註：目前落地版仍有不可逆分支）

> 為最快驗證「解耦 + ordinal」能否改善 FC，**Phase 1 刻意先不做 soft supersession**，改用不可逆操作、重用 vanilla 既有原語。

| 項目 | 設計（soft，目標版） | **Phase 1 as-built（destructive）** |
|---|---|---|
| 觸發 | config flag | env `MEM0_UPDATE_MODE=u5_classification`（零 yaml/agent.py 改動） |
| **SUPERSEDE 操作** | soft：標 `status=superseded`（**可逆**） | **物理 `_delete_memory` 舊 + `_create_memory` 新（不可逆）** |
| payload | 加 6 欄 | **只加 1 欄 `ordinal`** |
| search filter | status=active | 不動 |

**deterministic mapping（Phase 1 不可逆版）**：SUPERSEDE→DELETE舊+ADD新；ENRICHMENT→DELETE舊+ADD merged；COEXIST/NO_RELATION/UNCERTAIN→只ADD新；DUPLICATE→no-op。

> ⚠️ **設計一致性提醒**：原則 (b)「information-preserving / 非破壞」在 **Phase 1 只有 COEXIST/UNCERTAIN/NO_RELATION 成立；SUPERSEDE/ENRICHMENT 仍是 DELETE+ADD 物理刪除 = 破壞性不可逆**。要讓「非破壞」這個 claim 在執行層真正成立，需 **Phase 2 soft supersession 成套**（status 標記 + 檢索附 supersession 鏈 + DUPLICATE drop 守門）。在 paper 講「可逆/非破壞」時，須以 Phase 2 為準，或明確標注 Phase 1 是 destructive 驗證版。

---

## 6. ordinal 的設計定論（method 層，須知）

- **ordinal = write-time STAMP、query-time USE**。write-time 的 SUPERSEDE 實際幾乎不靠 ordinal case (c)，而靠 case (b)「同屬性單值 + 矛盾」；ordinal 在 write-time 近乎惰性（候選恆嚴格更舊使 case (c) 零鑑別力）。
- 但 **write-time stamp 仍必要**：否則 query-time 無時序可用（vanilla 即此缺陷）。
- prompt 的 case (c) 為 vestigial（可移除或保留無害）。
- **去 FC-specific 措辭**（future patch）：ordinal 應描述為「storage system 在記錄時賦予的單調遞增整數，反映 fact 進入系統的時間，與輸入文字無關」，避免讀者誤以為 ordinal = FC 序號。

---

## 7. 與 intro framework 的對接

- 本檔的 §2(a) 解耦 + §3「LLM 只分類」對應 intro 的「judgment/execution 解耦」地基。
- §2(b) 非破壞 + Phase 2 soft supersession 對應 intro 的「two-tier / 可逆 / space-for-reliability」。
- §4 六類關係對應 intro 「關係空間完整到不逼出誤判」那隻手。
- 完整 intro framework 見 [intro_framework_design_2026-06-15.md](intro_framework_design_2026-06-15.md)。
- 各 baseline 的對照（mem0 / mem0g / lightmem / zep 各自 update 機制與可逆性）見 [docs/related work/](../related%20work/)。

> **本檔只到「方法設計差異」為止；證據（FC-SH 6k/32k/64k 漏斗、失敗模式翻轉、轉移矩陣）見 0612 原始 doc §15–18，不在此重複。**
