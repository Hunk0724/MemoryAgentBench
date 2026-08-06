#!/usr/bin/env python3
"""UNIFORM cross-method world-prior indicator for FC-SH 5.2.2 (gpt-4o-mini, committed data).

For every method x 4 lengths, of has_pair FAILURES, % whose FINAL ANSWER == gt_OLD surface
(= reverted to world-knowledge-consistent old value). Uniform signature regardless of where
the pipeline failed.

answered_old := official_subem(final_answer, [old_surface])   (rescore_canonical primitives)
failure      := not official_subem(final_answer, gt_new_aliases)
old_surface  := rescore_canonical.extract_old_surface(gt_fact_text, old_fact_text)

Answer-field parsing per method (documented):
 - Reliable results.json `output`  : q_llm_recency, struct, no_p5, native(Mem0 Vanilla), temp0(LCA)
 - Per-qid `response` (aggregated `output` is documented-corrupted): Zep, Mem0+P1(dest)
   [see compute_pool_acc_crosstab.py _em_from_perqid docstring: Zep 32k 48/65 + mem0+P1 33-42/N
    aggregated outputs replaced by "Answer:" placeholders while per-qid response is real.]
 - Don't Ask committed rows[].answer / subem  (authors' file, no results.json).
gt_new aliases come from results.json `answer` (alias list) where available, else mquake gt_answer.
"""
import json, glob, sys
sys.path.insert(0, "analysis")
from rescore_canonical import official_subem, extract_old_surface, load_haspair, pick_canonical_file

LENGTHS = ["6k", "32k", "64k", "262k"]

def old_surface(row): return extract_old_surface(row.get("gt_fact_text",""), row.get("old_fact_text",""))
def answered_old(ans, os_): return bool(os_) and official_subem(ans, [os_])

def qresponse(dirn, kdir, L, qid):
    fs = glob.glob(f"outputs/rag_retrieved/{dirn}/{kdir}/factconsolidation_sh_{L}/chunksize_512/query_{qid}_context_*.json")
    if not fs: return None
    return (json.load(open(fs[0])).get("response") or "")

def results_map(rundir, L):
    f = pick_canonical_file(f"outputs/{rundir}", L)
    if not f: return None, None
    data = json.load(open(f))["data"]
    return {d["query_id"]: d for d in data}, f.split("/")[-1]

# ---- generic: results.json output (reliable methods) ----
def method_output(rundir, L):
    byq, fname = results_map(rundir, L)
    hp = load_haspair(L)
    nf = nold = 0; details=[]
    if byq is None: return None
    for qid,row in hp.items():
        d = byq.get(qid)
        if d is None: continue
        ans = d.get("output"); aliases = d.get("answer")
        if official_subem(ans, aliases): continue
        nf += 1
        if answered_old(ans, old_surface(row)): nold += 1
        else: details.append((qid, ans))
    return nf, nold, fname, details

# ---- per-qid response (Zep, dest) ----
def method_perqid(dirn, kdir, rundir_for_aliases, L):
    byq, _ = results_map(rundir_for_aliases, L)   # aliases only (answer field is not corrupted)
    hp = load_haspair(L)
    nf = nold = nother = nempty = 0; details=[]
    for qid,row in hp.items():
        resp = qresponse(dirn, kdir, L, qid)
        if resp is None: continue
        aliases = (byq.get(qid,{}).get("answer") if byq else None) or [row.get("gt_answer")]
        if official_subem(resp, aliases): continue
        nf += 1
        if answered_old(resp, old_surface(row)): nold += 1
        else:
            details.append((qid, resp[:60]))
            if not resp.strip() or "no answer" in resp.lower(): nempty += 1
            else: nother += 1
    return nf, nold, nempty, nother, details

# ---- Don't Ask committed rows ----
def method_dontask(L):
    path = f"outputs/maxserial_theircode/{L}_gpt-4o-mini_vector100.json"
    rows = {r["query_id"]: r for r in json.load(open(path))["rows"]}
    hp = load_haspair(L)
    nf = nold = 0
    for qid,row in hp.items():
        r = rows.get(qid)
        if r is None or r.get("subem"): continue
        nf += 1
        if answered_old(r.get("answer"), old_surface(row)): nold += 1
    return nf, nold

