#!/usr/bin/env python3
"""F_backbone_spectrum — HEADLINE figure: gap-narrowing across backbone spectrum.

Two-panel figure showing the falsifiable prediction:
- Panel A (6k): gemma3-1B → gemma3-27B → gpt-4o-mini
    weak→mid backbones; ours gap widens
- Panel B (64k): gpt-4o-mini → gpt-4.1-mini
    mid→strong backbones; ours gap collapses

Same 3 methods, same colors across panels; gpt-4o-mini anchor point appears
in both panels for visual continuity.

Data verified from per-qid response via MAB default_post_process semantics.
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

# ---- Panel A: 6k across weak+mid backbones ----
PANEL_A_BACKBONES = ["gemma3-1B", "gemma3-4B", "gemma3-12B", "gemma3-27B", "gpt-4o-mini"]
# has_pair EM (N=74 for 6k)
PANEL_A_SERIES = [
    ("ours (identity grouping)",         [25, 54, 73, 70, 69], "#222222"),
    ("zep (decoupled write-time label)", [12, 17, 43, 35, 46], "#888888"),
    ("mem0+unified extract",             [ 0,  0, 44, 36, 34], "#CCCCCC"),
]
PANEL_A_N = 74

# ---- Panel B: 64k across mid+strong backbones ----
PANEL_B_BACKBONES = ["gpt-4o-mini", "gpt-4.1-mini"]
# has_pair EM (N=66 for 64k)
PANEL_B_SERIES = [
    ("ours (identity grouping)",         [60, 53], "#222222"),
    ("zep (decoupled write-time label)", [36, 23], "#888888"),
    ("mem0+unified extract",             [34, 55], "#CCCCCC"),
]
PANEL_B_N = 66

fig, (axA, axB) = plt.subplots(
    1, 2, figsize=(15.5, 5.4),
    gridspec_kw={"width_ratios": [len(PANEL_A_BACKBONES), len(PANEL_B_BACKBONES) + 0.4]},
    sharey=True,
)

def draw_panel(ax, backbones, series, N):
    x = np.arange(len(backbones))
    n = len(series)
    w = 0.24
    for i, (label, hits, fc) in enumerate(series):
        offs = (i - (n - 1) / 2) * w
        pcts = [100 * h / N for h in hits]
        ax.bar(x + offs, pcts, w, label=label, facecolor=fc, edgecolor="black",
               linewidth=0.9, zorder=3)
        for xb, pct, h in zip(x + offs, pcts, hits):
            ax.annotate(f"{round(pct)}%\n({h}/{N})", (xb, pct),
                        textcoords="offset points", xytext=(0, 3),
                        ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(backbones)
    ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

draw_panel(axA, PANEL_A_BACKBONES, PANEL_A_SERIES, PANEL_A_N)
draw_panel(axB, PANEL_B_BACKBONES, PANEL_B_SERIES, PANEL_B_N)

axA.set_ylim(0, 132)
axA.set_yticks(range(0, 101, 20))
axA.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
axA.set_xlabel("Panel A: 6k conversation history  (weak → mid backbone)", fontsize=11)
axB.set_xlabel("Panel B: 64k conversation history  (mid → strong backbone)", fontsize=11)

axA.set_title("weak → mid: baselines collapse; ours holds", fontsize=11, pad=6)
axB.set_title("mid → strong: mem0 catches up; Zep hedges", fontsize=11, pad=6)

# shared legend at figure top
handles = [Patch(facecolor=fc, edgecolor="black", label=lbl) for (lbl, _, fc) in PANEL_A_SERIES]
fig.legend(handles=handles, loc="upper center", ncol=3, fontsize=10,
           frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, 1.02))

fig.suptitle("FC-SH has_pair EM across backbone spectrum — gap widens on weak, collapses on strong",
             fontsize=13, y=1.08)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"), os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_backbone_spectrum.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
