# Hardware + API Summary — 2026-05-12_230733_phase2_pct99

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T23:07:33+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 346.9s (5.8 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.6 GB | 5% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.9 GB | 4% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 70s | 14.88 GB | 14.88 GB | 24.5 GB | 1% / 0% | 6.2 GB | 0 | 0 | 0 | $0.0000 |
| `query/sh_6k` | 93s | 15.40 GB | 15.40 GB | 22.6 GB | 8% / 0% | 2.6 GB | 38 | 146,551 | 351 | $0.0111 |
| `done/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.5 GB | 10% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 4s | 0.00 GB | 0.00 GB | 5.9 GB | 4% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 70s | 14.96 GB | 14.96 GB | 24.7 GB | 2% / 0% | 6.1 GB | 0 | 0 | 0 | $0.0000 |
| `query/mh_6k` | 97s | 15.40 GB | 15.40 GB | 22.6 GB | 8% / 0% | 2.6 GB | 39 | 150,997 | 2,275 | $0.0120 |
| `done/mh_6k` | 2s | 15.40 GB | 15.40 GB | 22.4 GB | 10% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 349s | — | — | — | — | — | 77 | 297,548 | 2,626 | $0.0231 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 15.40 GB)
- GPU total peak (all procs): 15.40 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `indexing/mh_6k`, `query/mh_6k`, `done/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778598730 | gemini-3.1-flash-lite-preview | 3,863 | 828 | False |
| 1778598790 | gemini-3.1-flash-lite-preview | 3,815 | 464 | False |
| 1778598782 | gemini-3.1-flash-lite-preview | 3,868 | 252 | False |
| 1778598545 | gemini-3.1-flash-lite-preview | 3,934 | 71 | False |
| 1778598731 | gemini-3.1-flash-lite-preview | 3,948 | 48 | False |
