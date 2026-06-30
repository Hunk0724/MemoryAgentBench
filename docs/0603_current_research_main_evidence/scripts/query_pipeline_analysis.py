"""
Query-pipeline analysis (retrieval -> inference), per (task, ctx).

Decomposes each query's outcome into:
  RETRIEVAL: were ALL the query's GT (current/correct) hop-facts retrieved into
             the top-k memories? did any STALE (old/superseded) fact leak in?
             (old-leak ties back to write-time: a leaked old fact == write-time
             failed to resolve that conflict, leaving both versions in store.)
  INFERENCE: given what was retrieved, did the LLM answer correctly (exact_match)?

Buckets (per query):
  clean-win        R-clean (all GT in, no old leak)  & correct
  inference-fail   R-clean                            & wrong   <- LLM/multi-hop/H2
  stale-leak-*     old fact leaked into retrieval (correct or wrong)
  retrieval-miss   some GT hop-fact NOT retrieved     (correct or wrong)

Matching is by normalized fact text (L2 extraction is verbatim, so GT fact text
== stored memory text up to case/trailing period).
"""
import argparse
import json
import glob
import re
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--rr", required=True, help="rag_retrieved dir with query_*_context_0.json")
ap.add_argument("--results", required=True, help="Conflict_Resolution results json")
ap.add_argument("--gt", required=True, help="mquake analysis json (mh: hops / sh: top-level)")
ap.add_argument("--mode", choices=["mh", "sh"], required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return s.strip().rstrip(".").lower() if s else ""


def hops_of(q):
    if args.mode == "mh":
        return q.get("hops", [])
    # sh: single hop at top level
    return [{"conflict_type": q.get("conflict_type"),
             "gt_fact_text": q.get("gt_fact_text"),
             "old_fact_text": q.get("old_fact_text")}]


gt = {q["query_id"]: q for q in json.load(open(args.gt))}
results = {d["qa_pair_id"].split("_no")[-1]: d for d in json.load(open(args.results))["data"]}

rows = []
for f in sorted(glob.glob(f"{args.rr}/query_*_context_0.json"),
                key=lambda p: int(re.search(r"query_(\d+)_", p).group(1))):
    qid = int(re.search(r"query_(\d+)_", f).group(1))
    if qid not in gt:
        continue
    rj = json.load(open(f))
    retrieved = {norm(m["memory"]) for m in rj.get("retrieved_memories", [])}
    em = bool(results.get(str(qid), {}).get("exact_match")) if str(qid) in results else None

    hops = hops_of(gt[qid])
    gt_facts = [norm(h.get("gt_fact_text")) for h in hops if h.get("gt_fact_text")]
    old_facts = [norm(h.get("old_fact_text")) for h in hops
                 if h.get("conflict_type") == "has_pair" and h.get("old_fact_text")]

    all_gt_in = all(g in retrieved for g in gt_facts) if gt_facts else None
    n_gt_in = sum(1 for g in gt_facts if g in retrieved)
    any_old_leak = any(o in retrieved for o in old_facts)
    n_old_leak = sum(1 for o in old_facts if o in retrieved)

    rows.append({"qid": qid, "em": em, "n_hops": len(hops),
                 "gt_facts": len(gt_facts), "gt_in": n_gt_in, "all_gt_in": all_gt_in,
                 "old_facts": len(old_facts), "old_leak": n_old_leak, "any_old_leak": any_old_leak})

# aggregate
n = len(rows)
em_rate = sum(1 for r in rows if r["em"]) / n * 100
buckets = Counter()
for r in rows:
    rclean = r["all_gt_in"] and not r["any_old_leak"]
    if r["all_gt_in"] is False:
        buckets["retrieval-miss " + ("(correct)" if r["em"] else "(WRONG)")] += 1
    elif r["any_old_leak"]:
        buckets["stale-leak " + ("(correct)" if r["em"] else "(WRONG)")] += 1
    else:  # r-clean
        buckets["clean " + ("win" if r["em"] else "INFERENCE-FAIL")] += 1

print(f"=== {args.mode.upper()} query pipeline | n={n} | EM={em_rate:.0f}% ===")
print(f"  retrieval: all-GT-retrieved {sum(1 for r in rows if r['all_gt_in'])}/{n}"
      f" | any-old-leak {sum(1 for r in rows if r['any_old_leak'])}/{n}")
print("  buckets (retrieval x answer):")
for k, v in sorted(buckets.items()):
    print(f"    {k:28s}: {v}")
# inference-side failure share among retrieval-clean queries
rclean = [r for r in rows if r["all_gt_in"] and not r["any_old_leak"]]
if rclean:
    inf_fail = sum(1 for r in rclean if not r["em"])
    print(f"  among retrieval-clean ({len(rclean)}): inference-fail {inf_fail} "
          f"({inf_fail/len(rclean)*100:.0f}%)  <- LLM/multi-hop/parametric")

json.dump({"em_rate": em_rate, "n": n, "buckets": dict(buckets), "rows": rows},
          open(args.out, "w"), ensure_ascii=False, indent=1)
print(f"  written: {args.out}")
