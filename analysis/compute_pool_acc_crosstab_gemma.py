"""Tier-1 (evaluation_protocol_main §4.2): return_context x Acc 4x2 cross-tab.

For each method x backbone, classify every has_pair query by (a) the POOL STATE of
the resolved context actually sent to the answer LLM — Both / new_only / old_only /
Neither (from per-query new_in/old_in) — and (b) Acc (exact-match ✓/✗). This is the
RIGOROUS attribution the protocol adopts INSTEAD of Resolution-alone: it separates
"pool isolates NEW" from "reader answered right", showing e.g. Both→✓ (reader picked
new from a mixed pool) vs new_only→✗ (reader override on a clean pool).

GX10 weak-model (gemma3) FC-SH 6k, methods ours_struct / ours_no_p5, from
analysis/results/resolution_per_query{,_no_p5}_6k_<size>.json (pool = post
group_and_resolve / phase2_resolve context). No GPU / embedding.
  python3 analysis/compute_pool_acc_crosstab.py > <out>.md
"""
import json, os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
SIZES = ["1b", "4b", "12b", "27b"]
METHODS = [("ours_struct", "resolution_per_query_6k_{}.json"),
           ("ours_no_p5", "resolution_per_query_no_p5_6k_{}.json")]


def state(v):
    n, o = v["new_in"], v["old_in"]
    return "both" if (n and o) else "new_only" if n else "old_only" if o else "neither"


print("# return_context × Acc cross-tab — GX10 weak-model (gemma3), FC-SH 6k has_pair")
print()
print("> Pool state = version-state of the resolved context sent to the answer LLM. "
      "Acc = has_pair exact-match. N=74. Reading: `new_only→✓` = method isolated NEW "
      "and reader used it; `both→✓` = reader picked NEW from a mixed pool (method did "
      "not isolate, reader rescued); `new_only→✗` = reader override on a clean pool; "
      "`old_only/neither→✗` = new version absent from pool (extraction/write loss).")
print()
ORDER = ["new_only", "both", "old_only", "neither"]
for mname, patt in METHODS:
    print(f"## {mname}")
    print()
    print("| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM |")
    print("| :-- | :-: | :-: | :-: | :-: | :-: |")
    for s in SIZES:
        p = f"analysis/results/{patt.format(s)}"
        if not os.path.exists(p):
            print(f"| {s} | _missing_ | | | | |"); continue
        d = json.load(open(p))
        cell = {st: [0, 0] for st in ORDER}   # [✓, ✗]
        for v in d.values():
            cell[state(v)][0 if v["em"] else 1] += 1
        em = sum(1 for v in d.values() if v["em"])
        row = " | ".join(f"{cell[st][0]}/{cell[st][1]}" for st in ORDER)
        print(f"| {s} | {row} | {em}/74 |")
    print()
print("**How to read the attribution:**")
print("- **new_only ✓** = method (pool isolates NEW) + reader both worked — the clean win.")
print("- **both ✓** = reader RESCUE (mixed pool, reader still picked NEW).")
print("- **new_only ✗** = reader OVERRIDE (clean pool, reader answered OLD from prior) — the 27B drag.")
print("- **old_only / neither ✗** = NEW absent from the pool (weak extraction/retrieval) — the 1B/4B floor.")
