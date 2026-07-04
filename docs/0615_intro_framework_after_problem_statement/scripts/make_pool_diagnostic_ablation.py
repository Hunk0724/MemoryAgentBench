"""Figure: F_pool_diagnostic — pool state distribution × Acc-in-bucket, 3 lengths.

2x3 subplot grid (rows = view, cols = length):
  Row 1: stacked bar of pool-state share (%) across 6 methods per length.
  Row 2: grouped bar of Acc-in-bucket (%) across the 4 pool states per method.

Data source: docs/.../paper_current/results/pool_acc_crosstab.md (hand-copied
here to avoid re-running matcher v3 for each figure edit; regenerate that file
via `analysis/compute_pool_acc_crosstab.py` if numbers change).

Style: B&W-safe (see paper_current/style_rules_tables_figures_writing.md §2):
- PP-New = green accent (#009E73)
- PP-Both = dark grey (#333)
- PP-OldOnly = white + '///' hatch
- PP-Missing = white + '...' hatch (dense dots to distinguish from ///)
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
# Data (from pool_acc_crosstab.md, chunk_4096 Zep k=10; commit 0fa2edc)
# Value = (acc_count, bucket_size)
# ============================================================================
DATA = {
    "6k": {
        "N": 74,
        "cells": {
            "o-Full":  {"PP-New": (52, 53), "PP-Both": (14, 19), "PP-OldOnly": (1, 1),  "PP-Missing": (1, 1),  "E2E": (68, 74)},
            "o-NoP5":  {"PP-New": (51, 52), "PP-Both": (16, 20), "PP-OldOnly": (1, 1),  "PP-Missing": (1, 1),  "E2E": (69, 74)},
            "o-Struct":{"PP-New": (47, 47), "PP-Both": (18, 25), "PP-OldOnly": (2, 2),  "PP-Missing": (0, 0),  "E2E": (67, 74)},
            "o-P3":    {"PP-New": (48, 48), "PP-Both": (21, 24), "PP-OldOnly": (1, 1),  "PP-Missing": (1, 1),  "E2E": (71, 74)},
            "m0-P1":   {"PP-New": (15, 27), "PP-Both": (5, 12),  "PP-OldOnly": (4, 15), "PP-Missing": (10, 20),"E2E": (34, 74)},
            "Zep":     {"PP-New": (0, 0),   "PP-Both": (44, 72), "PP-OldOnly": (2, 2),  "PP-Missing": (0, 0),  "E2E": (46, 74)},
        },
    },
    "32k": {
        "N": 65,
        "cells": {
            "o-Full":  {"PP-New": (40, 40), "PP-Both": (14, 21), "PP-OldOnly": (0, 3),  "PP-Missing": (1, 1),  "E2E": (55, 65)},
            "o-NoP5":  {"PP-New": (39, 40), "PP-Both": (16, 21), "PP-OldOnly": (1, 3),  "PP-Missing": (1, 1),  "E2E": (57, 65)},
            "o-Struct":{"PP-New": (32, 32), "PP-Both": (19, 29), "PP-OldOnly": (0, 3),  "PP-Missing": (1, 1),  "E2E": (52, 65)},
            "o-P3":    {"PP-New": (39, 39), "PP-Both": (17, 22), "PP-OldOnly": (1, 3),  "PP-Missing": (1, 1),  "E2E": (58, 65)},
            "m0-P1":   {"PP-New": (12, 22), "PP-Both": (7, 14),  "PP-OldOnly": (4, 11), "PP-Missing": (6, 18), "E2E": (29, 65)},
            "Zep":     {"PP-New": (0, 1),   "PP-Both": (4, 62),  "PP-OldOnly": (0, 1),  "PP-Missing": (0, 1),  "E2E": (4, 65)},
        },
    },
    "64k": {
        "N": 66,
        "cells": {
            "o-Full":  {"PP-New": (35, 38), "PP-Both": (21, 23), "PP-OldOnly": (4, 5),  "PP-Missing": (0, 0),  "E2E": (60, 66)},
            "o-NoP5":  {"PP-New": (35, 38), "PP-Both": (21, 23), "PP-OldOnly": (4, 5),  "PP-Missing": (0, 0),  "E2E": (60, 66)},
            "o-Struct":{"PP-New": (30, 30), "PP-Both": (25, 33), "PP-OldOnly": (3, 3),  "PP-Missing": (0, 0),  "E2E": (58, 66)},
            "o-P3":    {"PP-New": (34, 36), "PP-Both": (20, 25), "PP-OldOnly": (4, 5),  "PP-Missing": (0, 0),  "E2E": (58, 66)},
            "m0-P1":   {"PP-New": (13, 25), "PP-Both": (6, 15),  "PP-OldOnly": (6, 17), "PP-Missing": (2, 9),  "E2E": (27, 66)},
            "Zep":     {"PP-New": (1, 1),   "PP-Both": (34, 62), "PP-OldOnly": (1, 3),  "PP-Missing": (0, 0),  "E2E": (36, 66)},
        },
    },
}

METHODS = ["o-Full", "o-NoP5", "o-Struct", "o-P3", "m0-P1", "Zep"]
LENGTHS = ["6k", "32k", "64k"]
BUCKETS = ["PP-New", "PP-Both", "PP-OldOnly", "PP-Missing"]

# B&W-safe colors + hatches
FACE = {
    "PP-New":     "#009E73",  # green accent (ours main story)
    "PP-Both":    "#4A4A4A",  # dark grey
    "PP-OldOnly": "#FFFFFF",
    "PP-Missing": "#FFFFFF",
}
EDGE = {
    "PP-New":     "#007A57",
    "PP-Both":    "#4A4A4A",
    "PP-OldOnly": "#000000",
    "PP-Missing": "#000000",
}
HATCH = {
    "PP-New":     "",
    "PP-Both":    "",
    "PP-OldOnly": "///",
    "PP-Missing": "....",
}
TEXT_ON = {  # text color on top of the fill for stacked-bar counts
    "PP-New":     "white",
    "PP-Both":    "white",
    "PP-OldOnly": "black",
    "PP-Missing": "black",
}


def shares(cell):
    """Return {method: [share_bucket_i,...] summing to ~100} using bucket_size."""
    out = {}
    for m in METHODS:
        sizes = [cell[m][b][1] for b in BUCKETS]
        T = sum(sizes) or 1
        out[m] = [100 * s / T for s in sizes]
    return out


def accs(cell):
    """Return {method: [acc%|None per bucket]}."""
    out = {}
    for m in METHODS:
        row = []
        for b in BUCKETS:
            a, n = cell[m][b]
            row.append(100 * a / n if n > 0 else None)
        out[m] = row
    return out


def draw_stacked(ax, share_dict, cell, x, title):
    bottom = np.zeros(len(METHODS))
    for bi, b in enumerate(BUCKETS):
        heights = np.array([share_dict[m][bi] for m in METHODS])
        ax.bar(
            x, heights, bottom=bottom, width=0.72,
            facecolor=FACE[b], edgecolor=EDGE[b], hatch=HATCH[b],
            linewidth=0.7,
        )
        # Annotate n (bucket size) inside stack when segment tall enough
        for i, h in enumerate(heights):
            if h >= 7:
                n = cell[METHODS[i]][b][1]
                ax.text(
                    x[i], bottom[i] + h / 2, f"{n}",
                    ha="center", va="center", fontsize=7,
                    color=TEXT_ON[b],
                )
        bottom += heights
    ax.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xticklabels(METHODS, rotation=25, ha="right", fontsize=8)
    ax.set_title(title, fontsize=10)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def draw_grouped_acc(ax, cell, x, n_threshold=3):
    """Row 2: only show PP-New / PP-Both (the two large-N buckets).

    Rationale: PP-OldOnly / PP-Missing often have n=1-2 → 100% bars are misleading.
    Tiny samples (n < n_threshold) are drawn as grey stubs with dagger marker;
    n = 0 shows a dash. Full 4-bucket table stays in pool_acc_crosstab.md.
    """
    focus_buckets = ["PP-New", "PP-Both"]
    n_b = len(focus_buckets)
    width = 0.34
    offsets = (np.arange(n_b) - (n_b - 1) / 2) * width
    tiny_flag = False
    for bi, b in enumerate(focus_buckets):
        for i, m in enumerate(METHODS):
            a, n = cell[m][b]
            xc = x[i] + offsets[bi]
            if n == 0:
                ax.text(xc, 6, "n=0", ha="center", va="bottom", fontsize=6, color="#888",
                        rotation=90)
                continue
            h = 100 * a / n
            if n < n_threshold:
                # Tiny sample: grey shaded stub, dagger marker
                ax.bar(xc, h, width=width * 0.90,
                       facecolor="#EEEEEE", edgecolor="#999", linewidth=0.5, alpha=0.7)
                ax.text(xc, min(h + 2, 108), f"{a}/{n}†",
                        ha="center", va="bottom", fontsize=6, color="#666")
                tiny_flag = True
            else:
                ax.bar(xc, h, width=width * 0.90,
                       facecolor=FACE[b], edgecolor=EDGE[b], hatch=HATCH[b], linewidth=0.6)
                ax.text(xc, min(h + 1.5, 108), f"{a}/{n}",
                        ha="center", va="bottom", fontsize=6.5, color="#111")
    ax.set_ylim(0, 118)
    ax.set_xticks(x)
    ax.set_xticklabels(METHODS, rotation=25, ha="right", fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    return tiny_flag


def main():
    fig, axes = plt.subplots(2, 3, figsize=(12.5, 6.8), sharey="row")
    x = np.arange(len(METHODS))

    for col, L in enumerate(LENGTHS):
        Lentry = DATA[L]
        cell = Lentry["cells"]
        # -- Row 1: pool state share --
        draw_stacked(axes[0, col], shares(cell), cell, x,
                     title=f"{L}  (has_pair N={Lentry['N']})")
        if col == 0:
            axes[0, col].set_ylabel("(a) Pool state share (%)", fontsize=9)
        # -- Row 2: Acc-in-bucket (PP-New + PP-Both only) --
        draw_grouped_acc(axes[1, col], cell, x)
        if col == 0:
            axes[1, col].set_ylabel("(b) Acc within bucket (%)\nPP-New / PP-Both only", fontsize=9)

    # Shared legend at top (all 4 buckets appear in row 1 stack)
    handles = [
        mpatches.Patch(facecolor=FACE[b], edgecolor=EDGE[b], hatch=HATCH[b], label=b)
        for b in BUCKETS
    ]
    # Add dagger marker note for tiny samples
    handles.append(mpatches.Patch(facecolor="#EEEEEE", edgecolor="#999",
                                   label="†  n < 3 (small sample)"))
    fig.legend(
        handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.005),
        ncol=5, frameon=False, fontsize=8.5,
    )

    plt.tight_layout(rect=(0, 0, 1, 0.955))

    OUT_FIGCUR.mkdir(parents=True, exist_ok=True)
    OUT_PAPER.mkdir(parents=True, exist_ok=True)
    for d in (OUT_FIGCUR, OUT_PAPER):
        for ext in ("png", "pdf"):
            fig.savefig(d / f"F_pool_diagnostic_ablation.{ext}", dpi=200, bbox_inches="tight")
    print(f"Saved F_pool_diagnostic_ablation.{{png,pdf}} to:")
    print(f"  {OUT_FIGCUR}")
    print(f"  {OUT_PAPER}")


if __name__ == "__main__":
    main()
