"""
Generate figures for motivation_narrative.md.

8 figures aligned with narrative sections:
  Fig 1 (§1): SH→MH drop — 3 systems × 2 splits
  Fig 2 (§1.5): HippoRAG retrieval coverage — chain_new / chain_old by hop count
  Fig 3 (§2.A): Channel ceiling ladder — 6 setups (orig prompt, rule-clean 96)
  Fig 4 (§2.A): Mode C dose-response — n_inject vs acc (true dose-response)
  Fig 5 (§2.B): Cross-cleanness × prompt-variant — 5 cleanness × {orig, +trailer}
  Fig 6 (§4.3.A): Detection coverage — Mem0 vs Zep, per-hop and all_detected
  Fig 7 (§4.2): Pulled-by-old failure rate by num_hops — Mem0 + Zep
  Fig 8 (§7): Phase 1 V0 result vs ladder

All figures saved to analysis/paper_motivation/figures/v2/.
"""

import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

BASE = Path('/home/yhchiang/MemoryAgentBench')
DIAG = BASE / 'analysis/results/diagnostic'
FIG_DIR = BASE / 'analysis/paper_motivation/figures/v2'
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Common colors
C_VANILLA = '#888888'
C_FILTER = '#1f77b4'
C_ORACLE = '#2ca02c'
C_CEILING = '#9467bd'
C_NEW = '#2ca02c'
C_OLD = '#d62728'

plt.rcParams.update({
    'font.size': 11,
    'font.family': 'sans-serif',
    'font.sans-serif': ['Noto Sans CJK JP', 'Noto Serif CJK TC', 'Noto Serif CJK JP', 'AR PL UKai TW MBE', 'DejaVu Sans'],
    'axes.unicode_minus': False,
})

# ===== Fig 1: SH→MH drop =====
fig, ax = plt.subplots(figsize=(8, 4.5))
systems = ['HippoRAG-v2\n(vanilla)', 'Mem0 customized\n(filter)', 'Zep\n(annotation)']
sh = [77, 77, 79]
mh = [22, 43, 8]
x = np.arange(len(systems))
w = 0.36
b1 = ax.bar(x - w/2, sh, w, label='FC-SH', color='#7fbc41', edgecolor='black')
b2 = ax.bar(x + w/2, mh, w, label='FC-MH', color='#de77ae', edgecolor='black')
for i, (s, m) in enumerate(zip(sh, mh)):
    ax.text(i - w/2, s + 1, f'{s}%', ha='center', fontsize=10, fontweight='bold')
    ax.text(i + w/2, m + 1, f'{m}%', ha='center', fontsize=10, fontweight='bold')
    drop = s - m
    ax.annotate('', xy=(i + w/2, m + 8), xytext=(i - w/2, s - 5),
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
    ax.text(i, (s + m) / 2, f'-{drop}pp', ha='center', color='red',
            fontweight='bold', fontsize=10,
            bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='red', alpha=0.85))
ax.set_xticks(x)
ax.set_xticklabels(systems)
ax.set_ylabel('Exact Match (%)')
ax.set_title('Fig 1 — FC-SH → FC-MH 全面 drop (Gemini 3.1 FL Preview)')
ax.set_ylim(0, 95)
ax.legend(loc='upper right')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig1_sh_mh_drop.png', dpi=150, bbox_inches='tight')
plt.close()
print(f'Saved fig1')

