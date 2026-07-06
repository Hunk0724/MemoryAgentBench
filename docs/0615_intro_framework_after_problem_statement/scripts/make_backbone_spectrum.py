#!/usr/bin/env python3
"""F_backbone_spectrum — HEADLINE figure: single-length (6k) backbone spectrum.

Single panel, 6-tier backbone (gemma3-1B/4B/12B/27B -> gpt-4o-mini -> gpt-4.1-mini),
3 methods. Shows the falsifiable prediction at ONE consistent length:
  ours−baseline gap is huge on weak backbones (mem0 = 0 on 1B/4B),
  narrows as backbone judgment strengthens (gap +13pp on gpt-4.1-mini).

64k reversal (mem0 overtakes ours at gpt-4.1-mini) is disclosed separately in
§4.3.4 cross-length table, NOT in this clean headline.

has_pair EM, N=74 (6k). Data verified from per-qid response via MAB
default_post_process semantics (2026-07-07: gpt-4.1-mini ours-main no_p5 = 66/74).
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import os

BACKBONES = ["gemma3-1B", "gemma3-4B", "gemma3-12B", "gemma3-27B", "gpt-4o-mini", "gpt-4.1-mini"]
N = 74  # has_pair @ 6k
SERIES = [
    ("ours (identity grouping)",         [25, 54, 73, 70, 69, 66], "#222222"),
    ("zep (decoupled write-time label)", [12, 17, 43, 35, 46, 46], "#888888"),
    ("mem0+unified extract",             [ 0,  0, 44, 36, 34, 56], "#CCCCCC"),
]

fig, ax = plt.subplots(figsize=(11.5, 5.2))
x = np.arange(len(BACKBONES))
n = len(SERIES)
w = 0.26
for i, (label, hits, fc) in enumerate(SERIES):
    offs = (i - (n - 1) / 2) * w
    pcts = [100 * h / N for h in hits]
    ax.bar(x + offs, pcts, w, label=label, facecolor=fc, edgecolor="black",
           linewidth=0.9, zorder=3)
    for xb, pct, h in zip(x + offs, pcts, hits):
        ax.annotate(f"{round(pct)}%\n({h}/{N})", (xb, pct),
                    textcoords="offset points", xytext=(0, 3),
                    ha="center", va="bottom", fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels(BACKBONES)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.set_ylim(0, 118)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("has_pair Exact-Match (%)  ↑", fontsize=11)
ax.set_xlabel("Backbone  (weak → strong judgment)", fontsize=11)

handles = [Patch(facecolor=fc, edgecolor="black", label=lbl) for (lbl, _, fc) in SERIES]
ax.legend(handles=handles, loc="upper center", ncol=3, fontsize=9.5,
          frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, 1.10))
fig.suptitle("FC-SH has_pair EM across backbone spectrum @ 6k — gap widens on weak, collapses on strong",
             fontsize=12.5, y=1.02)

fig.tight_layout()
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
OUTDIRS = [
    os.path.join(BASE, "figures_current"),
    os.path.join(BASE, "paper_current", "figures"),
    os.path.join(BASE, "paper_current", "narrative_experiment_evidence", "figures"),
]
for d in OUTDIRS:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_backbone_spectrum.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
