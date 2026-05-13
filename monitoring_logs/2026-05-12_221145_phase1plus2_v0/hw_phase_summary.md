# Hardware + API Summary — 2026-05-12_221145_phase1plus2_v0

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T22:11:45+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 1115.9s (18.6 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.6 GB | 5% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.9 GB | 3% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 72s | 14.96 GB | 14.96 GB | 24.8 GB | 2% / 0% | 6.2 GB | 0 | 0 | 0 | $0.0000 |
| `query/sh_6k` | 774s | 15.40 GB | 15.40 GB | 22.6 GB | 1% / 0% | 2.6 GB | 100 | 360,001 | 567 | $0.0272 |
| `done/sh_6k` | 4s | 15.40 GB | 15.40 GB | 22.4 GB | 7% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 6s | 0.01 GB | 0.01 GB | 6.0 GB | 4% / 0% | 1.6 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 70s | 14.96 GB | 14.96 GB | 24.7 GB | 2% / 0% | 6.1 GB | 0 | 0 | 0 | $0.0000 |
| `query/mh_6k` | 182s | 15.40 GB | 15.40 GB | 22.6 GB | 5% / 0% | 2.6 GB | 98 | 348,926 | 4,642 | $0.0276 |
| `done/mh_6k` | 2s | 15.40 GB | 15.40 GB | 22.4 GB | 5% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 1118s | — | — | — | — | — | 198 | 708,927 | 5,209 | $0.0547 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 15.40 GB)
- GPU total peak (all procs): 15.40 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `done/sh_6k`, `indexing/mh_6k`, `query/mh_6k`, `done/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778596167 | gemini-3.1-flash-lite-preview | 3,912 | 429 | False |
| 1778596085 | gemini-3.1-flash-lite-preview | 3,860 | 327 | False |
| 1778596208 | gemini-3.1-flash-lite-preview | 3,919 | 257 | False |
| 1778596094 | gemini-3.1-flash-lite-preview | 3,863 | 274 | False |
| 1778596073 | gemini-3.1-flash-lite-preview | 3,826 | 307 | False |
