---
name: project_gemini3_thinking_determinism
description: "gemini-3.1-flash-lite 無法完全關 thinking,thinking_budget=0 對 G3 無效;0603 實驗的 mem0 答題路徑曾以預設 High thinking 在跑"
metadata: 
  node_type: memory
  type: project
  originSessionId: a277aac2-fee2-4880-847c-cfaeb30f8fee
---

`gemini-3.1-flash-lite`(Gemini 3.x)**無法完全關閉 thinking**。官方:「Gemini 3 Flash/Flash-Lite do not support full thinking-off」。

- `thinking_budget` 是 **Gemini 2.5** 參數,**不適用 G3**;G3 用 `thinking_level`(minimal/low/medium/high)。最低 `minimal` ≈ no-thinking 但**不保證**真的關。
- 同時送 `thinking_budget` + `thinking_level` → 400;都不設 → 預設 **High**。
- 即使 minimal + temperature=0,Gemini 託管 API 仍**非 bit-deterministic**(MoE/batching/浮點)。真 determinism 達不到,minimal 是上限。
- SDK `google-genai 1.75.0` 的 `ThinkingConfig` 已支援 `thinking_level="minimal"`(實測 OK)。

**MABench code 問題(2026-06-03 發現)**:
1. [agent.py:718] 與 [methods/mem0_vertex_gemini_llm.py:92] 用 `thinking_budget=0` → 在 G3 上很可能被忽略,實際以 High thinking 跑。
2. **最嚴重**:[agent.py:520-523] `_answer_with_client` 完全沒設 thinking_config,而它是 [agent.py:961] mem0 最終 FC 答題的路徑 → 0603 的 FC 答案是在**預設 High thinking** 下生成。
修法:全路徑統一 `ThinkingConfig(thinking_level="minimal")`(取代 budget=0,勿並存)。

**⚠️ 2026-06-05 controlled re-trial 修正「空輸出=thinking 隨機」的舊解釋**:精準重放 32k FC-SH 空輸出題(qid7/33/51)的 stored prompt → **同設定 `max_output_tokens=10` 下確定性空(3/3 trial,finish=MAX_TOKENS,thoughts_token_count=0)**;放大到 2048 → **三題全答出完全正確答案**(STOP)。→ 空輸出主因是 **benchmark `generation_max_length=10`(=self.max_tokens)對此模型太小**,長答案(≥~5-6 token)回空,**非 thinking 非確定性**(thought_tok=0、且確定性,不是偶發)。所以單 trial 空輸出**不是 EM 雜訊式的隨機,而是可預測的截斷**;真實 EM 天花板被低估(32k SH 90→93%)。thinking_level 仍應改 minimal(其他理由),但**空輸出該歸因 max_tokens,不是 thinking**。腳本 `docs/0603_current_research_main_evidence/scripts/retrial_empty_outputs.py`。

**Why**: 0603 既有實驗結果可能受 thinking 污染、且非 deterministic,reproduce/重跑前須修正;但**空輸出的具體歸因已從 thinking 改為 max_tokens=10 截斷**(controlled 實驗坐實)。
**How to apply**: 改 thinking_level=minimal(架構理由);**空輸出要靠調大 generation_max_length 修**,非調 thinking。disclose 時說明 minimal≠完全關。關聯 [[feedback_research_rigor_pipeline_alignment]]、[[project_mem0_failure_decomposition]]。
