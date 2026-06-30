"""
generate_step1a_charts.py
=========================
Step 1A 分析圖表：FC-MH 衝突跳數 vs 答對率

輸出：
  analysis/results/fig_conflict_hops_vs_acc.png        -- 折線圖（答對題數/總題數標注）
  analysis/results/fig_hop_composition.png              -- 每組的 2/3/4-hop 組成 + Acc overlay
  analysis/results/fig_retrieval_vs_acc.png             -- 折線圖（retrieval 品質 vs Acc）
  analysis/results/fig_error_distribution.png           -- 堆疊長條圖（失敗原因分布）
"""

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)

# ── 載入分析結果 ──────────────────────────────────────────────────────────────
with open(OUT / "mh_512_mquake_analysis.json") as f:
    entries = json.load(f)


def count_conflict_hops(e):
    return sum(1 for h in e["hops"] if h["conflict_type"] == "has_pair")


groups = defaultdict(list)
for e in entries:
    groups[count_conflict_hops(e)].append(e)

conflict_counts = sorted(groups.keys())   # [1, 2, 3, 4]
n_list      = [len(groups[k]) for k in conflict_counts]
correct_list = [sum(1 for e in groups[k] if e["exact_match"]) for k in conflict_counts]
acc_list    = [c / n * 100 for c, n in zip(correct_list, n_list)]

# 每組的 num_hops 構成：{n_conflict: {num_hops: count}}
hop_composition = {}
for k in conflict_counts:
    comp = defaultdict(int)
    for e in groups[k]:
        comp[e["num_hops"]] += 1
    hop_composition[k] = dict(sorted(comp.items()))

# ── Figure 1：衝突跳數 vs Accuracy 折線圖（標注 correct/total） ──────────────
fig, ax = plt.subplots(figsize=(7.5, 5))

ax.plot(conflict_counts, acc_list,
        marker='o', linewidth=2.5, markersize=10,
        color='#E05C5C', zorder=5, label='Accuracy (%)')

for x, acc, correct, n in zip(conflict_counts, acc_list, correct_list, n_list):
    # 標注：答對題數/總題數 + 百分比（兩行）
    ax.annotate(
        f"{correct}/{n}\n({acc:.1f}%)",
        xy=(x, acc), xytext=(0, 16),
        textcoords='offset points', ha='center', fontsize=9.5,
        color='#333333',
        bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.7)
    )

ax.set_xticks(conflict_counts)
ax.set_xticklabels(
    [f"{k} conflict hop{'s' if k > 1 else ''}" for k in conflict_counts],
    fontsize=10
)
ax.set_ylabel("Accuracy (%)", fontsize=11)
ax.set_title(
    "FC-MH (HippoRAG-v2, chunk=512, k=10)\nAccuracy vs Number of Conflicting Hops",
    fontsize=12, pad=12
)
ax.set_ylim(-5, 48)
ax.axhline(y=11.0, color='gray', linestyle='--', linewidth=1,
           label='Overall Acc 11/100 (11.0%)')
ax.legend(fontsize=9)
ax.grid(axis='y', alpha=0.3)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig(str(OUT / "fig_conflict_hops_vs_acc.png"), dpi=150, bbox_inches='tight')
plt.close()
print("✅ fig1 saved: fig_conflict_hops_vs_acc.png")

# ── Figure 4：每組的 2/3/4-hop 構成 + Accuracy overlay ───────────────────────
all_num_hops = [2, 3, 4]
hop_colors   = {'2': '#4C72B0', '3': '#DD8452', '4': '#8172B3'}
hop_labels   = {2: '2-hop', 3: '3-hop', 4: '4-hop'}

fig, ax1 = plt.subplots(figsize=(8, 5))
x = np.arange(len(conflict_counts))
width = 0.55
bottoms = np.zeros(len(conflict_counts))

for nh in all_num_hops:
    vals = np.array([hop_composition[k].get(nh, 0) for k in conflict_counts])
    bars = ax1.bar(x, vals, width, label=hop_labels[nh],
                   color=hop_colors[str(nh)], bottom=bottoms, alpha=0.85)
    # 在格子中標注題數（非零才標）
    for xi, (v, b) in enumerate(zip(vals, bottoms)):
        if v > 0:
            ax1.text(xi, b + v / 2, str(int(v)),
                     ha='center', va='center', fontsize=9, color='white', fontweight='bold')
    bottoms += vals

# 在每組頂端標注 "conflict / total hops" 說明
for xi, k in enumerate(conflict_counts):
    comp = hop_composition[k]
    total_q = sum(comp.values())
    # e.g. "1/2, 1/3, 1/4 each conflict hop"
    frac_parts = [f"{k}/{nh}" for nh in sorted(comp.keys()) if comp.get(nh, 0) > 0]
    frac_str = ", ".join(frac_parts) + " hops conflicted"
    ax1.text(xi, total_q + 0.5, frac_str,
             ha='center', va='bottom', fontsize=7.5, color='#555555', style='italic')

ax1.set_xticks(x)
ax1.set_xticklabels(
    [f"{k} conflict hop{'s' if k > 1 else ''}" for k in conflict_counts],
    fontsize=10
)
ax1.set_ylabel("Number of Questions", fontsize=11)
ax1.set_ylim(0, 62)
ax1.legend(title="Question type", fontsize=9, loc='upper right')
ax1.grid(axis='y', alpha=0.3)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# 右軸：Accuracy 折線
ax2 = ax1.twinx()
ax2.plot(x, acc_list, marker='o', linewidth=2.5, markersize=9,
         color='#E05C5C', zorder=5, label='Accuracy (%)')
