#!/usr/bin/env python3
"""F_backbone_spectrum -- HEADLINE Figure: 6-tier backbone spectrum @ FC-SH 6k.

Design (mirrors F_mainexp_ladder_6k.py style):
  - COLOR = KU-decision paradigm family
      deep-blue  = Ours          (query-time deterministic, Q-det)
      amber      = Vanilla-RAG   (query-time LLM temporal, Q-llm)
      burnt-orange = Don't Ask   (query-time LLM extraction, Q-llm)
      purple     = Zep           (write-time labeling / decoupled, W-decoupled)
      crimson    = Mem0+P1       (write-time destructive commit, W-destructive)
  - LINESTYLE = REDUNDANT encoding for B&W robustness
      solid  = query-time deterministic
      dashed = query-time LLM
      dotted = write-time LLM
  - Family band + separator: Gemma3 | GPT tier (both per-backbone extraction)

6-tier x-axis (weak -> mid -> strong):
  gemma3-1B -> 4B -> 12B -> 27B -> gpt-4o-mini -> gpt-5.4-mini
(gpt-4.1-mini dropped 2026-07-17 per paper decision.)

y = overall sEM (%) at 6k, N=100, official substring_exact_match.
Numbers sourced from canonical_fc_sh_metrics.md + fc_sh_main_table_4length.md
+ fc_sh_backbone_spectrum_6k.md + outputs/*_q_llm_recency__gemma3-*/
+ outputs/maxserial_theircode/6k_gemma3-*_vector100.json (2026-07-17 verified).
"""
import os
import numpy as np
import matplotlib.pyplot as plt

BACKBONES = ["gemma3\n-1B", "gemma3\n-4B", "gemma3\n-12B", "gemma3\n-27B",
             "gpt-4o\n-mini", "gpt-5.4\n-mini"]

# (label, values[6], color, linestyle, marker) — 5 methods x 6 tiers, overall sEM (%)
SERIES = [
    ("Ours (Struct + LLM-Fallback) [Q-det]",
     [44, 79, 99, 99, 94, 99], "#1a4fa0", "-",  "o"),   # deep blue
    ("Vanilla-RAG (Q-time LLM temporal) [Q-llm]",
     [30, 48, 68, 69, 93, 98], "#e69f00", "--", "s"),   # amber
    ("Don't Ask (Q-time LLM extraction) [Q-llm]",
     [ 2, 36, 84, 96, 80, 96], "#d55e00", "--", "^"),   # burnt orange
    ("Zep (Write-time decoupled) [W-llm]",
     [29, 32, 58, 62, 82, 93], "#8e5ca8", ":",  "D"),   # purple
    ("Mem0 + P1 (Write-time destructive) [W-llm]",
     [ 5, 11, 64, 54, 52, 70], "#d1495b", ":",  "X"),   # crimson
]

fig, ax = plt.subplots(figsize=(9.6, 5.6))
x = np.arange(len(BACKBONES))

for label, ys, color, ls, mk in SERIES:
    ax.plot(x, ys, ls=ls, color=color, marker=mk, markerfacecolor=color,
            markeredgecolor="white", markersize=8.5, linewidth=2.4,
            markeredgewidth=1.0, label=label, zorder=3, clip_on=False)

# --- axes ---
ax.set_xticks(x)
ax.set_xticklabels(BACKBONES, fontsize=9.5)
ax.set_xlim(-0.25, len(BACKBONES) - 0.75)
ax.set_ylim(0, 105)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("Overall sEM  (%)   ↑", fontsize=11)
ax.set_xlabel("Backbone   (weak → strong judgment)", fontsize=11)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

# --- family band (Gemma3 | GPT) : honest extraction caveat ---
ax.axvspan(-0.25, 3.5, facecolor="#000000", alpha=0.045, zorder=0)
ax.axvline(3.5, color="#BBBBBB", linewidth=0.9, linestyle=(0, (2, 2)), zorder=1)
ax.text(1.5, 103.5, "Gemma3", ha="center",
        va="bottom", fontsize=8.2, color="#777777")
ax.text(4.5, 103.5, "GPT", ha="center",
        va="bottom", fontsize=8.2, color="#777777")

ax.legend(loc="lower right", fontsize=8.4, frameon=True, framealpha=0.95,
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
        p = os.path.join(d, f"F_backbone_spectrum.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
