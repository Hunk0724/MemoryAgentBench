"""Paper figures from CURRENT data (FC-SH, gpt-4o-mini). Narrative-arc plots:
  F_robust_haspair : has_pair% vs history length (THE killer: ours flat, LCA collapse)
  F_overall        : overall% vs length
  F_ablation       : additive (a)native -> (b)mem0+P1 destructive -> (c)ours @6k/32k
Pending cells (mem0(b) 64k/262k, Zep 64k/262k) are simply not plotted (lines stop).
Outputs to figures_current/.  Single deterministic run -> no error bars.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

FIG = Path(f"{__import__('os').environ.get('REPO_ROOT') or str(__import__('pathlib').Path(__file__).resolve().parents[3])}/docs/0615_intro_framework_after_problem_statement/figures_current")
FIG.mkdir(parents=True, exist_ok=True)
LENS = ["6k", "32k", "64k", "262k"]
X = list(range(4))
C = {"ours": "#009E73", "LCA": "#0072B2", "Zep": "#CC79A7", "(b)mem0+P1": "#E69F00", "(a)vanilla": "#D55E00"}
# legend display names (match the advisor-update wording)
LABELS = {"ours": "ours", "LCA": "gpt-4o-mini", "Zep": "Zep",
          "(b)mem0+P1": "mem0+ours storage", "(a)vanilla": "mem0"}

# has_pair % (None = not yet run)
HP = {
    "ours":       [92, 86, 91, 88],
    "LCA":        [88, 71, 55, 31],
    "Zep":        [68, 55, 67, None],
    "(b)mem0+P1": [46, 45, 41, None],
    "(a)vanilla": [0, 3, 3, 1],
}
OV = {
    "ours":       [92, 89, 94, 91],
    "LCA":        [88, 74, 65, 42],
    "Zep":        [76, 69, 78, None],
    "(b)mem0+P1": [51, 61, 58, None],
    "(a)vanilla": [16, 22, 26, 17],
}
plt.rcParams.update({"font.size": 11})


def line_fig(data, ylab, title, name):
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for m in ["ours", "LCA", "Zep", "(b)mem0+P1", "(a)vanilla"]:
        ys = data[m]
        xs = [x for x, y in zip(X, ys) if y is not None]
        yy = [y for y in ys if y is not None]
        ax.plot(xs, yy, "-o", color=C[m], label=LABELS.get(m, m), linewidth=2.4 if m == "ours" else 1.6,
                markersize=7 if m == "ours" else 5, zorder=3 if m == "ours" else 2)
        for x, y in zip(xs, yy):
            ax.annotate(f"{y}", (x, y), textcoords="offset points", xytext=(0, 6), fontsize=7.5, ha="center")
    ax.set_xticks(X); ax.set_xticklabels([f"{L}" for L in LENS])
    ax.set_xlabel("Conversation-history length"); ax.set_ylabel(ylab)
    ax.set_ylim(-3, 100); ax.set_title(title)
    ax.legend(fontsize=9, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig); print(f"  -> {name}")


def ablation_fig():
    import numpy as np
    arms = [("(a) native\n(stock mem0)", [0, 3], "#D55E00"),
            ("(b) mem0+P1\n(destructive)", [46, 45], "#E69F00"),
            ("(c) ours\n(conservative+QT)", [92, 86], "#009E73")]
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    x = np.arange(2); w = 0.26
    for i, (lab, vals, col) in enumerate(arms):
        b = ax.bar(x + (i - 1) * w, vals, w, color=col, label=lab)
        for xi, v in zip(x + (i - 1) * w, vals):
            ax.text(xi, v + 1.5, f"{v}", ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(["6k", "32k"])
    ax.set_ylabel("has_pair EM (%)"); ax.set_ylim(0, 100)
    ax.set_title("Additive ablation (FC-SH has_pair)")
    ax.legend(fontsize=8.5, loc="upper right", frameon=False, ncol=1)
    ax.spines[["top", "right"]].set_visible(False)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"F_ablation.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig); print("  -> F_ablation")


print("generating ->", FIG)
line_fig(HP, "has_pair EM (%)  ↑", "has_pair EM vs conversation-history length", "F_robust_haspair")
line_fig(OV, "overall EM (%)  ↑", "Overall FC-SH accuracy across history length", "F_overall")
ablation_fig()
