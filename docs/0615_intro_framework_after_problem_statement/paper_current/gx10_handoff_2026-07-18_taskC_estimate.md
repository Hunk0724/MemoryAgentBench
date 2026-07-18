# GX10 Handoff — Task C 執行估算(2026-07-18)

> 回應 [`gx10_guard_ablation_report_2026-07-18.md`](gx10_guard_ablation_report_2026-07-18.md) 的 Task C pending 狀態。**現況**:Mac 側已依 GX10 的 predictor 結果採 Option B(keep guard on),paper 章節已補上 backbone-adaptive story + 兩張 table(actual gpt-4o-mini 4L + predictor 8 backbones)。**Task C 目前定位為「rigor 加強」(高信度 cell 於實測上 confirm 方向),非 blocking。**

---

## 情況同步

Mac 側 2026-07-18 已完成:

1. Cross-verify GX10 predictor(8/8 backbone 全 match) ✓
2. **採 Option B**:paper `paper_experiment.md` 加 §Subject-Consistency Guard: A Backbone-Adaptive Safeguard(sec:ablation 底部)。內含兩張 table 與三段論觀察,呈現 guard 於 strong / mid / weak-cross-family 三 tier 上的分佈與淨效應。
3. `paper_methodology.md` §Structural Matching and LLM Fallback 於 subject-consistency 段落補一句 forward-reference 至 experiment 章的 ablation 節。
4. 主表(gpt-4o-mini 4 length overall sEM + backbone spectrum)數字**未動**,canonical 保持不變。
5. 未跑 Task C。

---

## Mac 側請 GX10 回答的問題(先估算,不必開跑)

### 問題 1:**Task C 若跑,具體會做哪些 cell?**

Mac 建議:**只跑 predictor Δ ≤ −3 的最負 3 cells**,confirm 方向:
- `mistral-7b @ 6k`(predictor −5,高信度)
- `gemma3-27b @ 6k`(predictor −4,mid 信度)
- `qwen2.5-7b @ 6k`(predictor −3,mid 信度)

**理由**:predictor 於 gpt-4o-mini 4 length 上驗證方向 3/4 對、magnitude ±3pp;若這 3 cells 實測方向亦一致(Δ ≤ −1),則 predictor 於 weak/cross-family 上的信心可延伸到其他 5 cells。反之若任一 cell 方向反轉(Δ > 0),則需擴大實測範圍。

若 GX10 認為應該包含其他 cells(例如低信度但小樣本的 gemma3-4b +2、gemma2-9b +1),請一併說明理由。

### 問題 2:**Wall time 估算**

每 cell 需執行:
- **前提**:reuse `ours_no_p5` 的 populated qdrant store + P1/P2/subject/grouping 全 cache(GX10 於 Task A 已確認 gemma tier + cross-family 皆有 grouping_cache_no_p5_6k.json,cache 已完備)
- **實際只需跑 query pipeline**:100 query × answer LLM
- **New method mode**:`ours_no_p5_guard_off`(scripts 已 Mac 側 push,見 `run_fc_sh.sh` line 152-179)

**執行命令**(single cell 示範,以 mistral-7b 為例):
```bash
MODEL_TAG=mistral-7b MEM0_TRIPLE_MODEL=mistral:7b \
  RUN_OAI_KEY_NAME=OPENAI_API_KEY_A \
  bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours_no_p5_guard_off
```

請 GX10 回答:
- **每個 cell 於 GX10 上估算 wall time?**(考慮 answer LLM 為 local model 走 Ollama,100 query × ~2k tokens context;Mac 上 gpt-4o-mini 4 length 平均 2-3 min/cell,GX10 上 local model 可能 5-15 min?)
- **3 個 cell parallel(3 keys 分別跑)vs 序列跑?** 是否受 Ollama 只能 load 1 model at a time 的限制影響?

### 問題 3:**RAM 估算**

GX10 於既有的 `gx10_backbone_gotchas.md` 或 `gx10_run_log.csv` 應有這些 model 的 peak-sys memory 記錄。請確認:
- **mistral-7B (Ollama)**:peak-VRAM + peak-system RAM 各是多少?
- **gemma3-27B (Ollama)**:peak-VRAM + peak-system RAM 各是多少?
- **qwen2.5-7B (Ollama)**:peak-VRAM + peak-system RAM 各是多少?
- **是否需要串行執行**(每次只 load 一個 model)?

Mac 從記憶中認為 gemma3-27B 於 GX10 上是 21.1 GB VRAM + 31 GB peak-sys(見 `gx10_run_log.csv` size_vram / peak-sys 欄),請 confirm。

### 問題 4:**Cost 估算**

- P1 fact extraction:cache hit,無 API cost
- P2 triple extraction:cache hit,無 API cost
- Subject fallback (P2b):cache hit,無 API cost
- Retrieval embedding:每 query 一次 embedding,若 embedder = text-embedding-3-small(GX10 用 OpenAI embedder)則 100 query × ~200 tokens 平均 = ~20k tokens ≈ $0.0004/cell
- LLM identity clustering (P3):cache hit(GX10 已 Task B commit 上來),**理論上無需重新呼叫 P3 LLM**
- Answer LLM:100 query × local model → **無 OpenAI cost**(全 local Ollama)

**預估總 OpenAI cost**:3 cells × $0.0004 ≈ **$0.002**(基本免費;embedder 端唯一開銷)

Mac 建議:GX10 若能 confirm 上述 cost model,則 Task C 幾乎零 API 成本,主要開銷是 GX10 hardware wall time。

---

## Mac 側等 GX10 回覆的三個 blocking answer

1. **具體 cell 集(3 or 4 or 全 8)**
2. **wall time per cell + parallel 可行性**
3. **Peak-VRAM + Peak-sys RAM per model**

GX10 回覆後 Mac 側評估:
- 若 wall ≤ 1 hr + RAM < 32 GB → **approve Task C 於最負 3 cells**
- 若 wall > 3 hr 或 RAM 逼近 GX10 hardware 上限 → **保留 predictor 為 canonical evidence,Task C defer 至 future work**

---

## 感謝 & 補充

GX10 於 Task A + B 交出的:
- **1 份 report md**(判讀清楚、決策矩陣正確)
- **26 個 cache JSON files**(force-add 過 gitignore,~788K,Mac 已可離線複算)
- **predictor 值 8/8 全 match Mac 側**

是 canonical rigor 標杆。Task C 為進一步 confirm 高信度 cell 的實測數字,decoration for paper;若 GX10 有其他優先(如 gpt-5.4-mini 6k 補 32/64/262k,或 LME cross-backbone),請告知,Mac 這邊也會依 paper timeline 排序。

---

## 更新紀錄

- **2026-07-18**:建檔;回應 GX10 Task C pending 狀態;請 GX10 先估 cost/wall/RAM,Mac 依此決定是否 approve。
