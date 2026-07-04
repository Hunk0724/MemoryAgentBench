"""FC-SH 6k has_pair by backbone — STRUCTURAL (S,P)+temporal, GROUPED BARS.

Grouped bar per backbone shows the two things that must be read together:
  - Resolution Accuracy (METHOD): the resolved pool isolates the NEW version
    (GT_new present, GT_old absent, subject-scoped). This is what our structural
    (S,P)+deterministic-temporal step actually delivers, independent of the reader.
  - End-to-End QA EM (METHOD + READER): the final answer text matches GT.

Bars (not a line) because the x-axis is categorical (distinct model checkpoints,
+ a different-family reference) and the relationship is NON-monotonic — a line
would falsely imply a smooth size-trend. Reading the two bars side by side makes
the 27B story legible at a glance: the METHOD bar holds/rises into 27B while only
the READER's EM bar dips (27B overrides the pool with its world-consistent prior).

Numbers: analysis/results/resolution_vs_em_6k.json, refreshed by
scripts/compute_resolution_acc_6k.py after every struct re-run (NEW code:
normalize L1/L2 + fact-level ordinal). gpt-4o-mini: EM-only reference (its struct
store lives on the Mac; Resolution not computable here) -> dotted reference line.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import json, os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
FIG = Path("docs/0615_intro_framework_after_problem_statement/figures_current")
plt.rcParams.update({"font.size": 11})
D = json.load(open("analysis/results/resolution_vs_em_6k.json"))

order = ["1b", "4b", "12b", "27b"]
lab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B"}
res = [100.0 * D[b]["res"] / D[b]["N"] for b in order]
em = [100.0 * D[b]["em"] / D[b]["N"] for b in order]
mini_em = 100.0 * D["gpt-4o-mini"]["em"] / D["gpt-4o-mini"]["N"] if "gpt-4o-mini" in D else None

x = np.arange(len(order))
w = 0.38
fig, ax = plt.subplots(figsize=(6.8, 4.4))
b1 = ax.bar(x - w / 2, res, w, color="0.15", edgecolor="black",
            label="Resolution Acc (method: pool isolates NEW)")
b2 = ax.bar(x + w / 2, em, w, color="0.72", edgecolor="black", hatch="////",
            label="End-to-End EM (method + reader)")
for bars, vals in [(b1, res), (b2, em)]:
    for rect, v in zip(bars, vals):
        ax.annotate(f"{v:.0f}", (rect.get_x() + rect.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)

# 4o-mini EM reference kept OUT of the plot (declutter) -> reported in caption.
ax.set_xticks(x)
ax.set_xticklabels([lab[b] for b in order])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("has_pair Accuracy (%)  ↑")
ax.set_ylim(0, 116)
# make the METHOD explicit: this is ours_struct (deterministic, no LLM grouping)
ax.set_title("Method = ours_struct : structural (S,P) + deterministic temporal "
             "(no LLM grouping)\nFC-SH 6k has_pair, by backbone",
             fontsize=10.5, fontweight="bold", pad=8)
ax.legend(fontsize=9, loc="upper left", frameon=False, borderaxespad=0.6)
ax.grid(axis="y", ls=":", alpha=0.5)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_struct_backbone_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_struct_backbone_6k.{png,pdf}")
print("Resolution:", {b: round(v, 1) for b, v in zip(order, res)})
print("End-to-End:", {b: round(v, 1) for b, v in zip(order, em)})
