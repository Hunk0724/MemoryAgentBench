"""
Complete classification of ALL 100 FC-SH 6k queries (L2 run), by WHY each
succeeded/failed. Verifies the hypothesis that the 92 successes are either
single-fact (no conflict) or clean-resolved (only the new version in DB), and
surfaces any success that doesn't fit (e.g. STALE: both versions present yet
correct) for inspection.

Uses sh_query_conditional.json (per-query ingestion outcome + retrieval flags)
+ the run's actual results.output (NOT the stale sh_512 model_output field).
"""
import json, glob
from collections import Counter

BASE = "/home/yhchiang/MemoryAgentBench"
COND = json.load(open(f"{BASE}/docs/0603_current_research_main_evidence/logs/sh_6k_conditional.json"))
ODIR = f"{BASE}/outputs/gemini-3.1-flash-lite-mem0-chunk512-temp0-factaware-l2/Conflict_Resolution"
res = {d["qa_pair_id"].split("_no")[-1]: d for d in json.load(open(glob.glob(f"{ODIR}/factconsolidation_sh_6k_*results.json")[0]))["data"]}
gt = {q["query_id"]: q for q in json.load(open(f"{BASE}/analysis/results/sh_512_mquake_analysis.json"))}

def output(qid): return res[str(qid)].get("output", "")

cats = Counter()
detail = {"stale-correct": [], "other-success": [], "fail": []}
for r in COND:
    qid, em, hp, out = r["qid"], r["em"], r["has_pair"], r["outcome"]
    wf, of = r["winner_fate"], r["old_fate"]
    if em:
        if not hp:
            cat = "SUCCESS: single-fact (no_pair, 與衝突無關)"
        elif out == "CORRECT":      # winner STORED, old gone
            cat = "SUCCESS: clean-resolved (只剩新版)"
        elif out.startswith("STALE"):  # both present, yet correct
            cat = "SUCCESS: STALE-correct (新舊都在卻答對)"
            detail["stale-correct"].append(qid)
        else:
            cat = "SUCCESS: OTHER (需查)"
            detail["other-success"].append(qid)
    else:
        if out.startswith("DROPPED"):
            cat = "FAIL: write-time DROPPED (反事實被丟→答舊)"
        elif out == "CORRECT":
            o = output(qid)
            cat = f"FAIL: generation artifact ({'空輸出' if o=='' else '幻覺/其他'})"
        else:
            cat = "FAIL: OTHER"
        detail["fail"].append((qid, out, wf, of, output(qid)))
    cats[cat] += 1

print("=== FC-SH 6k 全 100 題分類 ===")
tot = 0
for k, v in sorted(cats.items(), key=lambda x: (-x[1])):
    print(f"  {v:3d}  {k}"); tot += v
print(f"  {tot:3d}  TOTAL")

print("\n=== clean-resolved 的 old(舊版)最終命運分布(確認都'消失') ===")
cr = [r for r in COND if r["em"] and r["has_pair"] and r["outcome"] == "CORRECT"]
print("  old_fate:", dict(Counter(r["old_fate"] for r in cr)))

print("\n=== STALE-correct (新舊都在卻答對) 逐題 ===")
for qid in detail["stale-correct"]:
    q = gt[qid]
    print(f"  qid{qid}: Q={q['question']}")
    print(f"      gt(新)={q.get('gt_answer')!r} old(舊)={q.get('old_answer')!r} 模型答={output(qid)!r}")

print("\n=== 8 個失敗 逐題(用真實 output) ===")
for qid, out, wf, of, o in detail["fail"]:
    q = gt[qid]
    print(f"  qid{qid} [{out}] winner_fate={wf} old_fate={of}")
    print(f"      gt(新)={q.get('gt_answer')!r} old(舊)={q.get('old_answer')!r} 模型答={o!r}")
