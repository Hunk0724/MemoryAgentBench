# LCA model 選擇 — FC-MH 6k 5-model 對比

> 日期:2026-05-29
> 目的:用 LCA(long-context agent)在 FC-MH 6k 上跑 5 個 Gemini model,選一個作為 mem0/mem0g 後續實驗的 backbone。

---

## 結果表

| Model | EM | F1 | rougeL | sEM | avg_input | avg_output | wall (s) | 備註 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash-lite | 4.0% | 5.0% | 5.4% | 4.0% | 7429 | 2.4 | 89 | 弱 |
| gemini-2.5-flash | 1.0% | 2.2% | 2.6% | 1.0% | 7429 | 2.4 | **1313** | 弱且慢 ~14× |
| **gemini-3.1-flash-lite (GA)** | **16.0%** | **17.2%** | **17.2%** | **16.0%** | 7429 | 2.6 | 112 | **🏆 backbone** |
| gemini-3.1-flash-lite-preview | 16.0% | 17.2% | 17.2% | 16.0% | 7429 | 2.6 | 132 | 原 reference,2026-07-09 sunset |
| gemini-3.5-flash | 1.0% | 2.2% | 2.6% | 1.0% | 7429 | 2.4 | 117 | 意外低 |

> Wall time 是 100 題完整跑完。輸入 ~7.4k token、輸出 ~2-3 token(short answer 設定)。

---

## 核心發現

### 1. 3.1-flash-lite (GA) ≈ preview(可作 backbone)

- **Aggregate metric 完全一致**:EM/F1/rougeL/sEM 四個指標小數點都對上(16.0% / 17.2% / 17.2% / 16.0%)
- **但 per-query output 並非完全相同**:80/100 題 output 字串完全相同,20/100 不同
- 結論:GA 是 preview 的 production 版本,行為非常接近但不是 identical
- ✅ **可以 confidence 用 GA 取代 preview 作為長期 backbone**

### 2. 其他 3 個 SOTA Gemini 都顯著差

- `2.5-flash-lite` 4%、`2.5-flash` 1%、`3.5-flash` 1%
- `2.5-flash` 跑 22 分鐘(其他 ~2 min)— 疑似 thinking/reasoning 模式被觸發,大量 reasoning token
- `3.5-flash` 表現差是意外的(理論上應該更強),可能:
  - prompt 對 3.5 不適配(FC-MH 用編號 fact 格式可能不對其 tokenizer)
  - model 在數字 / fact reasoning 上特化方向不同
  - generation_max_length=10 限制下無法展開思考(但 3.5-flash-lite-preview 同樣 10 token 卻能 16%)

### 3. Input 大小一致 → 對比公平

`avg_input=7429 tokens` 跨 5 個 model 完全相同(因為 LCA 就是塞整段 context,不切 chunk),所以差距純粹來自 model 本身。

---

## 對 mem0/mem0g 後續實驗的 backbone 決策

### Backbone 選 `gemini-3.1-flash-lite` (GA)

理由:
1. **跟 paper 既有 reference (preview) 行為對齊** — 16% EM 完全相同
2. **長期穩定**(GA 不會 sunset,preview 2026-07-09 EOL)
3. **比 preview 略快**(112s vs 132s 跑 100 題)
4. **避免主表結果依賴 deprecated model**

### 是否還需要跑其他 4 個 model?

**Spec §9 Stage 0a 要 4 readers 矩陣** ([FC_metrics_spec.md](../../sync_with_claude_chat/FC_metrics_spec.md))。但這次 LCA 結果顯示:

| Use case | 是否要跑 |
|---|---|
| 主結果 backbone | **gemini-3.1-flash-lite (GA) 一個** ✅ |
| Cross-model 穩定性 verification | 可選,但 3.5 / 2.5-flash 在 LCA 上太差,可能也壓 mem0/mem0g |
| 「為什麼選 backbone」justification | 已有此份 LCA 對比文件 ✅ |
| preview 對齊歷史 reference | 已跑 ✅ |

**建議**:
- **mem0/mem0g 主跑 `gemini-3.1-flash-lite` (GA) + `gemini-3.1-flash-lite-preview`**(2 model)
- 其他 3 個 model 視 cost 跟時間決定;若 mem0/mem0g 在 backbone 上 LCA EM 16% 都打不過,跑其他 model 的意義不大

---

## 跟 3.1-flash-lite-preview 既有 reference 對齊

| 指標 | preview | GA | delta |
|---|---:|---:|---:|
| EM | 16.0% | 16.0% | 0.0pp |
| F1 | 17.2% | 17.2% | 0.0pp |
| rougeL | 17.2% | 17.2% | 0.0pp |
| sEM | 16.0% | 16.0% | 0.0pp |
| Per-query output match | 80/100 字串相同 | — | — |
| Wall (100q) | 132s | 112s | -15% |

→ **可以放心用 GA 接續所有之前用 preview 跑的實驗,paper 結果無需改 reference**。

---

## 後續步驟

1. 跑 `mem0 × gemini-3.1-flash-lite × FC-MH 6k × chunk=512` 做為 mem0 baseline
2. 跑 `mem0g × gemini-3.1-flash-lite × FC-MH 6k × chunk=512`(啟 Neo4j → 跑完 → 關 Neo4j)
3. 寫 compute_m_core.py / compute_m_detection.py 算 hop-level CLEAN/LEAK/MISS,跟 [FC_metrics_spec.md §3-§4](../../sync_with_claude_chat/FC_metrics_spec.md) 對齊
4. 視結果決定是否擴 model 矩陣

---

## 相關位置

- 5 個 results JSON:[outputs/gemini-*/Conflict_Resolution/factconsolidation_mh_6k_*.json](../../../outputs/)
- LCA yaml(5 個):[configs/agent_conf/Long_Context_Agents/Long_context_agent_gemini-*.yaml](../../../configs/agent_conf/Long_Context_Agents/)
- 跑時 log:`logs/lca_*_mh_6k.log`
- Metrics spec:[[../../sync_with_claude_chat/FC_metrics_spec.md]]
- Pilot plan:[[mem0_mem0g_pilot_plan.md]]
