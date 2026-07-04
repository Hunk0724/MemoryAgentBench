# return_context × Acc cross-tab — GX10 weak-model (gemma3), FC-SH 6k has_pair

> **matcher v4** (`analysis.compute_m1_m2_m3.match_pair`, aligned to Mac canonical, 2026-07-05). **Caveat**: gemma runs have no per-qid dir, so pool state is from an OFFLINE re-run (qdrant + re-embed + re-retrieval) and EM is read from the aggregated `exact_match` (not MAB `default_post_process` max(raw,parsed)) — see `../matcher_specification.md §3.2`. Fixed once per-qid save lands (handoff Task B).

> Pool state = version-state of the resolved context sent to the answer LLM. Acc = has_pair exact-match. N=74. Reading: `new_only→✓` = method isolated NEW and reader used it; `both→✓` = reader picked NEW from a mixed pool (method did not isolate, reader rescued); `new_only→✗` = reader override on a clean pool; `old_only/neither→✗` = new version absent from pool (extraction/write loss).

## ours_struct

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 1b | 21/11 | 7/18 | 0/13 | 1/3 | 29/74 |
| 4b | 39/1 | 15/9 | 0/7 | 0/3 | 54/74 |
| 12b | 60/0 | 13/1 | 0/0 | 0/0 | 73/74 |
| 27b | 53/7 | 12/2 | 0/0 | 0/0 | 65/74 |

## ours_no_p5

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 1b | 20/12 | 5/20 | 0/13 | 0/4 | 25/74 |
| 4b | 41/1 | 13/9 | 0/7 | 0/3 | 54/74 |
| 12b | 60/0 | 13/1 | 0/0 | 0/0 | 73/74 |
| 27b | 58/4 | 12/0 | 0/0 | 0/0 | 70/74 |

**How to read the attribution:**
- **new_only ✓** = method (pool isolates NEW) + reader both worked — the clean win.
- **both ✓** = reader RESCUE (mixed pool, reader still picked NEW).
- **new_only ✗** = reader OVERRIDE (clean pool, reader answered OLD from prior) — the 27B drag.
- **old_only / neither ✗** = NEW absent from the pool (weak extraction/retrieval) — the 1B/4B floor.
