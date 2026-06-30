# B1 — Vanilla HippoRAG-v2 Retrieval Recall on FC-MH 100Q

**Data source**: ablation B's `passages_pre_filter_chunk_ids` (= ablation A retrieval, since Phase 2 filter runs on top of identical PPR retrieval; hyperedge adds 0 edges).

Matched queries: **100/100** (unmatched: 0)

## Overall — per-hop / per-query

| Metric | K=5 (LLM-visible) | K=10 (full retrieval) |
|---|---|---|
| **B1a** New-version Recall(per-hop)         | 177/237 (74.7%) | 223/237 (94.1%) |
| **B1b** Old-version Retrieval Rate(per-hop) | 130/177 (73.4%) | 167/177 (94.4%) |
| **B1c** Multi-hop Path Recall(per-query,所有 hop 都 hit) | 55/100 (55.0%) | 89/100 (89.0%) |

## By hop count — K=5

| Hop | B1a New-Recall | B1b Old-Rate | B1c Path-Recall |
|---|---|---|---|
| 2-hop | 94/115 (81.7%) | 72/90 (80.0%) | 43/61 (70.5%) |
| 3-hop | 47/69 (68.1%) | 34/51 (66.7%) | 8/24 (33.3%) |
| 4-hop | 36/53 (67.9%) | 24/36 (66.7%) | 4/15 (26.7%) |

## By hop count — K=10

| Hop | B1a New-Recall | B1b Old-Rate | B1c Path-Recall |
|---|---|---|---|
| 2-hop | 110/115 (95.7%) | 86/90 (95.6%) | 57/61 (93.4%) |
| 3-hop | 64/69 (92.8%) | 48/51 (94.1%) | 21/24 (87.5%) |
| 4-hop | 49/53 (92.5%) | 33/36 (91.7%) | 11/15 (73.3%) |

## By conflict_type (B1a only) — K=10

| conflict_type | new-recall |
|---|---|
| has_pair | 166/180 (92.2%) |
| no_conflict_pair | 57/57 (100.0%) |

## Reading the gap

- 在 K=5 LLM-visible window:**找到 new = 74.7%,同時也撈到 old = 73.4%** → 兩者並存 = 髒 context
- 在 K=10:new = 94.1%, old = 94.4% —— B1b 高就是「沒衝突機制」的代價
- **B1c(完整 path 都 hit)只有 K=5 55.0% / K=10 89.0%** → 多跳 retrieval 完整性問題
