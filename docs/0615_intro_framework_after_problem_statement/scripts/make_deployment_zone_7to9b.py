#!/usr/bin/env python3
"""F_deployment_zone_7to9b -- 7-9B on-device deployment zone @ FC-SH 6k.

Companion to F_backbone_spectrum.py. Same paradigm color / B&W linestyle
encoding, but the x-axis brackets the 4 cross-family 7-9B deployment-size models
between two gemma3 capability anchors (4B below, 12B above) to visualize the
4B->12B transition zone at the sizes that actually run on-device.

  COLOR   = KU-decision paradigm
    deep-blue    = Ours        (query-time deterministic (S,P)+temporal)
    amber        = Vanilla-RAG (query-time LLM temporal)
    burnt-orange = Don't Ask   (query-time LLM extraction)
    purple       = Zep         (write-time decoupled labeling)
    crimson      = Mem0+P1     (write-time destructive commit)
  LINESTYLE = redundant B&W encoding
    solid = Q-det | dashed = Q-llm | dotted = W-llm

x-axis: gemma3-4B | [llama3.1-8B  qwen2.5-7B  gemma2-9B  mistral-7B] | gemma3-12B
  The 4 middle models are the SAME ~7-9B capability tier, DIFFERENT families ->
  x-order WITHIN the shaded zone is arbitrary (not a capability ranking); it is
  drawn as a band, not a monotone axis. The two gemma3 anchors show where the
  zone sits in the gemma3 4B->12B transition.

y = overall sEM (%) @ 6k, N=100, official substring_exact_match.
Don't Ask uses the ours-P1 (per-backbone extraction) variant on every tier for
consistency with the deployment framing (gemma3-4B=38, 12B=84). Numbers verified
from experiment.md Table G0/G5 + outputs/*__{model}/ + maxserial *_oursP1_*.json.
"""
import os
import numpy as np
import matplotlib.pyplot as plt

XLABELS = ["gemma3\n-4B", "llama3.1\n-8B", "qwen2.5\n-7B",
           "gemma2\n-9B", "mistral\n-7B", "gemma3\n-12B"]

# (label, values[6], color, linestyle, marker) — overall sEM (%)
SERIES = [
    ("Ours (Struct + LLM-Fallback) [Q-det]",
     [79, 81, 91, 72, 66, 99], "#1a4fa0", "-",  "o"),   # deep blue
    ("Vanilla-RAG (Q-time LLM temporal) [Q-llm]",
     [48, 70, 27, 38, 26, 68], "#e69f00", "--", "s"),   # amber
    ("Don't Ask (Q-time LLM extraction) [Q-llm]",
     [38, 48, 42, 80, 21, 84], "#d55e00", "--", "^"),   # burnt orange
    ("Zep (Write-time decoupled) [W-llm]",
     [32, 63, 51, 73, 52, 58], "#8e5ca8", ":",  "D"),   # purple
    ("Mem0 + P1 (Write-time destructive) [W-llm]",
     [11,  8, 21, 27, 19, 64], "#d1495b", ":",  "X"),   # crimson
]

fig, ax = plt.subplots(figsize=(9.6, 5.6))
x = np.arange(len(XLABELS))

# --- 7-9B deployment zone band (middle 4; order arbitrary) ---
ax.axvspan(0.5, 4.5, facecolor="#1a4fa0", alpha=0.05, zorder=0)
ax.axvline(0.5, color="#BBBBBB", linewidth=0.9, linestyle=(0, (2, 2)), zorder=1)
ax.axvline(4.5, color="#BBBBBB", linewidth=0.9, linestyle=(0, (2, 2)), zorder=1)

for label, ys, color, ls, mk in SERIES:
    ax.plot(x, ys, ls=ls, color=color, marker=mk, markerfacecolor=color,
            markeredgecolor="white", markersize=8.5, linewidth=2.4,
            markeredgewidth=1.0, label=label, zorder=3, clip_on=False)

# --- axes ---
ax.set_xticks(x)
ax.set_xticklabels(XLABELS, fontsize=9.5)
ax.set_xlim(-0.25, len(XLABELS) - 0.75)
ax.set_ylim(0, 105)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("Overall sEM  (%)   ↑", fontsize=11)
ax.set_xlabel("gemma3-4B anchor  |  7–9B cross-family deployment zone  |  gemma3-12B anchor",
              fontsize=10.5)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

# --- zone caption (order-arbitrary caveat) ---
ax.text(2.5, 103.5, "7–9B deployment zone  (same tier, order arbitrary)",
        ha="center", va="bottom", fontsize=8.2, color="#555555")
ax.text(0.0, 103.5, "gemma3\n4B", ha="center", va="bottom", fontsize=7.6, color="#888888")
ax.text(5.0, 103.5, "gemma3\n12B", ha="center", va="bottom", fontsize=7.6, color="#888888")

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
        p = os.path.join(d, f"F_deployment_zone_7to9b.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
