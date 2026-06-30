"""
Classify each priority conflict pair by FINAL STORE STATE (from the replayed
vector_results final memory set — the QA-relevant ground truth, not the per-event
awt bucket), and cross with the reconstruction-QA EM.

store_has: new_only / old_only / both / neither (does the final store hold the
new fact's slot, the old fact's slot, both, or neither).
This is checked against the ACTUAL final memory texts (not top-k retrieval), so
it is the true store state.
"""
import argparse, json, re
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--vr-file", required=True)
ap.add_argument("--slice", required=True)
ap.add_argument("--priority-gt", required=True)
ap.add_argument("--qa-result", required=True, help="reconstruct_store_qa output (for EM)")
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return re.sub(r"\s+", " ", s.lower().strip().rstrip("."))


def parse_slice(s):
    if ":" not in s:
        return slice(int(s), None)
    a, b = s.split(":"); return slice(int(a) if a else None, int(b) if b else None)


lines = [json.loads(l) for l in open(args.vr_file)][parse_slice(args.slice)]
mem = {}
for ln in lines:
    for r in ln["vector_results"]["results"]:
        if r["event"] in ("ADD", "UPDATE"):
            mem[r["id"]] = r["memory"]
        elif r["event"] == "DELETE":
            mem.pop(r["id"], None)
memset = [norm(t) for t in mem.values()]


def common_stem(a, b):
    a, b = norm(a), norm(b); i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return a[:i].rstrip()


def in_store(stem, ans):
    key = stem[: max(10, len(stem) - 3)]
    return any(m.startswith(key) and norm(ans) in m for m in memset)


qa = {r["qa_id"]: r for r in json.load(open(args.qa_result))["rows"]}
items = json.load(open(args.priority_gt))
tab = Counter()
detail = []
for it in items:
    stem = common_stem(it["gt_fact_text"], it["old_fact_text"])
    new_in = in_store(stem, it["gt_answer"])
    old_in = in_store(stem, it["old_answer"])
    store = ("both" if (new_in and old_in) else "new_only" if new_in
             else "old_only" if old_in else "neither")
    em = bool(qa.get(it["qa_id"], {}).get("EM"))
    tab[(it.get("write_time_fate"), store, em)] += 1
    detail.append({"qa_id": it["qa_id"], "fate": it.get("write_time_fate"),
                   "final_store": store, "EM": em,
                   "output": qa.get(it["qa_id"], {}).get("output")})

# grids
by_store = {}
for (fate, store, em), n in tab.items():
    d = by_store.setdefault(store, {"n": 0, "em": 0})
    d["n"] += n; d["em"] += n if em else 0
genuinely_unresolved = sum(d["n"] for s, d in by_store.items() if s in ("old_only", "both", "neither"))
gu_em = sum(d["em"] for s, d in by_store.items() if s in ("old_only", "both", "neither"))

json.dump({"by_store": by_store, "detail": detail,
           "genuinely_unresolved_n": genuinely_unresolved,
           "genuinely_unresolved_EM": round(100 * gu_em / genuinely_unresolved, 1) if genuinely_unresolved else None},
          open(args.out, "w"), ensure_ascii=False, indent=1)

print(f"priority items={len(items)} | final memories={len(memset)}")
print("=== final store state x EM ===")
for store in ("new_only", "both", "old_only", "neither"):
    if store in by_store:
        d = by_store[store]
        print(f"  {store:9} n={d['n']:3}  EM={round(100*d['em']/d['n'],1):5}")
print(f"--- 真未解決(old_only+both+neither)n={genuinely_unresolved}  EM={round(100*gu_em/genuinely_unresolved,1) if genuinely_unresolved else None} ---")
print("written:", args.out)
