# Hardware + API Summary — 2026-05-12_181555_smoke_real_chunks_fp16

**Command**: `conda run -n hipporag_env --no-capture-output python scripts/smoke_test_monitoring.py`
**Started**: 2026-05-12T18:15:55+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 88.7s (1.5 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.5 GB | 4% / 0% | 1.0 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/smoke_6k` | 80s | 18.10 GB | 18.10 GB | 24.8 GB | 2% / 0% | 5.7 GB | 0 | 0 | 0 | $0.0000 |
| `query/smoke_6k` | 2s | 21.06 GB | 21.06 GB | 27.9 GB | 4% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| `done/smoke_6k` | 4s | 21.06 GB | 21.06 GB | 28.0 GB | 1% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 91s | — | — | — | — | — | 0 | 0 | 0 | $0.0000 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✗** (observed 21.06 GB)
- GPU total peak (all procs): 21.06 GB
- Phases with GPU > 5 GB (tree): `indexing/smoke_6k`, `query/smoke_6k`, `done/smoke_6k`
