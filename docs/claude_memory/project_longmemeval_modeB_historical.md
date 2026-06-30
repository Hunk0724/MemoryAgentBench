---
name: project-longmemeval-modeb-historical
description: "LongMemEval KU 揭露 Mode B 失敗模式(題目設計成要歷史/舊值或新舊雙值),freshness 解析丟舊→必錯;keep-all 最強論證,列為未來 case study"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

2026-06-27,ours 在官方 LongMemEval KU(78 題,gpt-4o-mini judge)得 **65/78=83.3%**;分析 13 個錯題揭露重要失敗模式:

**Mode A(≈3-4 題)**:新舊版本同時在解析後 context,inference LLM 挑了舊的(grouping/conflict-type 沒把它們歸成 FRESHNESS 群,如 F-150 vs Mustang 被當不同 model 專案)。→ 指向 grouping 可再強化。

**Mode B(≈7 題,最重要)**:**題目本身設計成要「歷史/舊值」**,但我們 query-time freshness 解析無條件 collapse 成最新 → 必錯。**已用 longmemeval_oracle.json 的 evidence sessions 驗證:非標註錯,benchmark 真的這樣設計。** 兩子類:
- **B1 純舊值**:「previous 5K best」GT 27:45、「Apex 更新前的舊目標」GT 100、「頭三個月幾顆球」GT 15、「earlier 釣魚行」GT 7。
- **B2 複合題(殺手級,答案字面需要舊 AND 新兩版)**:「剛上任帶幾個?現在幾個?」GT「4→5」;「以前多常打網球?現在?」GT「every week→every other week」。

**Why 重要(對論文有利)**:這是 keep-all(保守寫入、保留全版本)的**最強論證**——歷史值/複合題的舊版**只有保守寫入保住了 → 可救**;破壞性 baseline(mem0(b)/vanilla)舊版 write-time 已刪 → **連救的資料都沒有,再強 resolver 也無解**。修法=把 resolver 升級為 query-aware(偵測 previous/first/both 意圖就不 collapse)。

**How to apply**:**現在只記錄、不實作解法**(使用者明確指示)。未來作為 case study + baseline 對照(ours 可救 vs baseline 資料已失)。扣合 [[project_ku_taxonomy_battlefield]] 的「keep-all 必要因要答 temporal」與 [[project_phase0_structural_result]]。檔案:experiment_results.md §2.1;ours 答案在 outputs/rag_retrieved/...longmemeval_s_ku_s*n4/。
