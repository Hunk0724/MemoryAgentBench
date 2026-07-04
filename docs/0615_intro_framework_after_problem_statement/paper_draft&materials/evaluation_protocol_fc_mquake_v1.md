# Evaluation Protocol：FC × MQUAKE 記憶庫終態診斷（v1，2026-07-04）

> ⚠️ **重新定位：APPENDIX / FUTURE WORK BACKING**
> 當前主 protocol 已改為 [`evaluation_protocol_main.md`](evaluation_protocol_main.md)（Tier 1/2/3 priority）。
> 本文的 EFR/IRR/BJV **語意仍成立**，但已被 v2 的 M1 DLR 對接、且**降級為 appendix 輔助**（paper 主故事優先 E2E Acc + return_context × Acc，終態診斷屬「為什麼中的為什麼」）。
> 保留本文供 appendix 引用 + 未來若 reviewer 挑「write-time damage 有多嚴重」時 activate。

---

> **原目的（v1 提案時）**：把「架構層 #2（write-time 判斷盲目、密集、不可逆 → 錯誤累積且無法還原）」從論述變成三個可量化的數字。分析對象是 **baseline 跑完 FC 後的記憶庫終態**，不是 QA 準確率——QA 準確率混雜了檢索與推論，終態診斷直接隔離「更新機制本身做對了沒、做錯了救不救得回」。

---

## 0. 三個宣稱 → 三個指標（先釘死定義，再跑）

| 宣稱 | 指標 | 定義（一句話） |
|---|---|---|
| A. write-time 判斷密集且會錯 | **EFR (Event Failure Rate)** | 全部 conflict pair 中，終態未達成該系統「預期正確更新語意」的比例 |
| B. 錯誤不可還原（#2 的靈魂） | **IRR (Irrecoverability Ratio)** | 全部 pair 中，終態已**無法從記憶回答出 gt_new** 的比例（分母也另報「判錯 pair 中」的條件版本） |
| C. 判斷是盲目的（遠多於實際被查的） | **BJV (Blind Judgment Volume)** | write-time 跨筆 LLM 判斷次數 ÷ 實際被 query 觸及的 pair 數 |

**ours 的對照數字（by construction）**：忠實寫入下，終態恆為「所有版本都在」→ IRR ≡ 0、write-time 跨筆判斷次數 ≡ 0。ours 這邊要報的不是終態，而是查詢時的分群/解析正確率（見 §6）。

---

## 1. 輸入

1. **FC-SH 對話**，四個長度（6k / 32k / 64k / 262k），每長度含編號事實流（"newer facts have larger serial numbers"）。
2. **MQUAKE pair 標註**：每個 counterfactual 編輯對的 (gt_old triple, gt_new triple) 與其在對話中的 serial/位置。⚠️ 這是**全體 pair 母體 P**（每長度遠多於 100），不是只有被 100 題 query 到的那些——這正是量 BJV 的前提。
3. **Baseline 跑完 ingest 後的記憶庫終態**：
   - mem0：vector store（qdrant）全部 payload dump。
   - LightMem [3]（Fang et al.）：offline batch update **執行完之後**的 store dump（⚠️ 要在 `offline_update_all_entries()` 之後 snapshot，不是 ingest 完就 snapshot）。
   - Zep/Graphiti：graph edge dump，含 `valid_at / invalid_at / expired_at` 欄位。
4. **（可得則收）write-time 操作日誌**：每次 update prompt 的輸入候選、LLM 輸出的操作標籤（ADD/UPDATE/DELETE/NOOP 或 update/delete/ignore 或 contradicts/duplicates）。有 log 才能做 §5 的失因分類；沒有 log 只能報終態層指標（EFR/IRR 仍可算）。

## 2. Pair↔記憶條目的比對（matching）——先定死，避免「挑指標」質疑

對每個 pair p = (f_old, f_new)，在終態記憶庫中找「承載 f_old 的條目集合 E_old(p)」與「承載 f_new 的條目集合 E_new(p)」：

- **第一層（deterministic，優先）**：正規化字串比對——lowercase、去標點、數字正規化後，檢查條目文字是否包含 gt triple 的 (subject, object) 或其明確同義形（MQUAKE 提供 triple，subject+object 同現即命中；object 是被編輯的 value，是關鍵判準）。
- **第二層（LLM judge，僅第一層 miss 時）**：固定 prompt、固定 backbone（建議 gpt-4o，與被測系統無關的強模型）、輸出 yes/no：「這條記憶是否記載了〈triple〉這個事實？」。
- **稽核**：隨機抽 30 個 pair 人工核對 matcher 判定，回報 matcher precision/recall；論文附錄要放這個數字。
- **特別注意 mem0/LightMem 的 UPDATE 會改寫文字**：被 LLM rewrite 過的條目可能同時混含新舊資訊或都不含——matcher 對「rewrite 後仍能答出 gt_new 的 object value」才算命中 E_new，這是 IRR 的判準核心（能不能**答出來**，不是有沒有痕跡）。

## 3. 各系統的「正確更新語意」與終態分類

每個 pair 依 (E_old, E_new) 的存在狀態分類。**注意三個系統語意不同，指標定義必須各自對齊其設計意圖，否則會被反駁「你用別人不採用的標準打分」。**