# ===== Fig 2: HippoRAG retrieval coverage =====
fig, ax = plt.subplots(figsize=(8, 4.5))
labels = ['FC-SH\n(n=100)', 'FC-MH 2-hop\n(n=61)', 'FC-MH 3-hop\n(n=24)', 'FC-MH 4-hop\n(n=15)']
chain_new_rates = [99, 97, 94, 95]
chain_old_rates = [100, 98, 100, 97]
x = np.arange(len(labels))
w = 0.36
ax.bar(x - w/2, chain_new_rates, w, label='chain_new in top-10', color=C_NEW, edgecolor='black')
ax.bar(x + w/2, chain_old_rates, w, label='chain_old in top-10', color=C_OLD, edgecolor='black')
for i, (n, o) in enumerate(zip(chain_new_rates, chain_old_rates)):
    ax.text(i - w/2, n + 1, f'{n}%', ha='center', fontsize=10, fontweight='bold')
    ax.text(i + w/2, o + 1, f'{o}%', ha='center', fontsize=10, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_ylabel('Retrieval coverage in top-10 (%)')
ax.set_title('Fig 2 — HippoRAG-v2 retrieval 沒崩\nchain_new/chain_old 大多在 top-10 → bottleneck 在 retrieval 之後')
ax.set_ylim(80, 105)
ax.axhline(80, color='gray', alpha=0.3)
ax.legend(loc='lower right')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig2_retrieval_coverage.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig2')

# ===== Fig 3: Channel ceiling ladder =====
fig, ax = plt.subplots(figsize=(9, 5))
setups = [
    ('PureChain\n(chain_new only, 0 distractor)', 97, C_CEILING),
    ('OracleClean-All\n(全 olds 移除)', 61, C_ORACLE),
    ('OracleClean-ThisChain\n(本題 chain_old 移)', 55, C_ORACLE),
    ('OracleClean-Others\n(只留本題 chain_old)', 26, C_FILTER),
    ('Vanilla\n(全 olds 留)', 21, C_VANILLA),
]
setups_rev = list(reversed(setups))
y = np.arange(len(setups_rev))
vals = [s[1] for s in setups_rev]
colors = [s[2] for s in setups_rev]
ax.barh(y, vals, color=colors, edgecolor='black')
for i, v in enumerate(vals):
    ax.text(v + 1.5, i, f'{v}%', va='center', fontweight='bold', fontsize=11)
ax.set_yticks(y)
ax.set_yticklabels([s[0] for s in setups_rev], fontsize=10)
ax.set_xlabel('FC-MH EM (orig prompt, rule-clean 96)')
ax.set_xlim(0, 110)
ax.set_title('Fig 3 — Channel ceiling ladder\n移除「本題 chain_old」是主 gain (+34pp);移除其他 olds 邊際 (+6pp)')
# Annotations for key gaps
ax.annotate('', xy=(55, 1), xytext=(21, 1),
            arrowprops=dict(arrowstyle='<->', color='blue', lw=1.5))
ax.text(38, 1.3, '+34pp\n(本題 chain_old 移)', ha='center', color='blue', fontweight='bold', fontsize=9)
ax.annotate('', xy=(61, 2), xytext=(55, 2),
            arrowprops=dict(arrowstyle='<->', color='gray', lw=1.5))
ax.text(58, 2.3, '+6pp', ha='center', color='gray', fontsize=9)
ax.grid(axis='x', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig3_channel_ceiling_ladder.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig3')

# ===== Fig 4: Mode C dose-response =====
fig, ax = plt.subplots(figsize=(8, 4.5))
n_inject = [0, 1, 2, 3, 4]
acc_pct = [58, 9, 3, 0, 0]
n_q = [96, 96, 63, 16, 2]
ax.plot(n_inject, acc_pct, 'o-', color=C_OLD, linewidth=2, markersize=12, label='EM rate')
for x_, y_, n_ in zip(n_inject, acc_pct, n_q):
    ax.annotate(f'{y_}%\n(n={n_})', (x_, y_), textcoords='offset points',
                xytext=(0, 12), ha='center', fontweight='bold', fontsize=10)
ax.annotate('', xy=(1, 9), xytext=(0, 58),
            arrowprops=dict(arrowstyle='->', color='red', lw=2))
ax.text(0.5, 35, '注入 1 chain_old\n→ -49pp', color='red', fontweight='bold', fontsize=11,
        bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='red', alpha=0.9))
ax.set_xticks(n_inject)
ax.set_xlabel('chain_olds injected into saturated noise context')
ax.set_ylabel('FC-MH EM (rule-clean 96, orig prompt)')
ax.set_title('Fig 4 — Mode C true dose-response\n注入 1 chain_old 到飽和噪音 → 同 96 題 EM 從 58% → 9%')
ax.set_ylim(-5, 75)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig4_dose_response.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig4')

# ===== Fig 5: Cross-cleanness × prompt-variant =====
fig, ax = plt.subplots(figsize=(9, 5))
cleanness = ['Vanilla\n(髒)', 'OracleClean-\nOthers', 'OracleClean-\nThisChain', 'OracleClean-\nAll', 'PureChain\n(乾淨)']
orig_vals = [21, 26, 55, 61, 97]
trailer_vals = [23, 34, 83, 81, 98]  # OA2 mod is 83/96=86 with V2/V3, V1=83
deltas = [t - o for o, t in zip(orig_vals, trailer_vals)]

x = np.arange(len(cleanness))
w = 0.36
b1 = ax.bar(x - w/2, orig_vals, w, label='orig prompt', color='#74add1', edgecolor='black')
b2 = ax.bar(x + w/2, trailer_vals, w, label='+ V1 trailer', color='#fdae61', edgecolor='black')
for i, (o, t, d) in enumerate(zip(orig_vals, trailer_vals, deltas)):
    ax.text(i - w/2, o + 1, f'{o}%', ha='center', fontsize=9, fontweight='bold')
    ax.text(i + w/2, t + 1, f'{t}%', ha='center', fontsize=9, fontweight='bold')
    color = 'red' if d >= 20 else ('orange' if d >= 10 else 'gray')
    ax.text(i, max(o, t) + 7, f'+{d}pp', ha='center', color=color, fontweight='bold', fontsize=10,
            bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=color, alpha=0.85))

