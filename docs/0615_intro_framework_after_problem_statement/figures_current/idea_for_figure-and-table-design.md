一句話定位
-----

每張 figure / table 應 **self-contained** — 讀者不看 main text 也能理解。Caption 採三段論：**what / observation / implication**。

為什麼這 concept 重要
---------------

Reviewer 第一輪 skim 論文時，至少 30% 時間花在看圖表 + caption。Figure 自身傳達的 information 決定論文 first impression。Caption 寫不全，讀者得來回切換 main text，閱讀體驗下降。

機制 / 流程
-------

**Figure 必備元素**：

*   軸標含單位 (e.g. "Latency (ms)" 不是 "Latency")
*   Legend 區隔系列、不同顏色 / marker 至少 colorblind-safe
*   誤差棒 / shaded region 標示 variance (3+ run 取 mean ± std)
*   Font size 在 print 後仍可讀 (一般 ≥ 8 pt)

**Caption 三段論**：

> **Figure N.** *\[What\]* 顯示 \[系列\] 在 \[X 軸範圍\] 上的 \[Y 變量\]。*\[Observation\]* \[系列 A\] 在 \[條件\] 下超越 \[系列 B\] 約 \[Δ\]，但在 \[條件\] 下反轉。*\[Implication\]* 暗示 \[系列 A\] 適用 \[這類場景\]，\[系列 B\] 更適用 \[另一類\]。

**Table 設計**：

*   行 / 列邏輯一致 (e.g. row = method、column = dataset/metric — 不要反過來)
*   最好成績 **bold**、次佳底線
*   ↑ / ↓ 標示方向 (higher / lower is better)
*   不要超過頁寬，超寬考慮 sideways 或拆 table

好寫法 vs 壞寫法
----------

**✗ 壞 caption (只說 what)**：

> 「Figure 3. Accuracy of different methods.」

**✓ 好 caption (三段論)**：

> **Figure 3.** *Test accuracy vs training data fraction across four methods on CIFAR-100 (5 seeds, shaded = ± 1 std).* Our method (red) matches or exceeds baselines under 100% data and shows the smallest degradation (-2.1%) at 10% data, while ResNet-50 baseline drops -8.4%. This suggests our auxiliary self-supervised loss is particularly valuable in low-data regimes.

讀者只看圖 + caption 就能掌握三件事：圖呈現了什麼、發現了什麼、有什麼意義。

**✗ 壞 table 設計**：

| Method 1 | Method 2 | Method 3 | Method 4 |
| --- | --- | --- | --- |
| 76.3 | 78.1 | 82.4 | 80.1 |

— 沒 metric、沒方向、沒 dataset、沒 std。

**✓ 好 table 設計**：

| Method | CIFAR-10 Acc ↑ | ImageNet-1K Acc ↑ | Params (M) ↓ |
| --- | --- | --- | --- |
| ResNet-50 \[He'16\] | 93.6 ± 0.2 | 76.1 ± 0.3 | 25.5 |
| ViT-B/16 \[Doso'21\] | 95.1 ± 0.1 | 77.9 ± 0.2 | 86.4 |
| **Ours** | **95.8 ± 0.2** | **78.6 ± 0.2** | **31.2** |

每個 cell 含 mean ± std，最佳 bold，方向標清楚。

常見誤解
----

*   誤解 1：以為 figure 是 main text 的 "illustration" — 錯，figure 是 first-class evidence，main text 引用 figure 而非相反
*   誤解 2：以為 caption 應該短 — 錯，技術 paper 的 caption 平均 3-5 句、占 80-150 字才算合格