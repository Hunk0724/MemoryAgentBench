# KU Taxonomy & Scope — what kind of Knowledge-Update problem we address

> Anchor note (2026-06-23). Establishes, with paper + code evidence across four
> benchmarks, exactly which KU problem our architecture targets, why, and what is
> explicitly out of scope. This is the定錨 for methodology / experiment / defense
> writing. Companion memory: `project_ku_taxonomy_battlefield`.

---

## 0. One-paragraph answer

The KU literature is **not one problem**. Across the four benchmarks we surveyed,
"knowledge update" splits into two buckets by **how the authoritative value is
designated**:

- **Bucket (B) — implicit recency / "newer-wins":** the authoritative value of an
  evolving fact is its **most-recent authoritative assertion**. (FC, LongMemEval,
  BEAM.)
- **Bucket (A) — explicit user-initiated correction:** truth is designated by an
  explicit correction speech act ("I misspoke, correct it"); **recency does NOT
  win** (later same-attribute mentions can be noise). (MemBench.)

**Our battlefield is Bucket (B).** Our two structural commitments — *conservative
write* (keep all versions, no cross-memory LLM judgment) + *query-time temporal
resolution* (argmax by recency among query-relevant versions) — are the canonical
mechanism for Bucket (B). 3 of the 4 major benchmarks live here.

---

## 1. The taxonomy, with evidence

| Benchmark | Paper task name | Bucket | Killer evidence (paper) |
|---|---|---|---|
| **FC** (MemoryAgentBench) | *Selective Forgetting* (FC-SH/MH) | **(B) recency** | "newer facts have larger serial numbers… **finding the newest fact**"; "**prioritize later information** in case of conflict". MQuAKE counterfactual rewrite with **no correction marker**. The paper tests an explicit-negation rule (Policy B) as an ablation and it **underperforms** (−4.5 avg) → recency is the design. |
| **LongMemEval** | *Knowledge Update (KU)* | **(B) recency** | Two **independently dated** assertions of an evolving life-state; question phrased "**my most recent / last**"; judge: "the response… correct as long as **the updated answer** is the required answer". No "I misspoke". |
| **BEAM** | *Knowledge Update / Information Update* | **(B) recency** | original→update bullet pair; update is **deliberately implicit** ("embed new value in natural narrative, **don't state 'X is now Y'**"); probe asks "**most recent version rather than outdated**", and **strips all change cues** ("must not contain 'after, updated, revised…'") → model must infer recency. |
| **MemBench** | *Knowledge-updating* (Factual Memory) | **(A) explicit correction** | "**I just realized I need to correct myself**—Policing Forum only lasts for one day", gold = corrected value. **No newer-wins language anywhere**; code shows later same-attribute mentions are **noise distractors** → recency would answer wrong. |

Evidence is both **paper-level** (definitions/quotes above) and **code-level**
(eval-harness inspection, §3).

---

## 2. Sub-distinction inside Bucket (B) → our primary vs generalization

Recency is signalled differently, which sets the main result vs the generalization:

- **FC = externalized / engineered recency.** Recency is given explicitly as
  **serial numbers** ("larger serial number = newer"). Our **per-chunk `ordinal`**
  maps directly onto this, and scoring is **substring-EM** (strictest). → **Primary,
  clean, controlled main result.**
- **LongMemEval / BEAM = naturalistic recency.** Only timestamps / turn order
  (BEAM even removes the cues); **LLM-judge** scoring; real multi-session dialogue.
  → **Generalization** — a harder, more realistic test of the same mechanism
  (temporal resolution must *infer* recency rather than read a serial number).

---

## 3. Eval-protocol facts (rigor — what the system-under-test actually sees)

Verified from each benchmark's eval code. Two things matter: (a) **no benchmark
hands the memory method a structured fact store** — extraction from raw NL is
universal; (b) **scoring and truth-definition differ**.

| Benchmark | Ingestion to SUT | Oracle-only (never fed at runtime) | Scoring | "Truth" mechanism |
|---|---|---|---|---|
| FC | numbered NL fact list (chunked) | gold answer | **SubEM** | newest serial number |
| LongMemEval | one **concatenated**, date-sorted, role-labeled transcript (or RAG top-k) | `has_answer` (stripped), `answer_session_ids` | **LLM-judge** | static gold = latest value + judge prompt |
| BEAM | sequential role/content stream (long-ctx tail-prune or RAG) | `user_messages.json`, `time_anchor` (dropped), rubric, `source_chat_ids` | **LLM-judge vs rubric** | rubric = updated value |
| MemBench | **true incremental stream**, one turn per step | `(rel,attr,value)`, `target_step_id`, `choices`, `ground_truth` | **multiple-choice EM** | explicit correction turn |

Key retractions (earlier over-claims, corrected by code inspection):
- ❌ "read the authoritative subset from the data structure" — the SUT only sees raw
  NL turns (+role/time where present). `(rel,attr,value)` and `user_messages.json`
  are **oracle-only**; using them at ingestion would be cheating.
- ❌ "BEAM separating `user_messages` endorses user-authoritative extraction" — it's
  a generation-pipeline artifact, never a runtime input. Do **not** cite it.
