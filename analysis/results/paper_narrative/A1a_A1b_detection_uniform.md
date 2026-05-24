# A1a / A1b — Detection F1(統一框架)

**denominator**: has_pair hops with prop-matches = **175**(labels.json)

**A1a**(event-level): 所有 invalidation events 為單位;Precision = 正向 correct events / 總 events;Recall = unique GT pairs caught / has_pair 總數

**A1b**(per-query, per-chain-hop): 對每 query 的每 chain hop, 看方法有沒有 flag 該 hop(無論方向);TP=flag 到 has_pair hop, FN=漏掉的 has_pair hop, FP=flag 到 no_pair hop

## Results

| Method | #events | A1a P | A1a R | **A1a F1** | A1b P | A1b R | **A1b F1** | **Gap (A1a−A1b)** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mem0 customized × Gemini | 40 | 30.0% | 6.9% | **11.2%** | 100.0% | 10.6% | **19.2%** | -8.1% |
| Zep × Gemini | 33 | 30.3% | 8.6% | **13.4%** | 100.0% | 11.7% | **21.0%** | -7.6% |
| 我們 (B = Phase 2) | 253 | 78.3% | 77.7% | **78.0%** | 100.0% | 72.3% | **84.0%** | -6.0% |

## Event breakdown (A1a 內部分類)

| Method | #events | correct(對方向 + 對 GT pair) | wrong-direction | partial(只對 old 文字) | no-match(完全 FP) |
|---|---:|---:|---:|---:|---:|
| Mem0 customized × Gemini | 40 | 12 | 0 | 8 | 20 |
| Zep × Gemini | 33 | 10 | 0 | 3 | 20 |
| 我們 (B = Phase 2) | 253 | 198 | 0 | 0 | 55 |

## A1b TP/FP/FN

| Method | TP | FP | FN |
|---|---:|---:|---:|
| Mem0 customized × Gemini | 20 | 0 | 168 |
| Zep × Gemini | 22 | 0 | 166 |
| 我們 (B = Phase 2) | 136 | 0 | 52 |