ax.set_xticks(x)
ax.set_xticklabels(cleanness, fontsize=10)
ax.set_ylabel('FC-MH EM (rule-clean 96)')
ax.set_title('Fig 5 — Trailer prompt 在不同 cleanness 上效果\n中度乾淨 (OA2) 最強 (+28pp);太髒救不了,太乾淨已飽和')
ax.set_ylim(0, 115)
ax.legend(loc='upper left')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig5_cross_cleanness_trailer.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig5')

# ===== Fig 6: Detection coverage =====
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
# Per-hop
ax = axes[0]
labels = ['SH', 'MH']
mem0_perhop = [61, 57]
zep_perhop = [23, 37]
x = np.arange(len(labels))
w = 0.35
ax.bar(x - w/2, mem0_perhop, w, label='Mem0 (W1)', color='#1f77b4', edgecolor='black')
ax.bar(x + w/2, zep_perhop, w, label='Zep (Z1)', color='#ff7f0e', edgecolor='black')
for i, (m, z) in enumerate(zip(mem0_perhop, zep_perhop)):
    ax.text(i - w/2, m + 1, f'{m}%', ha='center', fontweight='bold')
    ax.text(i + w/2, z + 1, f'{z}%', ha='center', fontweight='bold')
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_ylabel('Per-hop detection rate (%)')
ax.set_title('Per-hop correct detection')
ax.set_ylim(0, 80)
ax.legend(); ax.grid(axis='y', alpha=0.3)

# Per-question all-detected
ax = axes[1]
mem0_perq = [33, 26]
zep_perq = [18, 8]
ax.bar(x - w/2, mem0_perq, w, label='Mem0', color='#1f77b4', edgecolor='black')
ax.bar(x + w/2, zep_perq, w, label='Zep', color='#ff7f0e', edgecolor='black')
for i, (m, z) in enumerate(zip(mem0_perq, zep_perq)):
    ax.text(i - w/2, m + 1, f'{m}%', ha='center', fontweight='bold')
    ax.text(i + w/2, z + 1, f'{z}%', ha='center', fontweight='bold')
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_ylabel('Per-question all-detected rate (%)')
ax.set_title('Per-question all-detected')
ax.set_ylim(0, 50)
ax.legend(); ax.grid(axis='y', alpha=0.3)
plt.suptitle('Fig 6 — 衝突偵測覆蓋率: Mem0 / Zep 在 FC-MH 都 < 30% (Gap 1)', y=1.0)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig6_detection_coverage.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig6')

# ===== Fig 7: Pulled-by-old by num_hops =====
fig, ax = plt.subplots(figsize=(9, 5))
hops = ['2-hop', '3-hop', '4-hop']
mem0_total = [34, 12, 11]
mem0_pulled = [28, 8, 11]
zep_total = [53, 24, 15]
zep_pulled = [44, 18, 13]
mem0_rate = [p / t * 100 for p, t in zip(mem0_pulled, mem0_total)]
zep_rate = [p / t * 100 for p, t in zip(zep_pulled, zep_total)]

