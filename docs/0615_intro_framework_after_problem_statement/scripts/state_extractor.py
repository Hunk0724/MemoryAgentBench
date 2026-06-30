"""Per-method L1/L2 + state->EM extractor (mem0-family: ours / (a)vanilla /
(b)mem0+P1). Reads each method's saved per-query JSONs (retrieved_memories +
memories_str) + GT, classifies has_pair context state:
  L1 (retrieved top-k):  {both, new_only, old_only, neither}
  L2 (final context fed to answer LLM): same 4 states
  L3 state->EM: per L2 state, (n, correct)
Output: analysis/results/phase0/state_eval_current.json  (feeds evidence figures)

The narrative: ours keeps both versions -> L1 both -> L2 collapses to new_only;
destructive (b) deletes a version at write-time -> never retrievable (old_only/
neither at L1); native (a) extracts ~nothing -> neither.
"""
import json, glob, re, os
from collections import defaultdict

ROOT = __import__("os").environ.get("REPO_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3])
METH = {  # name -> (rag_retrieved agent dir, result-json output dir)
    "ours":       ("Structure_rag_gpt-4o-mini-mem0_512_openai_unified",       "gpt-4o-mini-mem0-chunk512-temp0-openai-unified"),
    "(a)vanilla": ("Structure_rag_gpt-4o-mini-mem0_512_openai_native",        "gpt-4o-mini-mem0-chunk512-temp0-openai-native"),
    "(b)mem0+P1": ("Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest",  "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest"),
}
LENS = ["6k", "32k", "64k", "262k"]

def norm(t): return re.sub(r"\s+", " ", (t or "").strip().rstrip(".").lower())
def state(nin, oin): return "both" if nin and oin else "new_only" if nin else "old_only" if oin else "neither"

out = {}
for name, (adir, odir) in METH.items():
    for L in LENS:
        qd = f"{ROOT}/outputs/rag_retrieved/{adir}/k_100/factconsolidation_sh_{L}/chunksize_512"
        rfs = glob.glob(f"{ROOT}/outputs/{odir}/Conflict_Resolution/*sh_{L}*results*.json")
        if not glob.glob(f"{qd}/query_*.json") or not rfs:
            continue
        em = {r["query_id"]: bool(r.get("exact_match")) for r in json.load(open(rfs[0]))["data"]}
        gtmap = {r["query_id"]: r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_mquake_analysis.json")) if "query_id" in r}
        L1 = defaultdict(int); L2 = defaultdict(int)
        L3 = defaultdict(lambda: [0, 0])  # L2-state -> [n, correct]
        n = 0
        for qid, g in gtmap.items():
            if g.get("conflict_type") != "has_pair" or not g.get("matched"):
                continue
            fs = glob.glob(f"{qd}/query_{qid}_context_*.json")
            if not fs:
                continue
            q = json.load(open(fs[0])); n += 1
            new_t, old_t = norm(g["gt_fact_text"]), norm(g["old_fact_text"])
            rset = " ".join(norm(m.get("memory", "")) for m in q.get("retrieved_memories", []))
            ctx = norm(q.get("memories_str", ""))
            s1 = state(new_t in rset, old_t in rset)
            s2 = state(new_t in ctx, old_t in ctx)
            L1[s1] += 1; L2[s2] += 1
            L3[s2][0] += 1; L3[s2][1] += int(em.get(qid, False))
        out[f"{name}|{L}"] = {"n": n, "L1": dict(L1), "L2": dict(L2),
                              "L3": {k: v for k, v in L3.items()}}

os.makedirs(f"{ROOT}/analysis/results/phase0", exist_ok=True)
json.dump(out, open(f"{ROOT}/analysis/results/phase0/state_eval_current.json", "w"), ensure_ascii=False, indent=2)

# console summary
print(f"{'method|len':<18}{'n':>4}  L1(retrieved)                 L2(final ctx)")
for k, v in out.items():
    def fmt(d): return " ".join(f"{s}={d.get(s,0)}" for s in ["both", "new_only", "old_only", "neither"])
    print(f"{k:<18}{v['n']:>4}  {fmt(v['L1']):<30}{fmt(v['L2'])}")
print("\n-> analysis/results/phase0/state_eval_current.json")