def cell(nf, nold): return f"{nold}/{nf} ({100*nold/nf:.0f}%)" if nf else "0/0 (—)"

print("METHOD x LENGTH : answered gt_OLD / has_pair_fail (%)\n")
table = {}

# 1 Vanilla-RAG, 3 Struct-Only, 4 Ours main, 6 Mem0 Vanilla, 8 LCA : reliable output
reliable = [
    ("Vanilla-RAG (q_llm_recency)", "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_q_llm_recency"),
    ("Ours Struct-Only (struct)",   "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct"),
    ("Ours main (no_p5)",           "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_no_p5"),
    ("Mem0 Vanilla (native)",       "gpt-4o-mini-mem0-chunk512-temp0-openai-native"),
    ("LCA (temp0)",                 "gpt-4o-mini-temp0"),
]
for name, rundir in reliable:
    table[name] = {}
    for L in LENGTHS:
        r = method_output(rundir, L)
        table[name][L] = cell(r[0], r[1]) if r else "—"

# 2 Don't Ask
table["Don't Ask (maxserial)"] = {}
for L in LENGTHS:
    nf, nold = method_dontask(L)
    table["Don't Ask (maxserial)"][L] = cell(nf, nold)

# 5 Mem0+P1 (dest) per-qid, 7 Zep per-qid
perqid = [
    ("Mem0+P1 (dest)", "Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest", "k_100",
     "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest"),
    ("Zep (k=10)", "Structure_rag_zep", "k_10", "gpt-4o-mini-zep"),
]
zep_detail = {}
for name, dirn, kdir, aliasdir in perqid:
    table[name] = {}
    for L in LENGTHS:
        nf, nold, nempty, nother, det = method_perqid(dirn, kdir, aliasdir, L)
        table[name][L] = cell(nf, nold)
        if name.startswith("Zep"):
            zep_detail[L] = (nf, nold, nempty, nother)

order = ["Vanilla-RAG (q_llm_recency)","Don't Ask (maxserial)","Ours Struct-Only (struct)",
         "Ours main (no_p5)","Mem0+P1 (dest)","Mem0 Vanilla (native)","Zep (k=10)","LCA (temp0)"]
print(f"{'method':<30}" + "".join(f"{L:>16}" for L in LENGTHS))
for m in order:
    print(f"{m:<30}" + "".join(f"{table[m][L]:>16}" for L in LENGTHS))

# ---- LCA (a)/(b) split + truncation ----
print("\n--- LCA has_pair-failure split (a=gt_OLD world-prior, b=other/empty) + truncation ---")
for L in LENGTHS:
    byq, fname = results_map("gpt-4o-mini-temp0", L)
    hp = load_haspair(L)
    a=b=0; nf=0; ils=[]; bdet=[]
    for qid,row in hp.items():
        d=byq.get(qid);
        if d is None: continue
        ils.append(d.get("input_len"))
        if official_subem(d.get("output"), d.get("answer")): continue
        nf+=1
        if answered_old(d.get("output"), old_surface(row)): a+=1
        else: b+=1; bdet.append((qid, (d.get("output") or "")[:40]))
    ilmin, ilmax = (min(x for x in ils if x), max(x for x in ils if x)) if ils else (0,0)
    trunc = " <-- TRUNCATED (input_len < intended context; exceeds 128k)" if ilmax and ilmax < 200000 and L=="262k" else ""
    print(f"  {L}: fails={nf}  (a)gt_OLD={a} ({100*a/nf:.0f}%)  (b)other/empty={b} ({100*b/nf:.0f}%)  input_len={ilmin}-{ilmax}{trunc}")
    if L=="262k":
        for qid,o in bdet[:5]: print(f"       (b) qid{qid}: {o!r}")

# ---- Zep regime contrast ----
print("\n--- Zep answered-gt_OLD detail (short = no-invalidation->old ; 262k = retrieval-miss regime) ---")
for L in LENGTHS:
    nf,nold,nempty,nother = zep_detail[L]
    print(f"  {L}: fails={nf}  gt_OLD={nold} ({100*nold/nf:.0f}%)  empty/abstain={nempty}  other={nother}")
