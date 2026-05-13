# Hardware + API Summary — 2026-05-12_171111_A4_default_bs16

**Command**: `bash run_hipporag_gemini.sh`
**Started**: 2026-05-12T17:11:11+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 842.7s (14.0 min)

## Per-phase summary

| Phase | wall | GPU peak | GPU mean | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 10s | 0.00 GB | 0.00 GB | 5.3 GB | 3% / 0% | 0.0 GB | 0 | 0 | 0 | $0.0000 |
| `query` | 447s | 0.00 GB | 0.00 GB | 61.8 GB | 5% / 0% | 0.0 GB | 24 | 24,692 | 13,543 | $0.0059 |
| `transition` | 787s | 0.00 GB | 0.00 GB | 52.9 GB | 3% / 0% | 0.0 GB | 424 | 1,378,594 | 28,526 | $0.1120 |
| **TOTAL** | — | — | — | — | — | — | 448 | 1,403,286 | 42,069 | $0.1179 |

## Hardware invariant check

- GPU peak < 20 GB: **✓** (observed 0.00 GB)

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778577862 | gemini-3.1-flash-lite-preview | 3,839 | 773 | False |
| 1778577871 | gemini-3.1-flash-lite-preview | 3,858 | 532 | False |
| 1778577829 | gemini-3.1-flash-lite-preview | 3,879 | 283 | False |
| 1778577666 | gemini-3.1-flash-lite-preview | 3,822 | 276 | False |
| 1778577893 | gemini-3.1-flash-lite-preview | 3,920 | 127 | False |
