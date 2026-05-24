# A1a / A1b — Detection F1 v2(統一框架,full raw source)

**Denominator(has_pair)**: 175(labels.json prop-matched)

**Sources**:
- Mem0: 從 `~/.mem0/history.db` 抽完整 UPDATE events(since 2026-05-02T07:00:00)
- Zep: **僅** audit JSON 內存 33 個樣本(20 correct + 7 wrong + 6 FP);**完整 78 events 要重打 Zep API 才能拿**
- 我們: `monitoring_logs/2026-05-17_182907_ablation_B/verdict_events.jsonl`

## Results

| Method | #events | A1a P | A1a R | **A1a F1** | A1b P | A1b R | **A1b F1** | **Gap** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mem0 customized × Gemini | 1124 | 31.9% | 36.0% | **33.8%** | 99.0% | 57.8% | **73.0%** | -39.1% |
| Zep × Gemini (audit-saved partial) | 33 | 30.3% | 8.6% | **13.4%** | 91.2% | 17.2% | **29.0%** | -15.6% |
| 我們 (B = Phase 2) | 253 | 78.3% | 77.7% | **78.0%** | 88.0% | 77.2% | **82.2%** | -4.3% |

## Event-level breakdown(A1a 分類)

| Method | #events | correct(對方向 + 對 GT) | wrong-direction | partial(部分對) | fp_no_pair(flag 到 no_pair hop) | no_match(完全 FP) |
|---|---:|---:|---:|---:|---:|---:|
| Mem0 customized × Gemini | 1124 | 359 | 0 | 221 | 12 | 532 |
| Zep × Gemini (audit-saved partial) | 33 | 10 | 5 | 4 | 3 | 11 |
| 我們 (B = Phase 2) | 253 | 198 | 0 | 2 | 22 | 31 |

## A1b TP/FP/FN/TN(per chain hop)

| Method | TP | FP | FN | TN |
|---|---:|---:|---:|---:|
| Mem0 customized × Gemini | 104 | 1 | 76 | 56 |
| Zep × Gemini (audit-saved partial) | 31 | 3 | 149 | 54 |
| 我們 (B = Phase 2) | 139 | 19 | 41 | 38 |

## Reference — Zep audit 已發表完整數字(non-recomputed)

- Total invalidations: 78
- correct: 65, wrong: 7, fp: 6
- **Published P=83.3%, R=34.6%, F1=48.9%**
- Caveat: 上面 partial 數字嚴重 underestimate(只 33/78 events),真實 Zep A1a F1 ≈ 48.9% 為準
