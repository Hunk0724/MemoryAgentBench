#!/usr/bin/env python3
"""F_main_gpt4omini_6k_32k_64k — FC-SH has_pair EM main comparison @ gpt-4o-mini.

Extends the 6k+64k version to include 32k (verified from per-qid response via
MAB default_post_process; matches style_rules §10.3a).

Design (per style_rules_tables_figures_writing.md):
  - §2 B&W-safe: PURE GREYSCALE (ours #222 / zep #888 / mem0 #CCC)
  - §4 minimal chartjunk: axis + legend + on-bar data labels only
  - Interpretation goes in caption, not figure
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

LENGTHS = ["6k", "32k", "64k"]
SERIES = [
    ("ours (identity grouping + temporal argmax)",       [93.2, 87.7, 90.9], [(69,74),(57,65),(60,66)], "#222222"),
    ("zep (decoupled write-time labeling)",               [62.2, 50.8, 54.5], [(46,74),(33,65),(36,66)], "#888888"),
    ("mem0+unified extract (coupled write-time destr.)",  [45.9, 38.5, 51.5], [(34,74),(25,65),(34,66)], "#CCCCCC"),
]

x = np.arange(len(LENGTHS))
n = len(SERIES)
w = 0.24

fig, ax = plt.subplots(figsize=(9.0, 5.2))
for i, (label, pcts, frac, fc) in enumerate(SERIES):
    offs = (i - (n - 1) / 2) * w
    bars = ax.bar(x + offs, pcts, w, label=label, facecolor=fc, edgecolor="black", linewidth=0.9, zorder=3)
    for xb, pct, (hit, tot) in zip(x + offs, pcts, frac):
        ax.annotate(f"{round(pct)}%\n({hit}/{tot})", (xb, pct), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=9)

ax.set_ylim(0, 132)
ax.set_yticks(range(0, 101, 20))
ax.set_xticks(x)
ax.set_xticklabels(LENGTHS)
ax.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
ax.set_xlabel("Conversation-history length (chunk 512, retrieval top-K = 100 ours/mem0; 10 Zep)", fontsize=11)
ax.set_title("FC-SH has_pair EM — main comparison @ gpt-4o-mini backbone", fontsize=12, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(handles=[Patch(facecolor=fc, edgecolor="black", label=lbl) for (lbl, *_, fc) in SERIES],
          loc="upper right", fontsize=9, frameon=True, framealpha=0.95)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"), os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_main_gpt4omini_6k_32k_64k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
