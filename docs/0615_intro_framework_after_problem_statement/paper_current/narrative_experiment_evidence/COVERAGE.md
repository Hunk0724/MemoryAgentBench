# FC-SH 實驗 coverage 矩陣 — 「我們手上有哪些牌」

> **用途**:寫論述前一眼看清每個 backbone 在哪些長度跑過哪些 method。每格 N=100(has_pair 分母 6k=74 / 32k=65 / 64k=66)。
> **來源**:gpt backbones = 本機 `outputs/` 掃描(2026-07-07);gemma = GX10 跑、[`../results/weak_model_6k_analysis.md §1`](../results/weak_model_6k_analysis.md)。數字驗證見 [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md)。

**Method 代號**:`main`=struct+P3+argmax(無 P5,**論文主 method**) · `full`=+P5(appendix) · `struct`=struct-only · `p3only`=P3-only(無 (S,P)) · `b`=mem0+P1(held-fixed extraction + destructive) · `van`=vanilla mem0(native) · `Zep` · `LCA`=long-context 無記憶

---

## §1 Coverage 矩陣(backbone × 長度 → 已跑 method)

| Backbone(tier) | 6k | 32k | 64k |
|:--|:--|:--|:--|
| **gemma3-1B**(weak/GX10) | main·struct·p3only·b·Zep(**5**,無 van) | — | — |
| **gemma3-4B** | main·struct·p3only·b·van·Zep(**6 全**) | — | — |
| **gemma3-12B** | main·struct·p3only·b·van·Zep | — | — |
| **gemma3-27B** | main·struct·p3only·b·van·Zep | — | — |
| **gpt-4o-mini**(mid / **主 regime**) | **8 全**(main·full·struct·p3only·b·van·Zep·LCA) | **8 全** | **8 全** |
| **gpt-4.1-mini**(strong) | main·full·b·Zep(**4**) | main·b·Zep(**3**) | main·full·struct·p3only·b·Zep(**6**) |
| gpt-4o(額外 / 探索) | — | — | main·full(僅 2) |

> **weak-tier caveat**:gemma 為 per-backbone extraction(每 size 用自己的 gemma 抽取);同 backbone 內 method 比較公平,跨 backbone 絕對值混抽取品質。詳見 weak_model_6k_analysis §0。

---

## §2 支撐哪些論述(現有 coverage 夠不夠)

| 論述節點 | 需要的 coverage | 現況 | 夠嗎 |
|:--|:--|:--|:--:|
| **E-A 頭條**(6k backbone spectrum) | 6-tier × {main, b, Zep} @ 6k | ✅ 1B→4.1-mini 全到齊 | 🟢 |
| **E-A 誠實揭露**(§4.3.4 Table 4c) | main/b × {4o,4.1} × 3 長度 | ✅ **4.1×32k b 已補**(gap 三點完整) | 🟢 |
| **E-B 機制**(pool-state cross-tab) | 4o 全 method × 3 長度 + 4.1 64k | ✅ 完整 | 🟢 |
| **E-C ablation**(struct/P3/P5) | ours 4 變體 × backbone | ✅ 4o 三長度全、gemma 6k 全、4.1 64k 全 | 🟢 |
| **E-D 責任邊界**(case study) | 跨 backbone 同題 trace | ✅ gemma 6k + 4o/4.1 64k | 🟢 |

**結論:四條論述線的核心 coverage 全部齊了。** 剩餘缺格皆 optional 加固,不擋論述。

---

## §3 剩餘缺格(optional,列 future work / 不擋投稿)

| 缺格 | 影響 | 優先序 |
|:--|:--|:--|
| gemma 32k / 64k(weak 長 context) | E-A robustness(6k 已足支撐核心) | 低(GX10 wave 暫停) |
| gpt-4.1-mini 6k/32k ablation(struct·p3only) | E-C 於強端 6k/32k 更完整(64k 已有全 ablation) | 低 |
| gpt-4.1-mini full(+P5)× 32k | §4.5.3 P5 光譜(6k/64k 已有) | 低 |
| vanilla / LCA × gpt-4.1-mini | 次要 baseline(mid tier 已完整代表) | 低 |
| FC-**MH**(multi-hop) | 泛化到多跳 | 另議 |

---

*更新於 2026-07-07(gpt-4.1-mini × 32k mem0+P1 = 53/65 補完後)。*
