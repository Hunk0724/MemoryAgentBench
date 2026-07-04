"""FC-SH 6k has_pair: Resolution Accuracy vs End-to-End QA EM, by local backbone.

Separates the METHOD's contribution (Resolution Accuracy = the resolved pool
contains the NEW version and NOT the OLD one) from the READER's contribution
(End-to-End EM = final answer text matches GT). Numbers precomputed by
scratch resacc2.py (word-boundary + subject-scoped matching over the actual
group_and_resolve output) -> analysis/results/resolution_vs_em_6k.json.
gpt-4o-mini omitted: its struct store lives on the Mac, not this machine.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import json, os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
FIG = Path("docs/0615_intro_framework_after_problem_statement/figures_current")
plt.rcParams.update({"font.size": 11})
D = json.load(open("analysis/results/resolution_vs_em_6k.json"))

order = ["1b", "4b", "12b", "27b"]
lab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B"}
xs = list(range(len(order)))
res = [100.0 * D[b]["res"] / D[b]["N"] for b in order]
em = [100.0 * D[b]["em"] / D[b]["N"] for b in order]

fig, ax = plt.subplots(figsize=(6.6, 4.4))
ax.plot(xs, res, "-o", color="black", lw=2.6, ms=8, zorder=3,
        label="Resolution Accuracy (method: pool isolates NEW)")
ax.plot(xs, em, "--s", color="0.5", lw=2.6, ms=8, zorder=3,
        label="End-to-End QA EM (method + reader)")
for x, y in zip(xs, res):
    ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, 9),
                fontsize=8.5, ha="center")
for x, y in zip(xs, em):
    ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, -14),
                fontsize=8.5, ha="center", color="0.35")
# shade reader effect (gap between the two lines)
ax.fill_between(xs, res, em, color="0.85", zorder=1)
ax.set_xticks(xs)
ax.set_xticklabels([lab[b] for b in order])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("has_pair Accuracy (%)  ↑")
ax.set_ylim(0, 100)
ax.set_title("Method vs reader: Resolution Accuracy vs End-to-End EM (FC-SH 6k)",
             fontsize=11)
ax.legend(fontsize=8.8, loc="lower right", frameon=False)
ax.grid(axis="y", ls=":", alpha=0.5)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_resolution_vs_em_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_resolution_vs_em_6k.{png,pdf}")
print("Resolution:", {b: round(v, 1) for b, v in zip(order, res)})
print("End-to-End:", {b: round(v, 1) for b, v in zip(order, em)})
