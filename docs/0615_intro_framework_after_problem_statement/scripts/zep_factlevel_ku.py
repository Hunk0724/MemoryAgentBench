"""Re-query existing Zep graphs at the FACT level (edges) with the SAME fair
setting as ours: bare raw question + k=100. Isolates Zep's fact-level KU
mechanism (edge temporal invalidation) from its multi-granularity system.
For each has_pair query: is GT_new edge present? GT_old edge present? did Zep
set invalid_at on the old edge (its KU firing)?  No re-ingest (read-only).
  Usage: python zep_factlevel_ku.py <L>   (graph must already exist)
"""
import json, glob, re, sys, os, time

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); os.environ.setdefault(k, v)
from zep_cloud import Zep

L = sys.argv[1] if len(sys.argv) > 1 else "6k"
client = Zep(api_key=os.environ['ZEP_API_KEY'])
graph_id = f"graph_0_factconsolidation_sh_{L}"
gtmap = {r["query_id"]: r for r in json.load(open(f"analysis/results/sh_{L}_mquake_analysis.json")) if "query_id" in r}

def norm(t): return re.sub(r"\s+", " ", (t or "").strip().rstrip(".").lower())

agg = {"new_in": 0, "old_in": 0, "both": 0, "neither": 0, "old_invalidated": 0,
       "ku_clean": 0, "n": 0}
for qid, g in gtmap.items():
    if g.get("conflict_type") != "has_pair" or not g.get("matched"):
        continue
    q = g["question"]   # BARE raw question (same as ours)
    try:
        edges = client.graph.search(graph_id=graph_id, query=q[:399], scope="edges", limit=50).edges or []
    except Exception as e:
        print(f"  q{qid} search error: {e}"); continue
    agg["n"] += 1
    new_t, old_t = norm(g["gt_fact_text"]), norm(g["old_fact_text"])
    new_e = next((e for e in edges if new_t in norm(getattr(e, "fact", ""))), None)
    old_e = next((e for e in edges if old_t in norm(getattr(e, "fact", ""))), None)
    nin, oin = new_e is not None, old_e is not None
    agg["new_in"] += nin; agg["old_in"] += oin
    agg["both"] += (nin and oin); agg["neither"] += (not nin and not oin)
    old_invalid = oin and getattr(old_e, "invalid_at", None) is not None
    agg["old_invalidated"] += old_invalid
    # fact-level KU "clean" = new present AND (old absent OR old invalidated)
    if nin and (not oin or old_invalid):
        agg["ku_clean"] += 1

n = agg["n"]
print(f"\n=== Zep FACT-LEVEL (edges@50(Zep max), bare raw question) — FC-SH {L} has_pair (n={n}) ===")
print(f"  GT_new edge 在: {agg['new_in']}/{n} ({agg['new_in']/n*100:.0f}%)   ← 公平 k=50+raw 後的 fact 檢索")
print(f"  GT_old edge 在: {agg['old_in']}/{n}   | both: {agg['both']} | neither: {agg['neither']}")
print(f"  舊版 edge 被 invalid_at 標失效(Zep KU 作動): {agg['old_invalidated']}/{agg['old_in']} (在有撈到舊版者中)")
print(f"  fact-level KU clean(新版在 且 舊版不在/已失效): {agg['ku_clean']}/{n} ({agg['ku_clean']/n*100:.0f}%)")