x = np.arange(len(hops))
w = 0.35
b1 = ax.bar(x - w/2, mem0_rate, w, label='Mem0', color='#1f77b4', edgecolor='black')
b2 = ax.bar(x + w/2, zep_rate, w, label='Zep', color='#ff7f0e', edgecolor='black')
for i, (mr, zr, mp, mt, zp, zt) in enumerate(zip(mem0_rate, zep_rate, mem0_pulled, mem0_total, zep_pulled, zep_total)):
    ax.text(i - w/2, mr + 2, f'{mr:.0f}%\n({mp}/{mt})', ha='center', fontsize=9, fontweight='bold')
    ax.text(i + w/2, zr + 2, f'{zr:.0f}%\n({zp}/{zt})', ha='center', fontsize=9, fontweight='bold')
ax.axhline(82, color='red', linestyle='--', alpha=0.6, label='overall: 82% (both)')
ax.set_xticks(x); ax.set_xticklabels(hops)
ax.set_ylabel('Pulled-by-OLD rate among wrong cases (%)')
ax.set_title('Fig 7 — 答錯題目中 LLM output 含 chain_old 答案的比例\n6 cells 都 ≥ 67%, 4-hop Mem0 達 100% — Claim 1 evidence')
ax.set_ylim(0, 115)
ax.legend(loc='lower right')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig7_pulled_by_old.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig7')

# ===== Fig 8: Phase 1 V0 result vs ladder =====
fig, ax = plt.subplots(figsize=(9, 5))
setups = [
    ('PureChain (LLM reasoning ceiling)', 97, C_CEILING),
    ('OracleClean-All (oracle, 全 olds 移)', 61, C_ORACLE),
    ('OracleClean-ThisChain (oracle, OA2)', 55, C_ORACLE),
    ('Phase 1 V0 ★ (auto-detected supersession)', 44, '#e7298a'),
    ('OracleClean-Others (留 chain_old)', 26, C_FILTER),
    ('Vanilla (no filter)', 21, C_VANILLA),
]
setups_rev = list(reversed(setups))
y = np.arange(len(setups_rev))
vals = [s[1] for s in setups_rev]
colors = [s[2] for s in setups_rev]
ax.barh(y, vals, color=colors, edgecolor='black')
for i, v in enumerate(vals):
    label = setups_rev[i][0]
    is_v0 = '★' in label
    weight = 'bold' if is_v0 else 'normal'
    ax.text(v + 1.5, i, f'{v}%', va='center', fontweight=weight, fontsize=11)
ax.set_yticks(y)
ax.set_yticklabels([s[0] for s in setups_rev], fontsize=10)
ax.set_xlabel('FC-MH EM (orig prompt, rule-clean 96)')
ax.set_xlim(0, 110)
ax.set_title('Fig 8 — Phase 1 V0 (auto supersession) 拿到 OA2 oracle gain 的 67%\n22% → 44% (+23pp), recall 41% / precision 99%')
# Annotations
ax.annotate('', xy=(44, 2), xytext=(21, 2),
            arrowprops=dict(arrowstyle='<->', color='red', lw=1.8))
ax.text(32, 2.3, '+23pp', ha='center', color='red', fontweight='bold')
ax.annotate('', xy=(55, 3), xytext=(44, 3),
            arrowprops=dict(arrowstyle='<->', color='gray', lw=1.5))
