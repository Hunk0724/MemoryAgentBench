"""
Build the 32k conflict-pair GT by re-applying the SAME MQuAKE alignment used for
6k (analyze_mh_512_mquake.py: a hop's GT/old fact == cloze+answer text, located
in the context by exact text match) — only the context (and thus seq positions)
change.

Method: take each hop's gt_fact_text / old_fact_text from the 6k analysis (these
ARE the MQuAKE-derived sentences) and look them up in the 32k context to get the
32k seq. Verified faithful: all 322 conflict-pair sentences match the 32k context
verbatim (build_32k_gt verification). Output mirrors mh_512_mquake_analysis.json
structure so A-WT / full-accounting consume it unchanged.
"""
import json
import re
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
SRC = BASE / "analysis/results/mh_512_mquake_analysis.json"
CTX32 = BASE / "analysis/contexts/factconsolidation_32k_context.txt"
OUT = BASE / "analysis/results/mh_32k_mquake_analysis.json"


def ctx_index(path):
    by_lower = {}
    for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", path.read_text(), re.MULTILINE):
        by_lower[m.group(2).strip().rstrip(".").lower()] = int(m.group(1))
    return by_lower


def lookup(by_lower, text):
    if not text:
        return None
    return by_lower.get(text.strip().rstrip(".").lower())


def main():
    src = json.load(open(SRC))
    by_lower = ctx_index(CTX32)
    print(f"32k context facts: {len(by_lower)}")

    n_hops = n_gt_ok = n_old_ok = n_haspair = 0
    for q in src:
        for h in q.get("hops", []):
            n_hops += 1
            gt = lookup(by_lower, h.get("gt_fact_text"))
            if gt is not None:
                h["gt_seq"] = gt; n_gt_ok += 1
            if h.get("conflict_type") == "has_pair":
                n_haspair += 1
                old = lookup(by_lower, h.get("old_fact_text"))
                if old is not None:
                    h["old_seq"] = old; n_old_ok += 1
        # drop 6k-context-specific retrieval fields that no longer apply at 32k
        for f in ("gt_retrieved", "gt_rank", "gt_ppr", "old_retrieved", "old_rank",
                  "old_ppr", "same_passage", "retrieval_scores"):
            q.pop(f, None)
            for h in q.get("hops", []):
                h.pop(f, None)

    json.dump(src, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"hops: {n_hops} | gt remapped: {n_gt_ok} | has_pair: {n_haspair} | old remapped: {n_old_ok}")
    print(f"written: {OUT}")
    if n_old_ok != n_haspair:
        print(f"[WARN] {n_haspair-n_old_ok} has_pair hops failed to remap old_seq")


if __name__ == "__main__":
    main()
