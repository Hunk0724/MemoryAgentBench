"""FC-SH 6k OVERALL accuracy (x/100): ours_struct vs ours_struct+P3 (=ours_no_p5),
by gemma backbone. Grouped BARS — the ablation of adding the P3 LLM identity-
grouping step on top of the deterministic structural (S,P)+temporal core.

Message: adding P3 is CAPABILITY-GATED. It HURTS the weak backbone (1B), is
NEUTRAL in the middle (4B/12B: structural already does the work), and HELPS the
strong backbone (27B: good merges tighten the pool + curb the reader's parametric
override). The deterministic structural core is the stable floor; LLM judgment on
top only pays off once the backbone is strong enough not to mis-merge.

Numbers read live from results.json (both arms). B/W-safe: struct = solid dark,
struct+P3 = light + hatch; Δ annotated over each pair.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import json, glob, os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
FIG = Path("docs/0615_intro_framework_after_problem_statement/figures_current")
plt.rcParams.update({"font.size": 11})


def overall(suf, size):
    fs = glob.glob(f"outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified{suf}"
                   f"__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    if not fs:
        return None
    d = json.load(open(fs[0]))["data"]
    return sum(1 for r in d if r.get("exact_match"))  # x / 100


order = ["1b", "4b", "12b", "27b"]
lab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B"}
st = [overall("_struct", b) for b in order]
p3 = [overall("_no_p5", b) for b in order]
x = np.arange(len(order))
w = 0.38

fig, ax = plt.subplots(figsize=(7.0, 4.5))
b1 = ax.bar(x - w / 2, st, w, color="0.15", edgecolor="black",
            label="ours_struct  (deterministic (S,P)+temporal)")
b2 = ax.bar(x + w / 2, p3, w, color="0.72", edgecolor="black", hatch="////",
            label="ours_struct + P3  (add LLM identity grouping)")
for bars, vals in [(b1, st), (b2, p3)]:
    for rect, v in zip(bars, vals):
        ax.annotate(f"{v}", (rect.get_x() + rect.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)
# Δ (P3 minus struct) on a fixed top row so labels never collide with bars
for xi, s, p in zip(x, st, p3):
    d = p - s
    txt = "0" if d == 0 else (f"+{d}" if d > 0 else f"{d}")
    ax.annotate(f"P3 Δ{txt}", (xi, 112), ha="center", fontsize=9, fontweight="bold")

ax.set_xticks(x); ax.set_xticklabels([lab[b] for b in order])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("Overall Exact-Match Accuracy (x / 100)  ↑")
ax.set_ylim(0, 128)
ax.set_title("Ablation: add P3 LLM identity grouping on top of ours_struct\n"
             "FC-SH 6k overall EM, by backbone", fontsize=10.5, fontweight="bold", y=1.22)
ax.legend(fontsize=8.8, loc="lower left", frameon=False,
          bbox_to_anchor=(0.0, 1.005), borderaxespad=0.0)
ax.grid(axis="y", ls=":", alpha=0.5)
ax.set_axisbelow(True)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_struct_vs_p3_overall_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_struct_vs_p3_overall_6k.{png,pdf}")
print("struct   :", dict(zip(order, st)))
print("struct+P3:", dict(zip(order, p3)))
