# FC-SH error-mode — dominant bucket per method (gpt-4o-mini, all 4 lengths)

> **Thesis**: every baseline loses the NEW (counterfactual) version at a *different* pipeline stage, but the failure signature is identical — the final answer falls back to the LLM-prior-consistent OLD value (**gt_OLD**). Each family is measured with the metric that isolates its stage; all terminate in gt_OLD.
>
> **Reproduce**: `python analysis/errormode_dominant_buckets.py` (MABench env, repo root). Committed data only; no model re-runs. Backbone gpt-4o-mini, temp 0, single run.
> **Single ground truth**: `rescore_canonical.load_haspair(L)` → `analysis/results/sh_{L}_mquake_analysis.json`. **Single subEM matcher**: `rescore_canonical.official_subem` (MAB official substring-EM). **gt_OLD surface**: `rescore_canonical.extract_old_surface`; `answered_old := official_subem(pred, [old_surface])`.

---

## Consolidated table

Per-length proportion columns give the DOMINANT bucket's metric at 6k / 32k / 64k / 262k.

| Method | Pipeline stage new-version lost | Dominant bucket (metric) | 6k | 32k | 64k | 262k | Robustness | Source data |
|:--|:--|:--|:-:|:-:|:-:|:-:|:--|:--|
| **Vanilla-RAG** | query-time recency judge (downstream) | fall-to-gt_OLD (% of has_pair fails) | 100% (7/7) | 96% (22/23) | 100% (15/15) | 95% (18/19) | ROBUST | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_q_llm_recency/Conflict_Resolution/*results*.json` |
| **Ours (Struct-Only)** | query-time (S,P) canonicalization miss | fall-to-gt_OLD (% of has_pair fails) | 100% (7/7) | 100% (12/12) | 88% (7/8) | 79% (11/14) | ROBUST | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct/Conflict_Resolution/*results*.json` |
| **Don't Ask** | query-time LLM candidate extraction (upstream) | n_cand==1 ∧ gt_OLD (raw / D-flag-excl) | 100% raw / 100% Df | 79% raw / 92% Df | 83% raw / 100% Df | 71% raw / 83% Df | ROBUST (see D-flag note) | `outputs/maxserial_theircode/{L}_gpt-4o-mini_vector100.json` |
| **Mem0 + P1** | write-time destructive commit | pool new-absent = PP-OldOnly+PP-Missing (% has_pair) | 47% (35/74) | 45% (29/65) | 36% (24/66) | 47% (36/77) | ROBUST | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/**/query_*.json` (`retrieved_memories`) |
| **Mem0 Vanilla** | write-time mis-apply (coarse) | overall SubEM (no fine bucket) | 16% (16/100) | 22% (22/100) | 28% (28/100) | 17% (17/100) | COARSE | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-native/Conflict_Resolution/*results*.json` |
| **Zep (k=10)** | write-time no-KU-signal + query-time retrieval miss | NotBothExtracted (% has_pair) | 0% (0/74) | 5% (3/65) | 2% (1/66) | 82% (63/77) | ROBUST | `outputs/rag_retrieved/Structure_rag_zep/k_10/**/query_*.json` (`edges`,`response`) |

### Zep answer-side link (closes the no-KU-signal → answer-falls-to-old chain)

For SHORT lengths, among has_pair with an **Additive-NoKU** signal (old edge still valid; no invalidation → both versions effectively co-active for the answer LLM), the answer-side outcome:

| Length | Additive-NoKU (N) | of which FAILED | ... answered gt_OLD | % of failures = gt_OLD |
|:--|:-:|:-:|:-:|:-:|
| 6k | 29 | 2 | 2 | 100% |
| 32k | 50 | 17 | 17 | 100% |
| 64k | 49 | 23 | 23 | 100% |

This is fully recoverable: each Zep `query_*_context_*.json` carries BOTH the retrieved `edges` and the final `response`, so the retrieved-context → final-answer join is a within-file lookup. (262k is dominated by NotBothExtracted, not Additive-NoKU, so the answer-side link is reported for short lengths where the no-KU-signal path is the mechanism.)

### Mem0 + P1 pool-state detail (new-absent buckets have ~0 accuracy)

