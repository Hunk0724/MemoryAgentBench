# Pre-Plan-A Iteration History — 2026-05-28 ~ 2026-05-30

> **目的**:收容 RESULTS_MASTER.md refactor 時搬出的歷史內容。
> 留作後來想還原「為什麼做這些決定」的 audit trail。
> Plan A 鎖定後此檔內容**不再更新**;新進度全部寫進 [RESULTS_MASTER.md](../../RESULTS_MASTER.md)。

---

## 1. Temperature 決策過程(2026-05-29 → 30)

### 1.1 混雜狀態(Plan A 鎖定前)

| 跑過的設定 | 在哪幾個 run |
|---|---|
| `temp=0` top + `0.1` internal | LCA 早期 + 舊 mem0(50% MH 6k)+ 舊 mem0g-as-is(deprecated)|
| `temp=0.7` top + `0.7` internal | Mem0 temp07 × 3 trials、Mem0g-prompt-aware × 2(2026-05-29 night)|

### 1.2 Plot:temp=0.7 variance 過大證據

| Setting × Task | EM | Variance |
|---|---:|---:|
| Mem0 × SH 6k × temp=0.7 × 3 trials | 80.7% | ± 1.5%(穩定)|
| **Mem0 × MH 6k × temp=0.7 × 3 trials** | 52.5% | **± 16.3%**(42 / 64 / 70,極不穩)|
| Mem0 × MH 6k × temp=0/0.1 × 1 trial | 50.0% | — |

→ MH 上 temp=0.7 三 trials 跨 28pp,paper main result 無法用。

### 1.3 最終決定:Plan A 全部 temp=0(top + mem0 internal)

**理由**:
- Reproducibility 優先(deterministic)
- 1 trial 足夠,no 3x multiplier 成本
- LCA SH/MH 6k temp=0 與 temp=0.7 數字一樣(96/16)→ confirm LCA temp-insensitive,no penalty
- Paper appendix disclose 一段 cover

**Plan A 對 Mem0 SH 6k 的影響**:80.7%(temp=0.7)→ 92%(temp=0)= **+11pp**(LLM 不亂選)。確認 deterministic 顯著更好。

---

## 2. Pre-Plan-A cells(混合 temp,已過時)

| Method | Task | Ctx | Top | Internal | EM | 命運 |
|---|---|---:|---:|---:|---:|---|
| LCA × 6 cells | SH/MH/64k/262k | various | **0.7** | n/a | 96/91/16/16/12/4 | 6k/32k 已被 Plan A temp=0 取代;64k/262k temp=0 跑中 / 待跑 |
| Mem0 | MH | 6k | 0 | 0.1 | 50% | Plan A 重跑為 52%(差 2pp)|
| Mem0 | SH | 6k | 0.7 | 0.7 | 80.7 ± 1.5% | Plan A 重跑為 92%(+11pp from temp 影響)|
| Mem0 | MH | 6k | 0.7 | 0.7 | 52.5 ± 16.3% | Plan A 重跑為 52%(mean 接近,variance 解決) |
| Mem0g-pa | SH | 6k | 0.7 | 0.7 | 65% | Plan A 重跑為 79%(+14pp from temp)|
| Mem0g-pa | MH | 6k | 0.7 | 0.7 | 55% | Plan A 重跑為 66%(+11pp from temp)|

### Settings 混雜清單(歷史)

| Setting | 誰用過 |
|---|---|
| top=0 / internal=0.1 | Mem0(舊 MH 6k 50%)、Mem0g-as-is(deprecated)|
| top=0.7 / internal=0.7 | Mem0 × 3 trials、Mem0g-pa × 2 |

→ Plan A 全部統一 top=0 + internal=0 後,所有 confound 解開。

---

## 3. Deprecated runs 歷史

| Run | 為什麼 deprecated | 處理 |
|---|---|---|
| Mem0g(MABench-as-is)× ALL cells | F1 finding:wrapper agent.py:899 沒把 graph 進 prompt,所有 mem0g-as-is 結果不代表 graph 評估 | mv `outputs/_deprecated/mem0g_as_is_temp0p1_2026-05-29/` |
| Mem0g(as-is)SH 6k 71% / MH 6k 41% / MH 32k 32% | 同上 | 移除 |
| Mem0 × {SH 6k, SH 32k, MH 32k} × temp=0/0.1 (≦ 2026-05-29) | SQLite 並行衝突,update silent fail | Plan A 重跑取代 |
| Mem0 chunk4096 | chunk=4096 + Gemini → meta-summarize bug | mv `outputs/_deprecated/mem0_chunk4096_meta_summarize_bug/` |
| HippoRAG-v2 × preview backbone | preview ≠ GA,改 backbone 後不能直接比 | mv `outputs/hippo_rag_v2_nv_preview_REFERENCE/`(reference,不是 deprecated)|
| Mem0 trial1 MH 6k ingestion(24 chunks)| launcher 沒 wipe rag_retrieved,contaminated | EM ok(qdrant 乾淨),mechanism 不用 |

