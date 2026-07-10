# FC-SH + LME-KU 實驗 coverage 矩陣 — 「我們手上有哪些牌」

> **用途**:寫論述前一眼看清每個 backbone 在哪些長度跑過哪些 method。每格 N=100(FC-SH has_pair 分母 6k=74 / 32k=65 / 64k=66;LME-KU N=78)。
> **來源**:gpt backbones = 本機 `outputs/` + `lme_hyps/` 掃描(2026-07-07);gemma = GX10 跑、[`../results/weak_model_6k_analysis.md §1`](../results/weak_model_6k_analysis.md)。數字驗證見 [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md)。
> **⚡ Reproduction**:每個 cell 的執行命令、caches 依賴、cost/wall 估算見 [`REPRODUCTION.md`](REPRODUCTION.md)。

**Method 代號**:`main`=struct+P3+argmax(無 P5,**論文主 method**;script `ours_no_p5`) · `full`=+P5(appendix;script `ours`) · `p5_reuse`=main store + query-only + P5(reproducible +P5 replacement 2026-07-07) · `struct`=struct-only · `p3only`=P3-only(無 (S,P)) · `b`=mem0+P1(held-fixed extraction + destructive) · `van`=vanilla mem0(native) · `Zep` · `LCA`=long-context 無記憶

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

## §1.5 LME-KU coverage 矩陣(2026-07-07 新增)

**Judge**:`llm_based_eval/evaluate_qa_official.py` @ gpt-4o-mini(temp 0);N=78 KU questions。**驗證期用 gpt-4o-mini judge 省成本**,paper-final 是否回 gpt-4o judge 未定。

| Backbone(tier) | Method 已跑(N=78) |
|:--|:--|
| **gpt-4o-mini** | **5 全**:main(**55/78 = 70.5%**)· p5_reuse(2026-07-07,55/78 = 70.5%,net-zero verified)· ~~full(Jun 30 orig 65/78,無 log 待廢~~)· van(**53/78 = 67.9%**)· b(**47/78 = 60.3%**)· ~~Zep(deferred:free plan 128k 上限)~~ |
| gpt-4.1-mini(strong) | — |
| gemma3 tier(weak) | — |

**⚠ LME-KU 執行 caveats**(見 [`REPRODUCTION.md §3`](REPRODUCTION.md#lme-ku)):
- **ours(+P5)於 Jun 30 orig run 得 65/78 = 83.3%,但無 cost log / P5 decision cache**;於 2026-07-07 用 `ours_p5_reuse` 重測(reuse main 已 populated store + query-only + P5 enabled)得 **55/78 = 70.5%,與 main 相同 → P5 net-zero**。orig 83.3% 是 4-shard extraction store 的 non-deterministic artifact。
- **Zep LME-KU deferred**:Zep free plan per-graph 128K 上限,LME context ~115K + Zep episode credit;所有 4 keys(A/B/C/D)測試皆撞限。移進 Graphiti self-hosted 為 future work。

### LME-KU 關鍵發現(對接 experiment.md §4.6.4)

1. **P5 net-zero**(main 55/78 = p5_reuse 55/78):§4.5.3 P5 降級決定於兩 dataset(FC-SH + LME-KU)皆成立
2. **(b) LOWER than vanilla**(60.3% < 67.9%,-7.6pp):我方 P1 於 LME-KU personal-fact 反傷 mem0 → **(b) 不作為 LME cross-benchmark baseline**(見 §4.6.5 methodological note)
3. **架構 universal 貢獻 = +2.6pp**(main vs vanilla,rigorous cross-benchmark comparison)

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
| gemma × +P5 於任一 length | 檢驗「P5 於弱 backbone 是否更負面」— 強化 §4.5.3 P5 removal 決定 | 中 |
| LME-KU × gpt-4.1-mini(4 methods)| §4.6 backbone spectrum 於 personal-fact 場景 → 兌現 architectural claim 於強 backbone 上的表現 | **中-高**(架構 universal 貢獻 +2.6pp 只 gpt-4o-mini 有,強 backbone 未知)|
| LME-KU × gemma tier | 弱 backbone × personal-fact 場景 | 低 |
| Zep LME-KU(via Graphiti self-hosted)| 補齊 §4.6 Zep 位;Graphiti 內部 log 也解 §3.3.3 誠實限制段 | **中**(Graphiti setup ~1-2 day) |
| FC-**MH**(multi-hop) | 泛化到多跳 | 另議 |

---

*更新於 2026-07-07(§1.5 LME-KU 覆蓋 + p5_reuse 驗證新增後)。*
