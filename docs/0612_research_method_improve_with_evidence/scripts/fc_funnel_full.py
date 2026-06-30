"""FC-SH full funnel (Stage 0-4) + cross-method final-store transition matrix.
Denominator-explicit (raw m/n) for fair cross-method comparison.

PURPOSE: isolate "conflict-pair failure caused by the update component
corrupting the memory store (write-time)" from orthogonal causes
(retrieval R / inference Z / same-chunk). This is the battlefield the
structural claim must own.

Stages:
  0 overall EM (/100)
  1 EM by question type (CP / SF), from GT
  2 retrieval-state x Acc  (top-100 contains new/old) -> new_only/both/old_only/neither ; SF fact_in/out
  3 of conflict-pair WRONG: is new(gt) in the FINAL store?  -> write-time vs retrieval(R)/inference(Z)
  4 write-time failures subclass: old_only / neither{D0,D1,D2}
  T cross-method FINAL-STORE state transition matrix (vanilla -> ours), per conflict pair

Data:
  results : outputs/<out>/Conflict_Resolution/...results.json
  top-100 : outputs/rag_retrieved/<agent>/k_100/factconsolidation_sh_<L>/chunksize_512/query_<qid>_context_0.json
  events  : .../ingestion_context_0.jsonl  (vector_results.results = ADD/UPDATE/DELETE per chunk)
  GT      : analysis/results/sh_<L>_RUN_gt.json
"""
import json, re, sys, glob, os
from collections import Counter, defaultdict

L = sys.argv[1] if len(sys.argv) > 1 else "6k"
ROOT = "/home/yhchiang/MemoryAgentBench"
METHODS = {
    "vanilla": {"out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-rerun",
                "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun"},
    "ours(U5)": {"out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-u5",
                 "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_u5"},
}

def norm(s):
    s = (s or "").lower().strip()
    s = re.sub(r'^\s*\d+\.\s*', '', s)
    s = re.sub(r'\s+', ' ', s).rstrip('.').strip()
    return s

def has(memset, fact):
    f = norm(fact)
    return bool(f) and any(f == m or f in m or m in f for m in memset)