- ❌ "truth = latest-by-time, universally" — **MemBench violates it** (truth = the
  explicit correction; later mentions are noise).

---

## 4. Why "keep all versions" is *necessary*, not just convenient (strongest argument)

Even within pure newer-wins, the memory must **retain history**, because the **same
store also answers historical queries**:

- LongMemEval and BEAM contain **both** *knowledge-update* (asks the **current**
  value → take latest) **and** *temporal-reasoning* (asks a **past / specific-time**
  value → needs an older version). LongMemEval has **133 KU and 133 temporal-
  reasoning** questions.
- **Destructive write-time consolidation** (overwrite to the latest) **destroys the
  history → temporal-reasoning becomes unanswerable.**

Therefore: **keep all versions at write-time, and defer "which version" to
query-time, where the policy depends on the question** (latest for KU; specific-time
for temporal). This is the architecture's deepest justification, and it is backed by
the benchmarks' own ability distributions — not just by the KU task.

---

## 5. Scope statement (in / out)

**In scope (our contribution):**
- **Bucket (B) implicit-recency KU**, given a modality-appropriate atomic-fact
  extractor (extraction held constant, not solved — see §6).
- Two structural commitments: **conservative write** (all versions, no cross-memory
  LLM judgment) + **query-time KU resolution** (identity grouping via structural
  `(S,P)` + LLM fallback; **temporal argmax**; functional vs multi-valued guard).
- Inference-time contract: **memory is authoritative over the LLM's parametric
  knowledge** (this is what lets a *trusted* user counterfactual override the model).
- Evaluation: **FC primary** (externalized recency, SubEM, controlled);
  **LongMemEval + BEAM generalization** (naturalistic recency, judge, real dialogue).

**Out of scope (named, not hidden):**
- **Bucket (A) explicit-correction KU (MemBench):** our temporal-argmax answers it
  wrong (truth ≠ latest). Cited as the contrasting KU type → **future work:
  correction-aware query-time resolver**. It also demonstrates *why* keep-all +
  **pluggable** query-time resolution is the right general design (one store can host
  both a recency resolver and a correction resolver).
- **Solving extraction.** See §6.

---

## 6. Extraction is an orthogonal precondition (not our contribution)

The field under-addresses proactive KU partly because **generic memory extraction
across contexts is itself hard** — confirmed empirically:

- mem0 native `FACT_RETRIEVAL_PROMPT` (personal-only) **drops FC's world facts**
  entirely ("no personal info" → empty).
- A broadened "extract any asserted fact" prompt **over-extracts on dialogue**
  (LongMemEval: 208 vs 42 facts), hoovering up the **assistant's general knowledge**
  (running tips, travel advice) that the LLM already knows → noise.

The unifying selection *principle* is **knowledge-delta**: store facts the LLM
**doesn't know (personal)** or **contradicts (counterfactual)**; drop LLM-known
elaboration. But it is **modality-dependent to realize** and is **not our object of
study**. We therefore:
- hold extraction **constant within each benchmark** (same front-end for vanilla and
  ours → internal ablation stays apples-to-apples);
- for the **cross-system** baseline, run each system with its **own native
  extraction** (mem0 native fails FC honestly — that is the fair result);
- keep **`chunk_size = 512`** (validated: broadened-native ≈100% FC recall, conflict
  pairs preserved; triples extract cleanly from its atomic output);
- treat extraction degradation as **acceptable and to be reported**, not engineered
  to perfection (avoiding FC overfit).

Code: `methods/mem0_fc_prompt_fix.py::make_broadened_native_prompt` (additive,
flag `use_broadened_native_prompt` in `agent.py`); the FC-overfit L2 prompt is
retained only for reproducing prior results.

---

## 7. Corrected unifying abstraction (SUT view)

> A memory method receives a **long NL history** in which some `(entity, attribute)`
> values are **re-asserted with different values** over time. The task is to return,
> at query time, the **currently-authoritative value** of a queried fact — where
> "authoritative" is **recency** for Bucket (B) and **explicit correction** for
> Bucket (A). No benchmark exposes a structured `(entity, attribute, value, time)`
> store to the method; extraction from NL is intrinsic.

Our architecture supplies the **correct read/write discipline for this store** in the
Bucket (B) regime: append-only writes + query-time latest-value resolution, against
the field's destructive write-time overwrite.

---

## 8. Open threads (tracked, not blocking)

- Multi-valued (non-functional) attributes: same `(S,P)` must **COEXIST**, not argmax
  — guard already prototyped in `phase2`; write up as a bounded retrieval-module
  refinement.
- 262k scale: the real bottleneck is **per-fact sequential embedding** (≈#facts,
  invariant to chunk size), **not** chunk count — `chunk_size=4096` does **not** fix
  it and costs recall. Lever = **batch embeddings**. (chunk stays 512.)
- ordinal granularity at large chunks: registered hypothesis (old+new colliding in
  one chunk → tie). Non-issue at chunk=512; solvable (intra-chunk ordering) if ever
  pushed. Do not pre-catastrophize.
- Cross-system baselines (Zep, LightMem — cloned at `~/LightMem`) and FC-MH: future.
