"""Among a method's old_only conflict pairs (final store has OLD, not NEW),
split by whether the OLD version was VISIBLE to the update component, i.e. the
OLD fact was in the NEW fact's top-5 candidate pool at ingestion.

  VISIBLE  = old in new's top-5  -> update component SAW the conflict and still
             left old (no UPDATE) = pure conflict-RESOLUTION (judgement) failure
             = OUR MAIN-AXIS battlefield.
  INVISIBLE= old not retrieved as candidate -> candidate-miss (orthogonal retrieval),
             NOT the resolution-mechanism claim.

(old_only outcome already implies "not UPDATEd": had vanilla UPDATEd old->new the
store would hold new, i.e. new_only. So VISIBLE & old_only == "saw it, did NONE".)

Usage: python oldonly_visibility.py <L> [method]   method in {vanilla, ours(U5)}
"""
import json, re, sys, glob, os
from collections import Counter

L = sys.argv[1] if len(sys.argv) > 1 else "6k"
METH = sys.argv[2] if len(sys.argv) > 2 else "vanilla"
ROOT = "/home/yhchiang/MemoryAgentBench"
M = {
    "vanilla": {"out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-rerun",
                "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun",
                "log": "vanilla_rerun"},
    "ours(U5)": {"out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-u5",
                 "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_u5",
                 "log": "u5"},
}[METH]

def norm(s):
    s = (s or "").lower().strip()
    s = re.sub(r'^\s*\d+\.\s*', '', s)
    s = re.sub(r'\s+', ' ', s).rstrip('.').strip()
    return s
def hit(texts, fact):
    f = norm(fact)
    return bool(f) and any(f == t or f in t or t in f for t in texts)

gt = {r["query_id"]: r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_RUN_gt.json"))}
CP = [q for q, g in gt.items() if g["conflict_type"] == "has_pair"]

# final store replay -> old_only qids
retdir = f"{ROOT}/outputs/rag_retrieved/{M['agent']}/k_100/factconsolidation_sh_{L}/chunksize_512"
store = {}
for line in open(f"{retdir}/ingestion_context_0.jsonl"):
    for ev in json.loads(line).get("vector_results", {}).get("results", []):
        e, i, t = ev.get("event"), ev.get("id"), ev.get("memory")
        if e in ("ADD", "UPDATE") and t is not None: store[i] = t
        elif e == "DELETE": store.pop(i, None)
final = {norm(t) for t in store.values()}
old_only = [q for q in CP if hit(final, gt[q]["old_fact_text"]) and not hit(final, gt[q]["gt_fact_text"])]

# candidate pool: map normalized new_fact -> set of top5 candidate texts(norm)
candlog = f"{ROOT}/docs/0612_research_method_improve_with_evidence/logs/sh_{L}_{M['log']}/candidate_pool.jsonl"
new2cands = {}
for line in open(candlog):
    d = json.loads(line)
    for pf in d.get("per_fact_candidates", []):
        nf = norm(pf["new_fact"]); cs = {norm(c["text"]) for c in pf.get("top5", [])}
        new2cands.setdefault(nf, set()).update(cs)

def visible(g):
    nf = norm(g["gt_fact_text"]); old = norm(g["old_fact_text"])
    keys = [k for k in new2cands if k == nf or nf in k or k in nf]
    if not keys: return "NEW_NOT_LOGGED"
    cands = set().union(*[new2cands[k] for k in keys])
    return "VISIBLE" if hit(cands, old) else "INVISIBLE"

cnt = Counter(); rows = []
for q in old_only:
    v = visible(gt[q]); cnt[v] += 1
    rows.append((q, v, gt[q]["old_answer"], gt[q]["gt_answer"], gt[q]["question"][:42]))

n = len(old_only)
print(f"\nFC-SH {L}  method={METH}  |  CP={len(CP)}  old_only={n}")
print(f"  VISIBLE   (old in new's top-5, saw conflict, didn't UPDATE) = {cnt['VISIBLE']}/{n}"
      f"  ({100*cnt['VISIBLE']//n if n else 0}%)  <- MAIN-AXIS battlefield")
print(f"  INVISIBLE (old not a candidate; orthogonal retrieval)       = {cnt['INVISIBLE']}/{n}")
print(f"  NEW_NOT_LOGGED (new never an ingest fact / text mismatch)    = {cnt['NEW_NOT_LOGGED']}/{n}")
print("  --- per-case ---")
for q, v, oa, ga, ques in sorted(rows, key=lambda x: x[1]):
    print(f"    qid {q:>3}  {v:<14} old='{oa}' -> new='{ga}'  | {ques}")
