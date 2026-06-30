---
name: feedback_confirm_before_execute
description: "跑測試/執行前先把設計講清楚、等使用者確認再動手,別自行開跑"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

研究討論階段,**在跑任何測試/執行(實驗、benchmark、驗證腳本)之前,先把設計/方法的改動講清楚,等使用者確認後再動手**,不要自己直接開跑。

**Why:** 使用者要先理解「我們從哪裡、怎麼一步步改的」(例如從 mem0 native FACT_RETRIEVAL_PROMPT 如何演進到統一抽取器),掌握設計脈絡與決策權,而非看到一堆已執行的結果。自行開跑會讓他失去在關鍵設計點介入的機會。

**How to apply:** 提出改動 → 用 diff/表格說明每處改動 + 理由 → 標出待確認的決策點 → 等確認 → 才執行。背景已開跑的測試,在確認前不要拿它的結果繼續往下推。延續[[feedback_research_rigor_pipeline_alignment]]的嚴謹要求。相關設計脈絡見[[project_ku_taxonomy_battlefield]]。