| Length | PP-New | PP-Both | PP-OldOnly | PP-Missing | new-absent subEM acc |
|:--|:-:|:-:|:-:|:-:|:-:|
| 6k | 27 | 12 | 15 | 20 | 0/35 (0%) |
| 32k | 22 | 14 | 11 | 18 | 1/29 (3%) |
| 64k | 25 | 17 | 15 | 9 | 0/24 (0%) |
| 262k | 18 | 23 | 24 | 12 | 0/36 (0%) |

## Per-method metric rationale

- **Vanilla-RAG / Ours (Struct-Only)** — both are query-time methods that put the full ordinal pool in front of the answer LLM; the right metric is directly *whether the wrong answer is gt_OLD*. Vanilla-RAG loses NEW at the **downstream recency judge** (LLM ignores the max-ordinal rule, reverts to the semantically familiar old value); Struct-Only loses it at **(S,P) canonicalization** (new/old split into different structural buckets, argmax never compares them, pool keeps both, reader defaults to world-prior old).
- **Don't Ask** — identity is delegated to LLM candidate extraction, so the diagnostic signal is UPSTREAM: `n_candidates == 1` means the LLM extracted only ONE version; combined with `answered gt_OLD` it shows the single surviving candidate was the world-prior old value. Reported RAW and with benchmark-reversed (**D-flag**: `gt_seq < old_seq`, unwinnable by max-serial) queries excluded.
- **Mem0 + P1** — KU damage is at **write time**, so the mediator is the *pool state* (does the answering pool still contain gt_new?). `new-absent` = PP-OldOnly + PP-Missing = the destructive UPDATE/DELETE already erased gt_new before query time; its subEM accuracy is ~0.
- **Mem0 Vanilla** — coarse by design: no P1 faithful extraction, damage is write-time mis-apply; we report only overall SubEM and do NOT fabricate a fine M1/M2 split.
- **Zep** — KU decision lives in bi-temporal fields, not pool text. `NotBothExtracted` (one/both versions absent from the top-10 the answer LLM saw) is the headline at 262k; for short lengths the `Additive-NoKU` bucket (no invalidation signal) + the answer-side gt_OLD link shows the no-KU-signal → fall-to-old chain end to end.

## Provenance

- **Script**: `analysis/errormode_dominant_buckets.py` (this file).
- **Shared canonical primitives**: `analysis/rescore_canonical.py` (`official_subem`, `extract_old_surface`, `load_haspair`, `pick_canonical_file`).
- **Pool-state**: `analysis/compute_pool_acc_crosstab.py` (`classify_pool_state`, `extract_pool_texts`).
- **Zep bi-temporal**: `analysis/classify_zep_ku_resolution.py` (`classify_query`) + `analysis/compute_m1_m2_m3.py` (`match_pair`).
- **Ground truth**: `analysis/results/sh_{6k,32k,64k,262k}_mquake_analysis.json`.

## Caveats (what stays coarse / inference-level)

- **Mem0 M1/M2 split is NOT in this table.** The write-time-failure taxonomy (world-prior override vs coupled-update fragility, `mem0_event_taxonomy_gt4o.md`) is elimination-based inference from the event log (which does not record NONE/reject decisions), single-length (64k), and its scratchpad scripts are deleted. Here we report only the ROBUST pool-state fact (gt_new absent → ~0 acc) and leave M1/M2 as coarse mechanism prose.
- **Ours (main) residual** error split (reader-override vs struct-frag vs D-flag) stays coarse (see `fc_sh_4method_errormode_diag.md` Diagnostic 3); not re-derived here.
- **Don't Ask 64k**: RAW n_cand==1∧gt_OLD is ~83%; the '100%' figure requires excluding the 2 D-flag (benchmark-reversed) queries. Both are reported; do not cite '100%' without the D-flag qualifier.
- **Zep answer-side link at 262k**: 262k is dominated by NotBothExtracted (retrieval miss), so the Additive-NoKU answer-side link is only meaningful for short lengths and is reported there; at 262k the recoverable robust fact is NotBothExtracted.
- Single deterministic run (temp 0), no error bars; subEM percentages can wobble ±1 query but the DOMINANT bucket per method is stable.
