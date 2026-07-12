"""F2 — FC-SH 6k return_context×Acc decomposition, RELIABLE backbones only (12B/27B).

The pool-state cross-tab (§4.2) is trustworthy ONLY where gemma extraction aligns
to GT surface so matcher v4 can classify the pool — i.e. 12B/27B (store overlap
99-100% with the reference; pool-missing=0). 1B/4B are OMITTED on purpose (their
gemma extraction diverges -> matcher false-negatives; use E2E + case-study there).

Each has_pair question (N=74) is decomposed into WHY it was right/wrong:
  new_only ✓  clean win   : pipeline isolated NEW & reader used it
  both ✓      rescue      : pool still mixed, reader picked NEW
  new_only ✗  OVERRIDE    : pool clean (NEW-only) but reader answered OLD  <- 27B drag
  both ✗      lost        : mixed pool, reader picked OLD
(old_only/neither = 0 here -> NEW never absent at 12B/27B; the pipeline delivers a
clean pool). Stacked bars, B/W-safe: correct=solid dark→mid, wrong=hatched light.

Numbers: pool_acc_crosstab_gemma_6k.md (matcher v4, Acc = official substring_exact_match).
Message: structural KU delivers a clean pool at both backbones; the ONLY residual loss is
27B reader override (new_only✗ = 2), which P3 grouping (no_p5) curbs to 1. Under the
official metric the 27B "dip" nearly vanishes (was 7/4 under strict EM — most strict-wrong
27B answers were verbose-correct, not genuine override).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import os

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
FIG = Path("docs/0615_intro_framework_after_problem_statement/figures_current")
plt.rcParams.update({"font.size": 11})

# (label, new_only✓, both✓, new_only✗ override, both✗)  from crosstab MD
# (matcher v4, Acc = official substring_exact_match; 2026-07-11 canonical migration)
BARS = [
    ("12B\nstruct", 60, 13, 0, 1),
    ("12B\nno_p5", 60, 13, 0, 1),
    ("27B\nstruct", 58, 13, 2, 1),
    ("27B\nno_p5", 61, 12, 1, 0),
]
labels = [b[0] for b in BARS]
new_ok = np.array([b[1] for b in BARS])
both_ok = np.array([b[2] for b in BARS])
new_bad = np.array([b[3] for b in BARS])   # OVERRIDE
both_bad = np.array([b[4] for b in BARS])

x = np.arange(len(BARS))
w = 0.6
fig, ax = plt.subplots(figsize=(6.8, 4.6))
p1 = ax.bar(x, new_ok, w, color="0.20", edgecolor="black", label="new_only ✓  (clean win)")
p2 = ax.bar(x, both_ok, w, bottom=new_ok, color="0.55", edgecolor="black", label="both ✓  (reader rescue)")
p3 = ax.bar(x, new_bad, w, bottom=new_ok + both_ok, color="0.85", edgecolor="black",
            hatch="xxxx", label="new_only ✗  (reader OVERRIDE)")
p4 = ax.bar(x, both_bad, w, bottom=new_ok + both_ok + new_bad, color="0.95", edgecolor="black",
            hatch="....", label="both ✗  (lost in mixed)")

# annotate EM (correct total). Under official SubEM the override segment is 0-2
# questions (tiny) — left un-annotated; the near-absent hatch band IS the message.
for xi, b in zip(x, BARS):
    em = b[1] + b[2]
    ax.annotate(f"EM {em}", (xi, em / 2), ha="center", va="center", fontsize=8.5,
                color="white", fontweight="bold")

ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_xlabel("Backbone × method   (12B/27B only — 1B/4B cross-tab unreliable, see caption)")
ax.set_ylabel("has_pair questions (N=74)")
ax.set_ylim(0, 80)
ax.set_title("Why answers are right/wrong at strong backbones (12B/27B)\n"
             "structural KU gives a clean pool; 27B override negligible under official SubEM",
             fontsize=10, fontweight="bold", pad=8)
ax.legend(fontsize=8.4, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
ax.grid(axis="y", ls=":", alpha=0.5)
ax.set_axisbelow(True)
for ext in ["png", "pdf"]:
    fig.savefig(FIG / f"F_crosstab_1227_6k.{ext}", dpi=200, bbox_inches="tight")
print("saved F_crosstab_1227_6k.{png,pdf}")
for b in BARS:
    print(f"  {b[0].replace(chr(10),' '):12}: new_ok={b[1]} both_ok={b[2]} override={b[3]} both_bad={b[4]}  EM={b[1]+b[2]}")
