"""Evidence figures (why ours wins) from state_eval_current.json. Outputs to
figures_current/. The causal chain: write-time store -> L1 retrieved state ->
L2 resolved -> EM.
  F_recoverable   : new-fact recoverable % (both+new_only @L1) vs length  [IRREVERSIBILITY]
  F_L1_state      : has_pair L1 state composition per method x length (stacked)
  F_ours_L1L2     : ours L1 (retrieved) vs L2 (final ctx) -> the both->new_only collapse
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ROOT = __import__("os").environ.get("REPO_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3])
FIG = Path(f"{ROOT}/docs/0615_intro_framework_after_problem_statement/figures_current")
S = json.load(open(f"{ROOT}/analysis/results/phase0/state_eval_current.json"))
LENS = ["6k", "32k", "64k", "262k"]
ORDER = ["both", "new_only", "old_only", "neither"]
COL = {"both": "#009E73", "new_only": "#56B4E9", "old_only": "#D55E00", "neither": "#999999"}
LAB = {"both": "Both versions", "new_only": "New only", "old_only": "Old only (new LOST)", "neither": "Neither (new LOST)"}
MC = {"ours": "#009E73", "(b)mem0+P1": "#E69F00", "(a)vanilla": "#D55E00"}
plt.rcParams.update({"font.size": 11})


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig); print(f"  -> {name}")


def recoverable():
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for m in ["ours", "(b)mem0+P1", "(a)vanilla"]:
        xs, ys = [], []
        for i, L in enumerate(LENS):
            v = S.get(f"{m}|{L}")
            if not v:
                continue
            d = v["L1"]; n = v["n"]
            rec = (d.get("both", 0) + d.get("new_only", 0)) / n * 100
            xs.append(i); ys.append(rec)
        ax.plot(xs, ys, "-o", color=MC[m], label=m, linewidth=2.4 if m == "ours" else 1.7,
                markersize=7 if m == "ours" else 5)
        for x, y in zip(xs, ys):
            ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, 6), fontsize=8, ha="center")
    ax.set_xticks(range(4)); ax.set_xticklabels(LENS)
    ax.set_xlabel("Conversation-history length")
    ax.set_ylabel("New fact still recoverable (% of has_pair)  ↑")
    ax.set_ylim(-3, 103); ax.set_title("Conservative writes keep the new fact recoverable;\ndestructive writes lose it irreversibly")
    ax.legend(fontsize=9, loc="center right"); ax.spines[["top", "right"]].set_visible(False)
    save(fig, "F_recoverable")


def l1_state():
    meths = ["(a)vanilla", "(b)mem0+P1", "ours"]
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    pos, ticks, labs = 0, [], []
    for L in LENS:
        for m in meths:
            v = S.get(f"{m}|{L}")
            if not v:
                pos += 1; continue
            d = v["L1"]; n = v["n"]; b = 0
            for k in ORDER:
                ax.bar(pos, d.get(k, 0) / n * 100, 0.85, bottom=b, color=COL[k], edgecolor="white", linewidth=0.5)
                b += d.get(k, 0) / n * 100
            ticks.append(pos); labs.append(m.replace("(a)", "").replace("(b)", "")); pos += 1
        pos += 0.6
    ax.set_xticks(ticks); ax.set_xticklabels(labs, fontsize=7.5, rotation=40, ha="right")
    for i, L in enumerate(LENS):
        ax.text(i * 3.6 + 1, -22, L, ha="center", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 100); ax.set_ylabel("Share of has_pair (%)")
    ax.set_title("L1 retrieved state: is the conflicting fact's NEW version available?")
    h = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in ORDER]
    ax.legend(h, [LAB[k] for k in ORDER], fontsize=8, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.04), frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "F_L1_state")


def ours_l1l2():
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.0), sharey=True)
    for ax, layer, title in [(axes[0], "L1", "L1 — Retrieved (top-100)"), (axes[1], "L2", "L2 — Final context (after resolution)")]:
        for i, L in enumerate(LENS):
            v = S.get(f"ours|{L}")
            if not v:
                continue
            d = v[layer]; n = v["n"]; b = 0
            for k in ORDER:
                ax.bar(i, d.get(k, 0) / n * 100, 0.7, bottom=b, color=COL[k], edgecolor="white", linewidth=0.5)
                b += d.get(k, 0) / n * 100
        ax.set_xticks(range(4)); ax.set_xticklabels(LENS); ax.set_title(title, fontsize=11)
        ax.set_ylim(0, 100); ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Share of has_pair (%)")
    fig.suptitle("Ours: both versions retrieved (L1) -> query-time resolution collapses to new-only (L2)", fontsize=11.5, y=1.02)
    h = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in ORDER]
    fig.legend(h, [LAB[k] for k in ORDER], fontsize=8.5, ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.02), frameon=False)
    fig.subplots_adjust(bottom=0.16)
    save(fig, "F_ours_L1L2")


print("generating evidence figures ->", FIG)
recoverable(); l1_state(); ours_l1l2()
