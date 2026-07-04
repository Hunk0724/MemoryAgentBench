"""FC-SH 6k has_pair EM by backbone — STRUCTURAL (S,P)+temporal grouping ONLY.

Deliberately excludes the p3_only (LLM-grouping) curve: that arm is currently a
confounded measurement (ollama num_ctx not set -> 100-candidate prompt truncated;
+ one-shot identity grouping over top-100 overloads the model). Plotting it beside
struct invites the wrong conclusion. This figure shows struct's overall has_pair
EM (numerator = struct-correct, denominator = 74 = all has_pair), the SAME metric
as the main table, across gemma3-{1b,4b,12b,27b} + gpt-4o-mini reference.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import json, glob, os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
FIG = Path("docs/0615_intro_framework_after_problem_statement/figures_current")
plt.rcParams.update({"font.size": 11})


def hp_em(size):
    fs = glob.glob(f"outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct"
                   f"__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    if not fs:
        return None
    gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
    hp = [q for q, r in gt.items() if r["conflict_type"] == "has_pair"]
    d = {r["query_id"]: r["exact_match"] for r in json.load(open(fs[0]))["data"]}
    return 100.0 * sum(d.get(q, False) for q in hp) / len(hp)


struct = {}
for b in ["1b", "4b", "12b", "27b"]:
    v = hp_em(b)
    if v is not None:
        struct[b] = v
struct["gpt-4o-mini"] = 93.2  # Table 3 (Mac Studio, has_pair 6k)

xorder = [b for b in ["1b", "4b", "12b", "27b", "gpt-4o-mini"] if b in struct]
xlab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B", "gpt-4o-mini": "4o-mini"}
xs = list(range(len(xorder)))
ys = [struct[b] for b in xorder]

fig, ax = plt.subplots(figsize=(6.4, 4.3))
ax.plot(xs, ys, "-o", color="black", lw=2.6, ms=8, zorder=3,
        label="structural (S,P)+temporal grouping")
for x, y in zip(xs, ys):
    ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points",
                xytext=(0, 9), fontsize=9, ha="center")
ax.set_xticks(xs)
ax.set_xticklabels([xlab[b] for b in xorder])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("has_pair Exact-Match Accuracy (%)  ↑")
ax.set_ylim(0, 100)
ax.set_title("Structural KU resolution: has_pair EM by backbone (FC-SH 6k)", fontsize=11.5)
ax.legend(fontsize=9.5, loc="lower right", frameon=False)
ax.grid(axis="y", ls=":", alpha=0.5)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_struct_backbone_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_struct_backbone_6k.{png,pdf}")
print("struct:", {k: round(v, 1) for k, v in struct.items()})
