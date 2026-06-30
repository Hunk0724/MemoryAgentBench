"""Analyze: filter chain_old chunk but inject the chain_new it contains.

For each chain_old chunk (ground truth, has_pair hop):
  Q1. Does this chunk contain any GT chain_new prop (for any hop of same query)?
  Q2. If yes, is it the same hop's chain_new, or a different hop's?
  Q3. If different hop, is that chain_new also present in other (non-chain_old) chunks?
       (= redundancy: do we lose info if we just drop this chunk?)

Output table: filter-and-inject potential breakdown
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
prop_idx = {p['id']: p for p in json.load(open(
    BASE / 'outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/'
    'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json'))['propositions']}

# Build chunk → prop_ids map (all 450 props)
chunk_to_props = defaultdict(list)
for pid, p in prop_idx.items():
    chunk_to_props[p['source_chunk_id']].append(pid)

# For each has_pair hop, classify the chain_old chunk:
#   A. SAFE_DROP: chunk 不含任何 GT chain_new (any hop) — filter 安全
#   B. SAME_HOP_NEW: chunk 內含對應 hop 的 GT chain_new — filter 會殺到答案,必須 inject
#   C. CROSS_HOP_NEW_UNIQUE: chunk 含其他 hop 的 GT chain_new + 該 chain_new 不在其他 chunk
#   D. CROSS_HOP_NEW_REDUNDANT: chunk 含其他 hop 的 GT chain_new + 該 chain_new 也在其他 chunk (drop 不損失)

categories = Counter()
per_hop_cat = defaultdict(Counter)
sample_cases = defaultdict(list)

for q in labels_list:
    # Collect all GT chain_new prop_ids in this query (by hop)
    gt_news = {}  # hop_idx → chain_new_pid (only has_pair hops)
    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair': continue
        if not (hop['chain_new_matches'] and hop['chain_old_matches']): continue
        gt_news[hop['hop_idx']] = hop['chain_new_matches'][0]['prop_id']

    gt_new_pids = set(gt_news.values())

    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair': continue
        if not (hop['chain_new_matches'] and hop['chain_old_matches']): continue
        old_pid = hop['chain_old_matches'][0]['prop_id']
        old_chunk = hop['chain_old_matches'][0]['source_chunk_id']
        same_hop_new_pid = gt_news[hop['hop_idx']]

        # What GT chain_new props (any hop) are in this chain_old chunk?
        props_in_chunk = chunk_to_props[old_chunk]
        new_in_chunk = [pid for pid in props_in_chunk if pid in gt_new_pids]

        if not new_in_chunk:
            cat = 'A_SAFE_DROP'
        elif same_hop_new_pid in new_in_chunk:
            cat = 'B_SAME_HOP_NEW'
        else:
            # Cross-hop: check if those chain_news exist in OTHER chunks
            redundant = True
            for new_pid in new_in_chunk:
                new_chunk_of_pid = prop_idx[new_pid]['source_chunk_id']
                # is this new_pid in a non-chain_old chunk?
                # (any source_chunk_id != old_chunk implies redundancy)
                # Actually we want: does this new_pid have another chunk source?
                # Each prop has single source_chunk_id, so check if new_pid's chunk == old_chunk
                if new_chunk_of_pid == old_chunk:
                    redundant = False
                    break
            cat = 'D_CROSS_HOP_REDUNDANT' if redundant else 'C_CROSS_HOP_UNIQUE'

        categories[cat] += 1
        per_hop_cat[q['num_hops']][cat] += 1
        if len(sample_cases[cat]) < 3:
            sample_cases[cat].append({
                'qid': q['qa_pair_id'], 'hop': hop['hop_idx'],
                'old_chunk': old_chunk,
                'old_text': hop['chain_old_matches'][0]['prop_text'],
                'news_in_chunk': new_in_chunk,
                'gt_chain_new': hop['chain_new_matches'][0]['prop_text'],
            })

total = sum(categories.values())
print(f"=== Chain_old chunk classification (for {total} has_pair hops) ===\n")
print(f"{'Category':<30} {'Count':>8} {'%':>6}")
for cat in ['A_SAFE_DROP', 'B_SAME_HOP_NEW', 'C_CROSS_HOP_UNIQUE', 'D_CROSS_HOP_REDUNDANT']:
    n = categories[cat]
    print(f"  {cat:<28} {n:>8} {100*n/max(total,1):>5.0f}%")

print(f"\n=== By hop depth ===")
print(f"{'Hop':<8} {'n':>4} {'A SAFE_DROP':>14} {'B SAME_HOP':>14} {'C CROSS_UNIQ':>14} {'D CROSS_RED':>14}")
for h in sorted(per_hop_cat):
    c = per_hop_cat[h]
    tot = sum(c.values())
    print(f"{h}-hop  {tot:>4}  "
          f"{c['A_SAFE_DROP']:>4}/{tot} ({100*c['A_SAFE_DROP']//tot:>3}%)  "
          f"{c['B_SAME_HOP_NEW']:>4}/{tot} ({100*c['B_SAME_HOP_NEW']//tot:>3}%)  "
          f"{c['C_CROSS_HOP_UNIQUE']:>4}/{tot} ({100*c['C_CROSS_HOP_UNIQUE']//tot:>3}%)  "
          f"{c['D_CROSS_HOP_REDUNDANT']:>4}/{tot} ({100*c['D_CROSS_HOP_REDUNDANT']//tot:>3}%)")

print(f"\n=== Sample cases ===")
for cat, samples in sample_cases.items():
    print(f"\n{cat} (showing up to 3):")
    for s in samples:
        print(f"  [{s['qid']} h{s['hop']}] chunk={s['old_chunk']}")
        print(f"    OLD: {s['old_text']}")
        print(f"    GT_NEW (same hop): {s['gt_chain_new']}")
        print(f"    chain_new pids in this chunk: {len(s['news_in_chunk'])}")

# Markdown table
with open(OUT / 'A6_filter_inject_breakdown.md', 'w') as f:
    f.write("# A6 — Chain_old Chunk Classification: Filter + Inject Potential\n\n")
    f.write("For each ground-truth `chain_old` prop's source_chunk, classify whether the chunk also contains GT `chain_new` props:\n\n")
    f.write("## Categories\n\n")
    f.write("| Category | Means | Filter strategy |\n|---|---|---|\n")
    f.write("| **A SAFE_DROP** | chunk 不含任何 GT chain_new | 直接 drop 安全 |\n")
    f.write("| **B SAME_HOP_NEW** | chunk 內含**同 hop 對應的** chain_new | drop 會殺到答案 → **必須 inject** chain_new 回 context |\n")
    f.write("| **C CROSS_HOP_UNIQUE** | chunk 含**其他 hop 的** chain_new + 該 chain_new **只在這 chunk** | drop 會漏失另一 hop → **應 inject** |\n")
    f.write("| **D CROSS_HOP_REDUNDANT** | chunk 含其他 hop 的 chain_new + 該 chain_new **也在其他 chunk** | drop 無損失(redundancy) |\n\n")
    f.write("## Overall distribution\n\n")
    f.write(f"| Category | Count | % |\n|---|---|---|\n")
    for cat in ['A_SAFE_DROP', 'B_SAME_HOP_NEW', 'C_CROSS_HOP_UNIQUE', 'D_CROSS_HOP_REDUNDANT']:
        n = categories[cat]
        f.write(f"| {cat} | {n} | {100*n/max(total,1):.0f}% |\n")
    f.write("\n## By hop depth\n\n")
    f.write("| Hop | n | A SAFE_DROP | B SAME_HOP_NEW | C CROSS_UNIQUE | D CROSS_REDUNDANT |\n")
    f.write("|---|---|---|---|---|---|\n")
    for h in sorted(per_hop_cat):
        c = per_hop_cat[h]
        tot = sum(c.values())
        f.write(f"| {h}-hop | {tot} | "
                f"{c['A_SAFE_DROP']} ({100*c['A_SAFE_DROP']//tot}%) | "
                f"{c['B_SAME_HOP_NEW']} ({100*c['B_SAME_HOP_NEW']//tot}%) | "
                f"{c['C_CROSS_HOP_UNIQUE']} ({100*c['C_CROSS_HOP_UNIQUE']//tot}%) | "
                f"{c['D_CROSS_HOP_REDUNDANT']} ({100*c['D_CROSS_HOP_REDUNDANT']//tot}%) |\n")
    f.write("\n## Filter + Inject design implication\n\n")
    aplusD = categories['A_SAFE_DROP'] + categories['D_CROSS_HOP_REDUNDANT']
    bplusC = categories['B_SAME_HOP_NEW'] + categories['C_CROSS_HOP_UNIQUE']
    f.write(f"**A+D 可以放心 drop**: {aplusD}/{total} = {100*aplusD/total:.0f}%\n\n")
    f.write(f"**B+C 必須 inject 該 chunk 內 chain_new 才能 safely drop**: {bplusC}/{total} = {100*bplusC/total:.0f}%\n\n")
    f.write("→ 若不 inject,B+C 這 {} 個 hops 的 filter 會誤殺 chain_new 答案.\n".format(bplusC))

# Chart: stacked bar by hop
fig, ax = plt.subplots(figsize=(10, 6))
hops = sorted(per_hop_cat)
cats_order = ['A_SAFE_DROP', 'D_CROSS_HOP_REDUNDANT', 'C_CROSS_HOP_UNIQUE', 'B_SAME_HOP_NEW']
labels_cat = ['A: SAFE DROP\n(chunk 無 chain_new)',
              'D: CROSS-HOP REDUNDANT\n(別處有 redundancy)',
              'C: CROSS-HOP UNIQUE\n(chain_new 只在此 chunk)',
              'B: SAME-HOP NEW\n(同 hop chain_new 在此!)']
colors_c = ['#66bb6a', '#aed581', '#ffb74d', '#ef5350']
bottom = np.zeros(len(hops))
for cat, lbl, col in zip(cats_order, labels_cat, colors_c):
    vals = [per_hop_cat[h][cat] for h in hops]
    bars = ax.bar([f'{h}-hop\n(n={sum(per_hop_cat[h].values())})' for h in hops],
                  vals, bottom=bottom, label=lbl, color=col)
    for b, v in zip(bars, vals):
        if v > 0:
            ax.text(b.get_x() + b.get_width()/2, b.get_y() + b.get_height()/2,
                    f'{v}', ha='center', va='center', fontsize=9, fontweight='bold')
    bottom += np.array(vals)
ax.set_ylabel('# GT has_pair hops')
ax.set_title('A6: chain_old chunk classification — filter+inject potential\n'
             '(B+C 需要 inject chain_new 否則 filter 誤殺答案)')
ax.legend(loc='upper right', fontsize=9)
plt.tight_layout()
plt.savefig(OUT / 'A6_filter_inject_breakdown.png', dpi=150)
plt.close()

print(f"\n[wrote] {OUT}/A6_filter_inject_breakdown.md + .png")
