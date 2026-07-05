"""64k has_pair case study trace — 3 body methods × wrong-qid list per bucket.

For each (method, qid) pair, prints a structured trace suitable for pasting
into results/case_studies.md and for classifying error mode (A/B/C/D/E per
evaluation_protocol_main §5.1):
  A. Predicate stem mismatch  — new/old same (S), predicate different form
  B. Subject fragmentation    — same entity, different subject_id
  C. LLM world-knowledge override — pool has gt_new, LLM answers world knowledge
  D. Dataset temporal reversal — gt_seq < old_seq (impossible for argmax)
  E. Surface variant          — GT_new/GT_old surface-similar (substring)

Also: prints which OTHER methods got the same qid right/wrong — for cross-method
attribution.
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from utils.eval_other_utils import normalize_answer, parse_output  # noqa: E402
from analysis.compute_m1_m2_m3 import match_pair  # noqa: E402


METHOD_TO_PERQID_DIR = {
    "ours (no_p5)": REPO / "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5/k_100",
    "ours (struct)": REPO / "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_struct/k_100",
    "ours (p3_only)": REPO / "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_p3_only_no_struct/k_100",
    "(b) mem0+P1": REPO / "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100",
    "Zep (k=10)": REPO / "outputs/rag_retrieved/Structure_rag_zep/k_10",
}

METHOD_TO_POOL_KEY = {
    "ours (no_p5)": "memories_str",
    "ours (struct)": "memories_str",
    "ours (p3_only)": "memories_str",
    "(b) mem0+P1": "retrieved_memories",
    "Zep (k=10)": "edges",
}


def load_perqid(method, L, qid):
    root = METHOD_TO_PERQID_DIR[method]
    sub = f"factconsolidation_sh_{L}"
    p = root / sub / "chunksize_512" / f"query_{qid}_context_0.json"
    if not p.exists():
        return None
    return json.load(open(p))


def extract_pool(query_json, method):
    key = METHOD_TO_POOL_KEY[method]
    if key == "memories_str":
        ms = query_json.get("memories_str", "")
        return [line.lstrip("- ").strip() for line in ms.split("\n") if line.strip()]
    if key == "retrieved_memories":
        rm = query_json.get("retrieved_memories") or []
        return [m.get("memory", "") for m in rm]
    if key == "edges":
        eds = query_json.get("edges") or []
        return [e.get("fact", "") for e in eds]
    return []


def classify_pool_state(pool_texts, gt_new, gt_old):
    has_new = any(match_pair(t, gt_new, gt_old, "new") for t in pool_texts)
    has_old = any(match_pair(t, gt_new, gt_old, "old") for t in pool_texts)
    if has_new and not has_old: return "PP-New"
    if has_new and has_old: return "PP-Both"
    if not has_new and has_old: return "PP-OldOnly"
    return "PP-Missing"


def em_check(response, gt_answer):
    parsed = parse_output(str(response or ""))
    if parsed is None:
        parsed = str(response or "")
    r = normalize_answer(parsed)
    gts = gt_answer if isinstance(gt_answer, list) else [gt_answer]
    return any(normalize_answer(str(g)) == r for g in gts if g)


def trace(qid, L, cases):
    """cases = list of method names. Print trace for each method + shared info."""
    # Load gt
    gt_map_file = REPO / f"analysis/results/sh_{'512' if L=='6k' else L}_mquake_analysis.json"
    gt_list = json.load(open(gt_map_file))
    gt = next((g for g in gt_list if g["query_id"] == qid), None)
    if not gt:
        print(f"qid={qid}: gt not found"); return

    print(f"\n{'='*72}")
    print(f"### qid = {qid}   (L = {L}   qa_pair_id = {gt.get('qa_pair_id')})")
    print(f"{'='*72}")
    print(f"Question    : {gt['question']}")
    print(f"GT answer   : {gt.get('gt_answer')}")
    print(f"gt_new_fact : {gt.get('gt_fact_text')}   [gt_seq={gt.get('gt_seq')}]")
    print(f"gt_old_fact : {gt.get('old_fact_text')}  [old_seq={gt.get('old_seq')}]")
    print(f"conflict_ty : {gt.get('conflict_type')}   update_gap={gt.get('update_gap')}")
    # D flag: gt_seq < old_seq (temporal reversal in dataset)
    if gt.get('gt_seq') and gt.get('old_seq') and gt['gt_seq'] < gt['old_seq']:
        print(f">>> D-flag: dataset temporal reversal (gt_seq {gt['gt_seq']} < old_seq {gt['old_seq']})")

    print()
    for method in cases:
        pq = load_perqid(method, L, qid)
        if pq is None:
            print(f"--- {method}: per-qid file missing"); continue
        pool = extract_pool(pq, method)
        state = classify_pool_state(pool, gt.get("gt_fact_text","") or "", gt.get("old_fact_text","") or "")
        resp = pq.get("response", "") or ""
        acc = em_check(resp, gt.get("gt_answer"))
        print(f"--- {method}")
        print(f"    Pool ({len(pool)} entries) state = {state}")
        # Show pool entries that mention gt_new or gt_old subject
        gt_new_s = (gt.get('gt_fact_text') or '').lower().split(' is ')[0].split(' was ')[0].split(' plays ')[0]
        matching = [t for t in pool if gt_new_s and gt_new_s.strip() in t.lower()][:6]
        if matching:
            print(f"    Pool matches on subject ~{gt_new_s.strip()!r}:")
            for i, m in enumerate(matching):
                marks = []
                if match_pair(m, gt.get("gt_fact_text","") or "", gt.get("old_fact_text","") or "", "new"):
                    marks.append("NEW")
                if match_pair(m, gt.get("gt_fact_text","") or "", gt.get("old_fact_text","") or "", "old"):
                    marks.append("OLD")
                mark_s = f" [{','.join(marks)}]" if marks else ""
                print(f"      [{i}]{mark_s}  {m[:120]}")
        else:
            print(f"    (no pool entries mention gt_new subject)")
        print(f"    Response    : {resp[:150]!r}")
        print(f"    EM = {acc}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--length", default="64k")
    args = p.parse_args()

    # 64k case study picks — cover A/B/C/D/E + write-time damage story
    L = args.length
    # (qid, cases-to-compare) — cases include the "failing" method + peers for contrast
    ALL_METHODS = ["ours (no_p5)", "(b) mem0+P1", "Zep (k=10)"]

    if L == "64k":
        picks = [
            (0, ALL_METHODS),   # ours PP-New wrong AND Zep PP-Both wrong (interesting shared qid)
            (40, ALL_METHODS),  # ours PP-New wrong
            (85, ALL_METHODS),  # ours PP-Both wrong
            (20, ALL_METHODS),  # ours PP-OldOnly wrong
            (50, ALL_METHODS),  # mem0 PP-Both wrong
            (1, ALL_METHODS),   # mem0 PP-OldOnly wrong (canonical write-time damage)
            (11, ALL_METHODS),  # mem0 PP-Missing wrong
            (23, ALL_METHODS),  # Zep PP-OldOnly wrong (rare Zep case)
        ]
    else:
        picks = []

    for qid, methods in picks:
        trace(qid, L, methods)


if __name__ == "__main__":
    main()
