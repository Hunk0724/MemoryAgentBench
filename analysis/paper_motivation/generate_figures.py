"""
Generate paper-quality figures for the motivation section.

Outputs PNGs to figures/.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BASE = Path("/home/yhchiang/MemoryAgentBench")
OUT = Path(__file__).parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.size": 11,
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.linestyle": ":",
    "grid.alpha": 0.4,
})


# ---------- Fig 1: SH vs MH drop ----------
def fig1_sh_mh_drop():
    systems = [
        ("HippoRAG-v2 ×\nGPT-4o-mini", 69, 11),
        ("HippoRAG-v2 ×\nGemini orig", 77, 22),
        ("HippoRAG-v2 ×\nGemini modified", 96, 23),
        ("Mem0 OOB ×\nGPT-4o-mini", 15, 1),
        ("Mem0 customized ×\nGemini", 77, 43),
        ("Zep ×\nGPT-4o-mini", 70, 28),
        ("Zep × Gemini\ninference", 79, 8),
    ]
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(systems))
    w = 0.38
    sh = [s[1] for s in systems]
    mh = [s[2] for s in systems]
    bars1 = ax.bar(x - w/2, sh, w, label="FC-SH", color="#4C9AFF")
    bars2 = ax.bar(x + w/2, mh, w, label="FC-MH", color="#FF6B6B")
    for i, (s, h, m) in enumerate(systems):
        ax.text(i - w/2, h + 1, f"{h}", ha="center", fontsize=9)
        ax.text(i + w/2, m + 1, f"{m}", ha="center", fontsize=9)
        ax.annotate(f"−{h-m}pp", xy=(i, max(h, m) + 6), ha="center",
                    fontsize=9, color="#444", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([s[0] for s in systems], fontsize=9)
    ax.set_ylabel("Exact Match (%)")
    ax.set_title("FC-SH vs FC-MH performance — every system × LLM combo drops ≥34pp",
                 fontsize=12, pad=15)
    ax.set_ylim(0, 110)
    ax.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(OUT / "fig1_sh_mh_drop.png", dpi=150)
    plt.close()
    print(f"Wrote {OUT / 'fig1_sh_mh_drop.png'}")


# ---------- Fig 2: Noise tolerance (Sim-OB-grad mixed pool vs NC-grad new-only) ----------
def fig2_simob_grad():
    data = json.load(open(BASE / "analysis/results/diagnostic/sim_ob_grad_results.json"))
    nc_data = json.load(open(BASE / "analysis/results/diagnostic/nc_grad_results.json"))
    from collections import defaultdict
    g = defaultdict(list)
    for r in data:
        g[(r["source"], r["noise_level"])].append(r["exact_match"])
    nc_g = defaultdict(list)
    for r in nc_data:
        nc_g[(r["source"], r["noise_level"])].append(r["exact_match"])

    levels_full = [10, 50, 100, 200, 455]
    levels_nc = [10, 50, 100, 200]
    random_em = [sum(g[("random", k)]) / len(g[("random", k)]) * 100 for k in levels_full]
    ppr_em = [sum(g[("ppr-nearby", k)]) / len(g[("ppr-nearby", k)]) * 100 for k in levels_full]
    nc_ppr_em = [sum(nc_g[("ppr-nearby", k)]) / len(nc_g[("ppr-nearby", k)]) * 100 for k in levels_nc]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(levels_full, random_em, marker="o", linewidth=2.5, color="#4C9AFF",
            label="random distractors (mixed old+new pool)", markersize=10)
    ax.plot(levels_full, ppr_em, marker="s", linewidth=2.5, color="#FF6B6B",
            label="PPR-nearby (mixed old+new pool)", markersize=10)
    ax.plot(levels_nc, nc_ppr_em, marker="^", linewidth=2.5, color="#5BC85B",
            label="PPR-nearby (NEW-ONLY pool, no conflicts) ★", markersize=11)
    for x, y in zip(levels_full, random_em):
        ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=9, color="#2A6FB5")
    for x, y in zip(levels_full, ppr_em):
        ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                    xytext=(0, -16), ha="center", fontsize=9, color="#B53A3A")
    for x, y in zip(levels_nc, nc_ppr_em):
        ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=9, color="#3A7E3A", fontweight="bold")
    # Annotate the 29pp gap at k=100
    ax.annotate("", xy=(100, 90), xytext=(100, 61),
                arrowprops=dict(arrowstyle="<->", color="#666", lw=1.8))
    ax.text(115, 75, "+29pp\nfrom removing\nold facts in pool", fontsize=9, color="#444",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFAE0", edgecolor="#D4A017"))
    ax.set_xlabel("# distractor facts added on top of N chain GT facts (k)")
    ax.set_ylabel("FC-MH Exact Match (%)")
    ax.set_xscale("log")
    ax.set_xticks(levels_full)
    ax.set_xticklabels(levels_full)
    ax.set_title("LLM tolerates pure new-fact noise (NC-grad ≥90%);\ncliff in mixed pool driven by OLD facts (cross-question conflict pairs)",
                 fontsize=11, pad=15)
    ax.legend(loc="lower left", fontsize=9)
    ax.set_ylim(0, 100)
    plt.tight_layout()
    plt.savefig(OUT / "fig2_simob_grad_noise.png", dpi=150)
    plt.close()
    print(f"Wrote {OUT / 'fig2_simob_grad_noise.png'}")


# ---------- Fig 5b: OA2 prompt ablation ----------
def fig5b_oa2_ablation():
    variants = [
        ("V1 orig", "orig", "orig", 55, "control"),
        ("V2", "modified ★", "orig", 81, "instruction-only"),
        ("V3", "orig", "modified ★", 75, "demo-only"),
        ("V4 modified", "modified ★", "modified ★", 83, "both (full)"),
    ]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(variants))
    colors = ["#9CB3D1", "#5BC85B", "#FFA94D", "#3B7DD8"]
    bars = ax.bar(x, [v[3] for v in variants], width=0.55, color=colors,
                  edgecolor="#333", linewidth=0.8)
    for i, (n, ins, demo, em, lbl) in enumerate(variants):
        ax.text(i, em + 2, f"{em}%", ha="center", fontsize=12, fontweight="bold")
        ax.text(i, 8, f"system:\n{ins}", ha="center", fontsize=9, color="#222")
        ax.text(i, 25, f"one-shot:\n{demo}", ha="center", fontsize=9, color="#222")
    # Δ vs orig
    for i, (n, ins, demo, em, lbl) in enumerate(variants):
        if i > 0:
            d = em - 55
            ax.text(i, em + 8, f"+{d}pp", ha="center", fontsize=10, color="#5BC85B", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{v[0]}\n({v[4]})" for v in variants], fontsize=10)
    ax.set_ylabel("OA2 FC-MH Exact Match (%)")
    ax.set_ylim(0, 100)
    ax.set_title("OA2 prompt ablation — instruction (+26pp) and demo (+20pp) each unlock most of +28pp; partially redundant",
                 fontsize=11, pad=15)
    plt.tight_layout()
    plt.savefig(OUT / "fig5b_oa2_ablation.png", dpi=150)
    plt.close()
    print(f"Wrote {OUT / 'fig5b_oa2_ablation.png'}")


# ---------- Fig 3: FC-MH performance ladder (decomposition) ----------
def fig3_ladder():
    # orig prompt regime
    items = [
        ("A1\nbaseline", 20, "with conflict\n+ 6k noise", "#FF6B6B"),
        ("NC orig\n(remove all olds)", 60, "no conflict\n+ 6k noise", "#FFA94D"),
        ("Sim-OB orig\n(chain only)", 97, "no conflict\n+ no noise", "#A0E0A0"),
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(items))
    bar = ax.bar(x, [i[1] for i in items], color=[i[3] for i in items], width=0.55)
    for i, (lbl, em, sub, c) in enumerate(items):
        ax.text(i, em + 2, f"{em}%", ha="center", fontsize=12, fontweight="bold")
        ax.text(i, em / 2, sub, ha="center", fontsize=9, color="#333")
    # arrows annotating gap
    ax.annotate("", xy=(0.5, 60), xytext=(0.5, 20),
                arrowprops=dict(arrowstyle="<->", color="#666", lw=2))
    ax.text(0.7, 40, "+40pp\nconflict\nhandling loss", fontsize=10, color="#666")
    ax.annotate("", xy=(1.5, 97), xytext=(1.5, 60),
                arrowprops=dict(arrowstyle="<->", color="#666", lw=2))
    ax.text(1.7, 78, "+37pp\n6k retrieval\nnoise loss", fontsize=10, color="#666")
    ax.set_xticks(x)
    ax.set_xticklabels([i[0] for i in items], fontsize=10)
    ax.set_ylabel("FC-MH Exact Match (%)")
    ax.set_ylim(0, 110)
    ax.set_title("FC-MH bottleneck decomposition (Gemini orig prompt) — two independent layers",
                 fontsize=11, pad=15)
    plt.tight_layout()
    plt.savefig(OUT / "fig3_ladder_decomposition.png", dpi=150)
    plt.close()
    print(f"Wrote {OUT / 'fig3_ladder_decomposition.png'}")


# ---------- Fig 4: Detection × Answer cascade by num_hops ----------
def fig4_cascade():
    cascade = json.load(open(BASE / "analysis/experiments/2026-05-03_writetime_querytime_eval/results/cascade_by_hops.json"))
    rows = cascade["rows"]
    from collections import defaultdict
    def bucket(x):
        if x == 1.0: return "all"
        if x > 0:    return "partial"
        return "none"

    agg = {"mem0": defaultdict(list), "zep": defaultdict(list)}
    for r in rows:
        nh = r["num_hops"]
        for sys in ("mem0", "zep"):
            b = bucket(r[f"{sys}_detect_pct"])
            agg[sys][(nh, b)].append(r[f"{sys}_em"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    hops = [2, 3, 4]
    buckets = ["all", "partial", "none"]
    bcolors = {"all": "#5BC85B", "partial": "#FFC75F", "none": "#FF6B6B"}
    blabels = {"all": "all detected", "partial": "partial", "none": "none detected"}
    width = 0.25

    for axi, sys in enumerate(["mem0", "zep"]):
        ax = axes[axi]
        for j, b in enumerate(buckets):
            xs, ems, ns = [], [], []
            for nh in hops:
                grp = agg[sys][(nh, b)]
                if grp:
                    xs.append(nh + (j - 1) * width)
                    ems.append(sum(grp) / len(grp) * 100)
                    ns.append(len(grp))
                else:
                    xs.append(nh + (j - 1) * width)
                    ems.append(0); ns.append(0)
            bars = ax.bar(xs, ems, width, color=bcolors[b], label=blabels[b],
                          edgecolor="#333", linewidth=0.5)
            for x, em, n, bar in zip(xs, ems, ns, bars):
                if n > 0:
                    correct = round(em / 100 * n)
                    # Show count fraction prominently, % secondary
                    label = f"{correct}/{n}"
                    pct_label = f"({em:.0f}%)"
                    # Small sample warning
                    fontsize = 9 if n >= 10 else 8
                    weight = "bold" if n >= 10 else "normal"
                    color = "#222" if n >= 10 else "#a05000"  # orange-ish for small n
                    ax.text(x, em + 2, label, ha="center", fontsize=fontsize, fontweight=weight, color=color)
                    ax.text(x, em + 8, pct_label, ha="center", fontsize=8, color="#666")
                    if n < 10:
                        ax.text(x, em / 2 if em > 10 else em + 14, "★", ha="center",
                                fontsize=11, color="#FFA94D")
        ax.set_xticks(hops)
        ax.set_xticklabels([f"{h}-hop" for h in hops])
        ax.set_xlabel("num_hops")
        ax.set_title(f"{sys.capitalize()} cascade", fontsize=11)
        ax.set_ylim(0, 100)
        if axi == 0:
            ax.set_ylabel("E2E Exact Match (%)")
            ax.legend(loc="upper right")
        # Caveat note
        ax.text(0.02, 0.97,
                "★ small sample (n<10):\n  each correct answer ≈ ±10pp",
                transform=ax.transAxes, fontsize=8, verticalalignment="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF8E0", edgecolor="#D4A017"))

    fig.suptitle("Detection × Answer cascade — counts shown as correct/total; small samples flagged",
                 fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(OUT / "fig4_cascade_by_hops.png", dpi=150)
    plt.close()
    print(f"Wrote {OUT / 'fig4_cascade_by_hops.png'}")


# ---------- Fig 5: Trailer effect across cleanliness ----------
def fig5_trailer():
    methods = [
        ("A1", 20, 23, "very noisy +\nwith conflict"),
        ("PAT", 36, 48, "mid-noisy +\nsoft labels"),
        ("NC", 60, 78, "clean conflict +\nheavy removal"),
        ("OA2", 55, 83, "clean conflict +\n6k intact"),
        ("Sim-OB", 97, 98, "cleanest\n(saturated)"),
    ]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(methods))
    w = 0.38
    orig = [m[1] for m in methods]
    mod = [m[2] for m in methods]
    deltas = [m[2] - m[1] for m in methods]
    ax.bar(x - w/2, orig, w, label="Orig prompt", color="#9CB3D1")
    ax.bar(x + w/2, mod, w, label="Modified prompt (with trailer)", color="#3B7DD8")
    for i, (m, o, mo, _) in enumerate(methods):
        ax.text(i - w/2, o + 1, f"{o}", ha="center", fontsize=9)
        ax.text(i + w/2, mo + 1, f"{mo}", ha="center", fontsize=9)
        d = deltas[i]
        clr = "#5BC85B" if d > 5 else ("#FFA94D" if d > 0 else "#888")
        ax.annotate(f"+{d}pp" if d >= 0 else f"{d}pp",
                    xy=(i, max(o, mo) + 7), ha="center", fontsize=11, fontweight="bold", color=clr)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{m[0]}\n({m[3]})" for m in methods], fontsize=9)
    ax.set_ylabel("FC-MH Exact Match (%)")
    ax.set_title("Trailer (per-hop chain prompt) effect: inverted-U with cleanliness — most useful at OA2 (+28pp)",
                 fontsize=11, pad=15)
    ax.set_ylim(0, 115)
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(OUT / "fig5_trailer_effect.png", dpi=150)
    plt.close()
    print(f"Wrote {OUT / 'fig5_trailer_effect.png'}")


def main():
    fig1_sh_mh_drop()
    fig2_simob_grad()
    fig3_ladder()
    fig4_cascade()
    fig5_trailer()
    fig5b_oa2_ablation()


if __name__ == "__main__":
    main()
