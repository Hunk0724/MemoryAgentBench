#!/usr/bin/env python3
"""F_length_scaling_gpt4omini_4length -- FC-SH overall sEM across 4 length @ gpt-4o-mini.

Design (mirrors F_mainexp_ladder_6k.py style):
  - COLOR = KU-decision paradigm family
      deep-blue    = Ours          (Q-det)
      burnt-orange = Don't Ask     (Q-llm identity extraction)
      amber        = Vanilla-RAG   (Q-llm temporal)
      purple       = Zep           (W-decoupled)
      crimson      = Mem0+P1       (W-destructive)
      dark-red     = Mem0 Vanilla  (W-native, extraction floor)
  - LINESTYLE = REDUNDANT encoding for B&W robustness
      solid  = Ours (Q-det)
      dashed = Q-llm family
      dotted = write-time family

x = context length (6k -> 32k -> 64k -> 262k, even-spaced for readability).
y = overall sEM (%), N=100, official substring_exact_match.
Numbers sourced from results/fc_sh_main_table_4length.md (canonical).

Four scaling patterns visible at a glance:
  Ours flat 91-94 across 4 length
  Don't Ask monotonic UP (80 -> 88, +8pp; large bank -> LLM extraction
    more often catches both versions)
  Vanilla-RAG non-monotonic dip at 32k (93 -> 77 -> 85 -> 81)
  Zep cliff at 262k (82 -> 80 -> 76 -> 29; retrieval-miss dominated,
    see zep_ku_resolution_bitemporal.md §4C)
  Mem0+P1 plateau 50-65 across length (destructive UPDATE ceiling)
  Mem0 Vanilla floor 16-28 (extraction collapse on dense-fact chunks)
"""
import os
import numpy as np
import matplotlib.pyplot as plt

LENGTHS = ["6k", "32k", "64k", "262k"]
X = np.arange(len(LENGTHS))

# (label, values[4], color, linestyle, marker) — 6 methods x 4 lengths, overall sEM (%)
SERIES = [
    ("Ours (Struct + LLM-Fallback) [Q-det]",
     [94, 91, 94, 91], "#1a4fa0", "-",  "o"),   # deep blue
    ("Don't Ask (Q-time LLM extraction) [Q-llm]",
     [80, 86, 88, 86], "#d55e00", "--", "^"),   # burnt orange
    ("Vanilla-RAG (Q-time LLM temporal) [Q-llm]",
     [93, 77, 85, 81], "#e69f00", "--", "s"),   # amber
    ("Zep (Write-time decoupled) [W-llm]",
     [82, 80, 76, 29], "#8e5ca8", ":",  "D"),   # purple
    ("Mem0 + P1 (Write-time destructive) [W-llm]",
     [52, 52, 65, 50], "#d1495b", ":",  "X"),   # crimson
    ("Mem0 Vanilla (Write-time LLM) [W-llm]",
     [16, 22, 28, 17], "#7f1d1d", ":",  "P"),   # dark red
]

fig, ax = plt.subplots(figsize=(9.0, 5.6))
for label, ys, color, ls, mk in SERIES:
    ax.plot(X, ys, ls=ls, color=color, marker=mk, markerfacecolor=color,
            markeredgecolor="white", markersize=8.5, linewidth=2.4,
            markeredgewidth=1.0, label=label, zorder=3, clip_on=False)

# --- axes ---
ax.set_xticks(X)
ax.set_xticklabels(LENGTHS, fontsize=10)
ax.set_xlim(-0.25, len(LENGTHS) - 0.75)
ax.set_ylim(0, 105)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("Overall sEM  (%)   ↑", fontsize=11)
ax.set_xlabel("Conversation-history length   (chunk 512, retrieval top-K=100 / Zep k=10)",
              fontsize=11)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

ax.legend(loc="lower left", fontsize=8.4, frameon=True, framealpha=0.95,
          handlelength=2.8, borderpad=0.6, labelspacing=0.4)

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
