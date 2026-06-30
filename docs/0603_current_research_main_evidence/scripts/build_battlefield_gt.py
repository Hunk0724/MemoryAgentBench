"""
Build the FINAL-STORE battlefield GT for one length: cross-chunk conflict pairs
whose final store is NOT clean (old_only / both / neither) — the QA-relevant
"vanilla mem0 didn't resolve" set that covers H1-miss(R1) + H2-refuse(R2) +
A4 over-fire(R2), regardless of the awt event bucket. Plus a new_only control
sample for the eventual no-regression check.

Each item gets `final_store` (and keeps `write_time_fate` for mechanism tracing).
Excludes same-chunk (different mechanism; our method needs extraction redesign).
"""
import argparse, json, re

ap = argparse.ArgumentParser()
ap.add_argument("--expanded-tagged", required=True)
ap.add_argument("--vr-file", required=True)
ap.add_argument("--slice", required=True)
ap.add_argument("--control-n", type=int, default=50, help="how many new_only control items")
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return re.sub(r"\s+", " ", s.lower().strip().rstrip("."))


def stem(a, b):
    a, b = norm(a), norm(b); i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return a[:i].rstrip()


def parse_slice(s):
    if s.startswith("-") and ":" not in s:
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
ms = [norm(t) for t in mem.values()]


def ins(st, ans):
    k = st[: max(10, len(st) - 3)]
    return any(m.startswith(k) and norm(ans) in m for m in ms)


items = json.load(open(args.expanded_tagged))
battlefield, control = [], []
for it in items:
    if it.get("write_time_fate") == "same-chunk":
        continue
    st = stem(it["gt_fact_text"], it["old_fact_text"])
    ni, oi = ins(st, it["gt_answer"]), ins(st, it["old_answer"])
    fs = "both" if (ni and oi) else "new_only" if ni else "old_only" if oi else "neither"
    it = {**it, "final_store": fs}
    if fs in ("old_only", "both", "neither"):
        battlefield.append(it)
    elif fs == "new_only":
        control.append(it)

out = battlefield + control[: args.control_n]
json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
from collections import Counter
print(f"battlefield(unresolved)={len(battlefield)} "
      f"{dict(Counter(b['final_store'] for b in battlefield))} | "
      f"control(new_only)={min(len(control), args.control_n)} | total written={len(out)} -> {args.out}")
