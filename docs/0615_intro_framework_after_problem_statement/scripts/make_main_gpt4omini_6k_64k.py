#!/usr/bin/env python3
"""
Rebuild F_main_gpt4omini_6k_64k — FC-SH has_pair EM main comparison @ gpt-4o-mini.

Design (follows style_rules_tables_figures_writing.md):
  - §2 B&W-safe via PURE GREYSCALE fills (no dense hatch) — ours #222 / Zep #888 / mem0+P1 #CCC
    (dense crosshatch removed: with only 3 series + on-bar data labels, hatch adds moiré noise,
     three grey levels print distinctly and read cleaner.)
  - §4 圖面精簡:only axis label + legend + data label; gridlines faint & single.
  - Interpretation (write-time paradigm cost) lives in the CAPTION per §5, not on the figure.

Data source: style_rules §10.3a (has_pair EM main table), single deterministic run (temp 0, no error bar).
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

# ---- data (has_pair EM; denominators = has_pair count at each length) ----
LENGTHS = ["6k", "64k"]
SERIES = [
    # (label, [6k pct, 64k pct], [(hit,total) 6k, (hit,total) 64k], facecolor)
    ("ours (identity grouping+temporal argmax)",   [93.2, 90.9], [(69, 74), (60, 66)], "#222222"),
    ("zep (decoupled write-time labeling)",         [62.2, 54.5], [(46, 74), (36, 66)], "#888888"),
    ("mem0+unified extract (coupled write-time destructive)", [45.9, 51.5], [(34, 74), (34, 66)], "#CCCCCC"),
]

x = np.arange(len(LENGTHS))
n = len(SERIES)
w = 0.24

fig, ax = plt.subplots(figsize=(8.4, 5.2))

for i, (label, pcts, frac, fc) in enumerate(SERIES):
    offs = (i - (n - 1) / 2) * w
    bars = ax.bar(x + offs, pcts, w, label=label,
                  facecolor=fc, edgecolor="black", linewidth=0.9, zorder=3)
    for xb, pct, (hit, tot) in zip(x + offs, pcts, frac):
        ax.annotate(f"{round(pct)}%\n({hit}/{tot})",
                    (xb, pct), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=9)

# ---- axes / cosmetics (§4 圖面精簡) ----
ax.set_ylim(0, 132)  # headroom so legend (upper-right) never occludes the 64k ours label
ax.set_yticks(range(0, 101, 20))
ax.set_xticks(x)
ax.set_xticklabels(LENGTHS)
ax.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
ax.set_xlabel("Conversation-history length "
              "(chunk 512, retrieval top-K = 100 ours/mem0; 10 Zep)", fontsize=11)
ax.set_title("FC-SH has_pair EM — main comparison @ gpt-4o-mini backbone",
             fontsize=12, pad=10)

# faint single-style gridline only on y, behind bars
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

ax.legend(handles=[Patch(facecolor=fc, edgecolor="black", label=lbl)
                   for (lbl, *_, fc) in SERIES],
          loc="upper right", fontsize=9, frameon=True, framealpha=0.95)

fig.tight_layout()

# ---- write to both figures_current (production) and paper_current (curated) ----
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)  # docs/0615_intro_framework_after_problem_statement
out_dirs = [
    os.path.join(BASE, "figures_current"),
    os.path.join(BASE, "paper_current", "figures"),
]
for d in out_dirs:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_main_gpt4omini_6k_64k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
