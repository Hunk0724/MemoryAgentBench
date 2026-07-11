"""Retrieval recall@K audit: does top-10 catch gt_new_fact as often as top-100?

For each FC-SH has_pair query, checks whether gt_new_fact appears in the top-K
retrieved memories (per stored `retrieved_memories` JSON, one file per query).

Two intended uses:
1. Justify top-10 for Q-llm-recency baseline (quantify recall saturation on ours
   store so choice of K doesn't confound the "LLM vs argmax on recency" test).
2. Quantify write-time L0 damage on (b) mem0+P1 store (top-100 recall of gt_new
   caps ~50%, evidence that destructive UPDATE removed the correct version;
   retrieval bandwidth cannot recover it).

Usage:
    python analysis/recall_at_k_check.py

Reads:
- analysis/results/sh_6k_mquake_analysis.json (has_pair ground truth)
- outputs/rag_retrieved/<agent>/k_100/factconsolidation_sh_6k/chunksize_512/
  query_{qid}_context_0.json (per-query retrieved_memories)

Uses matcher v4 (analysis/compute_m1_m2_m3.py::match_pair) for fact matching.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.compute_m1_m2_m3 import match_pair


def run(length="6k", ks=(10, 20, 50, 100), gt_file=None, dirs=None):
    if gt_file is None:
        gt_file = f"analysis/results/sh_{length}_mquake_analysis.json"
    GT = {r["query_id"]: r for r in json.load(open(gt_file)) if r.get("conflict_type") == "has_pair"}
    print(f"has_pair queries at {length}: {len(GT)}")

    if dirs is None:
        dirs = {
            "ours (main) store": f"outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5/k_100/factconsolidation_sh_{length}/chunksize_512",
            "(b) mem0+P1 store": f"outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/factconsolidation_sh_{length}/chunksize_512",
        }

    for label, base in dirs.items():
        if not os.path.isdir(base):
            print(f"\n{label}: DIR NOT FOUND {base}")
            continue
        print(f"\n=== {label} ===")
        for k in ks:
            n_new = 0; n_both = 0; n_total = 0; missed_new = []
            for qid, gt in GT.items():
                p = os.path.join(base, f"query_{qid}_context_0.json")
                if not os.path.exists(p):
                    continue
                mems = json.load(open(p)).get("retrieved_memories", [])[:k]
                fact_texts = [m.get("memory", "") for m in mems]
                gt_new_fact = gt.get("gt_fact_text", "")
                gt_old_fact = gt.get("old_fact_text", "")
                new_in = any(match_pair(f, gt_new_fact, gt_old_fact, "new") for f in fact_texts)
                old_in = any(match_pair(f, gt_new_fact, gt_old_fact, "old") for f in fact_texts)
                if new_in:
                    n_new += 1
                    if old_in:
                        n_both += 1
                else:
                    missed_new.append(qid)
                n_total += 1
            print(f"  top-{k:>3}: recall gt_new = {n_new}/{n_total} = {n_new/n_total*100:.1f}%; both-recalled = {n_both}/{n_total}")
            if k == 10 and missed_new:
                print(f"    top-10 missed gt_new qids (first 10): {missed_new[:10]}")


if __name__ == "__main__":
    length = sys.argv[1] if len(sys.argv) > 1 else "6k"
    run(length=length)