gt = {r["query_id"]: r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_RUN_gt.json"))}
CP = [q for q, g in gt.items() if g["conflict_type"] == "has_pair"]
SF = [q for q, g in gt.items() if g["conflict_type"] != "has_pair"]

def load(m):
    out, agent = METHODS[m]["out"], METHODS[m]["agent"]
    rp = glob.glob(f"{ROOT}/outputs/{out}/Conflict_Resolution/factconsolidation_sh_{L}_*results.json")[0]
    d = json.load(open(rp)); rows = d if isinstance(d, list) else d.get("results", d.get("data", []))
    res = {r.get("query_id", i): r for i, r in enumerate(rows)}
    retdir = f"{ROOT}/outputs/rag_retrieved/{agent}/k_100/factconsolidation_sh_{L}/chunksize_512"
    ret = {}
    for q in gt:
        p = f"{retdir}/query_{q}_context_0.json"
        ret[q] = ({norm(x["memory"]) for x in json.load(open(p)).get("retrieved_memories", []) if isinstance(x, dict)}
                  if os.path.exists(p) else None)
    # replay final store from ingestion events
    store = {}                 # id -> current text
    produced = set()           # norm(text) ever placed in store (ADD or UPDATE)
    epath = f"{retdir}/ingestion_context_0.jsonl"
    for line in open(epath):
        for ev in json.loads(line).get("vector_results", {}).get("results", []):
            e, i, t = ev.get("event"), ev.get("id"), ev.get("memory")
            if e in ("ADD", "UPDATE") and t is not None:
                store[i] = t; produced.add(norm(t))
            elif e == "DELETE":
                store.pop(i, None)
    final = {norm(t) for t in store.values()}
    return res, ret, final, produced

DATA = {m: load(m) for m in METHODS}

print(f"\n{'='*72}\nFC-SH {L}  |  CP={len(CP)}  SF={len(SF)}\n{'='*72}")

# Stage 0/1
print("\n### Stage 0/1 EM (correct/total) ###")
print(f"{'method':<11}{'overall':>13}{'conflict-pair':>16}{'single-fact':>14}")
for m in METHODS:
    res = DATA[m][0]
    o = sum(res[q].get('exact_match') for q in gt)
    c = sum(res[q].get('exact_match') for q in CP); s = sum(res[q].get('exact_match') for q in SF)
    print(f"{m:<11}{o:>4}/{len(gt):<8}{c:>4}/{len(CP):<11}{s:>4}/{len(SF):<9}")

def cp_ret(ret, g):
    if ret is None: return "NO_DUMP"
    n, o = has(ret, g["gt_fact_text"]), has(ret, g["old_fact_text"])
    return "both" if n and o else "new_only" if n else "old_only" if o else "neither"
def cp_store(final, g):
    n, o = has(final, g["gt_fact_text"]), has(final, g["old_fact_text"])
    return "both" if n and o else "new_only" if n else "old_only" if o else "neither"

# Stage 2
for m in METHODS:
    res, ret, final, produced = DATA[m]
    print(f"\n### Stage 2 {m}: retrieval-state x Acc (correct/in-bucket) ###")
    b = defaultdict(list)
    for q in CP: b[cp_ret(ret[q], gt[q])].append(q)
    print("  CP:", {k: f"{sum(res[q].get('exact_match') for q in v)}/{len(v)}" for k, v in
                    sorted(b.items(), key=lambda x: ["new_only","both","old_only","neither","NO_DUMP"].index(x[0]))})
    b = defaultdict(list)
    for q in SF: b["fact_in" if (ret[q] and has(ret[q], gt[q]["gt_fact_text"])) else "fact_out"].append(q)
    print("  SF:", {k: f"{sum(res[q].get('exact_match') for q in v)}/{len(v)}" for k, v in b.items()})

# Stage 3/4 : conflict-pair WRONG -> cause
for m in METHODS:
    res, ret, final, produced = DATA[m]
    wrong = [q for q in CP if not res[q].get("exact_match")]
    cause = Counter()
    detail = defaultdict(list)
    for q in wrong:
        g = gt[q]
        new_in_top = ret[q] is not None and has(ret[q], g["gt_fact_text"])
        new_in_store = has(final, g["gt_fact_text"])
        old_in_store = has(final, g["old_fact_text"])
        new_produced = has(produced, g["gt_fact_text"]); old_produced = has(produced, g["old_fact_text"])
        if new_in_top:
            c = "Z_retrieved_but_wrong"
        elif new_in_store:
            c = "R_in_store_not_retrieved"
        elif old_in_store:
            c = "old_only(write-time)"
        else:  # neither in store
            if new_produced: c = "neither:D2_new_destroyed"
            elif old_produced: c = "neither:D1_old_removed_new_never"
            else: c = "neither:D0_omission"
        cause[c] += 1; detail[c].append(q)
    print(f"\n### Stage 3/4 {m}: conflict-pair WRONG (n={len(wrong)}) cause breakdown ###")
    for c in ["old_only(write-time)", "neither:D0_omission", "neither:D1_old_removed_new_never",
              "neither:D2_new_destroyed", "R_in_store_not_retrieved", "Z_retrieved_but_wrong"]:
        if cause.get(c): print(f"    {c:<34} {cause[c]:>3}/{len(wrong)}")
    wt = sum(cause[c] for c in cause if c.startswith(("old_only", "neither")))
    print(f"    --> write-time(store corrupted) = {wt}/{len(wrong)} ; downstream(R+Z) = {len(wrong)-wt}/{len(wrong)}")

# Transition matrix (final-store state) vanilla -> ours
print(f"\n### Cross-method: CP FINAL-STORE state transition  vanilla -> ours (n={len(CP)}) ###")
vf, of = DATA["vanilla"][2], DATA["ours(U5)"][2]
tm = Counter()
for q in CP:
    tm[(cp_store(vf, gt[q]), cp_store(of, gt[q]))] += 1
states = ["new_only", "both", "old_only", "neither"]
print(f"{'van\\ours':<10}" + "".join(f"{s:>10}" for s in states))
for vs in states:
    print(f"{vs:<10}" + "".join(f"{tm.get((vs,os_),0):>10}" for os_ in states))
print("  (diagonal=unchanged; below-left=ours fixed; above-right=ours regressed)")
