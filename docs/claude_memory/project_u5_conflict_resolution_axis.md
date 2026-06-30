---
name: project_u5_conflict_resolution_axis
description: 2026-06-12 研究主軸轉向 U5（解耦判斷/執行 + ordinal 的非破壞 update component），FC-SH 6k 已驗 37→80
metadata: 
  node_type: memory
  type: project
  originSessionId: e4d17b27-3f2d-4191-a78d-49b567bd28bb
---

2026-06-12 研究主軸從「resolution 時機 write→query（v1/v2 query-time deferral）」**轉向 U5**：把 mem0 update component 的「判斷」與「執行」**解耦**——LLM 只做六類關係分類（NO_RELATION/DUPLICATE/ENRICHMENT/COEXIST/SUPERSEDE/UNCERTAIN）+ reason，Python deterministic 把類型映射成操作；並注入 **ordinal**（ingestion/chunk 順序）當時序訊號。攻擊的結構病灶 = vanilla `DEFAULT_UPDATE_MEMORY_PROMPT` 的「耦合+不可逆 commit / 無時序 / 強制 commit 無『不確定』」。

**Phase 1（as-built，destructive）**：先不做 soft supersession，SUPERSEDE→物理 DELETE舊+ADD新，重用 vanilla `_create_memory`/`_delete_memory`。在**工作 repo `MemoryAgentBench/`**（非 _original），env gate `MEM0_UPDATE_MODE=u5_classification`，候選池/單一 call/batch 與 vanilla 完全相同（唯一變量=輸出語義+ordinal）。分支點 `mem0/memory/main.py:328`，新 prompt `CONFLICT_CLASSIFICATION_PROMPT`。

**FC-SH 6k 結果（gpt-4o-mini，唯一變量=update component）**：vanilla 37/100 → **U5 80/100**。混淆：救回47/退步4。Stage3/4 鐵證：vanilla 衝突失敗 **98% 是 write-time store 寫壞**，U5 把它降到 17%、**失敗模式翻轉成 83% 是 inference 層 Z**（新版已在庫且檢索到、答題在新舊並存挑錯）→ 瓶頸從寫入層搬到 query-time 消歧（both bucket 29題/52% = 新戰場）。final-store 轉移矩陣：new 零破壞損失（實證 information-preserving）。

**claim 對齊缺口**：#2「ordinal 是 game-changer」尚未隔離（U5=decouple+ordinal 綁一起）→ **待做 ordinal on/off ablation**；且已論證 write-time 的 ordinal 數字鑑別力趨近零（候選恆嚴格更舊、方向由 NEW/EXISTING 框架編碼，已驗證 0 例外）→ **ordinal 真正角色＝持久化時間戳，裁決力在 query-time 兌現**（已登記預測：write-time ablation delta 小）。**vanilla 32k/64k rerun 與 09 漂移（51 vs 62、52 vs 45）→ 一律比自跑 matched baseline**。

**三長度全貌（2026-06-13）**：LCA 86/75/65、vanilla 37/51/52、ours 80/66/53 → **增益 +43/+15/+1 隨長度收斂**。主軸 claim 隨長度更強（vanilla write-time corruption 98/93/81%；old_only 衝突可見比例 85/94/100%；D1 via DELETE ~90-100%），但 64k 增益被兩個 scale 代價吃掉：檢索飽和 R 0→5→12（always-ADD store 變大，SF 還倒退 23→19）+ 累積誤刪 new_only→old_only/neither 0→5→7。→ **Phase 2 從可選變必要：soft supersession 一石二鳥（可逆 + 檢索過濾 superseded 縮小有效 store）+ query-time ordinal 消歧**。

文件：docs/0612_research_method_improve_with_evidence/conflict_resolution_main_design.md（§14-17 為實作+方法論+證據）。分析器：同目錄 scripts/fc_funnel_full.py。延續 [[project_mem0_failure_decomposition]] 的戰場（old_only），但改為主動修復而非僅歸因。
