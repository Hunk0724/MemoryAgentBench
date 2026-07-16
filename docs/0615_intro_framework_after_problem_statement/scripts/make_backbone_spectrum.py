#!/usr/bin/env python3
"""F_backbone_spectrum -- HEADLINE Figure: 6-tier backbone spectrum @ FC-SH 6k.

6-tier x-axis (weak -> mid -> strong):
  gemma3-1B -> 4B -> 12B -> 27B -> gpt-4o-mini -> gpt-5.4-mini
(gpt-4.1-mini dropped 2026-07-17 per paper decision: gpt-5.4-mini as strong tier.)

5 methods, LINE plot (per style_rules "trends -> lines"), overall sEM @ 6k
(N=100, official substring_exact_match). Numbers sourced from:
  - canonical_fc_sh_metrics.md (gemma weak tier)
  - fc_sh_main_table_4length.md (gpt-4o-mini column, 6k row)
  - fc_sh_backbone_spectrum_6k.md (gpt-5.4-mini)
  - outputs/*_q_llm_recency__gemma3-*/ (Vanilla-RAG gemma tier, verified 2026-07-17)
  - outputs/maxserial_theircode/6k_gemma3-*_vector100.json (Don't Ask gemma tier)

Style (per style_rules_tables_figures_writing.md):
  - line plot with marker+linestyle+greyscale (B&W-safe)
  - minimal chartjunk: axis + legend + on-line data labels
  - abbreviation caption gloss lives in the paper caption, not the figure
"""
import matplotlib.pyplot as plt
import numpy as np
import os

BACKBONES = ["gemma3-1B", "gemma3-4B", "gemma3-12B", "gemma3-27B",
             "gpt-4o-mini", "gpt-5.4-mini"]

# 5 methods x 6 tiers, overall sEM at 6k (N=100)
SERIES = [
    # (label, values[6], color, linestyle, marker)
    ("Ours (Struct + LLM-Fallback)",
     [44, 79, 99, 99, 94, 99], "#111111", "-",  "o"),
    ("Vanilla-RAG (Q-time LLM temporal)",
     [30, 48, 68, 69, 93, 98], "#333333", "--", "s"),
    ("Don't Ask (Q-time LLM extraction)",
     [ 2, 36, 84, 96, 80, 96], "#555555", "-.", "^"),
    ("Zep (Write-time decoupled)",
     [29, 32, 58, 62, 82, 93], "#777777", ":",  "D"),
    ("Mem0 + P1 (Write-time destructive)",
     [ 5, 11, 64, 54, 52, 70], "#999999", (0, (3,1,1,1)), "v"),
]

fig, ax = plt.subplots(figsize=(9.5, 5.6))
x = np.arange(len(BACKBONES))
for label, ys, color, ls, mk in SERIES:
    ax.plot(x, ys, color=color, linestyle=ls, marker=mk, linewidth=1.6,
            markersize=6, markerfacecolor="white", markeredgewidth=1.4,
            label=label, zorder=3)
    for xi, yi in zip(x, ys):
        ax.annotate(f"{yi}", (xi, yi), textcoords="offset points",
                    xytext=(0, 6), ha="center", va="bottom", fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels(BACKBONES, rotation=15, ha="right")
ax.set_ylim(-5, 108)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("Overall sEM  (%)  ↑", fontsize=11)
ax.set_xlabel("Backbone  (weak → strong)", fontsize=11)
ax.set_title("FC-SH 6k overall sEM across backbone spectrum",
             fontsize=12.5, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(loc="lower right", fontsize=9, frameon=True, framealpha=0.95,
          ncol=1)

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
