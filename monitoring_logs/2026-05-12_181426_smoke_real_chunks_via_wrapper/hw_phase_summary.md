# Hardware + API Summary — 2026-05-12_181426_smoke_real_chunks_via_wrapper

**Command**: `conda run -n hipporag_env --no-capture-output python scripts/smoke_test_monitoring.py`
**Started**: 2026-05-12T18:14:26+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 24.9s (0.4 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 2s | 0.00 GB | 0.00 GB | 5.0 GB | 0% / 0% | 0.0 GB | 0 | 0 | 0 | $0.0000 |
| `setup/smoke_6k` | 2s | 0.00 GB | 0.00 GB | 5.4 GB | 9% / 0% | 1.0 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/smoke_6k` | 19s | 50.08 GB | 50.08 GB | 58.5 GB | 7% / 0% | 6.9 GB | 0 | 0 | 0 | $0.0000 |
| `query/smoke_6k` | 2s | 50.08 GB | 50.08 GB | 58.4 GB | 1% / 0% | 3.1 GB | 0 | 0 | 0 | $0.0000 |
| `done/smoke_6k` | 2s | 50.08 GB | 50.08 GB | 58.4 GB | 1% / 0% | 3.1 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 27s | — | — | — | — | — | 0 | 0 | 0 | $0.0000 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✗** (observed 50.08 GB)
- GPU total peak (all procs): 50.08 GB
- Phases with GPU > 5 GB (tree): `indexing/smoke_6k`, `query/smoke_6k`, `done/smoke_6k`
