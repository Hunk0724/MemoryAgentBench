"""Cross-ablation comparison: join 4 ablation runs by qa_pair_id.

Outputs:
  - 4-way confusion matrix (correct/wrong in each ablation)
  - per-pair (A vs B/C/D) gain / loss / both-right / both-wrong tally
  - specific cases:
      * B vs C: same EM 31 — same questions correct?
      * D vs A: where W3 hurt (D wrong, A correct)?
      * A → B: which 14 queries did Phase 2 + filter gain?
  - join with mini-eval labels to see hop-conflict structure of gained/lost
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')


def load_results(dir_path: Path) -> dict:
    p = dir_path / 'results.json'
    if not p.exists():
        return {}
    data = json.load(open(p))['data']
    return {r['qa_pair_id']: r for r in data}


def main():
    # Locate latest 4 ablation dirs (most recent A/B/C/D)
    runs = {}
    for name in ('A', 'B', 'C', 'D'):
        dirs = sorted(Path(BASE / 'monitoring_logs').glob(f'*_ablation_{name}'))
        if not dirs:
            print(f"⚠️  No dir for ablation {name}")
            continue
        runs[name] = load_results(dirs[-1])
    print(f"[load] runs: {list(runs.keys())}, sizes: { {k: len(v) for k,v in runs.items()} }")

    labels = {q['qa_pair_id']: q
              for q in json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))}

    # Build correctness matrix per qa_pair_id
    qa_ids = sorted(set().union(*[r.keys() for r in runs.values()]))
    matrix = {}
    for qid in qa_ids:
        matrix[qid] = {
            name: bool(runs[name].get(qid, {}).get('exact_match'))
            for name in runs
        }

    # ─── 4-way confusion: count tuples (A,B,C,D) ───
    pattern_counts = Counter()
    for qid in qa_ids:
        pattern = tuple(int(matrix[qid][n]) for n in ('A','B','C','D'))
        pattern_counts[pattern] += 1
    print("\n=== 4-way correctness pattern (A,B,C,D) ===")
    print(f"  {'A':>2} {'B':>2} {'C':>2} {'D':>2} | count | description")
    for pattern in sorted(pattern_counts, key=lambda p: -pattern_counts[p]):
        n = pattern_counts[pattern]
        desc = []
        if all(pattern):
            desc.append("all correct")
        elif not any(pattern):
            desc.append("all wrong")
        else:
            corr = [n_ for n_, v in zip(('A','B','C','D'), pattern) if v]
            wrong = [n_ for n_, v in zip(('A','B','C','D'), pattern) if not v]
            desc.append(f"correct={'+'.join(corr)} wrong={'+'.join(wrong)}")
        a,b,c,d = pattern
        print(f"  {a:>2} {b:>2} {c:>2} {d:>2} |  {n:>3}  | {' '.join(desc)}")

    # ─── Per ablation: gain / loss / overlap vs A ───
    print("\n=== Per ablation vs A (vanilla, EM=17) ===")
    for target in ('B', 'C', 'D'):
        em_target = sum(matrix[q][target] for q in qa_ids)
        gained = [q for q in qa_ids if matrix[q][target] and not matrix[q]['A']]
        lost   = [q for q in qa_ids if not matrix[q][target] and matrix[q]['A']]
        both_right = [q for q in qa_ids if matrix[q][target] and matrix[q]['A']]
        both_wrong = [q for q in qa_ids if not matrix[q][target] and not matrix[q]['A']]
        print(f"\n  {target}: EM={em_target}, gained={len(gained)}, lost={len(lost)}, "
              f"both_right={len(both_right)}, both_wrong={len(both_wrong)}, "
              f"net Δ = +{len(gained)-len(lost)}")

    # ─── B vs C: same EM 31, but same questions? ───
    print("\n=== B vs C overlap (both 31/100) ===")
    b_right = set(q for q in qa_ids if matrix[q]['B'])
    c_right = set(q for q in qa_ids if matrix[q]['C'])
    print(f"  Both B+C right:        {len(b_right & c_right)}")
    print(f"  B right but C wrong:   {len(b_right - c_right)}")
    print(f"  C right but B wrong:   {len(c_right - b_right)}")
    print(f"  Jaccard:               {len(b_right & c_right) / max(len(b_right | c_right), 1):.3f}")
    # List the 'B right, C wrong' (W3 broke previously-correct)
    bc_diff_loss = list(b_right - c_right)
    bc_diff_gain = list(c_right - b_right)
    if bc_diff_loss:
        print(f"  → W3 (C) BROKE {len(bc_diff_loss)} previously-correct (B):")
        for qid in bc_diff_loss[:5]:
            r_b = runs['B'][qid]; r_c = runs['C'][qid]
            print(f"    [{qid}] gold={r_b.get('answer', ['?'])[0][:30]} "
                  f"| B={(r_b.get('output') or '')[:40]} | C={(r_c.get('output') or '')[:40]}")
    if bc_diff_gain:
        print(f"  → W3 (C) RESCUED {len(bc_diff_gain)} previously-wrong (B):")
        for qid in bc_diff_gain[:5]:
            r_b = runs['B'][qid]; r_c = runs['C'][qid]
            print(f"    [{qid}] gold={r_b.get('answer', ['?'])[0][:30]} "
                  f"| B={(r_b.get('output') or '')[:40]} | C={(r_c.get('output') or '')[:40]}")

    # ─── D vs A: where W3 minimal hurt ───
    print("\n=== D (W3 minimal) vs A (vanilla) — D=15 < A=17 ===")
    a_right = set(q for q in qa_ids if matrix[q]['A'])
    d_right = set(q for q in qa_ids if matrix[q]['D'])
    d_broke = list(a_right - d_right)
    d_gained_anyway = list(d_right - a_right)
    print(f"  D broke {len(d_broke)} that A had correct:")
    for qid in d_broke[:8]:
        r_a = runs['A'][qid]; r_d = runs['D'][qid]
        lbl = labels.get(qid, {})
        n_pair = sum(1 for h in lbl.get('hops', []) if h['conflict_type']=='has_pair')
        print(f"    [{qid} {lbl.get('num_hops','?')}h {n_pair}p] gold={r_a.get('answer',['?'])[0][:25]}"
              f" | A={(r_a.get('output') or '')[:35]} | D={(r_d.get('output') or '')[:35]}")
    print(f"\n  D still gained {len(d_gained_anyway)} that A had wrong:")
    for qid in d_gained_anyway[:5]:
        r_a = runs['A'][qid]; r_d = runs['D'][qid]
        print(f"    [{qid}] gold={r_a.get('answer',['?'])[0][:25]}"
              f" | A={(r_a.get('output') or '')[:35]} | D={(r_d.get('output') or '')[:35]}")

    # ─── B (Phase 2 + filter) gained 14 over A: which queries? ───
    print("\n=== B gained over A (+14, the main contribution) ===")
    b_gained = sorted(set(q for q in qa_ids if matrix[q]['B']) - set(q for q in qa_ids if matrix[q]['A']))
    # Tally hop-distribution of gained
    hop_dist = Counter()
    pair_count_dist = Counter()
    for qid in b_gained:
        lbl = labels.get(qid, {})
        hop_dist[lbl.get('num_hops', '?')] += 1
        pair_count_dist[sum(1 for h in lbl.get('hops', []) if h['conflict_type']=='has_pair')] += 1
    print(f"  Total gained: {len(b_gained)}")
    print(f"  by hop count: {dict(hop_dist)}")
    print(f"  by has_pair count: {dict(pair_count_dist)}")
    print(f"\n  Sample gained:")
    for qid in b_gained[:5]:
        r_a = runs['A'][qid]; r_b = runs['B'][qid]
        lbl = labels.get(qid, {})
        print(f"    [{qid} {lbl.get('num_hops','?')}h] gold={r_a.get('answer',['?'])[0][:25]}"
              f" | A={(r_a.get('output') or '')[:35]} | B={(r_b.get('output') or '')[:35]}")

    # B lost some too (B≠A, Phase 2 broke something vanilla had right)
    b_lost = sorted(set(q for q in qa_ids if not matrix[q]['B']) & set(q for q in qa_ids if matrix[q]['A']))
    print(f"\n  Phase 2 broke {len(b_lost)} previously-right (A→B):")
    for qid in b_lost[:5]:
        r_a = runs['A'][qid]; r_b = runs['B'][qid]
        lbl = labels.get(qid, {})
        print(f"    [{qid} {lbl.get('num_hops','?')}h] gold={r_a.get('answer',['?'])[0][:25]}"
              f" | A={(r_a.get('output') or '')[:35]} | B={(r_b.get('output') or '')[:35]}")

    # ─── Write detailed matrix ───
    OUT = BASE / 'analysis/results/full100_eval/ablation_cross_compare.json'
    json.dump({
        'meta': {'n_queries': len(qa_ids), 'ablations': list(runs.keys()),
                 'em_per_ablation': {n: sum(matrix[q][n] for q in qa_ids) for n in runs}},
        'matrix': {qid: matrix[qid] for qid in qa_ids},
        'b_gained_over_a': b_gained,
        'b_lost_over_a': b_lost,
        'bc_w3_broke': bc_diff_loss,
        'bc_w3_rescued': bc_diff_gain,
        'd_broke_vs_vanilla': d_broke,
        'd_still_gained': d_gained_anyway,
    }, open(OUT, 'w'), indent=2)
    print(f"\n[wrote] {OUT}")


if __name__ == '__main__':
    main()
