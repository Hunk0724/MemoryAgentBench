---
name: feedback_cheap_eval_during_validation
description: "驗證階段 evaluation/judge 用便宜模型(gpt-4o-mini),確認 pipeline 後、進論文前才用正式設定(gpt-4o)重跑"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

跑實驗時的成本控管慣例(2026-06-27 確立,LongMemEval KU 情境):**先用便宜模型把所有實驗 pipeline 跑順、確認方法/接線無誤;只有在確認某結果「有必要放進論文」時,才用原本正式(較貴)設定重跑一遍。**

具體:LongMemEval 官方 judge `evaluate_qa.py` 預設 gpt-4o LLM-judge → 驗證期改用 **gpt-4o-mini**(model_zoo 內建支援,傳 `gpt-4o-mini` 即可);paper-final 才切回 **gpt-4o**。生成端(記憶 agent 答題 LLM)本就已是 gpt-4o-mini。`run_lme_ku.sh` 以 `JUDGE_MODEL` env 控制(預設 mini)。

**Why:** judge/eval 對每題都要 LLM call,全矩陣(多方法×多長度×多 benchmark)成本可觀;驗證階段的目標只是確認 pipeline 正確,不需正式模型精度。
**How to apply:** 任何「驗證 pipeline」階段的 evaluation/judge/scoring 都優先用 gpt-4o-mini 等便宜模型;把「用正式設定重跑」當成進論文前的最後一步,別在反覆 iterate 時就燒貴模型。與 [[feedback_confirm_before_execute]]、[[project_ku_taxonomy_battlefield]] 相關。
