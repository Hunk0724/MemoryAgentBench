"""Phase 0 — faithful F1/F2 measurement on FC (per-chunk triple extraction).

Replicates the real ingestion path WITHOUT needing the embedder/vector store:
    context --(chunk_size=512)--> chunks --(our L2 extraction)--> per-chunk facts
    each chunk's facts --(phase0_triple_extractor)--> triples
So #LLM calls == #chunks (we reuse the FROZEN L2 extraction cache, i.e. the exact
facts the real run ingests; one triple call per chunk).

Outputs:
    F1 = triple null rate over all extracted facts (escape-hatch rate).
    F2 = conflict-pair (S,P) consistency: for each MQuAKE has_pair, do the new
         and old fact land in the SAME (subject_id, predicate_norm) group?
         This is the method's ceiling — only consistent pairs can be resolved.
    + inverted-pattern rate ("the X of Y | is" form: groups write-side but may
      miss query-side; a watch-item for M4).

Run: python docs/0615_.../scripts/measure_f1_f2.py 6k
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from methods.phase0_triple_extractor import (  # noqa: E402
    extract_triples_batch,
    normalize_predicate,
    normalize_subject,
)

LEN = sys.argv[1] if len(sys.argv) > 1 else "6k"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EXT_CACHE = os.path.join(ROOT, f"analysis/results/extraction_cache_{LEN}.json")
CTX = os.path.join(ROOT, f"analysis/contexts/factconsolidation_{LEN}_context.txt")
SH_ANALYSIS = os.path.join(ROOT, "analysis/results/sh_512_mquake_analysis.json")
TRIPLE_CACHE = os.path.join(ROOT, f"analysis/results/triple_cache_{LEN}.json")
MODEL = os.environ.get("MEM0_TRIPLE_MODEL", "gpt-4o-mini")
UID = "fc_measure"


def norm(t: str) -> str:
    return (t or "").strip().rstrip(".").strip().lower()


def sp(triple):
    if triple is None:
        return None
    return (normalize_subject(triple["subject"], UID), normalize_predicate(triple["predicate"]))


def main():
    chunks = json.load(open(EXT_CACHE, encoding="utf-8"))  # {chunk_key: [facts]}
    chunk_lists = list(chunks.values())
    n_facts = sum(len(c) for c in chunk_lists)
    print(f"[{LEN}] {len(chunk_lists)} chunks, {n_facts} facts "
          f"(=> {len(chunk_lists)} triple LLM calls, model={MODEL})")

    # Per-chunk triple extraction (one call per chunk; frozen cache persists).
    norm2triple = {}
    n_null = n_inv = 0
    t0 = time.time()
    for ci, facts in enumerate(chunk_lists):
        triples = extract_triples_batch(
            facts, model=MODEL, cache_path=TRIPLE_CACHE, batch_size=len(facts)
        )
        for f, t in zip(facts, triples):
            norm2triple[norm(f)] = t
            if t is None:
                n_null += 1
            else:
                s, p = sp(t)
                if p == "is" or s.startswith("the_") and "_of_" in s:
                    n_inv += 1
        print(f"  chunk {ci+1}/{len(chunk_lists)}: {len(facts)} facts done", end="\r")
    print(f"\n  extraction wall time: {time.time()-t0:.1f}s")

    # F1
    print(f"\n=== F1 (triple null rate) ===")
    print(f"  null {n_null}/{n_facts} = {n_null/n_facts:.1%}")
    print(f"  inverted-pattern ('... | is') {n_inv}/{n_facts-n_null} of extracted "
          f"= {n_inv/max(1,n_facts-n_null):.1%}  (M4 query-side watch-item)")

    # F2 (SH conflict pairs)
    analysis = json.load(open(SH_ANALYSIS, encoding="utf-8"))
    pairs = [(r["gt_fact_text"], r["old_fact_text"]) for r in analysis
             if r.get("conflict_type") == "has_pair" and r.get("gt_fact_text") and r.get("old_fact_text")]
    both = same = miss = one_null = 0
    resid_subj_diff = resid_pred_diff = 0  # residual inconsistency breakdown
    examples_subj, examples_pred = [], []
    for gt_txt, old_txt in pairs:
        gt_t = norm2triple.get(norm(gt_txt), "ABSENT")
        old_t = norm2triple.get(norm(old_txt), "ABSENT")
        if gt_t == "ABSENT" or old_t == "ABSENT":
            miss += 1
            continue
        if gt_t is None or old_t is None:
            one_null += 1  # one side nulled (F1 spillover) -> not groupable
            continue
        both += 1
        a, b = sp(gt_t), sp(old_t)
        if a == b:
            same += 1
        elif a[0] != b[0]:  # subjects differ -> structural / inversion residual
            resid_subj_diff += 1
            if len(examples_subj) < 5:
                examples_subj.append((gt_txt, a, old_txt, b))
        else:  # same subject, predicate differs -> synonymy / truncation -> D3
            resid_pred_diff += 1
            if len(examples_pred) < 5:
                examples_pred.append((gt_txt, a, old_txt, b))

    print(f"\n=== F2 (SH conflict-pair (S,P) consistency) ===")
    print(f"  has_pair total: {len(pairs)}")
    print(f"  both extracted (non-null): {both} | one-side null (F1): {one_null} | not-in-ext: {miss}")
    print(f"  SAME (S,P) [groupable]: {same}/{both} = {same/max(1,both):.1%} of both-extracted")
    print(f"  => method ceiling on SH has_pair ≈ {same}/{len(pairs)} = {same/max(1,len(pairs)):.1%}")
    print(f"\n  residual inconsistency breakdown (of {both-same} inconsistent):")
    print(f"    subject differs (structural/inversion; D3-predicate CANNOT fix): {resid_subj_diff}")
    print(f"    same subject, predicate differs (synonymy/truncation -> D3):     {resid_pred_diff}")
    if examples_subj:
        print("  [subject-differs examples]:")
        for g, a, o, b in examples_subj:
            print(f"    gt  {a}  <- {g}")
            print(f"    old {b}  <- {o}")
    if examples_pred:
        print("  [predicate-differs examples]:")
        for g, a, o, b in examples_pred:
            print(f"    gt  {a}  <- {g}")
            print(f"    old {b}  <- {o}")
    print(f"\nfrozen triple cache -> {TRIPLE_CACHE}")


if __name__ == "__main__":
    main()
