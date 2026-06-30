"""Two cross-method analyses the narrative needs:

A) Retrieval-state DISTRIBUTION comparison (vanilla vs ours), per length:
   among all conflict-pair questions, what the answering LLM actually saw
   in its top-100 (new_only / both / old_only / neither), with per-bucket Acc.
   This visualizes saturation: store-state vs retrieval-state gap.

B) Battlefield recovery: condition on VANILLA's failure cause per question
   (old_only / D0 / D1 / D2 / R / Z), report how many of each OURS answered
   correctly (recovered) vs still wrong. Plus the reverse: vanilla-correct ->
   ours-wrong regressions, with OURS' failure causes.

Usage: python battlefield_recovery.py <L>
"""
import json, re, sys, glob, os
from collections import Counter, defaultdict

L = sys.argv[1] if len(sys.argv) > 1 else "6k"
ROOT = "/home/yhchiang/MemoryAgentBench"
METHODS = {
    "vanilla": {"out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-rerun",
                "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun"},
    "ours": {"out": "gpt-4o-mini-mem0-chunk512-temp0-l2-openai-u5",
             "agent": "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_u5"},
}

def norm(s):
    s = (s or "").lower().strip()
    s = re.sub(r'^\s*\d+\.\s*', '', s); s = re.sub(r'\s+', ' ', s).rstrip('.').strip()
    return s
def has(S, f):
    f = norm(f); return bool(f) and any(f == m or f in m or m in f for m in S)

gt = {r["query_id"]: r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_RUN_gt.json"))}
CP = [q for q, g in gt.items() if g["conflict_type"] == "has_pair"]

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
    store = {}; produced = set()
    for line in open(f"{retdir}/ingestion_context_0.jsonl"):
        for ev in json.loads(line).get("vector_results", {}).get("results", []):
            e, i, t = ev.get("event"), ev.get("id"), ev.get("memory")
            if e in ("ADD", "UPDATE") and t is not None: store[i] = t; produced.add(norm(t))
            elif e == "DELETE": store.pop(i, None)
    final = {norm(t) for t in store.values()}
    return res, ret, final, produced

DATA = {m: load(m) for m in METHODS}

def rstate(ret, g):
    if ret is None: return "NO_DUMP"
    n, o = has(ret, g["gt_fact_text"]), has(ret, g["old_fact_text"])
    return "both" if n and o else "new_only" if n else "old_only" if o else "neither"

def cause(m, q):
    res, ret, final, produced = DATA[m]
    g = gt[q]
    if has(ret[q] or set(), g["gt_fact_text"]): return "Z"
    if has(final, g["gt_fact_text"]): return "R"
    if has(final, g["old_fact_text"]): return "old_only"
    if has(produced, g["gt_fact_text"]): return "D2"
    if has(produced, g["old_fact_text"]): return "D1"
    return "D0"

print(f"\n{'='*70}\nFC-SH {L}  CP={len(CP)}\n{'='*70}")

# ---- A) retrieval-state distribution + acc, both methods ----
print("\n### A) conflict-pair top-100 retrieval-state: distribution & Acc ###")
print(f"{'state':<10}{'van n':>7}{'van acc':>9}{'ours n':>8}{'ours acc':>10}")
for st in ["new_only", "both", "old_only", "neither"]:
    row = []
    for m in METHODS:
        res, ret, _, _ = DATA[m]
        qs = [q for q in CP if rstate(ret[q], gt[q]) == st]
        c = sum(1 for q in qs if res[q].get("exact_match"))
        row.append((len(qs), f"{c}/{len(qs)}" if qs else "-"))
    print(f"{st:<10}{row[0][0]:>7}{row[0][1]:>9}{row[1][0]:>8}{row[1][1]:>10}")

# ---- B) battlefield recovery: vanilla failure cause -> ours outcome ----
vres = DATA["vanilla"][0]; ores = DATA["ours"][0]
van_wrong = [q for q in CP if not vres[q].get("exact_match")]
rec = defaultdict(lambda: [0, 0])  # cause -> [recovered, still_wrong]
for q in van_wrong:
    c = cause("vanilla", q)
    rec[c][0 if ores[q].get("exact_match") else 1] += 1
print(f"\n### B1) vanilla 答錯題（n={len(van_wrong)}）按 vanilla 失敗成因 → ours 結果 ###")
print(f"{'vanilla cause':<12}{'n':>4}{'ours救回':>9}{'仍錯':>6}")
for c in ["old_only", "D0", "D1", "D2", "R", "Z"]:
    if c in rec:
        n = sum(rec[c]); print(f"{c:<12}{n:>4}{rec[c][0]:>9}{rec[c][1]:>6}")

# regressions: vanilla right -> ours wrong, with ours' causes
regs = [q for q in CP if vres[q].get("exact_match") and not ores[q].get("exact_match")]
cnt = Counter(cause("ours", q) for q in regs)
print(f"\n### B2) 退步題：vanilla 對 → ours 錯（n={len(regs)}），按 ours 失敗成因 ###")
for c, n in cnt.most_common():
    print(f"  {c:<10} {n}")
print("  qids:", sorted(regs))
