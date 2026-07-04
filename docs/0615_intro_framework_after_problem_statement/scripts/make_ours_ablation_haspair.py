"""Figure: ours ablation on FC-SH has_pair vs conversation-history length
(gpt-4o-mini, single deterministic run at temp 0).

Grouped bar chart (B&W-safe): 3 lengths × 3 methods per group. Each method has
a unique HATCH pattern (survives greyscale print) plus a light accent colour
for on-screen clarity.

Three variants (caption expands the mechanism):

  ours (full)                 — (S,P) structural routing + P3 LLM identity
                                grouping + P5 3-way conflict-type classifier
                                + deterministic temporal argmax
  ours (struct + time argmax) — (S,P) triple group + deterministic argmax on
                                chunk ordinal; NO LLM at query time
  ours (P3 LLM + time argmax) — P3 LLM identity clustering over the whole
                                top-k + deterministic argmax on chunk ordinal;
                                (S,P) structural routing disabled
"""
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(os.environ.get("REPO_ROOT") or Path(__file__).resolve().parents[3])
FIG = REPO / "docs/0615_intro_framework_after_problem_statement/figures_current"
FIG.mkdir(parents=True, exist_ok=True)

LENS = ["6k", "32k", "64k"]

DATA = {
    "ours (full)":                  [91.9, 84.6, 90.9],
    "ours (struct + time argmax)":  [90.5, 80.0, 87.9],
    "ours (P3 LLM + time argmax)":  [95.9, 89.2, 87.9],
}

# B&W-safe: unique hatch per method; colour is a light accent (grey / accent).
STYLE = {
    "ours (full)":                  dict(color="#333333", hatch="",   edgecolor="black"),
    "ours (struct + time argmax)":  dict(color="#BBBBBB", hatch="///", edgecolor="black"),
    "ours (P3 LLM + time argmax)":  dict(color="#009E73", hatch="xxx", edgecolor="black"),
}

plt.rcParams.update({"font.size": 11, "font.family": "DejaVu Sans"})

fig, ax = plt.subplots(figsize=(7.2, 4.6))
n_lens = len(LENS)
n_methods = len(DATA)
bar_w = 0.24
x = np.arange(n_lens)

for i, (method, ys) in enumerate(DATA.items()):
    offset = (i - (n_methods - 1) / 2) * bar_w
    bars = ax.bar(x + offset, ys, bar_w,
                  label=method,
                  color=STYLE[method]["color"],
                  hatch=STYLE[method]["hatch"],
                  edgecolor=STYLE[method]["edgecolor"],
                  linewidth=0.8)
    for xi, y in zip(x + offset, ys):
        ax.text(xi, y + 0.5, f"{y:.1f}", ha="center", va="bottom",
                fontsize=8.5)

ax.set_xticks(x)
ax.set_xticklabels(LENS)
ax.set_xlabel("Conversation-history length")
ax.set_ylabel("has_pair EM (%)  ↑")
ax.set_ylim(74, 100)
ax.set_yticks([75, 80, 85, 90, 95, 100])
ax.set_title("FC-SH has_pair — ours ablation (gpt-4o-mini, chunk 512)")
ax.grid(axis="y", linestyle=":", alpha=0.35)
ax.legend(fontsize=9, loc="lower center", ncol=3,
          bbox_to_anchor=(0.5, -0.26), frameon=False,
          handletextpad=0.5, columnspacing=1.8, handlelength=2.4)
ax.spines[["top", "right"]].set_visible(False)

for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_ours_ablation_haspair.{ext}", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"-> F_ours_ablation_haspair.png/pdf @ {FIG}")
