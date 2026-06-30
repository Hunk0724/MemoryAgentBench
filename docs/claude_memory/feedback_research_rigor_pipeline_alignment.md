---
name: 跨系統評估前必須先驗證 pipeline 對齊
description: 評估 production memory systems (Mem0/Zep) 時必先確認 query/inference pipeline 與該 benchmark 的 default 設定完全對齊,否則所得數字無意義
type: feedback
originSessionId: 9497e54a-867f-494f-ab3b-39eed4cb75dc
---
跑 production system (Mem0/Zep/HippoRAG-v2 等) 之前,必須先逐項驗證 evaluation pipeline 與 benchmark default (e.g. MABench `utils/templates.py` 中的 query template + agent_name normalization) 完全對齊。

**Why**: 在 FC-MH 研究中,我們以 bare `q["question"]` 跑 Mem0/Zep,實際上 MABench default 對所有 `rag` substring 的 agent_name (包括 `Structure_rag_mem0` / `Structure_rag_zep`) 都套 FC seq rule wrapper。這個 deviation 讓 Zep MH 數字差 -20pp (8% bare vs 28% aligned),完全改變失敗模式分析 (pulled-by-old 從 82% → 28%)。User 稱這是「論文研究大忌」,因為它讓我們花時間建構的 narrative 在數字基礎上錯位,需要重新審視所有主張。

**How to apply**:
1. 跑任何 baseline 之前先讀 benchmark 的 query template + agent_name normalize 邏輯,確認自己呼叫該系統的方式跟 MABench main pipeline 一致
2. 對於跨系統比較,**只報告 aligned 數字**,bare 結果如有也只當 internal sanity check,不放進論文表格
3. 任何發現自己 deviation 後,必須回頭重審所有受影響的 framing/claim,而不是僅換數字
4. 寫實驗腳本時 system prompt / wrapper / temperature / max_tokens 都要顯式對齊 benchmark default