---

## 4. Pre-Plan-A finding 演進(rolling drafts)

### 4.1 2026-05-29 evening — 第一版 mechanism finding(temp=0/0.1 + as-is)

當時數字:
- Mem0g-as-is MH 6k 41%(deprecated 因 F1)
- precision 0.95 / recall 0.50 / UPDATE-content 100%
- P(A\|R=1)=76% vs P(A\|R=0)=2% → R dominant

寫進 [2026-05-29_mechanism_findings.md](2026-05-29_mechanism_findings.md)(已存在)。

### 4.2 2026-05-29 night — Mem0g-pa MH 6k 第一次(temp=0.7)

當時數字:55% EM(超過 Mem0 temp=0.7 mean 52.5%),detection recall 0.76(↑ from as-is 0.50 — 推測 temp 0.1→0.7 影響 UPDATE 積極度)。

寫進 [CRITICAL_FINDINGS_2026-05-29_evening.md](../../baseline_methods/CRITICAL_FINDINGS_2026-05-29_evening.md)。

### 4.3 2026-05-30 — Plan A 最終版

進 [RESULTS_MASTER.md](../../RESULTS_MASTER.md)。

---

## 5. Pre-Plan-A "下一步建議行動" options(已執行 A,C,D,F)

| 選 | 描述 | Plan A 狀態 |
|---|---|---|
| A. 鎖定 temperature | 全部 temp=0 | ✅ 已執行 |
| B. 清理 deprecated | mv `outputs/_deprecated/` | ✅ 已執行 |
| C. Mem0 × 6k/32k/64k 序列 | serial,1 trial | ✅ 6k/32k 完;64k 跑中 |
| D. Mem0g-pa 補完 + 跑 6k/32k | 接續 Plan A | ✅ 已執行 6k/32k |
| E. HippoRAG-v2 + PropRAG GA 重跑 | 對齊 backbone | ⏸ 暫停(no GPU + user 指示用 historical reference)|
| F. 跑完每 cell 做 align + D + 3way | mechanism analysis | ✅ 已執行 6k+32k 8 cells |

---

## 6. Settings audit 過程(LCA 校正 incident)

2026-05-30 從 LCA result file 讀回 `agent_config` 發現:
- 我之前 master 寫的 "LCA temp=0" 是錯的
- 實際 LCA 跑時是 `temperature: 0.7`(matched benchmark default)
- 校正 master 表

→ 教訓:**任何「方法 × cell × 設定」記錄都從 result file 的 `agent_config` 讀回 ground-truth**,不從手寫表猜。

---

## 7. Launcher bugs(已修)

### 7.1 set -e leak(2026-05-30)

`run_plan_a_serial.sh` 在 function 內 `set +e` wrap python 然後 `set -e`,結果 -e 全域 leak,HippoRAG SH fail 後整批 abort。

**修法**:不在 function 內 toggle set -e;script-level 全程不開 set -e。

### 7.2 NV-Embed-v2 + transformers 5.x compat

`'NVEmbedModel' object has no attribute 'all_tied_weights_keys'` — newer transformers 預期該屬性。Monkey-patch 加進 `methods/hipporag/embedding_model/NVEmbedV2.py` 開頭:

```python
from transformers.modeling_utils import PreTrainedModel as _PTM
if not hasattr(_PTM, "all_tied_weights_keys"):
    _PTM.all_tied_weights_keys = {}
```

→ 但底層仍卡在 torch CPU only(2.9.1+cpu)+ NV-Embed-v2 需 GPU → HippoRAG-v2 仍跑不動,改用 historical preview pilot 作 reference。

### 7.3 rag_retrieved ingestion log 沒被 wipe(temp07 trial1 24 chunks 污染)

`run_mem0_temp07_3trials.sh` wipe_state 只 wipe qdrant + sqlite,沒 wipe ingestion_context_0.jsonl,導致 trial1 inherit 12 chunks。

**修法**:[Plan A launcher](../../../bash_files/sh/run_plan_a_serial.sh) `wipe_rag_retrieved` helper 一併 rm。

---

**End of 2026-05-30_pre_plan_a_iteration_history.md**
