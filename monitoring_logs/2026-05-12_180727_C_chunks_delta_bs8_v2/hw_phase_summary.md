# Hardware + API Summary — 2026-05-12_180727_C_chunks_delta_bs8_v2

**Command**: `conda run -n hipporag_env --no-capture-output python main.py         --agent_config configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml         --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml         --chunk_size_ablation 512`
**Started**: 2026-05-12T18:07:27+08:00
**Git SHA**: `e144fcc`

**Total wall time**: 24.9s (0.4 min)

## Per-phase summary

> `GPU tree`: GPU memory used by the run's process tree (target + descendants).
> `GPU total`: ALL processes on the GPU (sanity vs other users).
> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).

| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| `init` | 4s | 0.00 GB | 0.00 GB | 5.5 GB | 6% / 0% | 0.7 GB | 0 | 0 | 0 | $0.0000 |
| `setup/mh_6k` | 4s | 0.00 GB | 0.00 GB | 5.8 GB | 2% / 0% | 1.4 GB | 0 | 0 | 0 | $0.0000 |
| `indexing/mh_6k` | 19s | 51.24 GB | 51.24 GB | 60.0 GB | 4% / 0% | 6.1 GB | 24 | 23,306 | 10,915 | $0.0050 |
| **TOTAL** | 27s | — | — | — | — | — | 24 | 23,306 | 10,915 | $0.0050 |

## Hardware invariant check

- GPU tree peak < 20 GB: **✗** (observed 51.24 GB)
- GPU total peak (all procs): 51.24 GB
- Phases with GPU > 5 GB (tree): `indexing/mh_6k`

## Top 5 largest API calls (by total tokens)

| ts | model | in tok | out tok | cache hit |
|---|---|---|---|---|
| 1778580472 | gemini-3.1-flash-lite-preview | 1,125 | 993 | False |
| 1778580470 | gemini-3.1-flash-lite-preview | 1,161 | 956 | False |
| 1778580470 | gemini-3.1-flash-lite-preview | 1,159 | 939 | False |
| 1778580469 | gemini-3.1-flash-lite-preview | 1,148 | 929 | False |
| 1778580469 | gemini-3.1-flash-lite-preview | 1,142 | 915 | False |
