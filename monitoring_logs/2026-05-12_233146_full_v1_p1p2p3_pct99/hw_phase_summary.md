# Hardware + API Summary — 2026-05-12_233146_full_v1_p1p2p3_pct99

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T23:31:46+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 466.3s (7.8 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.6 GB | 6% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.9 GB | 2% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 70s | 14.83 GB | 14.83 GB | 25.0 GB | 2% / 0% | 6.3 GB | 0 | 0 | 0 | $0.0000 |
| `query/sh_6k` | 103s | 15.40 GB | 15.40 GB | 22.6 GB | 7% / 0% | 2.6 GB | 46 | 178,756 | 2,290 | $0.0141 |
| `done/sh_6k` | 4s | 15.40 GB | 15.40 GB | 22.4 GB | 8% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 6s | 0.00 GB | 0.00 GB | 5.9 GB | 5% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 70s | 14.96 GB | 14.96 GB | 24.7 GB | 1% / 0% | 6.1 GB | 0 | 0 | 0 | $0.0000 |
| `query/mh_6k` | 206s | 15.40 GB | 15.40 GB | 22.6 GB | 4% / 0% | 2.6 GB | 47 | 183,378 | 5,857 | $0.0155 |
| **TOTAL** | 468s | — | — | — | — | — | 93 | 362,134 | 8,147 | $0.0296 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 15.40 GB)
- GPU total peak (all procs): 15.40 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `done/sh_6k`, `indexing/mh_6k`, `query/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778600181 | gemini-3.1-flash-lite-preview | 3,934 | 453 | False |
| 1778600217 | gemini-3.1-flash-lite-preview | 3,895 | 414 | False |
| 1778600362 | gemini-3.1-flash-lite-preview | 3,847 | 400 | False |
| 1778600276 | gemini-3.1-flash-lite-preview | 3,845 | 399 | False |
| 1778600227 | gemini-3.1-flash-lite-preview | 3,914 | 272 | False |
