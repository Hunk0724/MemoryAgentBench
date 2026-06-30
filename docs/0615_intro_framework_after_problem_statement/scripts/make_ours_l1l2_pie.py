"""F_ours_L1L2_pie: ours' query-time resolution shown as a PIE grid.
Row 1 = L1 retrieved (top-100): mostly 'both' (both versions present).
Row 2 = L2 final context (after conflict-type + temporal resolution): collapses to
        'new_only' (old dropped only for true FRESHNESS conflicts).
Cols = history length. has_pair only. Data: state_eval_current.json (full-fact).

The point: ours retrieves both versions, then query-time resolution converts
'both' -> 'new_only' deterministically — the quantified value of resolving at
query time (and what mem0(b) cannot do, having destroyed a version at write time).
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = "/home/yhchiang/MemoryAgentBench"
FIG = Path(f"{ROOT}/docs/0615_intro_framework_after_problem_statement/figures_current")
S = json.load(open(f"{ROOT}/analysis/results/phase0/state_eval_current.json"))
LENS = ["6k", "32k", "64k", "262k"]
LAYERS = [("L1", "L1 — Retrieved (top-100)", "both"),
          ("L2", "L2 — Final context (resolved)", "new_only")]
ORDER = ["both", "new_only", "old_only", "neither"]
COL = {"both": "#009E73", "new_only": "#56B4E9", "old_only": "#D55E00", "neither": "#999999"}
LAB = {"both": "Both versions", "new_only": "New only", "old_only": "Old only", "neither": "Neither"}
plt.rcParams.update({"font.size": 10})

fig, axes = plt.subplots(2, len(LENS), figsize=(10.2, 5.8))
for ri, (layer, rowtitle, keyk) in enumerate(LAYERS):
    for ci, L in enumerate(LENS):
        ax = axes[ri][ci]
        v = S.get(f"ours|{L}")
        d = v[layer]; n = v["n"]
        vals = [d.get(k, 0) for k in ORDER]
        keypct = d.get(keyk, 0) / n * 100
        ax.pie(vals, colors=[COL[k] for k in ORDER], startangle=90,
               wedgeprops=dict(edgecolor="white", linewidth=1),
               autopct=lambda p: f"{p:.0f}" if p >= 7 else "", pctdistance=0.72, textprops={"fontsize": 8})
        ax.set_title(f"{keyk} {keypct:.0f}%", fontsize=8.5, color="#333", pad=2)
        if ri == 0:
            ax.annotate(L, xy=(0.5, 1.18), xycoords="axes fraction", ha="center", fontsize=12, fontweight="bold")
        if ci == 0:
            ax.annotate(rowtitle, xy=(-0.42, 0.5), xycoords="axes fraction", ha="center", va="center",
                        fontsize=10, fontweight="bold", rotation=90)

handles = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in ORDER]
fig.legend(handles, [LAB[k] for k in ORDER], ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.02), frameon=False, fontsize=10)
fig.suptitle("ours: L1 retrieved vs L2 resolved state   (has_pair)", fontsize=11.5, y=1.0)
fig.subplots_adjust(left=0.12, right=0.98, top=0.82, bottom=0.10, hspace=0.48, wspace=0.30)
for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_ours_L1L2_pie.{ext}", dpi=200, bbox_inches="tight")
print("  -> F_ours_L1L2_pie  (supersedes F_ours_L1L2.png)")
