"""FC-SH 6k has_pair: structural (S,P) grouping vs LLM identity grouping (p3_only),
across backbones (GX10 gemma3-{1b,4b,12b,27b} + Mac Studio gpt-4o-mini reference).

gemma3 numbers are read live from results.json; gpt-4o-mini from Table 3
(fc_sh_has_pair_main_table.md, 6k column). Re-run after 27b finishes to add it.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import json, glob, os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
FIG = Path("docs/0615_intro_framework_after_problem_statement/figures_current")
plt.rcParams.update({"font.size": 11})


def hp_em(size, suf):
    fs = glob.glob(f"outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified{suf}"
                   f"__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    if not fs:
        return None
    gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
    hp = [q for q, r in gt.items() if r["conflict_type"] == "has_pair"]
    d = {r["query_id"]: r["exact_match"] for r in json.load(open(fs[0]))["data"]}
    return 100.0 * sum(d.get(q, False) for q in hp) / len(hp)


struct, p3 = {}, {}
for b in ["1b", "4b", "12b", "27b"]:
    s, p = hp_em(b, "_struct"), hp_em(b, "_p3_only_no_struct")
    if s is not None: struct[b] = s
    if p is not None: p3[b] = p
struct["gpt-4o-mini"], p3["gpt-4o-mini"] = 93.2, 91.9  # Table 3 (6k)

xorder = [b for b in ["1b", "4b", "12b", "27b", "gpt-4o-mini"] if b in struct or b in p3]
xlab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B", "gpt-4o-mini": "4o-mini"}
xs = list(range(len(xorder)))
ys_s = [struct.get(b) for b in xorder]
ys_p = [p3.get(b) for b in xorder]

fig, ax = plt.subplots(figsize=(7.0, 4.6))
ax.plot(xs, ys_s, "-o", color="black", lw=2.6, ms=8, zorder=3,
        label="structural (S,P) grouping")
ax.plot(xs, ys_p, "--s", color="0.5", lw=2.6, ms=8, zorder=3,
        label="LLM identity grouping (p3-only)")
for x, y in zip(xs, ys_s):
    if y is not None:
        ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points",
                    xytext=(0, 9), fontsize=8.5, ha="center")
for x, y in zip(xs, ys_p):
    if y is not None:
        ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points",
                    xytext=(0, -14), fontsize=8.5, ha="center", color="0.35")
ax.set_xticks(xs)
ax.set_xticklabels([xlab[b] for b in xorder])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel("has_pair Exact-Match Accuracy (%)  ↑")
ax.set_ylim(0, 100)
ax.set_title("Identity grouping: structural vs LLM, by backbone (FC-SH 6k)", fontsize=11.5)
ax.legend(fontsize=9.5, loc="lower right", frameon=False)
ax.grid(axis="y", ls=":", alpha=0.5)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_p3only_vs_struct_backbone_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_p3only_vs_struct_backbone_6k.{png,pdf}")
print("struct :", {k: round(v, 1) for k, v in struct.items()})
print("p3_only:", {k: round(v, 1) for k, v in p3.items()})
