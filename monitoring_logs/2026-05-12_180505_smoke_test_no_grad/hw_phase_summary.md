# Hardware + API Summary — 2026-05-12_180505_smoke_test_no_grad

**Command**: `conda run -n hipporag_env --no-capture-output python scripts/smoke_test_monitoring.py`
**Started**: 2026-05-12T18:05:05+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 86.5s (1.4 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 2s | 0.00 GB | 0.00 GB | 5.0 GB | 0% / 0% | 0.0 GB | 0 | 0 | 0 | $0.0000 |
| `setup/smoke_6k` | 4s | 0.00 GB | 0.00 GB | 5.4 GB | 4% / 0% | 0.6 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/smoke_6k` | 76s | 19.54 GB | 19.54 GB | 26.3 GB | 2% / 0% | 5.5 GB | 0 | 0 | 0 | $0.0000 |
| `query/smoke_6k` | 4s | 19.55 GB | 19.55 GB | 26.3 GB | 0% / 0% | 1.8 GB | 0 | 0 | 0 | $0.0000 |
| `done/smoke_6k` | 2s | 19.55 GB | 19.55 GB | 26.3 GB | 0% / 0% | 1.8 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 89s | — | — | — | — | — | 0 | 0 | 0 | $0.0000 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 19.55 GB)
- GPU total peak (all procs): 19.55 GB
- Phases with GPU > 5 GB (tree): `indexing/smoke_6k`, `query/smoke_6k`, `done/smoke_6k`
