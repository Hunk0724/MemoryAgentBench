"""
Dissect an expanded-set QA run: for every failed-fate item, determine what the
top-100 retrieval actually contained (new fact / old fact / both / neither) and
cross with EM. Answers "why did some write-time failures still answer correctly?"

IMPORTANT consistency note: pass the fate from the SAME ingestion that produced
the QA store (i.e. tag with awt computed on this run's MEM0_CAND_LOG_DIR), else
fate labels can disagree with the store (gemini temp0 is not bit-deterministic,
so a separate re-ingest can resolve a pair the original run left as H1-miss).

Usage:
  python dissect_expanded_qa.py \
    --qa-result   logs/expanded_qa_6k_consistent.json \
    --tagged      analysis/results/expanded/sh_6k_EXPANDED_tagged.json \
    --rr          outputs/rag_retrieved/<agent>/k_100/factconsolidation_sh_6k/chunksize_512 \
    --out         logs/expanded_dissect_6k.json
"""
import argparse, json, re
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--qa-result", required=True)
ap.add_argument("--tagged", required=True)
ap.add_argument("--rr", required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return re.sub(r"\s+", " ", s.lower().strip().rstrip("."))


def common_stem(a, b):
    a, b = norm(a), norm(b)
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return a[:i].rstrip()


rows = json.load(open(args.qa_result))["rows"]
tagged = {it["qa_id"]: it for it in json.load(open(args.tagged))}

detail = []
tab = Counter()
for i, r in enumerate(rows):
    it = tagged[r["qa_id"]]
    # take fate from the (consistent) tagged GT, NOT the qa-result row, so fate and
    # store come from the same ingestion
    fate = it.get("write_time_fate", r.get("write_time_fate"))
    r = {**r, "write_time_fate": fate}
    if fate in ("resolved", "unmatched"):
        continue
    stem = common_stem(it["gt_fact_text"], it["old_fact_text"])
    na, oa = norm(it["gt_answer"]), norm(it["old_answer"])
    qf = Path(args.rr) / f"query_{i}_context_0.json"
    if not qf.exists():
        store = "no_retrieval_file"
    else:
        mems = [norm(m["memory"]) for m in json.load(open(qf))["retrieved_memories"]]
        key = stem[: max(10, len(stem) - 3)]
        slot = [m for m in mems if m.startswith(key)]
        new_in = any(na in m for m in slot)
        old_in = any(oa in m for m in slot)
        store = ("both" if (new_in and old_in) else "new_only" if new_in
                 else "old_only" if old_in else "neither")
    tab[(r["write_time_fate"], store, bool(r["exact_match"]))] += 1
    detail.append({"idx": i, "qa_id": r["qa_id"], "fate": r["write_time_fate"],
                   "store_has": store, "EM": bool(r["exact_match"]),
                   "stale_leak": bool(r["stale_leak"]),
                   "question": r["question"], "output": r["output"],
                   "gt_answer": it["gt_answer"], "old_answer": it["old_answer"]})

# summary grids
by_fate_store = {}
for (fate, store, em), n in tab.items():
    d = by_fate_store.setdefault(fate, {}).setdefault(store, {"EM_true": 0, "EM_false": 0})
    d["EM_true" if em else "EM_false"] += n

json.dump({"by_fate_store": by_fate_store, "detail": detail},
          open(args.out, "w"), ensure_ascii=False, indent=1)

print("=== failed-fate items: store_has x EM ===")
for fate in sorted(by_fate_store):
    print(f"  {fate}:")
    for store, d in sorted(by_fate_store[fate].items()):
        print(f"      {store:16} EM✓={d['EM_true']:3}  EM✗={d['EM_false']:3}")
print(f"\nwritten: {args.out}")
