# Detection Bucket Recomputation — Changelog (v1 → v2)

> 統一 Mem0/Zep × FC-SH/MH detection bucket 算法。
>
> 日期: 2026-05-07
>
> 主檔: [`aligned_detection_answer_correspondence.json`](aligned_detection_answer_correspondence.json)
> 重生 script: [`../regen_detection_buckets.py`](../regen_detection_buckets.py)
> 舊檔保留 (改名 `_v1_legacy.json`):
> - `analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/detection_answer_correspondence_v1_legacy.json`
> - `analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/mem0_detection_metrics_v1_legacy.json`
> - `analysis/results/diagnostic/zep_detection_metrics_v1_legacy.json`

## 為何要重生 (v1 vs v2 差異來源)

| 改進 | v1 | v2 |
|---|---|---|
| `text_match` 寬嚴 | 各 script 各自實作 (有些更嚴) | 統一 `lower + strip + rstrip puncts + article-stripping (the/a/an) + substring either direction` |
| Mem0 DELETE event | 沒考慮 | 跟 UPDATE 並列計入 detection (實測該時間窗 DELETE = 0,實際數字未受影響但邏輯完整) |
| `no_pair` bucket | SH 上 v1 把 no_has_pair 題目混入 `no_detection` | 獨立成 `no_pair` bucket — SH 100 道中 26 道沒衝突對,跟「has_pair 但沒被偵測到」要區分 |
| Zep SH per-hop 計算 | 17/74 = 23% | 26/74 = 35% (主因: text_match 寬嚴差異) |

## 結果對照

### Per-hop detection coverage (has_pair hops)

| | v1 | v2 | Δ |
|---|:---:|:---:|:---:|
| Mem0 SH | 45/74 = 61% | 46/74 = 62% | +1 hop |
| Mem0 MH | 108/188 = 57% | 111/188 = 59% | +3 hops |
| Zep SH | **17/74 = 23%** | **26/74 = 35%** | **+9 hops** |
| Zep MH | 70/188 = 37% | 71/188 = 38% | +1 hop |

### Per-question all_detected count (n=100)

| | v1 | v2 | Δ |
|---|:---:|:---:|:---:|
| Mem0 SH | 33 | 46 | **+13** (主因: v1 把 26 個 no_pair 混入 all_detected 中) |
| Mem0 MH | 26 | 41 | **+15** |
| Zep SH | 18 | 26 | +8 |
| Zep MH | 8 | 20 | **+12** |

### Per-question 完整 bucket × EM (v2)

| 系統 × split | all_det | partial | no_det | no_pair | overall |
|---|---|---|---|---|---|
| Mem0 SH | 41/46 = 89% | – | 22/28 = 79% | 22/26 = 85% | 85/100 = 85% |
| Mem0 MH | 26/41 = 63% | 11/37 = 30% | 7/22 = 32% | – | 44/100 = 44% |
| Zep SH | 22/26 = 85% | – | 41/48 = 85% | 26/26 = 100% | 89/100 = 89% |
| Zep MH | 8/20 = 40% | 6/35 = 17% | 14/45 = 31% | – | 28/100 = 28% |

> SH 沒有 partial bucket(SH 只有單一 has_pair hop,要嘛偵測到要嘛沒)。
> MH 沒有 no_pair bucket(FC-MH 100 題全部至少有一個 has_pair hop)。

## Mem0 vs Zep detection 機制差異 — 技術細節

### Mem0 (filter-at-write)
- 來源: `~/.mem0/history.db` (sqlite, table `history`)
- 欄位: `old_memory`, `new_memory`, `event` (`ADD`/`UPDATE`/`DELETE`/`NONE`), `created_at`
- Detection 觸發: 對每個 chain_old fact,檢查是否有 event 滿足:
  - `UPDATE`: `text_match(event.old_memory, gt.old_fact_text)` AND `text_match(event.new_memory, gt.gt_fact_text)`
  - `DELETE`: `text_match(event.old_memory, gt.old_fact_text)`
- 時間窗: `created_at >= "2026-05-02T07:00:00"` (對應 aligned ingestion 起始)
- 此次 mem0 events: `ADD: 2356, UPDATE: 1124, DELETE: 0`
- **物理含意**: UPDATE 直接覆寫 vector store entry;DELETE 直接移除 — chain_old 不再出現在 retrieval

### Zep (annotation-at-inference)
- 來源: `analysis/experiments/2026-05-03_writetime_querytime_eval/results/zep_full_retrieval_mh.json` (union of edges retrieved over 100 FC-MH queries)
- 欄位: 每 edge 含 `fact`, `valid_at`, `invalid_at`, `uuid`
- Detection 觸發: 對每個 chain_old fact,檢查是否有 edge 滿足:
  - `text_match(edge.fact, gt.old_fact_text)` AND `edge.invalid_at != None`
- 此次 Zep retrieval 中 unique edges: 349, 其中 67 個有 `invalid_at`
- **物理含意**: Zep 標 `invalid_at` 但 edge 仍在 graph 中 — chain_old 仍可能出現在後續 retrieval,LLM 必須讀時間戳判斷
- **限制**: 我們只看 retrieve 過的 edges,不是 Zep cloud graph 中所有 edges。某些被標 invalid 但從未被 retrieve 的 edges 沒被計入,所以這是 detection coverage 的下界。要拿全 graph 真值需要額外 Zep cloud API call

## 對 narrative 的影響

`motivation_narrative.md` 中所有 detection bucket 數字已對齊 v2 (我先前 in-flight 用了同樣 logic 寫 §4.3 表格)。`A_pipeline_alignment_verification.md` 也用 v2 數字。

舊 v1 數字在 narrative 已不再被引用,但保留 `_v1_legacy.json` 作歷史紀錄,如有需要做 v1 vs v2 對比 (例如說明算法演進) 可參考。