ax.text(49, 3.3, '+11pp\n(toward oracle)', ha='center', color='gray', fontsize=9)
ax.grid(axis='x', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig8_phase1_v0_vs_ladder.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig8')

print('Saved fig8')

# ===== Fig 9: P1.5 Same-pool single-hop validation =====
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
ax = axes[0]
labels = ['FC-SH\nbaseline', 'FC-MH pool\n(P1.5 per-hop)', 'FC-MH pool\n2-hop', 'FC-MH pool\n3-hop', 'FC-MH pool\n4-hop']
vals = [77, 78.3, 80.3, 77.8, 75.0]
ns = ['n=100', 'n=254 hops', 'n=122', 'n=72', 'n=60']
colors = ['#888888', '#e7298a', '#1f77b4', '#1f77b4', '#1f77b4']
bars = ax.bar(range(len(labels)), vals, color=colors, edgecolor='black')
for i, (v, n) in enumerate(zip(vals, ns)):
    ax.text(i, v + 1, f'{v:.1f}%\n({n})', ha='center', fontsize=9, fontweight='bold')
ax.axhline(77, color='red', linestyle='--', alpha=0.5)
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel('Per-hop EM (%, orig prompt)')
ax.set_title('P_KU on FC-MH pool ≈ FC-SH 77%\n→ multiplicative baseline 假設成立')
ax.set_ylim(0, 95)
ax.grid(axis='y', alpha=0.3)

ax = axes[1]
labels2 = ['2-hop', '3-hop', '4-hop']
predicted = [64.5, 47.1, 31.6]
observed = [65.6, 50.0, 26.7]
x = np.arange(len(labels2))
w = 0.35
ax.bar(x - w/2, predicted, w, label='Predicted (per-hop)^N', color='#74add1', edgecolor='black')
ax.bar(x + w/2, observed, w, label='Observed all-pass', color='#fdae61', edgecolor='black')
for i, (p, o) in enumerate(zip(predicted, observed)):
    ax.text(i - w/2, p + 1, f'{p:.1f}%', ha='center', fontsize=9, fontweight='bold')
    ax.text(i + w/2, o + 1, f'{o:.1f}%', ha='center', fontsize=9, fontweight='bold')
ax.set_xticks(x); ax.set_xticklabels(labels2)
ax.set_ylabel('All-pass rate (%)')
ax.set_title('Per-hop independence holds 拆解條件下\n→ MH collapse 22% 不是 hop dependence')
ax.set_ylim(0, 80); ax.legend(); ax.grid(axis='y', alpha=0.3)

plt.suptitle('Fig 9 — P1.5 same-pool baseline 驗證 multiplicative baseline 假設', y=1.02)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig9_p1_5_validation.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig9')

# ===== Fig 10: P1.4 No-seq-rule ablation =====
fig, ax = plt.subplots(figsize=(8, 5))
labels = ['n_inject=0\n(clean noise)', 'n_inject=1\n(+1 chain_old)']
with_seq = [58, 9]
without_seq = [47.9, 1.0]
x = np.arange(len(labels))
w = 0.36
b1 = ax.bar(x - w/2, with_seq, w, label='With FC seq rule (Mode C 原版)', color='#74add1', edgecolor='black')
b2 = ax.bar(x + w/2, without_seq, w, label='Without seq rule (P1.4 bare)', color='#fdae61', edgecolor='black')
for i, (a, b) in enumerate(zip(with_seq, without_seq)):
    ax.text(i - w/2, a + 1, f'{a}%', ha='center', fontsize=10, fontweight='bold')
    ax.text(i + w/2, b + 1, f'{b}%', ha='center', fontsize=10, fontweight='bold')
# Drop annotations
ax.annotate('', xy=(1 - w/2, 9), xytext=(0 - w/2, 58),
            arrowprops=dict(arrowstyle='->', color='red', lw=2))
ax.text(0.4, 35, '-49pp\n(with seq)', color='red', fontweight='bold', fontsize=10,
        bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='red', alpha=0.9))
ax.annotate('', xy=(1 + w/2, 1), xytext=(0 + w/2, 47.9),
            arrowprops=dict(arrowstyle='->', color='darkorange', lw=2))
ax.text(0.95, 25, '-46.9pp\n(no seq)', color='darkorange', fontweight='bold', fontsize=10,
        bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='darkorange', alpha=0.9))
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_ylabel('FC-MH EM (rule-clean 96)')
ax.set_title('Fig 10 — P1.4 No-seq-rule ablation\nchain_old 注入造成的崩潰 (-47pp) 在有/無 seq rule 都成立')
ax.set_ylim(0, 75)
ax.legend(loc='upper right'); ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(FIG_DIR / 'fig10_p1_4_no_seq_rule.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved fig10')

print(f'\n=== All 10 figures saved to {FIG_DIR} ===')
