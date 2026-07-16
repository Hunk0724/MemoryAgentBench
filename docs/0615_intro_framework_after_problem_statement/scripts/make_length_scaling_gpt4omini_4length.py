#!/usr/bin/env python3
"""F_length_scaling_gpt4omini_4length -- FC-SH overall sEM across 4 length @ gpt-4o-mini.

x-axis: context length (6k -> 32k -> 64k -> 262k, log-ish spacing)
y-axis: overall sEM (N=100, official substring_exact_match)
6 method lines showing four distinct scaling patterns:
  - Ours (Struct + LLM-Fallback): flat 91-94 across 4 length
  - Don't Ask: monotonic UP (80 -> 86, +6pp; bank saturates -> LLM extraction
    more often catches both versions)
  - Vanilla-RAG: non-monotonic dip at 32k (93 -> 77 -> 85 -> 81)
  - Zep: cliff at 262k (82 -> 80 -> 76 -> 29; retrieval-miss dominated,
    see zep_ku_resolution_bitemporal.md §4C)
  - Mem0+P1: plateau 52-65 across length (destructive UPDATE ceiling)
  - Mem0 Vanilla: floor 16-28 (extraction collapse on dense-fact chunks)

Numbers sourced from results/fc_sh_main_table_4length.md (canonical, N=100).
"""
import matplotlib.pyplot as plt
import numpy as np
import os

LENGTHS = ["6k", "32k", "64k", "262k"]
X = np.arange(len(LENGTHS))  # even spacing for readability

# 6 methods x 4 lengths, overall sEM at gpt-4o-mini (N=100)
SERIES = [
    ("Ours (Struct + LLM-Fallback)",
     [94, 91, 94, 91], "#111111", "-",  "o"),
    ("Don't Ask (Q-time LLM extraction)",
     [80, 86, 88, 86], "#333333", "--", "^"),
    ("Vanilla-RAG (Q-time LLM temporal)",
     [93, 77, 85, 81], "#555555", "-.", "s"),
    ("Zep (Write-time decoupled)",
     [82, 80, 76, 29], "#777777", ":",  "D"),
    ("Mem0 + P1 (Write-time destructive)",
     [52, 52, 65, 50], "#999999", (0, (3,1,1,1)), "v"),
    ("Mem0 Vanilla (Write-time LLM)",
     [16, 22, 28, 17], "#BBBBBB", (0, (5,2)),    "P"),
]

fig, ax = plt.subplots(figsize=(9.0, 5.6))
for label, ys, color, ls, mk in SERIES:
    ax.plot(X, ys, color=color, linestyle=ls, marker=mk, linewidth=1.6,
            markersize=6, markerfacecolor="white", markeredgewidth=1.4,
            label=label, zorder=3)
    for xi, yi in zip(X, ys):
        ax.annotate(f"{yi}", (xi, yi), textcoords="offset points",
                    xytext=(0, 6), ha="center", va="bottom", fontsize=8)

ax.set_xticks(X)
ax.set_xticklabels(LENGTHS)
ax.set_ylim(-5, 108)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("Overall sEM  (%)  ↑", fontsize=11)
ax.set_xlabel("Conversation-history length  (chunk 512, retrieval top-K=100 / Zep k=10)",
              fontsize=11)
ax.set_title("FC-SH overall sEM across 4 lengths @ gpt-4o-mini backbone",
             fontsize=12.5, pad=10)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(loc="lower left", fontsize=8.5, frameon=True, framealpha=0.95,
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
        p = os.path.join(d, f"F_length_scaling_gpt4omini_4length.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
