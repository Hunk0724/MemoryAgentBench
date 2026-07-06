#!/usr/bin/env python3
"""F_ours_ablation_gemma3_6k — ours internal ablation × 4 weak backbones.

3 variants (no P5 since GX10 didn't run +P5 on gemma3). Matches naming with
gpt-4o-mini ablation figure for cross-reference.

Data source: weak_model_6k_analysis.md §1 (has_pair EM, N=74).
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

BACKBONES = ["gemma3-1B", "gemma3-4B", "gemma3-12B", "gemma3-27B"]
# has_pair (N=74 for 6k)
# temporal argmax shared by all → dropped from legend, stated in caption.
# 3 series → pure greyscale, same palette as F_ours_ablation_gpt4omini_6k_32k_64k.
SERIES = [
    ("struct-only",              [29, 54, 73, 65], "#888888"),
    ("LLM-only",                 [ 7, 26, 46, 27], "#CCCCCC"),
    ("identity grouping  [main]",[25, 54, 73, 70], "#222222"),
]
N = 74

x = np.arange(len(BACKBONES))
n = len(SERIES)
w = 0.26

fig, ax = plt.subplots(figsize=(9.6, 5.4))
for i, (label, hits, fc) in enumerate(SERIES):
    offs = (i - (n - 1) / 2) * w
    pcts = [100 * h / N for h in hits]
    bars = ax.bar(x + offs, pcts, w, label=label, facecolor=fc, edgecolor="black", linewidth=0.9, zorder=3)
    for xb, pct, h in zip(x + offs, pcts, hits):
        ax.annotate(f"{round(pct)}%\n({h}/{N})", (xb, pct), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=9)

ax.set_ylim(0, 132)
ax.set_yticks(range(0, 101, 20))
ax.set_xticks(x)
ax.set_xticklabels(BACKBONES)
ax.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
ax.set_xlabel("Local weak backbone (per-backbone gemma extraction; ollama, GX10)", fontsize=11)
ax.set_title("FC-SH 6k has_pair EM — ours ablation × weak backbones", fontsize=12, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(handles=[Patch(facecolor=fc, edgecolor="black", label=lbl) for (lbl, _, fc) in SERIES],
          loc="upper left", fontsize=9, frameon=True, framealpha=0.95, ncol=3)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"), os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_ours_ablation_gemma3_6k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
