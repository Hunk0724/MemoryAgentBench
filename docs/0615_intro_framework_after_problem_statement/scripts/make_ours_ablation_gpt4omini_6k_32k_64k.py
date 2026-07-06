#!/usr/bin/env python3
"""F_ours_ablation_gpt4omini_6k_32k_64k — ours internal ablation @ gpt-4o-mini.

4 variants × 3 lengths (verified from per-qid response via MAB default_post_process;
matches style_rules §10.3a).

Naming per method_v1.md §3 & user 2026-07-05 directive:
  - ours (struct + temporal argmax)                    = struct-based identity only
  - ours (LLM + temporal argmax)                       = LLM-based identity only
  - ours (identity grouping + temporal argmax)         = struct + LLM identity (= main method)
  - ours (identity grouping + temporal argmax + P5)    = with conflict-type classifier (appendix)
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

LENGTHS = ["6k", "32k", "64k"]
SERIES = [
    # ordered by 6k performance for readability.
    # 4 series exceed what greyscale alone separates cleanly, so two solid darks
    # (struct, main) + two moderate-hatch lights (LLM //, +P5 xx) — light fills
    # carry hatch well; density kept moderate to avoid the dense-hatch moiré.
    # (label, pcts, fracs, facecolor, hatch)
    # temporal argmax is shared by all → dropped from legend, stated in caption.
    # 3 series → pure greyscale (no hatch), same palette as F_ours_ablation_haspair.
    ("struct-only",              [90.5, 80.0, 87.9], [(67,74),(52,65),(58,66)], "#888888", ""),
    ("LLM-only",                 [95.9, 89.2, 87.9], [(71,74),(58,65),(58,66)], "#CCCCCC", ""),
    ("identity grouping  [main]",[93.2, 87.7, 90.9], [(69,74),(57,65),(60,66)], "#222222", ""),
]

x = np.arange(len(LENGTHS))
n = len(SERIES)
w = 0.20

fig, ax = plt.subplots(figsize=(10.0, 5.4))
for i, (label, pcts, frac, fc, hatch) in enumerate(SERIES):
    offs = (i - (n - 1) / 2) * w
    bars = ax.bar(x + offs, pcts, w, label=label, facecolor=fc, hatch=hatch,
                  edgecolor="black", linewidth=0.9, zorder=3)
    for xb, pct, (hit, tot) in zip(x + offs, pcts, frac):
        ax.annotate(f"{round(pct)}%\n({hit}/{tot})", (xb, pct), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=8)

ax.set_ylim(60, 132)  # ablations cluster high; zoom in
ax.set_yticks(range(60, 101, 10))
ax.set_xticks(x)
ax.set_xticklabels(LENGTHS)
ax.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
ax.set_xlabel("Conversation-history length", fontsize=11)
ax.set_title("FC-SH has_pair EM — ours ablation @ gpt-4o-mini backbone", fontsize=12, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(handles=[Patch(facecolor=fc, hatch=hatch, edgecolor="black", label=lbl)
                   for (lbl, _p, _f, fc, hatch) in SERIES],
          loc="upper right", fontsize=8, frameon=True, framealpha=0.95, ncol=3)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"), os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_ours_ablation_gpt4omini_6k_32k_64k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
