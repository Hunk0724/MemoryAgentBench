# B3b — Per-hop EM Breakdown (4-ablation FC-MH 100Q)

## Overall

| Ablation | EM |
|---|---|
| A_vanilla | 17/100 (17.0%) |
| B_phase2 | 31/100 (31.0%) |
| C_w3_full | 31/100 (31.0%) |
| D_w3_min | 15/100 (15.0%) |

## By num_hops

| Ablation | 2-hop | 3-hop | 4-hop |
|---|---|---|---|
| A_vanilla | 13/61 (21.3%) | 2/24 (8.3%) | 2/15 (13.3%) |
| B_phase2 | 23/61 (37.7%) | 6/24 (25.0%) | 2/15 (13.3%) |
| C_w3_full | 23/61 (37.7%) | 6/24 (25.0%) | 2/15 (13.3%) |
| D_w3_min | 11/61 (18.0%) | 3/24 (12.5%) | 1/15 (6.7%) |

## By n_conflict

| Ablation | 1-conflict | 2-conflict | 3-conflict | 4-conflict |
|---|---|---|---|---|
| A_vanilla | 8/33 (24.2%) | 6/48 (12.5%) | 3/17 (17.6%) | 0/2 (0.0%) |
| B_phase2 | 11/33 (33.3%) | 17/48 (35.4%) | 3/17 (17.6%) | 0/2 (0.0%) |
| C_w3_full | 11/33 (33.3%) | 17/48 (35.4%) | 3/17 (17.6%) | 0/2 (0.0%) |
| D_w3_min | 9/33 (27.3%) | 4/48 (8.3%) | 2/17 (11.8%) | 0/2 (0.0%) |

## Cross-system compare(FC-MH overall) — 含 2026-05-02 Mem0/Zep × Gemini

| System | LLM | 2-hop | 3-hop | 4-hop | Overall |
|---|---|---|---|---|---|
| A_vanilla | (我們 ablation, LLM 待查) | 13/61 (21.3%) | 2/24 (8.3%) | 2/15 (13.3%) | 17/100 (17.0%) |
| B_phase2 | (我們 ablation, LLM 待查) | 23/61 (37.7%) | 6/24 (25.0%) | 2/15 (13.3%) | 31/100 (31.0%) |
| C_w3_full | (我們 ablation, LLM 待查) | 23/61 (37.7%) | 6/24 (25.0%) | 2/15 (13.3%) | 31/100 (31.0%) |
| D_w3_min | (我們 ablation, LLM 待查) | 11/61 (18.0%) | 3/24 (12.5%) | 1/15 (6.7%) | 15/100 (15.0%) |
| HippoRAG-v2 plain | Gemini-3.1 modified | (see motivation) | | | **23%** |
| Mem0 customized | Gemini-3.1 | 44.3% (27/61) | 50.0% (12/24) | 26.7% (4/15) | **43.0%** |
| Zep | Gemini-3.1 (inference) | 13.1% (8/61) | **0.0%** (0/24) | **0.0%** (0/15) | **8.0%** |
| Zep × GPT-4o-mini (legacy) | GPT-4o-mini | — | — | — | 28% |
| OA2 fact-level oracle | Gemini-3.1 modified | — | — | — | **83%** |
