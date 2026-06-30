"""L0 memory-BANK state: scan the ENTIRE store (not top-k) for each FC-SH length
and ask, per has_pair question, whether GT_new / GT_old are present in the bank.
Same full-fact matcher as the L1 (retrieved) state, so L0 vs L1 is directly
comparable:
  L0 missing NEW (old_only/neither)  -> the WRITE-TIME update destroyed the answer
                                         in the bank -> irreversible (retrieval can't help).
  L0 has NEW but L1 missing it       -> the bank kept it; only top-k retrieval missed.
Vector-memory methods only (mem0-family); Zep excluded (non-destructive: raw
episodes keep every version -> bank trivially has both -> nothing to detect).

Output: analysis/results/phase0/l0_bank_state.json  (+ console L0-vs-L1 table)
"""
import json, re, os
from collections import defaultdict
from qdrant_client import QdrantClient

ROOT = __import__("os").environ.get("REPO_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3])
STORE = f"{ROOT}/analysis/results/expanded/stores"
LENS = ["6k", "32k", "64k", "262k"]
METH = {  # display -> store tag
    "ours": "unified", "(b)mem0+P1": "unified_dest", "(a)vanilla": "native",
}

def norm(t): return re.sub(r"\s+", " ", (t or "").strip().rstrip(".").lower())
def state(nin, oin): return "both" if nin and oin else "new_only" if nin else "old_only" if oin else "neither"

def bank_blob(tag, L):
    p = f"{STORE}/qdrant_gpt4o_512_openai_{tag}__factconsolidation_sh_{L}"
    if not os.path.isdir(p):
        return None
    c = QdrantClient(path=p)
    try:
        col = c.get_collections().collections[0].name
        texts, off = [], None
        while True:
            pts, off = c.scroll(col, limit=2000, offset=off, with_payload=True, with_vectors=False)
            texts += [norm(pt.payload.get("data") or pt.payload.get("memory") or "") for pt in pts]
            if off is None:
                break
        return " || ".join(texts), len(texts)
    finally:
        c.close()

out = {}
for name, tag in METH.items():
    for L in LENS:
        res = bank_blob(tag, L)
        if not res:
            continue
        blob, nfacts = res
        gt = [r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_mquake_analysis.json"))
              if r.get("conflict_type") == "has_pair" and r.get("matched")]
        st = defaultdict(int)
        for g in gt:
            st[state(norm(g["gt_fact_text"]) in blob, norm(g["old_fact_text"]) in blob)] += 1
        out[f"{name}|{L}"] = {"n": len(gt), "n_facts": nfacts, "L0": dict(st)}

os.makedirs(f"{ROOT}/analysis/results/phase0", exist_ok=True)
json.dump(out, open(f"{ROOT}/analysis/results/phase0/l0_bank_state.json", "w"), indent=2)

# console: L0 (bank) vs L1 (retrieved) recoverable%
L1 = json.load(open(f"{ROOT}/analysis/results/phase0/state_eval_current.json"))
print(f"{'method|len':<16}{'bank_facts':>11}{'L0_recov':>10}{'L1_recov':>10}   verdict")
for k, v in out.items():
    d = v["L0"]; n = v["n"]
    l0 = (d.get("both", 0) + d.get("new_only", 0)) / n * 100
    l1 = ""
    verdict = ""
    if k in L1:
        ld = L1[k]["L1"]; l1v = (ld.get("both", 0) + ld.get("new_only", 0)) / L1[k]["n"] * 100
        l1 = f"{l1v:.0f}%"
        if l0 < 70:
            verdict = "BANK missing NEW -> write-time destruction"
        elif l0 - l1v > 15:
            verdict = "bank has NEW; top-k retrieval missed"
        else:
            verdict = "bank & retrieval consistent"
    print(f"{k:<16}{v['n_facts']:>11}{l0:>9.0f}%{l1:>10}   {verdict}")
print("\n-> analysis/results/phase0/l0_bank_state.json")
