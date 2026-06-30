"""
Build a GT of ALL in-store conflict pairs in a context (not just the queried
ones), mapped via MQuAKE-CF requested_rewrites. Emits the same per-query/hops
shape A-WT consumes (one synthetic single-hop query per pair), so A-WT can run
over the full pair set for maximum statistical power on the scaling question.
"""
import argparse
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--ctx", required=True)
ap.add_argument("--mquake", default="/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return s.strip().rstrip(".").lower()


ctx = {}
for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", Path(args.ctx).read_text(), re.MULTILINE):
    ctx[norm(m.group(2))] = (int(m.group(1)), m.group(2).strip().rstrip("."))

mq = json.load(open(args.mquake))
seen = set()
queries = []
for c in mq:
    for rw in c.get("requested_rewrite", []):
        subj, prompt = rw.get("subject", ""), rw.get("prompt", "")
        tn = rw.get("target_new", {}).get("str", "")
        tt = rw.get("target_true", {}).get("str", "")
        if "{}" not in prompt or not tn or not tt:
            continue
        stem = prompt.format(subj)
        nt, ot = norm(f"{stem} {tn}"), norm(f"{stem} {tt}")
        if nt in ctx and ot in ctx:
            key = (ctx[ot][0], ctx[nt][0])
            if key in seen:
                continue
            seen.add(key)
            queries.append({
                "qa_pair_id": f"pair_{key[0]}_{key[1]}",
                "hops": [{
                    "conflict_type": "has_pair",
                    "old_seq": ctx[ot][0], "old_fact_text": ctx[ot][1],
                    "gt_seq": ctx[nt][0], "gt_fact_text": ctx[nt][1],
                }],
            })

json.dump(queries, open(args.out, "w"), ensure_ascii=False, indent=1)
print(f"context facts: {len(ctx)} | full in-store pairs: {len(queries)} | written: {args.out}")
