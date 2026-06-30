"""Build sh_<LEN>_mquake_analysis.json for a length that lacks one (e.g. 64k),
reusing the SAME alignment as check_mquake_coverage.py / analyze_lca_mquake.py
(HF arrow questions -> MQuAKE-CF -> per-hop gt_seq/old_seq/conflict_type), plus
gt_fact_text/old_fact_text via the context. Schema-compatible with the existing
sh_512 / sh_32k analysis files (subset of fields used by our breakdown + L2).

Run: python docs/0615_.../scripts/build_sh_analysis.py 64k
"""
import json
import sys
from pathlib import Path

ROOT = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(ROOT / "analysis"))
from analyze_lca_mquake import (  # noqa: E402
    find_hop_gt,
    find_hop_old,
    load_mquake_index,
    parse_context,
)
from check_mquake_coverage import (  # noqa: E402
    align_one,
    load_arrow_rows,
    question_from_query,
)

LEN = sys.argv[1] if len(sys.argv) > 1 else "64k"
MODE = "sh"
OUT = ROOT / f"analysis/results/{MODE}_{LEN}_mquake_analysis.json"

_, sh_idx, mh_idx = load_mquake_index()
rows = load_arrow_rows()
src = f"factconsolidation_{MODE}_{LEN}"
row = next(r for r in rows if (r.get("metadata") or {}).get("source") == src)
questions, answers = row["questions"], row["answers"]

ctx_text = (ROOT / f"analysis/contexts/factconsolidation_{LEN}_context.txt").read_text(encoding="utf-8")
ctx_lines, ctx_by_lower = parse_context(ctx_text)
ctx_by_seq = {n: t for n, t in ctx_lines}

out, n_match, conf = [], 0, {"has_pair": 0, "no_conflict_pair": 0, "answer_not_in_ctx": 0}
for i, q in enumerate(questions):
    bare = question_from_query(q) if "Now Answer the Question" in q else q
    gt = answers[i] if isinstance(answers[i], list) else [answers[i]]
    res = align_one(MODE, bare, gt, sh_idx, mh_idx, ctx_lines, ctx_by_lower)
    rec = {"query_id": i, "question": bare, "gt_answer": (gt[0] if gt else None),
           "matched": res.get("matched", False)}
    if res.get("matched") and res.get("hops"):
        h = res["hops"][0]
        rec.update({
            "case_id": res["case_id"], "hop_idx": h["hop_idx"],
            "gt_seq": h["gt_seq"], "old_seq": h["old_seq"],
            "conflict_type": h["conflict_type"],
            "gt_fact_text": ctx_by_seq.get(h["gt_seq"]) if h["gt_seq"] is not None else None,
            "old_fact_text": ctx_by_seq.get(h["old_seq"]) if h["old_seq"] is not None else None,
        })
        n_match += 1
        conf[h["conflict_type"]] = conf.get(h["conflict_type"], 0) + 1
    out.append(rec)

OUT.parent.mkdir(parents=True, exist_ok=True)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[{MODE}_{LEN}] matched {n_match}/{len(questions)} | conflict dist {conf}")
print(f"  -> {OUT}")
