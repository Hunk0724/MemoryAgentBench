"""FC-SH 6k OVERALL accuracy: ours_struct vs b (mem0 DESTRUCTIVE update), by
gemma backbone. Grouped bars. Same held-fixed ours extraction for both; the only
difference is the WRITE-time update: ours = conservative (S,P) write + query-time
deterministic resolution; b = mem0's LLM-judged ADD/UPDATE/DELETE at write time.

Message: prior-work write-time destructive update is CATASTROPHIC on weak
backbones (1B/4B collapse to ~0 as mem0's update LLM degenerates to echoing its
prompt example "Name is John"), only becomes usable at 12B, and NEVER catches
ours at any backbone. Deferring KU to query-time is robust; committing it at
write-time via an LLM is not.

Numbers read live from results.json. B/W-safe: ours_struct solid dark,
b light+hatch; Δ (ours − b) annotated.
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
    return sum(1 for r in json.load(open(fs[0]))["data"] if r.get("exact_match"))


order = ["1b", "4b", "12b", "27b"]
lab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B"}
st = [overall("_struct", b) for b in order]
bb = [overall("_dest", b) for b in order]
x = np.arange(len(order))
w = 0.38

fig, ax = plt.subplots(figsize=(7.0, 4.6))
b1 = ax.bar(x - w / 2, st, w, color="0.15", edgecolor="black",
            label="ours_struct  (query-time deterministic resolution)")
b2 = ax.bar(x + w / 2, bb, w, color="0.72", edgecolor="black", hatch="////",
            label="b = mem0 destructive update  (write-time LLM ADD/UPDATE/DELETE)")
for bars, vals in [(b1, st), (b2, bb)]:
    for rect, v in zip(bars, vals):
        ax.annotate(f"{v}", (rect.get_x() + rect.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)
for xi, s, b in zip(x, st, bb):
    ax.annotate(f"+{s - b}", (xi, 122), ha="center", fontsize=9, fontweight="bold")

ax.set_xticks(x); ax.set_xticklabels([lab[b] for b in order])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("Overall Exact-Match Accuracy (x / 100)  ↑")
ax.set_ylim(0, 132)
ax.set_title("Write-time destructive update (mem0) vs query-time resolution (ours_struct)\n"
             "FC-SH 6k overall EM, by backbone   (both use ours' held-fixed extraction)",
             fontsize=10, fontweight="bold", y=1.02)
ax.legend(fontsize=8.6, loc="lower left", frameon=False,
          bbox_to_anchor=(0.0, 1.10), borderaxespad=0.0)
ax.grid(axis="y", ls=":", alpha=0.5)
ax.set_axisbelow(True)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_struct_vs_b_overall_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_struct_vs_b_overall_6k.{png,pdf}")
print("ours_struct:", dict(zip(order, st)))
print("b (mem0)   :", dict(zip(order, bb)))
