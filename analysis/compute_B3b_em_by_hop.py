"""B3b — Per-hop EM breakdown for our 4-ablation FC-MH 100Q.

Cross-tabs EM by num_hops and by n_conflict, matching the
2026-05-02 Mem0/Zep summary.md format for direct cross-system comparison.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/results/paper_narrative'
OUT.mkdir(parents=True, exist_ok=True)

ABLATIONS = {
    'A_vanilla':  'monitoring_logs/2026-05-17_182517_ablation_A/results.json',
    'B_phase2':   'monitoring_logs/2026-05-17_182907_ablation_B/results.json',
    'C_w3_full':  'monitoring_logs/2026-05-17_183341_ablation_C/results.json',
    'D_w3_min':   'monitoring_logs/2026-05-17_183627_ablation_D/results.json',
}

labels = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))
# Build qa_pair_id → (num_hops, n_conflict)
qid_meta = {}
for q in labels:
    n_conf = sum(1 for h in q['hops'] if h.get('conflict_type') == 'has_pair')
    qid_meta[q['qa_pair_id']] = (q['num_hops'], n_conf)


def em_breakdown(results_path):
    r = json.load(open(BASE / results_path))
    data = r['data']
    by_hops = defaultdict(lambda: [0, 0])
    by_conf = defaultdict(lambda: [0, 0])
    overall = [0, 0]
    by_combo = defaultdict(lambda: [0, 0])
    for rec in data:
        qid = rec.get('qa_pair_id')
        if qid not in qid_meta:
            continue
        nh, nc = qid_meta[qid]
        em = 1 if rec.get('exact_match') else 0
        overall[0] += em; overall[1] += 1
        by_hops[nh][0] += em; by_hops[nh][1] += 1
        by_conf[nc][0] += em; by_conf[nc][1] += 1
        by_combo[(nh, nc)][0] += em; by_combo[(nh, nc)][1] += 1
    return {
        'overall': overall,
        'by_hops': dict(by_hops),
        'by_conf': dict(by_conf),
        'by_combo': {f"{k[0]}h_{k[1]}c": v for k, v in by_combo.items()},
    }


def pct(p):
    return f"{p[0]}/{p[1]} ({100*p[0]/p[1]:.1f}%)" if p[1] else "n/a"


all_results = {name: em_breakdown(path) for name, path in ABLATIONS.items()}
json.dump(all_results, open(OUT / 'B3b_em_by_hop.json', 'w'), indent=2)

# Markdown report
with open(OUT / 'B3b_em_by_hop.md', 'w') as f:
    f.write("# B3b — Per-hop EM Breakdown (4-ablation FC-MH 100Q)\n\n")
    f.write("## Overall\n\n")
    f.write("| Ablation | EM |\n|---|---|\n")
    for name, r in all_results.items():
        f.write(f"| {name} | {pct(r['overall'])} |\n")

    f.write("\n## By num_hops\n\n")
    hops = sorted({h for r in all_results.values() for h in r['by_hops']})
    f.write("| Ablation | " + " | ".join(f"{h}-hop" for h in hops) + " |\n")
    f.write("|---|" + "---|" * len(hops) + "\n")
    for name, r in all_results.items():
        f.write(f"| {name} | " + " | ".join(pct(r['by_hops'].get(h,[0,0])) for h in hops) + " |\n")

    f.write("\n## By n_conflict\n\n")
    confs = sorted({c for r in all_results.values() for c in r['by_conf']})
    f.write("| Ablation | " + " | ".join(f"{c}-conflict" for c in confs) + " |\n")
    f.write("|---|" + "---|" * len(confs) + "\n")
    for name, r in all_results.items():
        f.write(f"| {name} | " + " | ".join(pct(r['by_conf'].get(c,[0,0])) for c in confs) + " |\n")

    # Cross-system comparison row (from 2026-05-02 summary.md)
    f.write("\n## Cross-system compare(FC-MH overall) — 含 2026-05-02 Mem0/Zep × Gemini\n\n")
    f.write("| System | LLM | 2-hop | 3-hop | 4-hop | Overall |\n|---|---|---|---|---|---|\n")
    for name, r in all_results.items():
        f.write(f"| {name} | (我們 ablation, LLM 待查) | "
                f"{pct(r['by_hops'].get(2,[0,0]))} | "
                f"{pct(r['by_hops'].get(3,[0,0]))} | "
                f"{pct(r['by_hops'].get(4,[0,0]))} | "
                f"{pct(r['overall'])} |\n")
    f.write("| HippoRAG-v2 plain | Gemini-3.1 modified | (see motivation) | | | **23%** |\n")
    f.write("| Mem0 customized | Gemini-3.1 | 44.3% (27/61) | 50.0% (12/24) | 26.7% (4/15) | **43.0%** |\n")
    f.write("| Zep | Gemini-3.1 (inference) | 13.1% (8/61) | **0.0%** (0/24) | **0.0%** (0/15) | **8.0%** |\n")
    f.write("| Zep × GPT-4o-mini (legacy) | GPT-4o-mini | — | — | — | 28% |\n")
    f.write("| OA2 fact-level oracle | Gemini-3.1 modified | — | — | — | **83%** |\n")

print(f"[wrote] {OUT}/B3b_em_by_hop.md + .json")
for name, r in all_results.items():
    print(f"\n{name} overall: {pct(r['overall'])}")
    for h in sorted(r['by_hops']):
        print(f"  {h}-hop: {pct(r['by_hops'][h])}")
