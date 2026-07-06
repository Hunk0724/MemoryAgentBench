#!/usr/bin/env python3
"""F_all_gpt41mini_64k — all methods at gpt-4.1-mini × 64k (backbone extension).

Both strict EM and sEM (substring EM) shown for Zep to disclose verbose-format
artifact per style_rules §10.3b.

Data source: style_rules §10.3b, verified from per-qid response via MAB
default_post_process.
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

# has_pair (N=66 at 64k)
METHODS = [
    # (label, strict_EM_hits, sEM_hits, color)
    # mixed figure (ours variants + baselines) → keep "ours (...)" to separate
    # our family from mem0/zep; drop the shared "+ argmax" (stated in caption).
    ("ours (identity grouping)  [main]",   53, 54, "#222222"),
    ("ours (struct)",                       52, 52, "#666666"),
    ("ours (LLM)",                          27, 28, "#AAAAAA"),
    ("ours (identity grouping + P5)",       51, 51, "#DDDDDD"),
    ("mem0+unified extract",                55, 55, "#999999"),
    ("zep (k=10)",                          23, 50, "#BBBBBB"),
]
N = 66

x = np.arange(len(METHODS))
w = 0.38

fig, ax = plt.subplots(figsize=(11.5, 5.6))

# strict EM bars
strict_pcts = [100 * m[1] / N for m in METHODS]
strict_bars = ax.bar(x - w/2, strict_pcts, w, label="strict EM", facecolor="#333333", edgecolor="black", linewidth=0.9, zorder=3)
for xb, pct, h in zip(x - w/2, strict_pcts, [m[1] for m in METHODS]):
    ax.annotate(f"{round(pct)}\n({h}/{N})", (xb, pct), textcoords="offset points", xytext=(0, 3),
                ha="center", va="bottom", fontsize=8)

# sEM bars (only differ for Zep visibly; show for all)
sem_pcts = [100 * m[2] / N for m in METHODS]
sem_bars = ax.bar(x + w/2, sem_pcts, w, label="sEM (substring)", facecolor="#CCCCCC", edgecolor="black", linewidth=0.9, zorder=3)
for xb, pct, h, m in zip(x + w/2, sem_pcts, [m[2] for m in METHODS], METHODS):
    # only annotate if sEM > strict (i.e., verbose format artifact)
    if m[2] > m[1]:
        ax.annotate(f"{round(pct)}\n({h}/{N})", (xb, pct), textcoords="offset points", xytext=(0, 3),
                    ha="center", va="bottom", fontsize=8, color="#333333")

ax.set_ylim(0, 110)
ax.set_yticks(range(0, 101, 20))
ax.set_xticks(x)
ax.set_xticklabels([m[0] for m in METHODS], rotation=15, ha="right", fontsize=9)
ax.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
ax.set_title("FC-SH 64k has_pair EM — all methods @ gpt-4.1-mini backbone (strict EM vs sEM)", fontsize=12, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(loc="upper right", fontsize=9, frameon=True, framealpha=0.95)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"), os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_all_gpt41mini_64k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
