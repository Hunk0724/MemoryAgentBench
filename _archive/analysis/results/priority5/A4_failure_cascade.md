# A4 — Failure Root-Cause Cascade (Ablation B)

Of 69 wrong queries, classify each by FIRST cascade stage that fails:

| Stage | Description | Count | % |
|---|---|---|---|
| `F2_not_both_in_chains` | One/both not in any top-5 chain | 27 | 39% |
| `F6_filter_no_drop` | Verdict correct, but filter didn't drop chain_old chunk | 18 | 26% |
| `F7_llm_answer_despite_clean_context` | Cascade clean but LLM still answered wrong | 17 | 25% |
| `F7_llm_answer` | No conflict hop, LLM answer wrong (other reasons) | 4 | 6% |
| `F4_llm_missed_identify` | In pool, but LLM didn't mark contradicting | 1 | 1% |
| `F5_verdict_wrong_status` | Identified but verdict didn't mark chain_old as superseded | 1 | 1% |
| `F0_no_phase2` | DPR fallback, Phase 2 not run | 1 | 1% |

## By hop depth

| Hop | F1 | F2 | F3 | F4 | F5 | F6 | F7 |
|---|---|---|---|---|---|---|---|
| 2-hop | 0 | 9 | 0 | 1 | 0 | 11 | 16 |
| 3-hop | 0 | 11 | 0 | 0 | 0 | 3 | 4 |
| 4-hop | 0 | 7 | 0 | 0 | 1 | 4 | 1 |
