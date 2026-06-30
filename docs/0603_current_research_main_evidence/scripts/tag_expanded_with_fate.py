"""
Enrich the expanded SH GT with each pair's vanilla-mem0 WRITE-TIME fate, taken
from the existing ingestion output (awt_result.json `rows`, computed from the
completed run's extraction/candidate/update logs — no re-ingestion).

write_time_fate in {resolved, H1-miss, H2-refuse, same-chunk}. The "priority"
evaluation set = items whose fate != resolved: these are exactly the conflict
pairs vanilla mem0 failed to consolidate at write time, i.e. the places a new
conflict-mechanism design must improve first. The resolved items are the control
group (a good design must KEEP these correct).

Output: a copy of the expanded GT with added fields
  write_time_fate, wt_loser_in_top5, wt_loser_rank, wt_update_idx
and two convenience files: <out>.priority.json (failed) for quick QA.
"""
import argparse, json
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--expanded", required=True)
ap.add_argument("--awt", required=True, help="awt_result.json from the SAME run's ingestion logs")
ap.add_argument("--out", required=True)
args = ap.parse_args()

awt = json.load(open(args.awt))
# key each awt row by the unordered (old_seq, gt_seq) context pair
fate = {}
for r in awt["rows"]:
    k = frozenset((r["old_seq"], r["gt_seq"]))
    fate[k] = r

items = json.load(open(args.expanded))
matched = 0
for it in items:
    k = frozenset((it["old_seq"], it["gt_seq"]))
    r = fate.get(k)
    if r:
        matched += 1
        it["write_time_fate"] = r["bucket"]
        it["wt_loser_in_top5"] = r.get("loser_in_top5")
        it["wt_loser_rank"] = r.get("loser_rank_in_winner_top5")
        it["wt_update_idx"] = r.get("update_idx")
    else:
        it["write_time_fate"] = "unmatched"

json.dump(items, open(args.out, "w"), ensure_ascii=False, indent=1)
priority = [it for it in items if it["write_time_fate"] not in ("resolved", "unmatched")]
json.dump(priority, open(args.out.replace(".json", ".priority.json"), "w"),
          ensure_ascii=False, indent=1)

dist = Counter(it["write_time_fate"] for it in items)
print(f"expanded={len(items)} matched_to_awt={matched} | fate={dict(dist)}")
print(f"priority(failed)={len(priority)} -> {args.out.replace('.json','.priority.json')}")
