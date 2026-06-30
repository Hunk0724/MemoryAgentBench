"""FC-SH funnel analysis (Stage 0-2), denominator-explicit (raw m/n).

Stage 0: overall EM (/100)
Stage 1: EM by question type (CP=conflict-pair / SF=single-fact), from GT.
Stage 2: retrieval-state x Acc.
  - CP : top-100 contains new(gt)/old fact? -> new_only/both/old_only/neither ; Acc per bucket (m/n)
  - SF : top-100 contains the needed fact?  -> fact_in/fact_out ; Acc per bucket (m/n)
  Plus the CP retrieval-state DISTRIBUTION per method (cross-method comparison #1).

Data sources (per method):
  results : outputs/<out>/Conflict_Resolution/...results.json  (exact_match per qid)
  top-100 : outputs/rag_retrieved/<agent>/k_100/factconsolidation_sh_<L>/chunksize_512/query_<qid>_context_0.json
  GT      : analysis/results/sh_<L>_RUN_gt.json  (gt_fact_text=new, old_fact_text=old, conflict_type)

Usage: python fc_funnel.py <L>   (L in 6k/32k/64k)
"""
import json, re, sys, glob, os
from collections import Counter

L = sys.argv[1] if len(sys.argv) > 1 else "6k"
ROOT = "/home/yhchiang/MemoryAgentBench"

METHODS = {
    "vanilla": {
        "out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-rerun",
        "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun",
    },
    "ours(U5)": {
        "out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-u5",
        "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_u5",
    },
}

def norm(s):
    s = (s or "").lower().strip()
    s = re.sub(r'^\s*\d+\.\s*', '', s)
    s = re.sub(r'\s+', ' ', s).rstrip('.').strip()
    return s

def contains(memset, fact):
    f = norm(fact)
    if not f:
        return False
    return any(f == m or f in m or m in f for m in memset)

gt = {r["query_id"]: r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_RUN_gt.json"))}
CP = [q for q, g in gt.items() if g["conflict_type"] == "has_pair"]
SF = [q for q, g in gt.items() if g["conflict_type"] != "has_pair"]

def load_method(m):
    out = METHODS[m]["out"]; agent = METHODS[m]["agent"]
    rp = glob.glob(f"{ROOT}/outputs/{out}/Conflict_Resolution/factconsolidation_sh_{L}_*results.json")[0]
    d = json.load(open(rp)); rows = d if isinstance(d, list) else d.get("results", d.get("data", []))
    res = {r.get("query_id", i): r for i, r in enumerate(rows)}
    retdir = f"{ROOT}/outputs/rag_retrieved/{agent}/k_100/factconsolidation_sh_{L}/chunksize_512"
    ret = {}
    for q in gt:
        p = f"{retdir}/query_{q}_context_0.json"
        if os.path.exists(p):
            dd = json.load(open(p))
            ret[q] = {norm(x["memory"]) for x in dd.get("retrieved_memories", []) if isinstance(x, dict)}
        else:
            ret[q] = None
    return res, ret

def em(res, qids):
    c = sum(1 for q in qids if res[q].get("exact_match")); return c, len(qids)

print(f"\n{'='*70}\nFC-SH {L}  |  CP(conflict-pair)={len(CP)}  SF(single-fact)={len(SF)}\n{'='*70}")

loaded = {m: load_method(m) for m in METHODS}

# ---- Stage 0 / 1 ----
print("\n### Stage 0/1 — EM (correct/total) ###")
print(f"{'method':<12}{'overall':>14}{'conflict-pair':>16}{'single-fact':>14}")
for m in METHODS:
    res, _ = loaded[m]
    o = em(res, list(gt)); cp = em(res, CP); sf = em(res, SF)
    print(f"{m:<12}{o[0]:>3}/{o[1]:<10}{cp[0]:>4}/{cp[1]:<11}{sf[0]:>4}/{sf[1]:<9}")

# ---- Stage 2 ----
def cp_state(ret_set, g):
    if ret_set is None: return "NO_DUMP"
    has_new = contains(ret_set, g["gt_fact_text"]); has_old = contains(ret_set, g["old_fact_text"])
    return ("both" if has_new and has_old else "new_only" if has_new
            else "old_only" if has_old else "neither")

def sf_state(ret_set, g):
    if ret_set is None: return "NO_DUMP"
    return "fact_in" if contains(ret_set, g["gt_fact_text"]) else "fact_out"

for m in METHODS:
    res, ret = loaded[m]
    print(f"\n### Stage 2 — {m}: retrieval-state x Acc (correct/in-bucket) ###")
    # CP
    buck = {}
    for q in CP:
        st = cp_state(ret[q], gt[q]); buck.setdefault(st, []).append(q)
    print("  conflict-pair:")
    for st in ["new_only", "both", "old_only", "neither", "NO_DUMP"]:
        if st in buck:
            qs = buck[st]; c = sum(1 for q in qs if res[q].get("exact_match"))
            print(f"    {st:<10} n={len(qs):<3}  Acc={c}/{len(qs)}")
    # SF
    buck = {}
    for q in SF:
        st = sf_state(ret[q], gt[q]); buck.setdefault(st, []).append(q)
    print("  single-fact:")
    for st in ["fact_in", "fact_out", "NO_DUMP"]:
        if st in buck:
            qs = buck[st]; c = sum(1 for q in qs if res[q].get("exact_match"))
            print(f"    {st:<10} n={len(qs):<3}  Acc={c}/{len(qs)}")

# ---- Cross-method #1: CP retrieval-state distribution ----
print(f"\n### Cross-method — CP top-100 retrieval-state distribution (n / {len(CP)}) ###")
print(f"{'method':<12}{'new_only':>10}{'both':>8}{'old_only':>10}{'neither':>9}")
for m in METHODS:
    res, ret = loaded[m]
    dist = Counter(cp_state(ret[q], gt[q]) for q in CP)
    print(f"{m:<12}{dist.get('new_only',0):>10}{dist.get('both',0):>8}{dist.get('old_only',0):>10}{dist.get('neither',0):>9}")
