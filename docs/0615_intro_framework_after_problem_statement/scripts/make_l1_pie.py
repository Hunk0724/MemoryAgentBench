"""F_L1_state_pie: L1 retrieved-context version-state as a PIE grid, for
VECTOR-memory methods only (ours / (b)mem0+P1 / (a)vanilla). Rows = method,
cols = length. Each pie = share of has_pair questions whose retrieved top-100
contains {both / new_only / old_only / neither} of the conflicting fact's versions
(full-fact match; from state_eval_current.json).

Zep is intentionally EXCLUDED: its fact/edge layer keeps BOTH versions as valid
edges (invalid_at rarely fires) and phrases facts differently from GT, so GT_old/
GT_new cannot be rigorously attributed at the retrieval layer. Zep is compared via
overall EM (Table 1) instead. (Honest scope note.)

Story: ours -> all 'both' (new recoverable); (b) destructive -> ~half old_only/
neither (new LOST at write-time, irreversible); (a) vanilla -> all 'neither'.
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
METHS = ["ours", "(b)mem0+P1", "(a)vanilla"]
ROWLAB = {"ours": "ours\n(conservative)", "(b)mem0+P1": "(b) mem0+P1\n(destructive)", "(a)vanilla": "(a) vanilla\n(native)"}
ORDER = ["both", "new_only", "old_only", "neither"]
COL = {"both": "#009E73", "new_only": "#56B4E9", "old_only": "#D55E00", "neither": "#999999"}
LAB = {"both": "Both versions", "new_only": "New only", "old_only": "Old only (new LOST)", "neither": "Neither (new LOST)"}
plt.rcParams.update({"font.size": 10})

fig, axes = plt.subplots(len(METHS), len(LENS), figsize=(10.2, 8.2))
for ri, m in enumerate(METHS):
    for ci, L in enumerate(LENS):
        ax = axes[ri][ci]
        v = S.get(f"{m}|{L}")
        if not v:
            ax.text(0.5, 0.5, "—\n(not run)", ha="center", va="center", fontsize=9, color="#888")
            ax.set_xticks([]); ax.set_yticks([]); ax.axis("off"); continue
        d = v["L1"]; n = v["n"]
        vals = [d.get(k, 0) for k in ORDER]
        recov = (d.get("both", 0) + d.get("new_only", 0)) / n * 100
        ax.pie(vals, colors=[COL[k] for k in ORDER], startangle=90,
               wedgeprops=dict(edgecolor="white", linewidth=1),
               autopct=lambda p: f"{p:.0f}" if p >= 7 else "", pctdistance=0.72, textprops={"fontsize": 8})
        # recoverable % under each pie (the key number: NEW still available)
        ax.set_title(f"new recoverable {recov:.0f}%", fontsize=8.5, color="#333", pad=2)
        if ri == 0:
            ax.annotate(L, xy=(0.5, 1.16), xycoords="axes fraction", ha="center", fontsize=12, fontweight="bold")
        if ci == 0:
            ax.annotate(ROWLAB[m], xy=(-0.35, 0.5), xycoords="axes fraction", ha="center", va="center",
                        fontsize=10.5, fontweight="bold", rotation=90)

handles = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in ORDER]
fig.legend(handles, [LAB[k] for k in ORDER], ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.01), frameon=False, fontsize=10)
fig.suptitle("L1 retrieved state   (vector-memory methods; has_pair)", fontsize=11.5, y=1.0)
fig.subplots_adjust(left=0.10, right=0.98, top=0.84, bottom=0.08, hspace=0.50, wspace=0.30)
for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_L1_state_pie.{ext}", dpi=200, bbox_inches="tight")
print("  -> F_L1_state_pie  (supersedes F_L1_state.png; Zep excluded — see caption)")
