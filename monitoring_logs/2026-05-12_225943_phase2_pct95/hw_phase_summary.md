# Hardware + API Summary — 2026-05-12_225943_phase2_pct95

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T22:59:43+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 447.8s (7.5 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.6 GB | 4% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.9 GB | 4% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 70s | 14.83 GB | 14.83 GB | 24.9 GB | 2% / 0% | 6.2 GB | 0 | 0 | 0 | $0.0000 |
| `query/sh_6k` | 124s | 15.40 GB | 15.40 GB | 22.6 GB | 6% / 0% | 2.6 GB | 68 | 261,910 | 362 | $0.0198 |
| `done/sh_6k` | 4s | 15.40 GB | 15.40 GB | 22.4 GB | 7% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 6s | 0.00 GB | 0.00 GB | 6.0 GB | 4% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 72s | 15.34 GB | 15.34 GB | 24.9 GB | 2% / 0% | 6.2 GB | 1 | 3,877 | 4 | $0.0003 |
| `query/mh_6k` | 163s | 15.40 GB | 15.40 GB | 22.6 GB | 5% / 0% | 2.6 GB | 71 | 274,581 | 5,533 | $0.0223 |
| `done/mh_6k` | 2s | 15.40 GB | 15.40 GB | 22.4 GB | 8% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 450s | — | — | — | — | — | 140 | 540,368 | 5,899 | $0.0423 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 15.40 GB)
- GPU total peak (all procs): 15.40 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `done/sh_6k`, `indexing/mh_6k`, `query/mh_6k`, `done/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778598421 | gemini-3.1-flash-lite-preview | 3,886 | 667 | False |
| 1778598387 | gemini-3.1-flash-lite-preview | 3,862 | 672 | False |
| 1778598414 | gemini-3.1-flash-lite-preview | 3,912 | 459 | False |
| 1778598356 | gemini-3.1-flash-lite-preview | 3,885 | 453 | False |
| 1778598310 | gemini-3.1-flash-lite-preview | 3,858 | 475 | False |