### 3.1 mem0（coupled，破壞性）
- **設計意圖的正確終態**：gt_new 在庫 ∧ gt_old 不在庫（它的 UPDATE 本來就要覆掉舊值）。
- 終態分類：`CORRECT`（new✓ old✗）/ `STALE_KEPT`（new✓ old✓：沒判到衝突，靠 inference 自救）/ `NEW_LOST`（new✗：新值被誤 DELETE、被錯誤 rewrite、或寫入時被判 NOOP 丟棄）/ `BOTH_LOST`（new✗ old✗）。
- **EFR** = 1 − |CORRECT|/|P|。
- **IRR** = (|NEW_LOST| + |BOTH_LOST|)/|P| —— gt_new 已無法從終態答出 = 不可還原。
- 註：`STALE_KEPT` 算 event 失敗但**不算**不可還原（新值還在，query-time 有機會救）——這個區分正是你 thesis 的核心：**失敗不可怕，不可還原才可怕**。

### 3.2 LightMem [3]（coupled，offline 批次，破壞性）
- 同 mem0 的分類與指標，但 snapshot 時點在 offline batch 後。
- 額外一欄：`REWRITE_CORRUPTED` —— payload["memory"] 被 update 改寫後 gt_new 的 value 消失或被改錯（其 update 由 LLM 產生 new_memory 文字，是額外的改寫誤差來源）。歸入 NEW_LOST 計 IRR，但單獨列出以指認機制。

### 3.3 Zep/Graphiti（decoupled，非破壞、檢索層凍結）
- **設計意圖的正確終態**：gt_new edge 存在且 valid（invalid_at 未設）∧ gt_old edge 被 invalidate。
- 終態分類：`CORRECT` / `STALE_VALID`（old 未被 invalidate：漏判衝突）/ `NEW_INVALIDATED`（gt_new 被錯誤設 invalid_at：誤判方向反了）/ `NEW_MISSING`（gt_new edge 根本沒建成：抽取端失敗）。
- **EFR** = 1 − |CORRECT|/|P|。
- **IRR（檢索層）** = (|NEW_INVALIDATED| + |NEW_MISSING|)/|P|。⚠️ **措辭紀律**：Zep 儲存層保留 edge body，所以對 Zep 一律寫「**檢索層**等效不可還原」（預設檢索過濾 invalid edge、且 invalid_at 寫定後不再回看），不可寫「刪除/銷毀」。這個區分要在論文表格附註明講，否則 Zep 可一句反駁。
- 加一個誠實對照：報「若檢索不過濾 invalid 是否可救回」的比例（理論上 NEW_INVALIDATED 可救、NEW_MISSING 不可）——這反而凸顯你的定位：Zep 保留了資料、但其架構在查詢時**不重解**，而重解正是我們的貢獻。

## 4. BJV（盲目密度）

- 分子：write-time 跨筆 LLM 判斷次數。mem0 = 每筆新事實觸發一次 update prompt（有候選時）；LightMem = offline batch 中對每個 target entry 的呼叫數；Zep = 每個新 edge 的 dedup/contradiction 判斷呼叫數。從操作日誌數，沒有日誌就用「觸發條件 × 事實數」估計並標明為估計值。
- 分母：該長度下實際被 100 題 query 觸及的 pair 數（≤100）。
- 解讀句（預先寫好，防被反問「判得多又怎樣」）：**BJV 本身不是罪，BJV × EFR 才是**——每次判斷都是一次帶 EFR 風險的提交，而其中 (BJV−1)/BJV 的判斷服務的是永遠不會被問到的事實。

## 5.（有日誌才做）失因分類

對每個非 CORRECT 的 pair，用日誌回溯第一個錯誤步驟：`檢索候選漏抓`（update prompt 的候選裡根本沒有對應舊事實 → match 無從發生）/ `操作誤判`（候選有、但 LLM 給錯標籤）/ `改寫毀損`（標籤對、rewrite 內容錯）。這張分佈圖直接回答老師的「他們到底在前面哪裡錯」。

## 6. ours 的對照報法

- 終態：恆為全版本保留（IRR ≡ 0、write-time 跨筆判斷 ≡ 0）——一行帶過，不需跑。
- 真正要報：**查詢時解析診斷**（僅對被 query 的 pair）：(i) grouping 正確率——gt_old 與 gt_new 是否被歸入同一 group（structural / P3 分開報）；(ii) resolution 正確率——group 對了之後 argmax 是否選中 gt_new（理論上 ordinal 正確即 100%，若非 100% 代表 ordinal 記錄有 bug）；(iii) 檢索覆蓋——gt_new 是否進 top-K（已有 raw-question recall 數據）。
- 這樣兩邊的表可以並排：baseline 的錯誤落在「終態、不可還原」，ours 的錯誤落在「當次查詢、可重解」。

## 7. 執行順序與產出

1. 先跑 matcher 稽核（30 pair 人工），釘住 matcher 品質。
2. mem0 → LightMem → Zep 依序 dump 終態、算 EFR/IRR/BJV，四個長度各一行。
3. 產出兩張主表：〈表 X：各系統終態診斷（EFR / IRR / BJV × 4 長度）〉、〈表 Y：失因分佈〉；一張對照小表：〈ours 查詢時解析診斷〉。
4. 論文敘事鉤子：表 X 的 IRR 直接接 LightMem §5.6 的自承（「他們自己說會不可逆丟失——這是量出來的比例」）。

## 8. 已知風險與待決事項

- ☐ **Zep 是否自跑**：終態診斷需要本地跑 Graphiti 拿 graph dump；若只用 MAB 公布數字（FC-SH 7%）則 Zep 只能進 QA 對比表、不能進終態診斷表。**需要決定。**
- ☐ mem0 baseline 的 (a)/(b) 兩變體差異是什麼（實作文件未寫明）——影響表格列數與命名。
- ☐ 262k 的全 pair 母體很大，matcher 的 LLM-judge fallback 成本要估；可先在 6k 全跑、長 context 抽樣。
- ☐ LightMem 的 offline batch 觸發時機要固定（全部 ingest 完觸發一次 vs 週期觸發），寫進 setup。
