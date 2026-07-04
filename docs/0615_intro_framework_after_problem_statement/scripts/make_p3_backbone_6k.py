"""Figure C — F_p3_backbone_6k: the +P3 ablation (ours_struct + P3 LLM identity
grouping, = ours_no_p5) analog of Figure B (F_struct_backbone_6k). Grouped bars
per backbone: Resolution Accuracy (method-end: pool isolates NEW) vs End-to-End
has_pair EM (method + reader). Read side by side with Figure B this shows whether
adding P3 changes the METHOD-end Resolution (pool isolation) or only the reader
outcome. Numbers: analysis/results/resolution_vs_em_no_p5_6k.json
(compute_resolution_per_query_no_p5.py). B/W-safe: Resolution solid dark,
EM light+hatch, data labels.
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
D = json.load(open("analysis/results/resolution_vs_em_no_p5_6k.json"))

order = ["1b", "4b", "12b", "27b"]
lab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B"}
res = [100.0 * D[b]["res"] / D[b]["N"] for b in order]
em = [100.0 * D[b]["em"] / D[b]["N"] for b in order]

x = np.arange(len(order))
w = 0.38
fig, ax = plt.subplots(figsize=(6.8, 4.6))
b1 = ax.bar(x - w / 2, res, w, color="0.15", edgecolor="black",
            label="Resolution Acc (method: pool isolates NEW)")
b2 = ax.bar(x + w / 2, em, w, color="0.72", edgecolor="black", hatch="////",
            label="End-to-End EM (method + reader)")
for bars, vals in [(b1, res), (b2, em)]:
    for rect, v in zip(bars, vals):
        ax.annotate(f"{v:.0f}", (rect.get_x() + rect.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)

ax.set_xticks(x); ax.set_xticklabels([lab[b] for b in order])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("has_pair Accuracy (%)  ↑")
ax.set_ylim(0, 116)
ax.set_title("Method = ours_struct + P3 : structural (S,P) + LLM identity grouping\n"
             "FC-SH 6k has_pair, by backbone", fontsize=10.5, fontweight="bold", pad=8)
ax.legend(fontsize=9, loc="upper left", frameon=False, borderaxespad=0.6)
ax.grid(axis="y", ls=":", alpha=0.5)
ax.set_axisbelow(True)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_p3_backbone_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_p3_backbone_6k.{png,pdf}")
print("Resolution:", {b: round(v, 1) for b, v in zip(order, res)})
print("End-to-End:", {b: round(v, 1) for b, v in zip(order, em)})
