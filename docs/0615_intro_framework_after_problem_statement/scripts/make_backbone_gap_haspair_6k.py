"""F1 — FC-SH 6k has_pair EM by backbone (E2E backbone-gap), GROUPED BARS.

OBJECTIVE E2E metric (MAB exact_match, no matcher) -> valid at ALL backbones,
including weak 1b/4b where the pool-state cross-tab is unreliable (GX10 runs use
per-backbone gemma extraction, so gemma-1b/4b fact surfaces diverge from GT and
matcher false-negates; see weak_model_6k_analysis.md §2).

Story: ours (struct / no_p5) dominates every backbone; write-time baselines
(mem0(b), Zep) collapse hardest on the weak end -> the ours-baseline gap widens
as the backbone weakens (paper's constrained-deployment claim).

Bars (not a line): x is categorical (distinct checkpoints) and the ours curve is
non-monotonic (27B dips). B/W-safe: grayscale fills + hatch. Reads results.json
LIVE (excludes smoke/size5 files); denominator = has_pair 74.
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

gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
HP = set(q for q, r in gt.items() if r["conflict_type"] == "has_pair")
N = len(HP)


def _pick(fs):
    fs = [f for f in fs if "smoke" not in f and "size5" not in f]
    if not fs:
        return None
    return max(fs, key=lambda f: len(json.load(open(f))["data"]))


def hp_em(pathglob):
    # official MAB metric = substring_exact_match (2026-07-11 canonical migration)
    f = _pick(glob.glob(pathglob))
    if not f:
        return None
    d = json.load(open(f))["data"]
    return sum(1 for r in d if r.get("substring_exact_match") and r["query_id"] in HP)


order = ["1b", "4b", "12b", "27b"]
lab = {"1b": "1B", "4b": "4B", "12b": "12B", "27b": "27B"}
# (display, path-template, facecolor, hatch)
BASE = "outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-{suf}__gemma3-{s}/Conflict_Resolution/*sh_6k*results*.json"
METH = [
    ("ours_struct  ((S,P)+temporal, no query-LLM)", lambda s: hp_em(BASE.format(suf="unified_struct", s=s)), "0.15", ""),
    ("ours_no_p5  (struct + P3 grouping)", lambda s: hp_em(BASE.format(suf="unified_no_p5", s=s)), "0.45", ""),
    ("(b) mem0+P1  (write-time destructive)", lambda s: hp_em(BASE.format(suf="unified_dest", s=s)), "0.72", "////"),
    ("Zep  (decoupled write-time)", lambda s: hp_em(f"outputs/gemma3-{s}-zep/Conflict_Resolution/*sh_6k*results*.json"), "0.90", "xxxx"),
]

x = np.arange(len(order))
w = 0.20
fig, ax = plt.subplots(figsize=(7.6, 4.5))
for i, (name, fn, fc, hatch) in enumerate(METH):
    vals = [fn(s) or 0 for s in order]
    bars = ax.bar(x + (i - 1.5) * w, vals, w, color=fc, edgecolor="black",
                  hatch=hatch, label=name)
    for rect, v in zip(bars, vals):
        ax.annotate(f"{v}", (rect.get_x() + rect.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 2), ha="center", fontsize=7.5)

ax.set_xticks(x)
ax.set_xticklabels([lab[b] for b in order])
ax.set_xlabel("Backbone  (weak → strong)")
ax.set_ylabel(f"has_pair substring-EM  (x / {N})  ↑")
ax.set_ylim(0, N + 12)
ax.set_title("FC-SH 6k knowledge-update accuracy by backbone (gemma3, GX10)\n"
             "official substring-EM — objective, valid at every backbone",
             fontsize=10.5, fontweight="bold", pad=8)
ax.legend(fontsize=8.2, loc="upper left", frameon=False, ncol=1, borderaxespad=0.4)
ax.grid(axis="y", ls=":", alpha=0.5)
ax.set_axisbelow(True)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_backbone_gap_haspair_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_backbone_gap_haspair_6k.{png,pdf}")
for name, fn, _, _ in METH:
    print(f"  {name.split('  ')[0]:14}:", {b: fn(b) for b in order})
