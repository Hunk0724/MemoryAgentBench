"""
Generate 5 slides figures per user spec.
ALL FIGURES use full 100 questions (no rule-clean filtering) for consistency.

Output: analysis/paper_motivation/figures/slides/
  F1 — Production systems FC-SH/FC-MH (slide 9)
  F2 — Construct validity + Multiplicative baseline composite (slide 10)
  F3 — Channel ceiling ladder with step annotations (slide 12)
  F4 — Cross-cleanness × prompt multi-line (slide 13)
  F5 — Mode C killer experiment (slide 14)
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/paper_motivation/figures/slides'
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    'font.size': 12,
    'font.family': 'sans-serif',
    'font.sans-serif': ['Noto Sans CJK JP', 'Noto Serif CJK TC', 'AR PL UKai TW MBE', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'axes.spines.top': False,
    'axes.spines.right': False,
})


# =====================================================================
# F1 — Production Systems on FC-MH (all 100, MABench-aligned: FC seq-rule wrapper)
# =====================================================================
fig, ax = plt.subplots(figsize=(8, 5))
systems = ['HippoRAG-v2\n(vanilla)', 'Mem0 customized', 'Zep']
sh = [77, 85, 89]
mh = [22, 44, 28]
drops = [s - m for s, m in zip(sh, mh)]

x = np.arange(len(systems))
w = 0.36
b1 = ax.bar(x - w/2, sh, w, label='FC-SH', color='#aed581', edgecolor='black', linewidth=1.2)
b2 = ax.bar(x + w/2, mh, w, label='FC-MH', color='#e91e63', edgecolor='black', linewidth=1.2)

for i in range(len(systems)):
    ax.text(i - w/2, sh[i] + 1.5, f'{sh[i]}%', ha='center', fontsize=11, fontweight='bold')
    ax.text(i + w/2, mh[i] + 1.5, f'{mh[i]}%', ha='center', fontsize=11, fontweight='bold')
    mid_x = i
    ax.annotate('', xy=(i + w/2 - 0.05, mh[i] + 6), xytext=(i - w/2 + 0.05, sh[i] - 4),
                arrowprops=dict(arrowstyle='->', color='red', lw=1.8))
    ax.text(mid_x, (sh[i] + mh[i]) / 2, f'-{drops[i]}pp', ha='center', color='red',
            fontweight='bold', fontsize=11,
            bbox=dict(boxstyle='round,pad=0.35', fc='white', ec='red', alpha=0.92))

ax.set_xticks(x)
ax.set_xticklabels(systems, fontsize=11)
ax.set_ylabel('Exact Match (%, n=100 each)')
ax.set_ylim(0, 100)
ax.legend(loc='upper right', frameon=True)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(OUT / 'fig1_production_sh_mh.png', dpi=160, bbox_inches='tight')
plt.close()
print('Saved F1')


# =====================================================================
# F2 — Construct Validity + Multiplicative Baseline Composite (full 100)
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5),
                          gridspec_kw={'width_ratios': [1, 1.3]})

# Panel A: Construct validity (full 100: Vanilla 20%, PureChain 97%)
ax = axes[0]
ax.set_facecolor('#f0f7fa')
labels_a = ['FC-MH\n(Vanilla, n=100)', 'PureChain\n(same 100Q,\nOLDs removed)']
vals_a = [20, 97]
colors_a = ['#e91e63', '#9c27b0']
bars_a = ax.bar(range(2), vals_a, color=colors_a, edgecolor='black', linewidth=1.5, width=0.55)
for i, v in enumerate(vals_a):
    ax.text(i, v + 2, f'{v}%', ha='center', fontsize=14, fontweight='bold')

ax.annotate('', xy=(1, 95), xytext=(0, 23),
            arrowprops=dict(arrowstyle='->', color='green', lw=2.5))
ax.text(0.5, 60, '+77pp gap', ha='center', color='green', fontsize=14, fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.5', fc='white', ec='green', alpha=0.95))
ax.text(0.5, 8, 'Task is solvable\nwhen context clean', ha='center', fontsize=11,
        style='italic', color='#333')

ax.set_xticks(range(2))
ax.set_xticklabels(labels_a, fontsize=11)
ax.set_ylabel('FC-MH EM (%, n=100)')
ax.set_ylim(0, 110)
ax.set_title('Panel A — Construct Validity', fontsize=13, fontweight='bold', pad=12)
ax.grid(axis='y', alpha=0.3)

# Panel B: Multiplicative baseline (full 100: P_KU=77, P_MH|noisy=60, Predicted=46, Observed=20)
ax = axes[1]
ax.set_facecolor('#fff8e1')
labels_b = ['$P_{KU}$\n(FC-SH)', '$P_{MH|\\mathrm{noisy}}$\n(OracleClean-All)',
            'Predicted\n(independence)', 'Observed\n(FC-MH vanilla)']
vals_b = [77, 60, 46, 20]
colors_b = ['#42a5f5', '#42a5f5', '#9e9e9e', '#e91e63']
bars_b = ax.bar(range(4), vals_b, color=colors_b, edgecolor='black', linewidth=1.4, width=0.6)
for i, v in enumerate(vals_b):
    ax.text(i, v + 2, f'{v}%', ha='center', fontsize=13, fontweight='bold')

ax.text(0.5, 38, '×', ha='center', fontsize=20, fontweight='bold', color='#333')
ax.text(1.5, 38, '=', ha='center', fontsize=20, fontweight='bold', color='#333')

ax.annotate('', xy=(3, 23), xytext=(2, 44),
            arrowprops=dict(arrowstyle='->', color='red', lw=2.5))
ax.text(2.5, 36, '-26pp gap', ha='center', color='red', fontsize=13, fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='red', alpha=0.95))
ax.text(2.5, 5, 'Failure below\nindependence baseline', ha='center', fontsize=10,
        style='italic', color='#333')

ax.text(0.97, 0.97, "$P_{KU}$ pool-invariance\nverified by P1.5\n(FC-MH pool: 78.3%\n vs FC-SH: 77%)",
        transform=ax.transAxes, fontsize=9, va='top', ha='right',
        bbox=dict(boxstyle='round,pad=0.45', fc='#e8f5e9', ec='#2e7d32', alpha=0.95))

ax.set_xticks(range(4))
ax.set_xticklabels(labels_b, fontsize=10)
ax.set_ylabel('Probability / EM (%, n=100)')
ax.set_ylim(0, 100)
ax.set_title('Panel B — Multiplicative Baseline', fontsize=13, fontweight='bold', pad=12)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig(OUT / 'fig2_construct_multiplicative.png', dpi=160, bbox_inches='tight')
plt.close()
print('Saved F2')


# =====================================================================
# F3 — Channel Ceiling Ladder (full 100)
# =====================================================================
fig, ax = plt.subplots(figsize=(11, 6.5))

# Setup labels: ✓/× notation showing what fact categories are KEPT in LLM context
# (chain_new is always kept — that's the answer)
setups = [
    'Vanilla\n✓ chain_old\n✓ other_olds',
    'OracleClean-\nOthers\n✓ chain_old\n× other_olds',
    'OracleClean-\nThisChain\n× chain_old\n✓ other_olds',
    'OracleClean-\nAll\n× chain_old\n× other_olds',
    'PureChain\nOnly chain_new\n(0 distractors)',
]
vals = [20, 25, 55, 60, 97]
colors = ['#e91e63', '#9e9e9e', '#1565c0', '#9e9e9e', '#9c27b0']

x = np.arange(len(setups))
bars = ax.bar(x, vals, color=colors, edgecolor='black', linewidth=1.4, width=0.6)
for i, v in enumerate(vals):
    ax.text(i, v + 1.5, f'{v}%', ha='center', fontsize=13, fontweight='bold')

# --- Inline semantic gap labels between adjacent bars ---

# (a) Vanilla → OracleClean-Others: +5pp, "other_olds 影響小"
ax.plot([0.3, 0.7], [25, 25], color='#666', lw=1.2, alpha=0.85)
ax.plot([0.7, 0.7], [20, 25], color='#666', lw=1.2, alpha=0.85)
ax.text(0.5, 33, '+5pp\nother_olds 影響小',
        ha='center', va='center', color='#444', fontsize=10, style='italic',
        bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#888', alpha=0.92, lw=0.8))

# (b) OracleClean-ThisChain → OracleClean-All: +5pp, "other_olds 影響小 (再次驗證)"
ax.plot([2.3, 2.7], [60, 60], color='#666', lw=1.2, alpha=0.85)
ax.plot([2.7, 2.7], [55, 60], color='#666', lw=1.2, alpha=0.85)
ax.text(2.5, 67, '+5pp\nother_olds 影響小\n(再次驗證)',
        ha='center', va='center', color='#444', fontsize=10, style='italic',
        bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#888', alpha=0.92, lw=0.8))

# (c) OracleClean-All → PureChain: +37pp suspended question (no semantic, prompt for verbal bridge to fig4)
ax.plot([3.3, 3.7], [97, 97], color='#444', lw=1.5, alpha=0.85)
ax.plot([3.7, 3.7], [60, 97], color='#444', lw=1.5, alpha=0.85)
ax.text(3.5, 80, '+37pp\n???',
        ha='center', va='center', color='#222', fontsize=12, fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.35', fc='#fff9c4', ec='#f9a825', alpha=0.95, lw=1.5))

# (d) Big spanning +35pp arrow from Vanilla → OracleClean-ThisChain — main story
#     Single arrow is enough: the 2x2 ladder layout itself implicitly shows that
#     OracleClean-Others → OracleClean-All gives the same +35pp (additive decomposition,
#     chain_old's effect is independent of other_olds presence). No need to draw it twice.
ax.annotate('', xy=(2, 55 + 0.5), xytext=(0, 20 + 0.5),
            arrowprops=dict(arrowstyle='->', color='red', lw=3, connectionstyle="arc3,rad=-0.32"))
ax.text(1.0, 50, '+35pp\nchain_old 是主因 ★',
        ha='center', va='center', color='red', fontweight='bold', fontsize=14,
        bbox=dict(boxstyle='round,pad=0.5', fc='white', ec='red', alpha=0.95, lw=2))

# (e) PureChain annotation — pure multi-hop reasoning ceiling
ax.text(4, 110, '純多跳推理 ceiling\n(no noise, no conflict)\n→ 理所當然解得了',
        ha='center', va='center', color='#6a1b9a', fontsize=10, fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.3', fc='#f3e5f5', ec='#6a1b9a', alpha=0.92, lw=1))

ax.set_xticks(x)
ax.set_xticklabels(setups, fontsize=9.5)
ax.set_ylabel('FC-MH EM (orig prompt, n=100)', fontsize=12)
ax.set_ylim(0, 122)
ax.grid(axis='y', alpha=0.3)
# Note explaining ✓/× convention (top-left)
ax.text(0.01, 0.98,
        '✓ = kept in LLM context | × = removed\n'
        '(chain_new always kept — it is the answer chain)',
        transform=ax.transAxes, fontsize=9, va='top', ha='left',
        style='italic', color='#555',
        bbox=dict(boxstyle='round,pad=0.35', fc='#f5f5f5', ec='#aaa', alpha=0.92))
plt.tight_layout()
plt.savefig(OUT / 'fig3_channel_ceiling_ladder.png', dpi=160, bbox_inches='tight')
plt.close()
print('Saved F3')


# =====================================================================
# F4 — Cross-cleanness × Prompt (full 100)
# Narrative: structured prompt designed to "stabilize multi-hop reasoning"
# - V1 trailer designed first; big gain on chain_old-free settings
# - V2/V3 added to test "is V1 overfit?" → similar gains, not overfit
# - Setup motivates memory-side retrieval guidance (no inference prompt change)
# =====================================================================
fig, ax = plt.subplots(figsize=(11, 6.5))

cleanness = ['Vanilla', 'OracleClean-\nOthers',
             'OracleClean-\nThisChain\n× chain_old\n✓ other_olds',
             'OracleClean-\nAll\n× chain_old\n× other_olds',
             'PureChain']
no_struct = [20, 25, 55, 60, 97]
v1_trailer = [23, 33, 83, 78, 98]
chain_old_kept = [True, True, False, False, False]  # chain_old still in context?

x = np.arange(len(cleanness))

# Background tint: light green for "chain_old removed" settings (where prompt thrives)
ax.axvspan(1.5, 3.5, alpha=0.13, color='#4caf50', zorder=0,
           label='_chain_old removed (prompt 發揮空間)')

# Plot lines
ax.plot(x, no_struct, 'o--', color='#9e9e9e', lw=2.2, markersize=10,
        label='No structured prompt (orig)', zorder=3)
ax.plot(x, v1_trailer, 'o-', color='#1976d2', lw=2.5, markersize=10,
        label='+ V1 trailer', zorder=4)

# V2/V3 markers at OracleClean-ThisChain (cluster at i=2)
ax.plot([2], [86], 's', color='#e65100', markersize=14,
        label='+ V2 cite-source', zorder=5)
ax.plot([2], [85], '^', color='#388e3c', markersize=14,
        label='+ V3 decompose', zorder=5)

# --- Double-arrows showing prompt gain at the two chain_old-removed settings ---
# Double arrow at OracleClean-ThisChain: orig 55 ↔ V1 83, +28pp
ax.annotate('', xy=(2 - 0.04, 83), xytext=(2 - 0.04, 55),
            arrowprops=dict(arrowstyle='<->', color='#2e7d32', lw=2.5))
ax.text(2 - 0.32, 69, '+28pp',
        ha='center', va='center', color='#2e7d32', fontweight='bold', fontsize=11,
        bbox=dict(boxstyle='round,pad=0.3', fc='#e8f5e9', ec='#2e7d32', alpha=0.95))

# Double arrow at OracleClean-All: orig 60 ↔ V1 78, +18pp
ax.annotate('', xy=(3, 78), xytext=(3, 60),
            arrowprops=dict(arrowstyle='<->', color='#2e7d32', lw=2.5))
ax.text(3 - 0.28, 69, '+18pp',
        ha='center', va='center', color='#2e7d32', fontweight='bold', fontsize=11,
        bbox=dict(boxstyle='round,pad=0.3', fc='#e8f5e9', ec='#2e7d32', alpha=0.95))

# Plot data labels
for i, (n, v) in enumerate(zip(no_struct, v1_trailer)):
    ax.text(i, n - 6, f'{n}%', ha='center', fontsize=10, color='#666')
    if i == 2:
        ax.text(i - 0.32, v + 4, f'{v}%', ha='right', va='center',
                fontsize=10, color='#1976d2', fontweight='bold')
    else:
        ax.text(i, v + 3, f'{v}%', ha='center', fontsize=10, color='#1976d2', fontweight='bold')

# V2/V3 labels at OA2
ax.text(2 + 0.18, 86, '86%', ha='left', va='center', fontsize=10,
        color='#e65100', fontweight='bold')
ax.text(2 + 0.18, 79, '85%', ha='left', va='center', fontsize=10,
        color='#388e3c', fontweight='bold')

# Annotations at extremes: trailer 救不了 / 已飽和
ax.text(0, 38, 'chain_old 還在\nprompt 救不了\n(+3pp)', ha='center', fontsize=9,
        color='#999', style='italic',
        bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='#bbb', alpha=0.85))

ax.text(4, 88, '已飽和\n(+1pp)', ha='center', fontsize=9, color='#999', style='italic',
        bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='#bbb', alpha=0.85))

# Top message
ax.text(2.5, 110, '結構化 prompt 在「chain_old 移除」條件下大幅提升 → 多跳推理需要 reasoning guide',
        ha='center', fontsize=10.5, color='#2e7d32', fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='#2e7d32', alpha=0.95))

ax.set_xticks(x)
ax.set_xticklabels(cleanness, fontsize=10)
ax.set_ylabel('FC-MH EM (n=100)', fontsize=12)
ax.set_ylim(0, 120)
ax.legend(loc='lower right', fontsize=9, frameon=True)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(OUT / 'fig4_cross_cleanness_prompt.png', dpi=160, bbox_inches='tight')
plt.close()
print('Saved F4')


# =====================================================================
# F5 — Chain_old Killer Effect Scales with Noise (3 single-variable pairs)
#       Same 100 Q, only diff in each pair: this Q's chain_old presence
# =====================================================================
fig, ax = plt.subplots(figsize=(11, 5.8))

# Three pair settings, low → high noise saturation
pairs = [
    {'label': 'Pair 1\n(ceiling, no distractor)',
     'no_old': 97, 'with_old': 89,
     'no_old_name': 'PureChain', 'with_old_name': 'Mode A\n(+chain_old)',
     'note': 'ctx ≈ chain_new only\n(~3 facts)'},
    {'label': 'Pair 2\n(HippoRAG-v2 retrieval)',
     'no_old': 55, 'with_old': 21,
     'no_old_name': 'OracleClean-ThisChain', 'with_old_name': 'Vanilla\n(retrieval含chain_old)',
     'note': 'ctx ≈ top-10 chunks\n(~378 facts)'},
    {'label': 'Pair 3\n(saturated full corpus)',
     'no_old': 56, 'with_old': 9,
     'no_old_name': 'Mode C n=0', 'with_old_name': 'Mode C n=1\n(+1 chain_old)',
     'note': 'ctx = chain_new + all\nnon-this-chain (~447 facts)'},
]

# Bar layout: each pair takes 3 slots (no_old, with_old, gap)
n_pairs = len(pairs)
bar_w = 0.36
pair_w = 1.0
group_x = []
for i in range(n_pairs):
    base = i * 2.2  # gap between pairs
    group_x.append((base, base + 0.85))

C_OK = '#43a047'
C_BAD = '#e53935'

for i, p in enumerate(pairs):
    x0, x1 = group_x[i]
    ax.bar(x0, p['no_old'], bar_w * 1.5, color=C_OK, edgecolor='black', linewidth=1.2)
    ax.bar(x1, p['with_old'], bar_w * 1.5, color=C_BAD, edgecolor='black', linewidth=1.2)
    # value labels
    ax.text(x0, p['no_old'] + 1.5, f'{p["no_old"]}%', ha='center', fontsize=13, fontweight='bold')
    ax.text(x1, p['with_old'] + 1.5, f'{p["with_old"]}%', ha='center', fontsize=13, fontweight='bold')
    # bar names
    ax.text(x0, -3.5, p['no_old_name'], ha='center', fontsize=9, color='#2e7d32')
    ax.text(x1, -3.5, p['with_old_name'], ha='center', fontsize=9, color='#c62828')
    # arrow + diff
    diff = p['no_old'] - p['with_old']
    ax.annotate('', xy=(x1, p['with_old'] + 4), xytext=(x0, p['no_old'] - 3),
                arrowprops=dict(arrowstyle='->', color='red', lw=2.2))
    mid_x = (x0 + x1) / 2
    mid_y = (p['no_old'] + p['with_old']) / 2 + 4
    ax.text(mid_x, mid_y, f'-{diff}pp', ha='center', color='red',
            fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='red', alpha=0.95, lw=1.2))
    # pair label below
    ax.text(mid_x, -10, p['label'], ha='center', fontsize=10, fontweight='bold', color='#333')
    ax.text(mid_x, -16.5, p['note'], ha='center', fontsize=8, color='#666', style='italic')

# Trend annotation (top)
ax.text(0.5, 1.06,
        'chain_old\'s killer effect amplifies with context saturation:'
        '  -8pp (ceiling) → -34pp (retrieval) → -47pp (saturated)',
        transform=ax.transAxes, ha='center', fontsize=11, fontweight='bold', color='#c62828')

ax.set_ylabel('FC-MH EM (orig prompt, n=100 each pair)', fontsize=12)
ax.set_ylim(-22, 110)
ax.set_xlim(-0.6, group_x[-1][1] + 0.6)
ax.set_xticks([])
ax.grid(axis='y', alpha=0.3)

# Legend manually
ax.bar(0, 0, color=C_OK, edgecolor='black', label='same context, no this-Q chain_old')
ax.bar(0, 0, color=C_BAD, edgecolor='black', label='same context, + this-Q chain_old')
ax.legend(loc='upper right', fontsize=10, frameon=True)

plt.tight_layout()
plt.savefig(OUT / 'fig5_chain_old_dose_scaling.png', dpi=160, bbox_inches='tight')
plt.close()
print('Saved F5 (chain_old dose-response across noise levels)')

# =====================================================================
# F6 — Mem0/Zep FC-MH detection × answer overview (stacked bar)
#       Use BEFORE fig7 (pulled-by-old) and the Claim 2 table.
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5),
                          gridspec_kw={'width_ratios': [1, 1]})

# Data: detection bucket × correct/wrong (aligned with MABench default = wrapped query)
# Aligned overall MH EM: Mem0 44/100, Zep 28/100
mem0_buckets = {
    'all_detected':       {'correct': 26, 'wrong': 15},  # 41
    'partial':            {'correct': 11, 'wrong': 26},  # 37
    'no_detection':       {'correct': 7,  'wrong': 15},  # 22
}
zep_buckets = {
    'all_detected':       {'correct': 8,  'wrong': 12},  # 20
    'partial':            {'correct': 6,  'wrong': 29},  # 35
    'no_detection':       {'correct': 14, 'wrong': 31},  # 45
}

bucket_order = ['all_detected', 'partial', 'no_detection']
y_pos = np.arange(len(bucket_order))

C_OK = '#4caf50'      # correct (green)
C_BAD = '#e91e63'     # wrong (red)

for ax, name, data in [(axes[0], 'Mem0 (n=100)', mem0_buckets),
                        (axes[1], 'Zep (n=100)',  zep_buckets)]:
    correct = [data[b]['correct'] for b in bucket_order]
    wrong = [data[b]['wrong'] for b in bucket_order]
    totals = [c + w for c, w in zip(correct, wrong)]
    em_rates = [(c / t * 100) if t else 0 for c, t in zip(correct, totals)]

    ax.barh(y_pos, correct, color=C_OK, edgecolor='black', linewidth=1.0, label='correct (EM)')
    ax.barh(y_pos, wrong, left=correct, color=C_BAD, edgecolor='black', linewidth=1.0, label='wrong')

    # Annotations: counts inside / right of bars
    for i, (c, w, t, em) in enumerate(zip(correct, wrong, totals, em_rates)):
        # Correct count inside green portion (if big enough)
        if c >= 4:
            ax.text(c / 2, i, f'{c}', ha='center', va='center', fontsize=11, fontweight='bold', color='white')
        elif c > 0:
            ax.text(c + 0.5, i, f'{c}', ha='left', va='center', fontsize=10, fontweight='bold', color=C_OK)
        # Wrong count inside red portion
        if w >= 4:
            ax.text(c + w / 2, i, f'{w}', ha='center', va='center', fontsize=11, fontweight='bold', color='white')
        elif w > 0:
            ax.text(c + w + 0.5, i, f'{w}', ha='left', va='center', fontsize=10, fontweight='bold', color=C_BAD)
        # Total + EM rate at the right
        ax.text(t + 5, i, f'(n={t}, EM={em:.0f}%)',
                ha='left', va='center', fontsize=10, color='#333')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(bucket_order, fontsize=11)
    ax.set_xlim(0, 110)
    ax.set_xlabel('# questions', fontsize=11)
    ax.set_title(name, fontsize=13, fontweight='bold', pad=10)
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.3)
    ax.legend(loc='lower right', fontsize=10, frameon=True)

# Bridge text below subplots
fig.text(0.5, 0.02,
         '數字採 MABench-aligned default pipeline (含 FC seq-rule wrapper)\n'
         '綠色 = 答對  → all_detected EM 仍 Mem0 63% / Zep 40% ⇒ Claim 2 (偵測對 ≠ 答對)\n'
         '紅色 = 答錯  → 仍 28-29% wrong 含 chain_old ⇒ Claim 1',
         ha='center', fontsize=10, style='italic', color='#444',
         bbox=dict(boxstyle='round,pad=0.4', fc='#f5f5f5', ec='#888', alpha=0.9))

plt.tight_layout(rect=[0, 0.07, 1, 1])
plt.savefig(OUT / 'fig6_detection_answer_overview.png', dpi=160, bbox_inches='tight')
plt.close()
print('Saved F6')

print(f'\n=== 6 slides figures saved (all using n=100 consistently) to {OUT} ===')
