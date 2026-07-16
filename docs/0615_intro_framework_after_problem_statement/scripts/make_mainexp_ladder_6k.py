#!/usr/bin/env python3
"""F_mainexp_ladder_6k — 主實驗折線圖(current data):KU 正確率 x backbone x method-ladder.

依 experiment_prove_main_claim.md 的 ladder 設計:
  linestyle 編碼「KU 決策範式」——
    solid  = query-time 確定性(ours main / ours struct = Q-det)
    dashed = query-time 但 LLM 做決策(p3-only = Q-llm, LLM identity)
    dotted = write-time LLM commit(mem0 / Zep = W-llm)
一眼讀出:solid 線在弱端仍高、dotted/dashed 線在弱端崩 → C0(ours vs write-time)
與 C1(確定性 vs query-time-LLM)同框呈現。

y = has_pair Exact-Match (%),N=74 @ 6k。數字來源:
results/objective_data_consolidated.md §3 Table B(canonical)。
struct / p3-only 於 gpt-4.1-mini 尚未跑(future)→ 該點留 NaN、線自然斷。

⚠ 誠實 caveat(寫進 caption):x 軸前 4 tier 為 Gemma3(per-backbone extraction)、
後 2 tier 為 GPT;跨 backbone 絕對值混抽取品質,承重點為「同 backbone 內 gap 趨勢」。
"""
import os
import numpy as np
import matplotlib.pyplot as plt

BACKBONES = ["gemma3\n-1B", "gemma3\n-4B", "gemma3\n-12B", "gemma3\n-27B",
             "gpt-4o\n-mini", "gpt-4.1\n-mini"]
N = 74  # has_pair @ 6k
NAN = np.nan

# 顏色編碼「陣營」:藍=ours(query-time 確定性,高)、橘=query-time 但 LLM 決策、
# 暖色(紅/紫)=write-time LLM commit(弱端崩)。linestyle 為冗餘編碼(黑白也可辨)。
# (label, hits[6], color, linestyle, marker)
SERIES = [
    ("ours (main): query-time struct + identity + argmax",
     [25, 54, 73, 70, 69, 66], "#1a4fa0", "-",  "o"),   # deep blue
    ("ours (struct): query-time deterministic [Q-det]",
     [29, 54, 73, 65, 67, NAN], "#4fa3d1", "-",  "s"),   # light blue
    ("ours(LLM): query-time, LLM decides [Q-llm]",
     [ 7, 26, 46, 27, 71, NAN], "#e69f00", "--", "^"),   # amber
    ("mem0: write-time destructive commit [W-llm]",
     [ 0,  0, 44, 36, 34, 56], "#d1495b", ":",  "X"),   # crimson
    ("Zep: write-time labeling commit [W-llm]",
     [12, 17, 43, 35, 46, 46], "#8e5ca8", ":",  "D"),   # purple
]

fig, ax = plt.subplots(figsize=(9.2, 5.6))
x = np.arange(len(BACKBONES))

for label, hits, color, ls, mk in SERIES:
    y = [100.0 * h / N if not (isinstance(h, float) and np.isnan(h)) else np.nan
         for h in hits]
    ax.plot(x, y, ls=ls, color=color, marker=mk, markerfacecolor=color,
            markeredgecolor="white", markersize=8.5, linewidth=2.4,
            markeredgewidth=1.0, label=label, zorder=3, clip_on=False)

# --- axes ---
ax.set_xticks(x)
ax.set_xticklabels(BACKBONES, fontsize=9.5)
ax.set_xlim(-0.25, len(BACKBONES) - 0.75)
ax.set_ylim(0, 105)
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("has_pair Exact-Match (%)   ↑", fontsize=11)
ax.set_xlabel("Backbone   (weak → strong judgment)", fontsize=11)
ax.yaxis.grid(True, color="#DDDDDD", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

# --- family band (Gemma3 | GPT) : honest extraction caveat ---
# 淺灰底色帶區隔兩個 backbone 家族(中性灰 → 黑白印出仍可辨,不搶 5 條線的色彩編碼)。
ax.axvspan(-0.25, 3.5, facecolor="#000000", alpha=0.045, zorder=0)      # Gemma3 側(淡灰)
ax.axvline(3.5, color="#BBBBBB", linewidth=0.9, linestyle=(0, (2, 2)), zorder=1)
ax.text(1.5, 103.5, "Gemma3  (per-backbone extraction)", ha="center",
        va="bottom", fontsize=8.2, color="#777777")
ax.text(4.5, 103.5, "GPT", ha="center", va="bottom", fontsize=8.2, color="#777777")

ax.legend(loc="lower right", fontsize=8.4, frameon=True, framealpha=0.95,
          handlelength=2.8, borderpad=0.6, labelspacing=0.4)

fig.tight_layout()

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
OUTDIRS = [
    os.path.join(BASE, "figures_current"),
    os.path.join(BASE, "paper_current", "figures"),
]
for d in OUTDIRS:
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"F_mainexp_ladder_6k.{ext}")
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print("wrote", p)
