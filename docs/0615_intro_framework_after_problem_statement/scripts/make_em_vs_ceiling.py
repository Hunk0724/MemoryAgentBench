"""F_em_vs_ceiling: combine performance (EM) with the recall CEILING (is the NEW
version present in the final answer context) for the recall-analyzable vector
methods. Per method: dashed = recall ceiling (upper bound on answerable), solid =
actual has_pair EM. EM can only approach its ceiling; the ceiling itself is set at
write-time (whether the new version survives in the bank/context).

ceiling = (both+new_only) in the FINAL context:  ours -> L2 (after KU resolution);
mem0 / mem0+ours storage -> L1 (no query-time resolution). FC-SH has_pair.
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
X = {L: i for i, L in enumerate(LENS)}
# (display, state-key, layer-for-ceiling, color, has_pair EM by length)
SPECS = [
    ("ours", "ours", "L2", "#009E73", {"6k": 92, "32k": 86, "64k": 91, "262k": 88}),
    ("mem0+ours storage", "(b)mem0+P1", "L1", "#E69F00", {"6k": 46, "32k": 45, "64k": 41}),
]

def ceiling(key, layer, L):
    v = S.get(f"{key}|{L}")
    if not v:
        return None
    d = v[layer]; n = v["n"]
    return (d.get("both", 0) + d.get("new_only", 0)) / n * 100

plt.rcParams.update({"font.size": 11})
fig, ax = plt.subplots(figsize=(7.0, 4.6))
for lab, key, layer, col, em in SPECS:
    xc, yc, xe, ye = [], [], [], []
    for L in LENS:
        c = ceiling(key, layer, L)
        if c is not None:
            xc.append(X[L]); yc.append(c)
        if L in em:
            xe.append(X[L]); ye.append(em[L])
    ax.plot(xc, yc, "--", color=col, lw=1.6, marker="o", ms=5, mfc="white", alpha=0.95, zorder=2)
    ax.plot(xe, ye, "-", color=col, lw=2.6, marker="o", ms=7, label=lab, zorder=3)

ax.set_xticks(range(4)); ax.set_xticklabels(LENS)
ax.set_xlabel("Conversation-history length")
ax.set_ylabel("has_pair (%)  ↑")
ax.set_ylim(-4, 104)
ax.set_title("has_pair: EM achieved (solid) vs recall ceiling (dashed)", fontsize=11.5)
ax.legend(fontsize=10, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_em_vs_ceiling.{ext}", dpi=200, bbox_inches="tight")
print("  -> F_em_vs_ceiling")
