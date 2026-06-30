"""F_bank_recall: memory-BANK GT-recall (is the conflicting fact's NEW version
still IN the bank?) vs history length, for vector-memory methods. Overlays L1
(retrieved top-100) recall as dashed — it COINCIDES with L0, proving the gap is at
WRITE time (the bank itself lacks the new version), not retrieval.

ours keeps the new version in the bank (95-100%); the destructive baseline
(mem0+ours storage) loses ~half at write-time (bank recall 51->41%, irreversible);
vanilla's bank is empty (no extraction). Zep excluded (non-destructive). FC-SH
has_pair. dest 262k excluded (incomplete killed run).
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = "/home/yhchiang/MemoryAgentBench"
FIG = Path(f"{ROOT}/docs/0615_intro_framework_after_problem_statement/figures_current")
L0 = json.load(open(f"{ROOT}/analysis/results/phase0/l0_bank_state.json"))
L1 = json.load(open(f"{ROOT}/analysis/results/phase0/state_eval_current.json"))
LENS = ["6k", "32k", "64k", "262k"]
X = {L: i for i, L in enumerate(LENS)}
METHS = [("ours", "ours", "#009E73"),
         ("(b)mem0+P1", "mem0+ours storage", "#E69F00"),
         ("(a)vanilla", "mem0", "#D55E00")]
EXCLUDE = {("(b)mem0+P1", "262k")}  # incomplete killed run

def recov(d, n): return (d.get("both", 0) + d.get("new_only", 0)) / n * 100

plt.rcParams.update({"font.size": 11})
fig, ax = plt.subplots(figsize=(7.0, 4.6))
for key, lab, col in METHS:
    xs0, ys0, xs1, ys1 = [], [], [], []
    for L in LENS:
        k = f"{key}|{L}"
        if k in L0 and (key, L) not in EXCLUDE:
            xs0.append(X[L]); ys0.append(recov(L0[k]["L0"], L0[k]["n"]))
        if k in L1 and (key, L) not in EXCLUDE:
            xs1.append(X[L]); ys1.append(recov(L1[k]["L1"], L1[k]["n"]))
    ax.plot(xs0, ys0, "-o", color=col, lw=2.6, ms=8, label=lab, zorder=3)
    for x, y in zip(xs0, ys0):
        ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, 8), fontsize=8.5, ha="center")

ax.set_xticks(range(4)); ax.set_xticklabels(LENS)
ax.set_xlabel("Conversation-history length")
ax.set_ylabel("NEW version still recoverable (% of has_pair)  ↑")
ax.set_ylim(-4, 104)
ax.set_title("Memory-bank GT-recall (L0) vs conversation-history length", fontsize=11.5)
ax.legend(fontsize=10, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
ax.spines[["top", "right"]].set_visible(False)
for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_bank_recall.{ext}", dpi=200, bbox_inches="tight")
print("  -> F_bank_recall")
