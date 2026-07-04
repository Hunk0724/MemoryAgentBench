# return_context × Acc cross-tab — GX10 weak-model (gemma3), FC-SH 6k has_pair

> Pool state = version-state of the resolved context sent to the answer LLM. Acc = has_pair exact-match. N=74. Reading: `new_only→✓` = method isolated NEW and reader used it; `both→✓` = reader picked NEW from a mixed pool (method did not isolate, reader rescued); `new_only→✗` = reader override on a clean pool; `old_only/neither→✗` = new version absent from pool (extraction/write loss).

## ours_struct

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 1b | 27/16 | 1/12 | 0/13 | 1/4 | 29/74 |
| 4b | 47/1 | 7/9 | 0/7 | 0/3 | 54/74 |
| 12b | 68/0 | 5/1 | 0/0 | 0/0 | 73/74 |
| 27b | 62/7 | 3/2 | 0/0 | 0/0 | 65/74 |

## ours_no_p5

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 1b | 25/18 | 0/13 | 0/13 | 0/5 | 25/74 |
| 4b | 49/1 | 5/9 | 0/7 | 0/3 | 54/74 |
| 12b | 68/0 | 5/1 | 0/0 | 0/0 | 73/74 |
| 27b | 67/4 | 3/0 | 0/0 | 0/0 | 70/74 |

**How to read the attribution:**
- **new_only ✓** = method (pool isolates NEW) + reader both worked — the clean win.
- **both ✓** = reader RESCUE (mixed pool, reader still picked NEW).
- **new_only ✗** = reader OVERRIDE (clean pool, reader answered OLD from prior) — the 27B drag.
- **old_only / neither ✗** = NEW absent from the pool (weak extraction/retrieval) — the 1B/4B floor.
