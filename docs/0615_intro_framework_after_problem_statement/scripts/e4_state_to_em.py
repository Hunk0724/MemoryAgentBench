"""E4 (F_state_to_em): pooled final-context state -> EM, across all methods x
lengths (has_pair only). Reads L3 from state_eval_current.json where
  L3 = { L2-state : [n, correct] }  per "method|len" cell.
Pools every cell to show that answer correctness is (almost) fully determined by
the final-context state fed to the answer LLM:  new_only -> ~high, others -> low.
This closes the causal chain E-rec -> E-L1 -> E-L1L2 -> E4.
Output: figures_current/F_state_to_em.png|pdf
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path

ROOT = "/home/yhchiang/MemoryAgentBench"
FIG = Path(f"{ROOT}/docs/0615_intro_framework_after_problem_statement/figures_current")
S = json.load(open(f"{ROOT}/analysis/results/phase0/state_eval_current.json"))
ORDER = ["new_only", "both", "old_only", "neither"]
COL = {"new_only": "#56B4E9", "both": "#009E73", "old_only": "#D55E00", "neither": "#999999"}
LAB = {"new_only": "New only", "both": "Both versions", "old_only": "Old only", "neither": "Neither"}

pool = defaultdict(lambda: [0, 0])  # state -> [n, correct]
for cell, v in S.items():
    for st, nc in v.get("L3", {}).items():
        pool[st][0] += nc[0]; pool[st][1] += nc[1]

plt.rcParams.update({"font.size": 11})
fig, ax = plt.subplots(figsize=(6.0, 4.2))
rates = [pool[s][1] / max(1, pool[s][0]) * 100 for s in ORDER]
ax.bar(range(len(ORDER)), rates, color=[COL[s] for s in ORDER], width=0.62)
for i, s in enumerate(ORDER):
    n, c = pool[s]
    ax.text(i, rates[i] + 1.8, f"{rates[i]:.0f}%\n({c}/{n})", ha="center", fontsize=9)
ax.set_xticks(range(len(ORDER))); ax.set_xticklabels([LAB[s] for s in ORDER], fontsize=9.5)
ax.set_ylabel("Exact-match accuracy (%)  ↑"); ax.set_ylim(0, 110)
ax.set_xlabel("Final-context state (after resolution) for the conflicting fact")
ax.set_title("Answer correctness is determined by the final-context state\n(pooled: all methods × lengths, has_pair)")
ax.spines[["top", "right"]].set_visible(False)
for ext in ("png", "pdf"):
    fig.savefig(FIG / f"F_state_to_em.{ext}", dpi=200, bbox_inches="tight")
plt.close(fig)
print("  -> F_state_to_em")
for s in ORDER:
    n, c = pool[s]
    print(f"    {s:<10} {c}/{n} = {c/max(1,n)*100:.0f}%")
