"""Figure v2: F_pool_diagnostic — pool state share (row A) × E2E + failure attribution (row B).

Redesign rationale (feedback):
The v1 layout looked like a system-tuning dashboard (24 bars × 4 buckets),
not a hypothesis proof. V2 keeps the main body figure focused on the core
claim ("KU is a query-time problem") and moves ablations to a separate figure.

Row A: Pool state distribution (share%) for 3 memory-based methods.
Row B: 100%-normalized stacked bar — **bottom = E2E Acc, top = failure
attribution decomposed by pool state**. Row B same colors as Row A so the
reader can, at a glance, trace *which pool state caused each method's
failures*.

Main methods (rest go to ablation figure):
  ours     — ours(no_p5, struct + P3 LLM grouping)  → paper main
  mem0+P1  — (b) mem0+P1 (destructive write)         → prior work
  Zep      — Zep(k=10, chunk_512)                    → prior work
  LCA      — long-context gpt-4o-mini                → reference (no pool,
             shown as dashed E2E line on row B only)

Backbone: gpt-4o-mini (future work extends to gemma3 27B / 4B — v3 will add).

Failure attribution reading:
  mem0+P1 → PP-OldOnly + PP-Missing large top block (destructive write damage)
  Zep     → PP-Both dominates top (multi-granularity + no query-time KU;
             32k = 89% PP-Both-wrong = "reasoning overload not memory miss")
  ours    → tiny top; correct dominates
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

REPO = Path(__file__).resolve().parents[3]
OUT_FIGCUR = REPO / "docs/0615_intro_framework_after_problem_statement/figures_current"
OUT_PAPER = REPO / "docs/0615_intro_framework_after_problem_statement/paper_current/figures"

# ============================================================================
# Data (from pool_acc_crosstab.md after 2026-07-04 (matcher v4 + per-qid EM) patch).
# Value = (acc_count, bucket_size) per pool state per method.
# ============================================================================
DATA = {
    "6k": {
        "N": 74,
        "cells": {
            "ours":    {"PP-New": (52, 53), "PP-Both": (17, 21), "PP-OldOnly": (0, 0),  "PP-Missing": (0, 0)},
            "mem0+P1": {"PP-New": (25, 27), "PP-Both": (9, 12),  "PP-OldOnly": (0, 15), "PP-Missing": (0, 20)},
            "Zep":     {"PP-New": (0, 0),   "PP-Both": (46, 74), "PP-OldOnly": (0, 0),  "PP-Missing": (0, 0)},
        },
        "LCA_e2e_pct": 87.8,  # LCA (long-ctx gpt-4o-mini) has_pair EM = 65/74
    },
    "32k": {
        "N": 65,
        "cells": {
            "ours":    {"PP-New": (39, 40), "PP-Both": (17, 22), "PP-OldOnly": (0, 2),  "PP-Missing": (1, 1)},
            "mem0+P1": {"PP-New": (21, 22), "PP-Both": (4, 14),  "PP-OldOnly": (0, 11), "PP-Missing": (0, 18)},
            "Zep":     {"PP-New": (1, 2),   "PP-Both": (32, 62), "PP-OldOnly": (0, 1),  "PP-Missing": (0, 0)},
        },
        "LCA_e2e_pct": 70.8,  # 46/65
    },
    "64k": {
        "N": 66,
        "cells": {
            "ours":    {"PP-New": (35, 38), "PP-Both": (24, 26), "PP-OldOnly": (1, 2),  "PP-Missing": (0, 0)},
            "mem0+P1": {"PP-New": (25, 25), "PP-Both": (9, 17),  "PP-OldOnly": (0, 15), "PP-Missing": (0, 9)},
            "Zep":     {"PP-New": (1, 1),   "PP-Both": (35, 65), "PP-OldOnly": (0, 0),  "PP-Missing": (0, 0)},
        },
        "LCA_e2e_pct": 54.5,  # 36/66
    },
}

METHODS = ["ours", "mem0+P1", "Zep"]
LENGTHS = ["6k", "32k", "64k"]
BUCKETS = ["PP-New", "PP-Both", "PP-OldOnly", "PP-Missing"]

# Row A palette: same as v1
FACE_A = {
    "PP-New":     "#009E73",  # green accent
    "PP-Both":    "#4A4A4A",
    "PP-OldOnly": "#FFFFFF",
    "PP-Missing": "#FFFFFF",
}
EDGE_A = {
    "PP-New":     "#007A57",
    "PP-Both":    "#4A4A4A",
    "PP-OldOnly": "#000000",
    "PP-Missing": "#000000",
}
HATCH_A = {
    "PP-New":     "",
    "PP-Both":    "",
    "PP-OldOnly": "///",
    "PP-Missing": "....",
}

# Row B: solid Correct + failure decomposition matching Row A.
# "PP-New wrong" uses green + dense hatch to distinguish from "Correct" solid.
FACE_B = {
    "Correct":         "#009E73",   # solid dark green
    "PP-New wrong":    "#B7EAD8",   # light green
    "PP-Both wrong":   "#4A4A4A",
    "PP-OldOnly wrong":"#FFFFFF",
    "PP-Missing wrong":"#FFFFFF",
}
EDGE_B = {
    "Correct":         "#007A57",
    "PP-New wrong":    "#007A57",
    "PP-Both wrong":   "#4A4A4A",
    "PP-OldOnly wrong":"#000000",
    "PP-Missing wrong":"#000000",
}
HATCH_B = {
    "Correct":         "",
    "PP-New wrong":    "///",     # green background + hatch = "pool right but LLM wrong"
    "PP-Both wrong":   "",
    "PP-OldOnly wrong":"///",
    "PP-Missing wrong":"....",
}


def row_a_shares(cell, N):
    """{method: [share_bucket_i,...] summing to 100%}, using bucket_size / N."""
    out = {}
    for m in METHODS:
        sizes = [cell[m][b][1] for b in BUCKETS]
        # Some methods (Zep 6k) have all pool_size < N because empty pool contributes 0
        # In practice sum(sizes) == N when every qid classified. If N mismatch, normalise to sum(sizes).
        T = sum(sizes) or 1
        out[m] = [100 * s / T for s in sizes]
    return out


def row_b_stacks(cell, N):
    """{method: [correct_pct, PP-New wrong pct, PP-Both wrong pct, OldOnly wrong pct, Missing wrong pct]}.
    Sums to 100%. Normalized by N (total has_pair count)."""
    out = {}
    for m in METHODS:
        correct = sum(cell[m][b][0] for b in BUCKETS)
        rows = [100 * correct / N]  # Correct
        for b in BUCKETS:
            a, n = cell[m][b]
            wrong = n - a
            rows.append(100 * wrong / N)
        out[m] = rows
    return out


def draw_row_a(ax, cell, N, x, title):
    shares = row_a_shares(cell, N)
    bottom = np.zeros(len(METHODS))
    for bi, b in enumerate(BUCKETS):
        heights = np.array([shares[m][bi] for m in METHODS])
        ax.bar(x, heights, bottom=bottom, width=0.65,
               facecolor=FACE_A[b], edgecolor=EDGE_A[b], hatch=HATCH_A[b], linewidth=0.7)
        for i, h in enumerate(heights):
            if h >= 8:
                n = cell[METHODS[i]][b][1]
                col = "white" if b in ("PP-New", "PP-Both") else "black"
                ax.text(x[i], bottom[i] + h / 2, f"{n}",
                        ha="center", va="center", fontsize=8, color=col)
        bottom += heights
    ax.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xticklabels(METHODS, rotation=0, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def draw_row_b(ax, cell, N, x, lca_pct):
    """Row B: 100% stacked. bottom = Correct (E2E Acc), top = failures decomposed."""
    stacks = row_b_stacks(cell, N)
    stack_names = ["Correct", "PP-New wrong", "PP-Both wrong", "PP-OldOnly wrong", "PP-Missing wrong"]
    bottom = np.zeros(len(METHODS))
    for si, s in enumerate(stack_names):
        heights = np.array([stacks[m][si] for m in METHODS])
        ax.bar(x, heights, bottom=bottom, width=0.65,
               facecolor=FACE_B[s], edgecolor=EDGE_B[s], hatch=HATCH_B[s], linewidth=0.7)
        # Annotate: E2E Acc% on the bottom "Correct" band; large wrong bands get count
        for i, h in enumerate(heights):
            if si == 0 and h >= 8:  # Correct band → show E2E Acc %
                ax.text(x[i], bottom[i] + h / 2, f"{h:.1f}%",
                        ha="center", va="center", fontsize=9, color="white", weight="bold")
            elif si > 0 and h >= 6:  # wrong band large enough → show count
                # Compute wrong count for annotation
                if si == 1:
                    n_wrong = cell[METHODS[i]]["PP-New"][1] - cell[METHODS[i]]["PP-New"][0]
                elif si == 2:
                    n_wrong = cell[METHODS[i]]["PP-Both"][1] - cell[METHODS[i]]["PP-Both"][0]
                elif si == 3:
                    n_wrong = cell[METHODS[i]]["PP-OldOnly"][1] - cell[METHODS[i]]["PP-OldOnly"][0]
                else:
                    n_wrong = cell[METHODS[i]]["PP-Missing"][1] - cell[METHODS[i]]["PP-Missing"][0]
                col = "white" if s == "PP-Both wrong" else "black"
                ax.text(x[i], bottom[i] + h / 2, f"{n_wrong}",
                        ha="center", va="center", fontsize=7.5, color=col)
        bottom += heights
    # LCA reference line
    ax.axhline(lca_pct, color="#B54B00", linestyle="--", linewidth=1.4, alpha=0.85)
    ax.text(len(METHODS) - 0.4, lca_pct + 1.5, f"LCA {lca_pct:.1f}%",
            fontsize=8, color="#B54B00", ha="right")
    ax.set_ylim(0, 105)
    ax.set_xticks(x)
    ax.set_xticklabels(METHODS, rotation=0, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def main():
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 7.2), sharey="row")
    x = np.arange(len(METHODS))

    for col, L in enumerate(LENGTHS):
        entry = DATA[L]
        draw_row_a(axes[0, col], entry["cells"], entry["N"], x,
                   title=f"{L}  (has_pair N={entry['N']})")
        draw_row_b(axes[1, col], entry["cells"], entry["N"], x, entry["LCA_e2e_pct"])
        if col == 0:
            axes[0, col].set_ylabel("(a) Pool state share (%)", fontsize=10)
            axes[1, col].set_ylabel("(b) E2E outcome (%)\nbottom = Correct; top = failure decomp", fontsize=10)

    # Legend row A (top)
    handles_a = [
        mpatches.Patch(facecolor=FACE_A[b], edgecolor=EDGE_A[b], hatch=HATCH_A[b], label=b)
        for b in BUCKETS
    ]
    # Legend row B (bottom): Correct + 4 failure types + LCA line
    handles_b = [
        mpatches.Patch(facecolor=FACE_B["Correct"], edgecolor=EDGE_B["Correct"],
                       hatch=HATCH_B["Correct"], label="Correct (E2E)"),
        mpatches.Patch(facecolor=FACE_B["PP-New wrong"], edgecolor=EDGE_B["PP-New wrong"],
                       hatch=HATCH_B["PP-New wrong"], label="PP-New wrong"),
        mpatches.Patch(facecolor=FACE_B["PP-Both wrong"], edgecolor=EDGE_B["PP-Both wrong"],
                       hatch=HATCH_B["PP-Both wrong"], label="PP-Both wrong"),
        mpatches.Patch(facecolor=FACE_B["PP-OldOnly wrong"], edgecolor=EDGE_B["PP-OldOnly wrong"],
                       hatch=HATCH_B["PP-OldOnly wrong"], label="PP-OldOnly wrong"),
        mpatches.Patch(facecolor=FACE_B["PP-Missing wrong"], edgecolor=EDGE_B["PP-Missing wrong"],
                       hatch=HATCH_B["PP-Missing wrong"], label="PP-Missing wrong"),
    ]
    # LCA reference line manual entry
    import matplotlib.lines as mlines
    lca_line = mlines.Line2D([], [], color="#B54B00", linestyle="--", linewidth=1.4,
                             label="LCA (long-ctx gpt-4o-mini, E2E)")

    fig.legend(handles=handles_a, loc="upper center", bbox_to_anchor=(0.5, 1.005),
               ncol=4, frameon=False, fontsize=9, title="Row (a): Pool state distribution")
    fig.legend(handles=handles_b + [lca_line], loc="lower center",
               bbox_to_anchor=(0.5, -0.03), ncol=6, frameon=False, fontsize=8.5,
               title="Row (b): E2E outcome — bottom Correct, top failure attribution")

    plt.tight_layout(rect=(0, 0.04, 1, 0.94))

    OUT_FIGCUR.mkdir(parents=True, exist_ok=True)
    OUT_PAPER.mkdir(parents=True, exist_ok=True)
    for d in (OUT_FIGCUR, OUT_PAPER):
        for ext in ("png", "pdf"):
            fig.savefig(d / f"F_pool_diagnostic.{ext}", dpi=200, bbox_inches="tight")
    print(f"Saved F_pool_diagnostic.{{png,pdf}} to:")
    print(f"  {OUT_FIGCUR}")
    print(f"  {OUT_PAPER}")


if __name__ == "__main__":
    main()
