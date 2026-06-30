"""Corrected cascade: asymmetric, filter-driven.

Filter 的真正必要 cascade (per has_pair hop):
  S1. chain_OLD ∈ ∪ candidate_chains  (chain_old 被選為 focus)
  S2. focus=chain_old 的 pool 內含 chain_NEW (LLM 有東西可 identify)
  S3. LLM identify chain_new 為 contradicting
  S4. mechanical 比較 ts → chain_old 標 superseded by chain_new
  S5. chain_old 的 source_chunk 在 top-20 retrieval (filter 可作用範圍)
  S6. filter 真的 drop 該 chunk (rescue 沒救它)

chain_NEW 不要求進 chain — 它可從 dynamic_lookup 直接撈進 chain_old 的 pool.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/results/priority5'

labels_list = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))


def normalize_query(q):
    p = 'Based on the provided Knowledge Pool, '
    if q.startswith(p):
        q = q[len(p):]
    q = q.split('\nAnswer:')[0]
    return q.strip().rstrip('?').strip().lower()


def load_run(name):
    dirs = sorted((BASE / 'monitoring_logs').glob(f'*_ablation_{name}'))
    if not dirs:
        return None
    d = dirs[-1]
    dump = {}
    if (d / 'phase2_w13_dump.jsonl').exists():
        for line in open(d / 'phase2_w13_dump.jsonl'):
            e = json.loads(line)
            dump[normalize_query(e['query'])] = e
    verdicts = defaultdict(dict)
    if (d / 'verdict_events.jsonl').exists():
        for line in open(d / 'verdict_events.jsonl'):
            e = json.loads(line)
            verdicts[normalize_query(e['query'])][e['focus_pid']] = e
    return {'dump': dump, 'verdicts': verdicts}


B = load_run('B')

# ─── Filter cascade per hop ───
cascade = defaultdict(lambda: defaultdict(int))
total = defaultdict(int)

for q in labels_list:
    nq = normalize_query(q['question'])
    dump = B['dump'].get(nq)
    if not dump or dump.get('phase2_status') != 'RAN':
        continue
    verdicts_q = B['verdicts'].get(nq, {})
    chains_pid_union = set().union(*[set(c['proposition_ids']) for c in dump['chains']]) if dump['chains'] else set()
    chain_old_pids_dump = set(dump.get('chain_old_pids', []))
    pre_filter_chunks = set(dump.get('passages_pre_filter_chunk_ids', []))
    dropped_chunks = set(dump.get('passages_dropped_chunk_ids', []))

    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair':
            continue
        if not (hop['chain_new_matches'] and hop['chain_old_matches']):
            continue
        new_pid = hop['chain_new_matches'][0]['prop_id']
        old_pid = hop['chain_old_matches'][0]['prop_id']
        old_chunk = hop['chain_old_matches'][0]['source_chunk_id']
        n_hops = q['num_hops']

        total[n_hops] += 1

        # S1: chain_OLD in chain union
        if old_pid in chains_pid_union:
            cascade[n_hops]['S1_old_in_chain'] += 1
        else:
            continue  # skip later stages (cascade)

        # S2: chain_NEW in focus=chain_old's pool
        ev_old = verdicts_q.get(old_pid)
        new_in_old_pool = ev_old and new_pid in ev_old.get('pool_pids', [])
        if new_in_old_pool:
            cascade[n_hops]['S2_new_in_old_pool'] += 1
        else:
            continue

        # S3: LLM identify chain_new in focus=chain_old's verdict
        new_in_old_llm = ev_old and new_pid in ev_old.get('llm_contradicting_pids', [])
        if new_in_old_llm:
            cascade[n_hops]['S3_llm_identified'] += 1
        else:
            continue

        # S4: verdict status = superseded AND superseder=chain_new
        # Check chain_old_pids (which is what filter uses)
        if old_pid in chain_old_pids_dump:
            cascade[n_hops]['S4_verdict_superseded'] += 1
        else:
            continue

        # S5: chain_old chunk in top-20 (pre-filter scope)
        if old_chunk in pre_filter_chunks:
            cascade[n_hops]['S5_chunk_in_top20'] += 1
        else:
            continue

        # S6: chain_old chunk dropped
        if old_chunk in dropped_chunks:
            cascade[n_hops]['S6_chunk_dropped'] += 1

# Aggregate over all hops
print("=== Asymmetric filter-driven cascade (Ablation B) ===\n")
print(f"{'Hop':>6} {'n':>4}  "
      f"{'S1 old∈chain':>14}  "
      f"{'S2 new∈pool':>14}  "
      f"{'S3 LLM ident':>14}  "
      f"{'S4 verdict':>14}  "
      f"{'S5 chunk∈top20':>16}  "
      f"{'S6 dropped':>14}")
for h in sorted(total):
    t = total[h]
    s1 = cascade[h]['S1_old_in_chain']
    s2 = cascade[h]['S2_new_in_old_pool']
    s3 = cascade[h]['S3_llm_identified']
    s4 = cascade[h]['S4_verdict_superseded']
    s5 = cascade[h]['S5_chunk_in_top20']
    s6 = cascade[h]['S6_chunk_dropped']
    print(f"{h}-hop  {t:>4}  "
          f"{s1:>5}/{t} ({100*s1//t:>3}%)  "
          f"{s2:>5}/{t} ({100*s2//t:>3}%)  "
          f"{s3:>5}/{t} ({100*s3//t:>3}%)  "
          f"{s4:>5}/{t} ({100*s4//t:>3}%)  "
          f"{s5:>5}/{t} ({100*s5//t:>5}%)  "
          f"{s6:>5}/{t} ({100*s6//t:>3}%)")

total_all = sum(total.values())
all_cascade = {k: sum(cascade[h][k] for h in total) for k in
               ['S1_old_in_chain', 'S2_new_in_old_pool', 'S3_llm_identified',
                'S4_verdict_superseded', 'S5_chunk_in_top20', 'S6_chunk_dropped']}
print(f"\nTotal (all hops, n={total_all}):")
for k, v in all_cascade.items():
    print(f"  {k}: {v}/{total_all} = {100*v/max(total_all,1):.0f}%")

# Write markdown
with open(OUT / 'A5b_filter_cascade_asymmetric.md', 'w') as f:
    f.write("# A5b — Asymmetric Filter-Driven Cascade (Ablation B)\n\n")
    f.write("**校正:filter 真正必要 cascade 是 asymmetric**(只需 chain_old ∈ chain,chain_new 可從 dynamic_lookup 進 pool)。\n\n")
    f.write("## Cascade definition\n\n")
    f.write("| Stage | Definition |\n|---|---|\n")
    f.write("| S1 | chain_OLD ∈ ∪ candidate chains (chain_old 被選為 focus) |\n")
    f.write("| S2 | focus=chain_old 的 pool 含 chain_NEW (LLM 可看到對立) |\n")
    f.write("| S3 | LLM identify chain_new 為 contradicting |\n")
    f.write("| S4 | Mechanical → verdict 標 chain_old=superseded by chain_new |\n")
    f.write("| S5 | chain_old chunk ∈ top-20 retrieval (filter scope) |\n")
    f.write("| S6 | filter 真的 drop chain_old chunk (rescue 沒救) |\n\n")
    f.write("## Per-hop cascade rates\n\n")
    f.write("| Hop | n | S1 old∈chain | S2 new∈old's pool | S3 LLM ident | S4 verdict supersed | S5 chunk∈top20 | S6 dropped |\n")
    f.write("|---|---|---|---|---|---|---|---|\n")
    for h in sorted(total):
        t = total[h]
        c = cascade[h]
        f.write(f"| {h}-hop | {t} | "
                f"{c['S1_old_in_chain']} ({100*c['S1_old_in_chain']//t}%) | "
                f"{c['S2_new_in_old_pool']} ({100*c['S2_new_in_old_pool']//t}%) | "
                f"{c['S3_llm_identified']} ({100*c['S3_llm_identified']//t}%) | "
                f"{c['S4_verdict_superseded']} ({100*c['S4_verdict_superseded']//t}%) | "
                f"{c['S5_chunk_in_top20']} ({100*c['S5_chunk_in_top20']//t}%) | "
                f"{c['S6_chunk_dropped']} ({100*c['S6_chunk_dropped']//t}%) |\n")
    f.write(f"| **All** | **{total_all}** | "
            f"{all_cascade['S1_old_in_chain']} ({100*all_cascade['S1_old_in_chain']//total_all}%) | "
            f"{all_cascade['S2_new_in_old_pool']} ({100*all_cascade['S2_new_in_old_pool']//total_all}%) | "
            f"{all_cascade['S3_llm_identified']} ({100*all_cascade['S3_llm_identified']//total_all}%) | "
            f"{all_cascade['S4_verdict_superseded']} ({100*all_cascade['S4_verdict_superseded']//total_all}%) | "
            f"{all_cascade['S5_chunk_in_top20']} ({100*all_cascade['S5_chunk_in_top20']//total_all}%) | "
            f"{all_cascade['S6_chunk_dropped']} ({100*all_cascade['S6_chunk_dropped']//total_all}%) |\n")

# Chart: bar groups per hop, stages on x
fig, ax = plt.subplots(figsize=(12, 6))
stages = ['S1_old_in_chain', 'S2_new_in_old_pool', 'S3_llm_identified',
          'S4_verdict_superseded', 'S5_chunk_in_top20', 'S6_chunk_dropped']
labels_s = ['S1\nold∈chain', 'S2\nnew∈pool', 'S3\nLLM ident', 'S4\nverdict', 'S5\nchunk∈top20', 'S6\ndropped']
colors_h = {2: '#42a5f5', 3: '#fb8c00', 4: '#d32f2f'}
x = np.arange(len(stages))
w = 0.25
for i, h in enumerate(sorted(total)):
    t = total[h]
    vals = [100*cascade[h][s]/max(t,1) for s in stages]
    bars = ax.bar(x + (i-1)*w, vals, w, label=f'{h}-hop (n={t})', color=colors_h.get(h, 'gray'))
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, b.get_height(), f'{v:.0f}',
                ha='center', va='bottom', fontsize=8)
ax.set_xticks(x)
ax.set_xticklabels(labels_s)
ax.set_ylabel('% of has_pair hops surviving stage')
ax.set_title('A5b: Asymmetric filter-driven cascade by hop (Ablation B)\n'
             '(chain_new 不需要進 chain — 可從 dynamic_lookup 直接進 pool)')
ax.legend()
ax.set_ylim(0, 110)
plt.tight_layout()
plt.savefig(OUT / 'A5b_filter_cascade_asymmetric.png', dpi=150)
plt.close()

print(f"\n[wrote] {OUT}/A5b_filter_cascade_asymmetric.md + .png")
