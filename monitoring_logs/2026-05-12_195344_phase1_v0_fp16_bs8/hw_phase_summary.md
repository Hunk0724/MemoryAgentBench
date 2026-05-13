# Hardware + API Summary — 2026-05-12_195344_phase1_v0_fp16_bs8

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T19:53:44+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 785.4s (13.1 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.5 GB | 6% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.8 GB | 2% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 97s | 21.10 GB | 21.10 GB | 28.4 GB | 2% / 0% | 6.2 GB | 24 | 24,692 | 13,543 | $0.0059 |
| `query/sh_6k` | 270s | 15.40 GB | 15.40 GB | 22.7 GB | 3% / 0% | 2.8 GB | 200 | 676,110 | 4,725 | $0.0521 |
| `done/sh_6k` | 4s | 15.40 GB | 15.40 GB | 20.7 GB | 6% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 4s | 0.00 GB | 0.00 GB | 5.8 GB | 4% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 103s | 21.10 GB | 21.10 GB | 28.4 GB | 2% / 0% | 6.1 GB | 24 | 24,692 | 13,543 | $0.0059 |
| `query/mh_6k` | 299s | 15.40 GB | 15.40 GB | 22.8 GB | 3% / 0% | 2.8 GB | 200 | 677,777 | 10,311 | $0.0539 |
| `done/mh_6k` | 2s | 15.40 GB | 15.40 GB | 22.5 GB | 2% / 0% | 2.2 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 787s | — | — | — | — | — | 448 | 1,403,271 | 42,122 | $0.1179 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✗** (observed 21.10 GB)
- GPU total peak (all procs): 21.10 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `done/sh_6k`, `indexing/mh_6k`, `query/mh_6k`, `done/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778587569 | gemini-3.1-flash-lite-preview | 3,839 | 773 | False |
| 1778587576 | gemini-3.1-flash-lite-preview | 3,858 | 532 | False |
| 1778587543 | gemini-3.1-flash-lite-preview | 3,879 | 283 | False |
| 1778587404 | gemini-3.1-flash-lite-preview | 3,822 | 276 | False |
| 1778587593 | gemini-3.1-flash-lite-preview | 3,920 | 127 | False |
