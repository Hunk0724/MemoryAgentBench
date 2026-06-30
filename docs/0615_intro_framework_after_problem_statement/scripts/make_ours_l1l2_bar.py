"""F_ours_L1L2_bar: conference-grade paired STACKED BAR (preferred over pie at
top venues) for ours' L1 retrieved vs L2 resolved version-state, per length.
Each length has two stacked bars (L1, L2); the green(both)->blue(new_only) shift
visualizes the query-time resolution. Minimal on-figure text; story in caption.
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = __import__("os").environ.get("REPO_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3])
FIG = Path(f"{ROOT}/docs/0615_intro_framework_after_problem_statement/figures_current")
S = json.load(open(f"{ROOT}/analysis/results/phase0/state_eval_current.json"))
LENS = ["6k", "32k", "64k", "262k"]
ORDER = ["both", "new_only", "old_only", "neither"]
COL = {"both": "#009E73", "new_only": "#56B4E9", "old_only": "#D55E00", "neither": "#999999"}
LAB = {"both": "Both versions", "new_only": "New only", "old_only": "Old only", "neither": "Neither"}
plt.rcParams.update({"font.size": 11})

fig, ax = plt.subplots(figsize=(7.2, 4.4))
w = 0.36
for i, L in enumerate(LENS):
    v = S[f"ours|{L}"]; n = v["n"]
    for j, layer in enumerate(["L1", "L2"]):
        d = v[layer]; x = i + (j - 0.5) * (w + 0.03); bottom = 0
        for k in ORDER:
            h = d.get(k, 0) / n * 100
            ax.bar(x, h, w, bottom=bottom, color=COL[k], edgecolor="white", linewidth=0.6)
            bottom += h
        ax.text(x, -5, layer, ha="center", va="top", fontsize=8.5, color="#555")

ax.set_xticks(range(len(LENS))); ax.set_xticklabels(LENS, fontsize=11)
ax.tick_params(axis="x", pad=18)
ax.set_ylabel("Share of has_pair questions (%)")
ax.set_xlabel("Conversation-history length")
ax.set_ylim(0, 100); ax.set_xlim(-0.6, 3.6)
ax.set_title("ours: L1 retrieved vs L2 resolved state   (has_pair)", fontsize=11.5)
handles = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in ORDER]
ax.legend(handles, [LAB[k] for k in ORDER], fontsize=9, ncol=1,
          loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
ax.spines[["top", "right"]].set_visible(False)
for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_ours_L1L2_bar.{ext}", dpi=200, bbox_inches="tight")
print("  -> F_ours_L1L2_bar")
