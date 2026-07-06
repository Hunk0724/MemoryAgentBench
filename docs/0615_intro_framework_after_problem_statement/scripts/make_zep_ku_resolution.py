#!/usr/bin/env python3
"""F_zep_ku_resolution_6k_32k_64k — Zep bi-temporal KU-resolution × length.

Why a LINE chart (not bar): the story is a TREND across conversation length
(Additive-NoKU rises 39->77->74 as the graph grows and bounded top-k candidate
search misses the old edge), per advisor rule "有趨勢用 line".

Numbers are canonical from `analysis/classify_zep_ku_resolution.py`
(gpt-4o-mini x temp0, has_pair, handoff-verified buckets). Detailed table +
mechanism: paper_current/results/zep_ku_resolution_bitemporal.md.

Design (style_rules_tables_figures_writing.md):
  - §2 B&W-safe: pure greyscale + distinct linestyle + marker per series
  - §4 minimal chartjunk: axis + legend + data labels only
  - Interpretation lives in the caption, not the figure
"""
import matplotlib.pyplot as plt
import numpy as np
import os

LENGTHS = ["6k", "32k", "64k"]
x = np.arange(len(LENGTHS))

# --- Panel (a): bucket SHARE (%) of has_pair, per length ---
# (RC = Resolved-Correct, RB = Resolved-Backward, Add = Additive-NoKU,
#  Oth = Other-Ambiguous; NotBothExtracted <=5% omitted, noted in caption)
SHARE = [
    # label,                         6k    32k   64k   color     ls        marker
    ("Additive-NoKU (no temporal signal)", [39.2, 76.9, 74.2], "#222222", "-",   "o"),
    ("Resolved-Correct (old invalidated)", [23.0,  9.2, 16.7], "#555555", "--",  "s"),
    ("Resolved-Backward (new invalidated)",[29.7,  3.1,  0.0], "#888888", "-.",  "^"),
    ("Other-Ambiguous",                    [ 8.1,  6.2,  7.6], "#AAAAAA", ":",   "D"),
]

# --- Panel (b): EM accuracy (%) WITHIN bucket (robust buckets only) ---
ACC = [
    ("Resolved-Correct", [88.2, 100.0, 100.0], "#555555", "--", "s"),
    ("Additive-NoKU",    [69.0,  44.0,  40.8], "#222222", "-",  "o"),
]
E2E = [62.2, 50.8, 54.5]              # canonical Zep has_pair EM (objective_data §2/§4)
RB_6K = 36.4                          # Resolved-Backward acc, only 6k has usable n

fig, (axa, axb) = plt.subplots(1, 2, figsize=(11.0, 4.6))

# Panel (a)
for label, ys, c, ls, mk in SHARE:
    axa.plot(x, ys, ls, color=c, marker=mk, markersize=7, linewidth=2.0,
             markeredgecolor="black", markeredgewidth=0.6, label=label, zorder=3)
    for xi, yi in zip(x, ys):
        axa.annotate(f"{yi:.0f}", (xi, yi), textcoords="offset points",
                     xytext=(0, 7), ha="center", fontsize=8, color=c)
axa.set_ylim(-4, 92)
axa.set_yticks(range(0, 81, 20))
axa.set_xticks(x); axa.set_xticklabels(LENGTHS)
axa.set_ylabel("Share of has_pair queries (%)", fontsize=10)
axa.set_xlabel("Conversation-history length", fontsize=10)
axa.set_title("(a) What Zep did with each (new,old) pair", fontsize=11, pad=8)
axa.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
axa.set_axisbelow(True)
for s in ("top", "right"):
    axa.spines[s].set_visible(False)
axa.legend(loc="upper left", fontsize=8, frameon=True, framealpha=0.95,
           bbox_to_anchor=(0.0, 1.0))

# Panel (b)
for label, ys, c, ls, mk in ACC:
    axb.plot(x, ys, ls, color=c, marker=mk, markersize=7, linewidth=2.0,
             markeredgecolor="black", markeredgewidth=0.6, label=f"{label} bucket", zorder=3)
    for xi, yi in zip(x, ys):
        axb.annotate(f"{yi:.0f}", (xi, yi), textcoords="offset points",
                     xytext=(0, 7), ha="center", fontsize=8, color=c)
axb.plot(x, E2E, color="#BBBBBB", linestyle=(0, (1, 1)), linewidth=1.8,
         marker="x", markersize=6, label="overall has_pair EM", zorder=2)
# lone Resolved-Backward 6k point (n too small at 32k/64k)
axb.plot([0], [RB_6K], color="#888888", marker="^", markersize=7,
         markeredgecolor="black", markeredgewidth=0.6, linestyle="none",
         label="Resolved-Backward (6k only)", zorder=3)
axb.annotate(f"{RB_6K:.0f}", (0, RB_6K), textcoords="offset points",
             xytext=(0, -13), ha="center", fontsize=8, color="#888888")
axb.set_ylim(20, 112)
axb.set_yticks(range(20, 101, 20))
axb.set_xticks(x); axb.set_xticklabels(LENGTHS)
axb.set_ylabel("Exact-Match within bucket (%)", fontsize=10)
axb.set_xlabel("Conversation-history length", fontsize=10)
axb.set_title("(b) Answer-LLM EM, conditioned on what Zep did", fontsize=11, pad=8)
axb.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
axb.set_axisbelow(True)
for s in ("top", "right"):
    axb.spines[s].set_visible(False)
axb.legend(loc="lower left", fontsize=8, frameon=True, framealpha=0.95)

fig.suptitle("Zep KU-resolution vs length @ gpt-4o-mini (FC-SH has_pair, bi-temporal)",
             fontsize=12, y=1.00)
fig.tight_layout()

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for d in [os.path.join(BASE, "figures_current"),
          os.path.join(BASE, "paper_current", "figures")]:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_zep_ku_resolution_6k_32k_64k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
