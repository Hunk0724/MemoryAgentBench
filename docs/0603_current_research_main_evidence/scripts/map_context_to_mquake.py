"""
Authoritative conflict/single composition of a FC context, mapped to MQuAKE-CF.

A MQuAKE-CF requested_rewrite gives, for an edited (subject, relation):
    old fact = prompt.format(subject) + " " + target_true.str
    new fact = prompt.format(subject) + " " + target_new.str
A context fact is:
    conflict-new  : matches a rewrite's new form, and its old partner is ALSO present  -> a real in-store pair
    conflict-old  : matches a rewrite's old form, and its new partner is ALSO present
    new-only/old-only : matches a rewrite but the partner is absent from the context
    single        : matches no rewrite (a non-edited / real chain fact)

Run for any context (6k/32k/64k) with --ctx.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--ctx", required=True)
ap.add_argument("--mquake", default="/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")
args = ap.parse_args()


def norm(s):
    return s.strip().rstrip(".").lower()


# context: norm(text) -> seq
ctx = {}
for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", Path(args.ctx).read_text(), re.MULTILINE):
    ctx[norm(m.group(2))] = int(m.group(1))
N = len(ctx)
print(f"context facts: {N}")

mq = json.load(open(args.mquake))
# enumerate every edit's old/new fact text
new_to_old = {}   # norm(new_text) -> norm(old_text)
old_to_new = {}
for c in mq:
    for rw in c.get("requested_rewrite", []):
        subj = rw.get("subject", "")
        prompt = rw.get("prompt", "")
        if "{}" not in prompt:
            continue
        stem = prompt.format(subj)
        tn = rw.get("target_new", {}).get("str", "")
        tt = rw.get("target_true", {}).get("str", "")
        if not tn or not tt:
            continue
        nt, ot = norm(f"{stem} {tn}"), norm(f"{stem} {tt}")
        new_to_old[nt] = ot
        old_to_new[ot] = nt
print(f"MQuAKE edits enumerated: new forms={len(new_to_old)}")

# classify each context fact
cls = Counter()
pair_present = set()  # canonical (old_seq?) — track present pairs by old text
for txt, seq in ctx.items():
    if txt in new_to_old:
        old = new_to_old[txt]
        if old in ctx:
            cls["conflict-new (pair present)"] += 1
            pair_present.add(old)
        else:
            cls["new-only (old absent)"] += 1
    elif txt in old_to_new:
        new = old_to_new[txt]
        if new in ctx:
            cls["conflict-old (pair present)"] += 1
        else:
            cls["old-only (new absent)"] += 1
    else:
        cls["single (no edit)"] += 1

print("\n=== context composition (mapped to MQuAKE-CF) ===")
for k, v in cls.most_common():
    print(f"  {k:28s}: {v}  ({v/N*100:.1f}%)")
n_pairs = len(pair_present)
print(f"\n  in-store conflict PAIRS (both versions present): {n_pairs}")
print(f"  facts in those pairs                           : {n_pairs*2}")
print(f"  single/new-only/old-only (non-pair) facts      : {N - n_pairs*2}")
