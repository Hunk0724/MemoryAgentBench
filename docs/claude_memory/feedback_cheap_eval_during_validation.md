---
name: feedback_cheap_eval_during_validation
description: "LongMemEval 的 LLM judge 驗證期用 gpt-4o-mini 省成本;最終是否回官方 gpt-4o judge 未定(非既定計畫)。FC-SH 是 exact_match 無 judge,不適用。別跟系統 backbone 混淆——backbone 的 model sweep 方向往「更小」(weak-model)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

跑實驗時的成本控管慣例(2026-06-27 確立,2026-06-30 釐清適用範圍):**驗證 pipeline 階段,凡需 LLM 評分的地方先用便宜模型把實驗跑順、確認方法/接線無誤;是否用較貴的正式設定重跑,當成「進論文前再決定」的選項,別在反覆 iterate 時就燒貴模型。**

**這條只適用 LongMemEval。** LongMemEval 的 QA 用 **LLM judge** 評分(官方 `evaluate_qa.py` 預設 **gpt-4o**)→ 驗證期為省成本改用 **gpt-4o-mini**(`run_lme_ku.sh` 以 `JUDGE_MODEL` env 控制,預設 mini);**最終 paper 是否切回 gpt-4o judge 未定**(待成本/精度權衡,非既定計畫)。**FC-SH 不適用**:它用 `exact_match`(drqa normalize + 字串 ==),**沒有 LLM judge**。

⚠ **別把兩個 model 軸混為一談**:
- **judge model**(上面講的,只有 LongMemEval 有):gpt-4o-mini → 可能回 gpt-4o(未定)。
- **系統 backbone / inference model**(跑 extraction / grouping / conflict-type / 答題的 LLM):目前 gpt-4o-mini,但 **model sweep 方向是往「更小」**(優先測比 gpt-4o-mini 更小的 weak-model,如 Gemma-3-4B),用來扣 intro narrative(ours 平緩、prior work drop),**不是往 gpt-4o**。

**Why:** judge 對每題都要 LLM call,全矩陣(多方法×多長度)成本可觀;驗證階段只需確認 pipeline 正確,不需正式 judge 精度。
**How to apply:** 驗證階段的 LLM judge/scoring 優先用便宜模型;「是否用官方 gpt-4o judge 重跑」是進論文前再決定的選項、非預設。系統 backbone 的 model 選擇是另一回事(走 weak-model sweep,見 [[project_research_positioning]] 的 narrative)。與 [[feedback_confirm_before_execute]]、[[project_ku_taxonomy_battlefield]] 相關。
