# Hardware + API Summary — 2026-05-12_175004_C_chunks_delta_bs8

**Command**: `conda run -n hipporag_env --no-capture-output python main.py         --agent_config configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml         --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml         --chunk_size_ablation 512`
**Started**: 2026-05-12T17:50:04+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 380.2s (6.3 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.3 GB | 5% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 4s | 0.00 GB | 0.00 GB | 5.7 GB | 3% / 0% | 1.5 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 374s | 51.24 GB | 51.24 GB | 59.9 GB | 1% / 0% | 6.9 GB | 23 | 22,158 | 11,361 | $0.0051 |
| **TOTAL** | 382s | — | — | — | — | — | 23 | 22,158 | 11,361 | $0.0051 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✗** (observed 51.24 GB)
- GPU total peak (all procs): 51.24 GB
- Phases with GPU > 5 GB (tree): `indexing/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778579425 | gemini-3.1-flash-lite-preview | 1,159 | 978 | False |
| 1778579425 | gemini-3.1-flash-lite-preview | 1,161 | 957 | False |
| 1778579425 | gemini-3.1-flash-lite-preview | 1,149 | 925 | False |
| 1778579425 | gemini-3.1-flash-lite-preview | 1,142 | 916 | False |
| 1778579426 | gemini-3.1-flash-lite-preview | 1,125 | 903 | False |