for xi, (acc, correct, n) in enumerate(zip(acc_list, correct_list, n_list)):
    ax2.annotate(
        f"{correct}/{n}\n({acc:.1f}%)",
        xy=(xi, acc), xytext=(18, 0),
        textcoords='offset points', ha='left', va='center', fontsize=8.5,
        color='#E05C5C',
        arrowprops=dict(arrowstyle='-', color='#E05C5C', lw=0.8)
    )
ax2.set_ylabel("Accuracy (%)", fontsize=11, color='#E05C5C')
ax2.tick_params(axis='y', labelcolor='#E05C5C')
ax2.set_ylim(-2, 45)
ax2.spines['top'].set_visible(False)
ax2.axhline(y=11.0, color='#E05C5C', linestyle=':', linewidth=1, alpha=0.5)

ax1.set_title(
    "FC-MH: Question Composition per Conflict-Hop Group\n"
    "(stacked bars = question type; line = accuracy)",
    fontsize=12, pad=12
)

# 合併 legend
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(
    ax1.get_legend_handles_labels()[0] + lines2,
    ax1.get_legend_handles_labels()[1] + labels2,
    title="", fontsize=9, loc='upper right'
)

plt.tight_layout()
plt.savefig(str(OUT / "fig_hop_composition.png"), dpi=150, bbox_inches='tight')
plt.close()
print("✅ fig4 saved: fig_hop_composition.png")

# ── Figure 2：Retrieval 品質 vs Accuracy 折線圖 ───────────────────────────────
gt_ret_rate, old_ret_rate, all_both_rate = [], [], []

for k in conflict_counts:
    grp = groups[k]
    hp_hops = [h for e in grp for h in e["hops"] if h["conflict_type"] == "has_pair"]
    gt_r  = sum(1 for h in hp_hops if h.get("gt_retrieved")) / len(hp_hops) * 100
    old_r = sum(1 for h in hp_hops if h.get("old_retrieved")) / len(hp_hops) * 100
    n_ab  = sum(
        1 for e in grp
        if all(
            h.get("gt_retrieved") and h.get("old_retrieved")
            for h in e["hops"] if h["conflict_type"] == "has_pair"
        )
    )
    gt_ret_rate.append(gt_r)
    old_ret_rate.append(old_r)
    all_both_rate.append(n_ab / len(grp) * 100)

fig, ax = plt.subplots(figsize=(7, 4.5))
ax.plot(conflict_counts, gt_ret_rate,   marker='s', linewidth=2.2, markersize=8,
        color='#4C72B0', label='GT new-fact retrieved (per hop)')
ax.plot(conflict_counts, old_ret_rate,  marker='^', linewidth=2.2, markersize=8,
        color='#DD8452', label='Old fact retrieved (per hop)')
ax.plot(conflict_counts, all_both_rate, marker='D', linewidth=2.2, markersize=8,
        color='#55A868', label='All conflict hops: both retrieved (per entry)')
ax.plot(conflict_counts, acc_list,      marker='o', linewidth=2.2, markersize=8,
        color='#E05C5C', linestyle='--', label='Accuracy (%)')

ax.set_xticks(conflict_counts)
ax.set_xticklabels(
    [f"{k} conflict hop{'s' if k > 1 else ''}" for k in conflict_counts],
    fontsize=10
)
ax.set_ylabel("Rate (%)", fontsize=11)
ax.set_title(
    "FC-MH: Retrieval Quality vs Accuracy\nby Number of Conflicting Hops",
    fontsize=12, pad=12
)
ax.set_ylim(0, 110)
ax.legend(fontsize=8.5, loc='lower left')
ax.grid(axis='y', alpha=0.3)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig(str(OUT / "fig_retrieval_vs_acc.png"), dpi=150, bbox_inches='tight')
plt.close()
print("✅ fig2 saved: fig_retrieval_vs_acc.png")

# ── Figure 3：失敗原因分布 堆疊長條圖 ────────────────────────────────────────
error_types = ["older_fact", "entity_confused", "hallucination", "intermediate_stop"]
colors      = ["#E05C5C", "#DD8452", "#8172B3", "#64B5CD"]

data = {}
for k in conflict_counts:
    grp = groups[k]
    total = len(grp)
    data[k] = {
        "correct": sum(1 for e in grp if e["exact_match"]) / total * 100
    }
    for et in error_types:
        data[k][et] = (
            sum(1 for e in grp if not e["exact_match"] and e.get("error_type") == et)
            / total * 100
        )

fig, ax = plt.subplots(figsize=(7, 4.5))
x = np.arange(len(conflict_counts))
width = 0.55
bottoms = np.zeros(len(conflict_counts))

vals = np.array([data[k]["correct"] for k in conflict_counts])
ax.bar(x, vals, width, label="Correct", color="#55A868", bottom=bottoms)
bottoms += vals

for et, color in zip(error_types, colors):
    vals = np.array([data[k][et] for k in conflict_counts])
    ax.bar(x, vals, width, label=et, color=color, bottom=bottoms)
    bottoms += vals

ax.set_xticks(x)
ax.set_xticklabels(
    [f"{k} conflict hop{'s' if k > 1 else ''}\n(n={len(groups[k])})"
     for k in conflict_counts],
    fontsize=10
)
ax.set_ylabel("Proportion (%)", fontsize=11)
ax.set_title(
    "FC-MH: Answer Outcome Distribution\nby Number of Conflicting Hops",
    fontsize=12, pad=12
)
ax.set_ylim(0, 115)
ax.legend(fontsize=9, bbox_to_anchor=(1.01, 1), loc='upper left')
ax.grid(axis='y', alpha=0.3)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig(str(OUT / "fig_error_distribution.png"), dpi=150, bbox_inches='tight')
plt.close()
print("✅ fig3 saved: fig_error_distribution.png")

print("\n🎉 所有圖表輸出完成")
