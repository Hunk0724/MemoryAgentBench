# Hardware + API Summary — 2026-05-12_224401_phase2_pct90

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T22:44:01+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 908.4s (15.1 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.5 GB | 5% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.9 GB | 3% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 70s | 14.91 GB | 14.91 GB | 24.4 GB | 2% / 0% | 6.2 GB | 0 | 0 | 0 | $0.0000 |
| `query/sh_6k` | 585s | 15.40 GB | 15.40 GB | 22.6 GB | 2% / 0% | 2.6 GB | 86 | 331,316 | 783 | $0.0251 |
| `done/sh_6k` | 2s | 0.00 GB | 0.00 GB | 5.2 GB | 5% / 0% | 0.1 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 6s | 0.00 GB | 0.00 GB | 5.9 GB | 5% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 72s | 15.34 GB | 15.34 GB | 24.9 GB | 2% / 0% | 6.2 GB | 1 | 3,878 | 4 | $0.0003 |
| `query/mh_6k` | 167s | 15.40 GB | 15.40 GB | 22.6 GB | 5% / 0% | 2.6 GB | 82 | 316,845 | 5,976 | $0.0256 |
| **TOTAL** | 910s | — | — | — | — | — | 169 | 652,039 | 6,763 | $0.0509 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 15.40 GB)
- GPU total peak (all procs): 15.40 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `indexing/mh_6k`, `query/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778597792 | gemini-3.1-flash-lite-preview | 3,867 | 883 | False |
| 1778597938 | gemini-3.1-flash-lite-preview | 3,881 | 525 | False |
| 1778597815 | gemini-3.1-flash-lite-preview | 3,865 | 465 | False |
| 1778597931 | gemini-3.1-flash-lite-preview | 3,910 | 344 | False |
| 1778597922 | gemini-3.1-flash-lite-preview | 3,838 | 397 | False |
