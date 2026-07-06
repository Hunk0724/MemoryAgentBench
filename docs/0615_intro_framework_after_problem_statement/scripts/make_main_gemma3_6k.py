#!/usr/bin/env python3
"""F_main_gemma3_6k — FC-SH 6k has_pair EM main comparison × 4 weak backbones.

Data source: docs/handoff/gx10_sync_2026-07-05.md §3 (E2E has_pair EM cross-verified
by weak_model_6k_analysis.md §1). Per-qid data on GX10 (not pulled locally); numbers
authored by GX10 with matcher v4 + MAB default_post_process.

Naming aligned with gpt-4o-mini main comparison figure for cross-reference.
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

BACKBONES = ["gemma3-1B", "gemma3-4B", "gemma3-12B", "gemma3-27B"]
# has_pair (denominator = 74 for 6k)
SERIES = [
    ("ours (identity grouping + temporal argmax)",       [25, 54, 73, 70], "#222222"),
    ("zep (decoupled write-time labeling)",               [12, 17, 43, 35], "#888888"),
    ("mem0+unified extract (coupled write-time destr.)",  [ 0,  0, 44, 36], "#CCCCCC"),
]
N = 74

x = np.arange(len(BACKBONES))
n = len(SERIES)
w = 0.24

fig, ax = plt.subplots(figsize=(9.6, 5.2))
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
ax.set_title("FC-SH 6k has_pair EM — main comparison × weak backbones", fontsize=12, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(handles=[Patch(facecolor=fc, edgecolor="black", label=lbl) for (lbl, _, fc) in SERIES],
          loc="upper left", fontsize=9, frameon=True, framealpha=0.95)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"), os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_main_gemma3_6k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
