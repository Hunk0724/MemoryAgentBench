# return_context × Acc cross-tab — GX10 weak-model (gemma3), FC-SH 6k has_pair

> **matcher v4** + **REAL per-qid `memories_str`** (the pool the answer LLM actually saw; agent.py:1100), aligned to Mac's canonical method. N=74. **Acc = official `substring_exact_match`** (2026-07-11 canonical migration; was strict exact_match). Reading: `new_only→✓` method isolated NEW & reader used it; `both→✓` reader RESCUE (mixed pool, picked NEW); `new_only→✗` reader OVERRIDE (clean pool, answered OLD); `old_only/neither→✗` NEW absent from pool (extraction/write loss).

> ⚠️ **EXTRACTION IS PER-BACKBONE GEMMA, NOT held-fixed gpt-4o-mini** (GX10 matrix sets `MEM0_TRIPLE_MODEL=gemma3:$SIZE`). The cross-tab is only RELIABLE for 12b/27b; on **1b/4b the pool-state axis is NOT trustworthy** — gemma-1b/4b extract fewer facts (store ≈370 vs 12b/27b ≈450) whose surface diverges from GT, so matcher v4 false-negatives inflate the `old_only/neither` (NEW-absent) bucket. **For 1b/4b use E2E + case-study** (`weak_model_6k_analysis.md`). Store overlap-with-27b: 1b=5/100, 4b=82/100, 12b=99/100.

## ours_struct

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM | pool-missing |
| :-- | :-: | :-: | :-: | :-: | :-: | :-: |
| 1b | 23/9 | 8/17 | 0/13 | 1/3 | 32/74 | 0 |
| 4b | 39/1 | 15/9 | 0/7 | 0/3 | 54/74 | 0 |
| 12b | 60/0 | 13/1 | 0/0 | 0/0 | 73/74 | 0 |
| 27b | 58/2 | 13/1 | 0/0 | 0/0 | 71/74 | 0 |

## ours_no_p5

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM | pool-missing |
| :-- | :-: | :-: | :-: | :-: | :-: | :-: |
| 1b | 22/10 | 5/20 | 0/13 | 0/4 | 27/74 | 0 |
| 4b | 41/0 | 13/10 | 0/7 | 0/3 | 54/74 | 0 |
| 12b | 60/0 | 13/1 | 0/0 | 0/0 | 73/74 | 0 |
| 27b | 61/1 | 12/0 | 0/0 | 0/0 | 73/74 | 0 |

## ours_p3_only

| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM | pool-missing |
| :-- | :-: | :-: | :-: | :-: | :-: | :-: |
| 1b | 3/0 | 5/50 | 0/13 | 0/3 | 8/74 | 0 |
| 4b | 12/0 | 14/38 | 0/7 | 0/3 | 26/74 | 0 |
| 12b | 5/0 | 41/28 | 0/0 | 0/0 | 46/74 | 0 |
| 27b | 15/0 | 18/41 | 0/0 | 0/0 | 33/74 | 0 |

**Attribution key**: new_only ✓ = clean method+reader win · both ✓ = reader rescue · new_only ✗ = reader override (27B drag) · old_only/neither ✗ = NEW absent (1B/4B floor).
