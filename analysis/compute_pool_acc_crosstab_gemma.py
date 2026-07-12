"""Tier-1 (§4.2) return_context × Acc 4×2 cross-tab — GX10 weak-model (gemma3).

Mirrors Mac's canonical analysis/compute_pool_acc_crosstab.py METHOD, adapted to
gemma agent_name paths: reads the ACTUAL per-qid pipeline output
(`memories_str` = pool the answer LLM saw, saved by agent.py:1100), classifies
pool state with matcher v4 (`analysis.compute_m1_m2_m3.match_pair`), and crosses
with EM (aggregated `exact_match`). NO offline reconstruction (superseded 2026-07-05
after discovering gemma DOES save per-qid, just under Structure_rag_gemma3-*).

  python3 analysis/compute_pool_acc_crosstab_gemma.py > <out>.md
"""
import sys, os, json, glob
sys.path.insert(0, os.path.expanduser("~/MemoryAgentBench"))
from collections import Counter
from analysis.compute_m1_m2_m3 import match_pair   # matcher v4

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
L = "6k"
gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
HP = [q for q, r in gt.items() if r["conflict_type"] == "has_pair"]
SIZES = ["1b", "4b", "12b", "27b"]
# (display, agent_name suffix, aggregated output-dir suffix, pool field)
METHODS = [
    ("ours_struct", "unified_struct", "unified_struct", "memories_str"),
    ("ours_no_p5", "unified_no_p5", "unified_no_p5", "memories_str"),
    ("ours_p3_only", "unified_p3_only_no_struct", "unified_p3_only_no_struct", "memories_str"),
]
ORDER = ["new_only", "both", "old_only", "neither"]


def em_map(outsuf, s):
    # official MAB metric = substring_exact_match (2026-07-11 canonical migration);
    # exclude smoke/size5 side-files and pick the full run.
    fs = [f for f in glob.glob(f"outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-{outsuf}__gemma3-{s}/Conflict_Resolution/*sh_6k*results*.json")
          if "smoke" not in f and "size5" not in f]
    if not fs:
        return None
    best = max(fs, key=lambda f: len(json.load(open(f))["data"]))
    return {r["query_id"]: bool(r["substring_exact_match"]) for r in json.load(open(best))["data"]}


def pool_of(agentsuf, s, qid):
    p = (f"outputs/rag_retrieved/Structure_rag_gemma3-{s}-mem0_512_openai_{agentsuf}"
         f"/k_100/factconsolidation_sh_{L}/chunksize_512/query_{qid}_context_0.json")
    if not os.path.exists(p):
        return None
    ms = json.load(open(p)).get("memories_str", "")
    return [ln.lstrip("- ").strip() for ln in ms.split("\n") if ln.strip()]


def state(pool, gtn, gto):
    n = any(match_pair(t, gtn, gto, "new") for t in pool)
    o = any(match_pair(t, gtn, gto, "old") for t in pool)
    return "both" if (n and o) else "new_only" if n else "old_only" if o else "neither"


print("# return_context × Acc cross-tab — GX10 weak-model (gemma3), FC-SH 6k has_pair")
print()
print("> **matcher v4** + **REAL per-qid `memories_str`** (the pool the answer LLM actually "
      "saw; agent.py:1100), aligned to Mac's canonical method. N=74. **Acc = official "
      "`substring_exact_match`** (2026-07-11 canonical migration; was strict exact_match). "
      "Reading: `new_only→✓` method isolated NEW & reader used it; `both→✓` reader RESCUE "
      "(mixed pool, picked NEW); `new_only→✗` reader OVERRIDE (clean pool, answered OLD); "
      "`old_only/neither→✗` NEW absent from pool (extraction/write loss).")
print()
print("> ⚠️ **EXTRACTION IS PER-BACKBONE GEMMA, NOT held-fixed gpt-4o-mini** (GX10 matrix sets "
      "`MEM0_TRIPLE_MODEL=gemma3:$SIZE`). The cross-tab is only RELIABLE for 12b/27b; on **1b/4b "
      "the pool-state axis is NOT trustworthy** — gemma-1b/4b extract fewer facts (store ≈370 vs "
      "12b/27b ≈450) whose surface diverges from GT, so matcher v4 false-negatives inflate the "
      "`old_only/neither` (NEW-absent) bucket. **For 1b/4b use E2E + case-study** "
      "(`weak_model_6k_analysis.md`). Store overlap-with-27b: 1b=5/100, 4b=82/100, 12b=99/100.")
print()
for disp, agentsuf, outsuf, _ in METHODS:
    print(f"## {disp}")
    print()
    print("| backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | EM | pool-missing |")
    print("| :-- | :-: | :-: | :-: | :-: | :-: | :-: |")
    for s in SIZES:
        em = em_map(outsuf, s)
        if em is None:
            print(f"| {s} | _no aggregated_ | | | | | |"); continue
        cell = {st: [0, 0] for st in ORDER}; miss = 0
        for q in HP:
            pool = pool_of(agentsuf, s, q)
            if pool is None:
                miss += 1; continue
            st = state(pool, gt[q]["gt_fact_text"], gt[q]["old_fact_text"])
            cell[st][0 if em.get(q) else 1] += 1
        emn = sum(1 for q in HP if em.get(q))
        row = " | ".join(f"{cell[st][0]}/{cell[st][1]}" for st in ORDER)
        print(f"| {s} | {row} | {emn}/74 | {miss} |")
    print()
print("**Attribution key**: new_only ✓ = clean method+reader win · both ✓ = reader rescue · "
      "new_only ✗ = reader override (27B drag) · old_only/neither ✗ = NEW absent (1B/4B floor).")
