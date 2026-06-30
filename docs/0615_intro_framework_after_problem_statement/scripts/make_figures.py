"""Generate the narrative figures (F1-F4) from the three-level eval JSONs.
Colorblind-safe (Okabe-Ito), axis units, >=8pt fonts, self-contained.
Single deterministic run (temp=0, frozen caches) -> no error bars.
Outputs PNG (slides) + PDF (paper) to docs/0615_.../figures/.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/home/yhchiang/MemoryAgentBench")
RES = ROOT / "analysis/results/phase0"
FIG = ROOT / "docs/0615_intro_framework_after_problem_statement/figures"
FIG.mkdir(parents=True, exist_ok=True)
LENGTHS = ["6k", "32k", "64k"]

# Okabe-Ito colorblind-safe
C = {"green": "#009E73", "blue": "#56B4E9", "vermillion": "#D55E00",
     "gray": "#999999", "orange": "#E69F00", "navy": "#0072B2", "purple": "#CC79A7"}
plt.rcParams.update({"font.size": 11})

l1 = json.load(open(RES / "l1_retrieval_eval.json"))
l2 = json.load(open(RES / "l2_resolution_eval.json"))
l3 = json.load(open(RES / "l3_state_em.json"))


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {name}.png/.pdf")


# ── F1: store shrinkage ─────────────────────────────────────────────────────
def f1():
    import numpy as np
    ours = [l1[f"ours_{L}"]["store_points"] for L in LENGTHS]
    van = [l1[f"vanilla_{L}"]["store_points"] for L in LENGTHS]
    x = np.arange(len(LENGTHS)); w = 0.38
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    b1 = ax.bar(x - w/2, ours, w, label="Ours (conservative ADD)", color=C["green"])
    b2 = ax.bar(x + w/2, van, w, label="Vanilla Mem0 (destructive)", color=C["vermillion"])
    for xi, o, v in zip(x, ours, van):
        ax.text(xi + w/2, v + max(ours)*0.01, f"{v/o*100:.0f}%\nof ours", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(LENGTHS)
    ax.set_xlabel("Conversation-history length"); ax.set_ylabel("Facts stored in memory bank (count)")
    ax.set_title("Vanilla Mem0 irreversibly deletes facts at write-time")
    ax.legend(fontsize=9, loc="upper left"); ax.spines[["top", "right"]].set_visible(False)
    save(fig, "F1_store_shrinkage")


# ── F2: has_pair retrieval composition (MAIN) ───────────────────────────────
def f2():
    import numpy as np
    order = ["both", "new_only", "old_only", "neither"]
    col = {"both": C["green"], "new_only": C["blue"], "old_only": C["vermillion"], "neither": C["gray"]}
    lab = {"both": "Both retrieved", "new_only": "New only",
           "old_only": "Old only (new lost)", "neither": "Neither (both lost)"}
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    groups, xticks, xlabs = [], [], []
    pos = 0
    for L in LENGTHS:
        for mode, tag in [("Vanilla", "vanilla"), ("Ours", "ours")]:
            d = l1[f"{tag}_{L}"]["has_pair"]; n = l1[f"{tag}_{L}"]["n_has_pair"]
            groups.append((pos, [d[k] / n * 100 for k in order])); xticks.append(pos); xlabs.append(mode)
            pos += 1
        pos += 0.6
    for pos_i, vals in groups:
        bottom = 0
        for k, v in zip(order, vals):
            ax.bar(pos_i, v, 0.85, bottom=bottom, color=col[k], edgecolor="white", linewidth=0.5)
            bottom += v
    ax.set_xticks(xticks); ax.set_xticklabels(xlabs, fontsize=9)
    # length group labels
    for i, L in enumerate(LENGTHS):
        ax.text(i * 2.6 + 0.5, -13, L, ha="center", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 100); ax.set_ylabel("Share of has_pair queries (%)")
    ax.set_title("Retrieval (top-100): is the current (new) fact recoverable?")
    handles = [plt.Rectangle((0, 0), 1, 1, color=col[k]) for k in order]
    ax.legend(handles, [lab[k] for k in order], fontsize=8, ncol=2, loc="lower center",
              bbox_to_anchor=(0.5, 1.06), frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "F2_has_pair_retrieval")


# ── F3: resolution clean_rate (phase0 vs phase2) ────────────────────────────
def f3():
    import numpy as np
    def clean(tag, L):
        bt = l2[f"{tag}_{L}"]["both_transition"]; n = sum(bt.values())
        return bt["new_only"] / max(1, n) * 100
    p0 = [clean("phase0", L) for L in LENGTHS]; p2 = [clean("phase2", L) for L in LENGTHS]
    x = np.arange(len(LENGTHS)); w = 0.38
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.bar(x - w/2, p0, w, label="Structural only (Ours-Phase0)", color=C["orange"])
    ax.bar(x + w/2, p2, w, label="Structural + LLM grouping (Ours-Phase2)", color=C["green"])
    for xi, a, b in zip(x, p0, p2):
        ax.text(xi - w/2, a + 1, f"{a:.0f}", ha="center", fontsize=8)
        ax.text(xi + w/2, b + 1, f"{b:.0f}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(LENGTHS)
    ax.set_xlabel("Conversation-history length")
    ax.set_ylabel("Resolution clean rate (%)  ↑")
    ax.set_title("Query-time resolution: of pairs where both are retrieved,\nfraction cleanly collapsed to new-only")
    ax.set_ylim(0, 100); ax.legend(fontsize=8.5, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "F3_resolution_clean_rate")


# ── F4: state -> EM (causal) ────────────────────────────────────────────────
def f4():
    col = {"both": C["green"], "new_only": C["blue"], "old_only": C["vermillion"],
           "neither": C["gray"], "present": C["green"], "missing": C["gray"]}

    def agg(cell_key, order):
        a = {s: [0, 0] for s in order}
        for v in l3.values():
            for s, (n, c) in v.get(cell_key, {}).items():
                if s in a:
                    a[s][0] += n; a[s][1] += c
        return a

    hp_order = ["new_only", "both", "old_only", "neither"]
    nc_order = ["present", "missing"]
    hp, nc = agg("cells", hp_order), agg("cells_no_conflict", nc_order)
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.5),
                             gridspec_kw={"width_ratios": [2, 1]}, sharey=True)
    for ax, data, order, title in [(axes[0], hp, hp_order, "Conflict (has_pair)"),
                                   (axes[1], nc, nc_order, "No-conflict")]:
        rates = [data[s][1] / max(1, data[s][0]) * 100 for s in order]
        ax.bar(range(len(order)), rates, color=[col[s] for s in order], width=0.62)
        for i, s in enumerate(order):
            n, c = data[s]
            ax.text(i, rates[i] + 1.5, f"{rates[i]:.0f}%\n(n={n})", ha="center", fontsize=8)
        ax.set_xticks(range(len(order))); ax.set_xticklabels(order, fontsize=8.5, rotation=0)
        ax.set_title(title, fontsize=10.5); ax.set_ylim(0, 110)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Exact-match accuracy (%)  ↑")
    fig.suptitle("Answer correctness is determined by the final-context state", fontsize=12, y=1.02)
    save(fig, "F4_state_to_em")


# ── F6: full EM matrix (per length: 3 subsets x 3 methods) ──────────────────
# Values from analyze_overall_em.py (deterministic; has_pair/no_conflict/overall).
EM = {
    "6k":  {"vanilla": [27, 65, 37], "phase0": [82, 100, 87], "phase2": [88, 100, 91]},
    "32k": {"vanilla": [37, 83, 53], "phase0": [68, 94, 77],  "phase2": [78, 94, 84]},
    "64k": {"vanilla": [42, 62, 49], "phase0": [58, 71, 62],  "phase2": [62, 71, 65]},
}


def f6():
    import numpy as np
    subsets = ["has_pair", "no_conflict", "overall"]
    methods = [("Vanilla Mem0", "vanilla", C["vermillion"]),
               ("Ours-Phase0 (structural)", "phase0", C["orange"]),
               ("Ours-Phase2 (struct.+LLM)", "phase2", C["green"])]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    x = np.arange(len(subsets)); w = 0.26
    for ax, L in zip(axes, LENGTHS):
        for i, (lab, key, col) in enumerate(methods):
            vals = EM[L][key]
            bars = ax.bar(x + (i - 1) * w, vals, w, color=col, label=lab if L == "6k" else None)
            for xi, v in zip(x + (i - 1) * w, vals):
                ax.text(xi, v + 1.5, f"{v}", ha="center", fontsize=7.5)
        ax.set_title(f"{L} context", fontsize=11)
        ax.set_xticks(x); ax.set_xticklabels(subsets, fontsize=9)
        ax.set_ylim(0, 108); ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Exact-match accuracy (%)  ↑")
    fig.legend(loc="lower center", ncol=3, fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("KU accuracy by conflict subset and history length", fontsize=12, y=1.02)
    save(fig, "F6_em_matrix")


# ── F6-overall: single-panel overall EM, baseline vs ours, across lengths ────
def f6_overall():
    import numpy as np
    methods = [("Vanilla Mem0", "vanilla", C["vermillion"]),
               ("Ours (structural)", "phase0", C["orange"]),
               ("Ours (structural+LLM)", "phase2", C["green"])]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    x = np.arange(len(LENGTHS)); w = 0.26
    for i, (lab, key, col) in enumerate(methods):
        vals = [EM[L][key][2] for L in LENGTHS]  # index 2 = overall
        ax.bar(x + (i - 1) * w, vals, w, color=col, label=lab)
        for xi, v in zip(x + (i - 1) * w, vals):
            ax.text(xi, v + 1.2, f"{v}", ha="center", fontsize=8.5)
    ax.set_xticks(x); ax.set_xticklabels([f"{L} context" for L in LENGTHS], fontsize=10)
    ax.set_ylim(0, 105); ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel("Overall exact-match accuracy (%)  ↑")
    ax.legend(fontsize=9, loc="upper right", frameon=False)
    ax.set_title("Overall KU accuracy across history lengths", fontsize=12)
    save(fig, "F6_overall_em")


# ── F-L1 / F-L2: context STATE before vs after resolution (has_pair + no_conflict)
HP_ORDER = ["both", "new_only", "old_only", "neither"]
HP_COL = {"both": C["green"], "new_only": C["blue"], "old_only": C["vermillion"], "neither": C["gray"]}
HP_LAB = {"both": "Both", "new_only": "New only", "old_only": "Old only (new lost)", "neither": "Neither"}
NC_ORDER = ["present", "missing"]
NC_COL = {"present": C["green"], "missing": C["gray"]}
NC_LAB = {"present": "Current fact present", "missing": "Current fact missing"}


def _stacked(ax, get_frac, order, col, title):
    import numpy as np
    pos, ticks, labs = 0, [], []
    for L in LENGTHS:
        for mode in ["Mem0", "Ours"]:
            fr = get_frac(mode, L)
            b = 0
            for k in order:
                ax.bar(pos, fr[k], 0.85, bottom=b, color=col[k], edgecolor="white", linewidth=0.5)
                b += fr[k]
            ticks.append(pos); labs.append(mode); pos += 1
        pos += 0.6
    ax.set_xticks(ticks); ax.set_xticklabels(labs, fontsize=8)
    for i, L in enumerate(LENGTHS):
        ax.text(i * 2.6 + 0.5, -13, L, ha="center", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 100); ax.set_title(title, fontsize=10.5)
    ax.spines[["top", "right"]].set_visible(False)


def _legend(fig, order, col, lab, y):
    h = [plt.Rectangle((0, 0), 1, 1, color=col[k]) for k in order]
    fig.legend(h, [lab[k] for k in order], ncol=len(order), fontsize=8,
               loc="lower center", bbox_to_anchor=(0.5, y), frameon=False)


def _state_fig(name, title, hp_get, nc_get):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    _stacked(axes[0], hp_get, HP_ORDER, HP_COL, "Conflict queries (has_pair)")
    _stacked(axes[1], nc_get, NC_ORDER, NC_COL, "No-conflict queries")
    axes[0].set_ylabel("Share of queries (%)")
    fig.suptitle(title, fontsize=12.5, y=1.0)
    # legends below each panel (clear of titles)
    h1 = [plt.Rectangle((0, 0), 1, 1, color=HP_COL[k]) for k in HP_ORDER]
    fig.legend(h1, [HP_LAB[k] for k in HP_ORDER], fontsize=8, ncol=2,
               loc="upper center", bbox_to_anchor=(0.30, 0.05), frameon=False)
    h2 = [plt.Rectangle((0, 0), 1, 1, color=NC_COL[k]) for k in NC_ORDER]
    fig.legend(h2, [NC_LAB[k] for k in NC_ORDER], fontsize=8, ncol=1,
               loc="upper center", bbox_to_anchor=(0.78, 0.05), frameon=False)
    fig.subplots_adjust(bottom=0.22, top=0.86)
    save(fig, name)


def f_l1():
    tag = lambda m: "vanilla" if m == "Mem0" else "ours"
    def hp(m, L):
        d = l1[f"{tag(m)}_{L}"]["has_pair"]; n = l1[f"{tag(m)}_{L}"]["n_has_pair"]
        return {k: d[k] / n * 100 for k in HP_ORDER}
    def nc(m, L):
        d = l1[f"{tag(m)}_{L}"]["no_conflict"]; n = l1[f"{tag(m)}_{L}"]["n_no_conflict"]
        return {"present": d["retrieved"] / n * 100, "missing": d["missing"] / n * 100}
    _state_fig("F_L1_retrieved_state", "L1 — Retrieved context state (top-100, before resolution)", hp, nc)


def f_l2():
    # Mem0 has no query-time resolution -> its L2 == L1; Ours uses Phase-2 resolution.
    def hp(m, L):
        if m == "Mem0":
            d = l1[f"vanilla_{L}"]["has_pair"]; n = l1[f"vanilla_{L}"]["n_has_pair"]
            return {k: d[k] / n * 100 for k in HP_ORDER}
        d = l2[f"phase2_{L}"]["L2"]; n = sum(d.values())
        return {k: d[k] / n * 100 for k in HP_ORDER}
    def nc(m, L):
        if m == "Mem0":
            d = l1[f"vanilla_{L}"]["no_conflict"]; n = l1[f"vanilla_{L}"]["n_no_conflict"]
            return {"present": d["retrieved"] / n * 100, "missing": d["missing"] / n * 100}
        c = l2[f"phase2_{L}"]["no_conflict"]; n = c["n"]
        return {"present": c["l2_kept"] / n * 100, "missing": (n - c["l2_kept"]) / n * 100}
    _state_fig("F_L2_resolved_state", "L2 — Final context state (after resolution; Mem0 has none)", hp, nc)


def f_l1l2_hp():
    """has_pair state, L1 (retrieved) vs L2 (after resolution) side by side."""
    def hp_l1(m, L):
        t = "vanilla" if m == "Mem0" else "ours"
        d = l1[f"{t}_{L}"]["has_pair"]; n = l1[f"{t}_{L}"]["n_has_pair"]
        return {k: d[k] / n * 100 for k in HP_ORDER}
    def hp_l2(m, L):
        if m == "Mem0":  # no query-time resolution -> L2 == L1
            d = l1[f"vanilla_{L}"]["has_pair"]; n = l1[f"vanilla_{L}"]["n_has_pair"]
        else:
            d = l2[f"phase2_{L}"]["L2"]; n = sum(d.values())
        return {k: d[k] / n * 100 for k in HP_ORDER}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    _stacked(axes[0], hp_l1, HP_ORDER, HP_COL, "L1 — Retrieved (before resolution)")
    _stacked(axes[1], hp_l2, HP_ORDER, HP_COL, "L2 — Final context (after resolution)")
    axes[0].set_ylabel("Share of has_pair queries (%)")
    fig.suptitle("Conflict queries: context state before vs after resolution", fontsize=12.5, y=1.0)
    h = [plt.Rectangle((0, 0), 1, 1, color=HP_COL[k]) for k in HP_ORDER]
    fig.legend(h, [HP_LAB[k] for k in HP_ORDER], fontsize=8.5, ncol=4,
               loc="upper center", bbox_to_anchor=(0.5, 0.05), frameon=False)
    fig.subplots_adjust(bottom=0.2, top=0.86)
    save(fig, "F_L1L2_haspair_compare")


if __name__ == "__main__":
    print("generating figures ->", FIG)
    f1(); f2(); f3(); f4(); f6(); f6_overall(); f_l1(); f_l2(); f_l1l2_hp()
