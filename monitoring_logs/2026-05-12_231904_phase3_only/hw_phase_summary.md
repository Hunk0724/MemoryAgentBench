# Hardware + API Summary — 2026-05-12_231904_phase3_only

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T23:19:04+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 739.4s (12.3 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.5 GB | 5% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/sh_6k` | 4s | 0.00 GB | 0.00 GB | 5.8 GB | 4% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/sh_6k` | 72s | 15.33 GB | 15.33 GB | 24.8 GB | 2% / 0% | 6.2 GB | 0 | 0 | 0 | $0.0000 |
| `query/sh_6k` | 322s | 15.40 GB | 15.40 GB | 22.6 GB | 3% / 0% | 2.6 GB | 100 | 389,159 | 6,224 | $0.0311 |
| `done/sh_6k` | 2s | 0.00 GB | 0.00 GB | 5.2 GB | 5% / 0% | 0.1 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 6s | 0.00 GB | 0.00 GB | 5.9 GB | 5% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 70s | 14.83 GB | 14.83 GB | 24.4 GB | 1% / 0% | 6.0 GB | 0 | 0 | 0 | $0.0000 |
| `query/mh_6k` | 259s | 15.40 GB | 15.40 GB | 22.6 GB | 3% / 0% | 2.6 GB | 100 | 389,763 | 13,037 | $0.0331 |
| `done/mh_6k` | 2s | 15.40 GB | 15.40 GB | 22.4 GB | 2% / 0% | 2.1 GB | 0 | 0 | 0 | $0.0000 |
| **TOTAL** | 741s | — | — | — | — | — | 200 | 778,922 | 19,261 | $0.0642 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✓** (observed 15.40 GB)
- GPU total peak (all procs): 15.40 GB
- Phases with GPU > 5 GB (tree): `indexing/sh_6k`, `query/sh_6k`, `indexing/mh_6k`, `query/mh_6k`, `done/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778599827 | gemini-3.1-flash-lite-preview | 3,890 | 484 | False |
| 1778599710 | gemini-3.1-flash-lite-preview | 3,915 | 413 | False |
| 1778599638 | gemini-3.1-flash-lite-preview | 3,899 | 368 | False |
| 1778599822 | gemini-3.1-flash-lite-preview | 3,871 | 376 | False |
| 1778599729 | gemini-3.1-flash-lite-preview | 3,926 | 319 | False |
