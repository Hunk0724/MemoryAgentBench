Observation 與 Discussion 撰寫
一句話定位
Experiments 章節不能只列數字，要寫 observation — 從 table / figure 抽出 pattern 並給 explanation。Discussion 進一步 step back 討論 implication、limitation、failure case。

為什麼這 concept 重要
"Table 3 shows X." 這種純描述句沒有 added value — reviewer 自己會看 table。論文的價值在於作者比 reviewer 多花了 6 個月深入這個問題，能看出 reviewer 第一眼看不出的 pattern。Observation 是這層 added value 的載體。

機制 / 流程
Observation 三段式：

What：明確指出 pattern (在哪一欄、哪幾個 row、有什麼規律)
Why：給出可能的 explanation (引用 methodology 或 prior work)
Implication：這 pattern 暗示什麼 (對後續實驗、對 application)
Discussion 章節要回答的問題：

什麼 condition 下我的 method work？什麼 condition 不 work？
Failure case 長什麼樣？為什麼?
對 application practitioner 的建議是什麼？
對 follow-up research 的建議是什麼？
Discussion 比 observation 抽象一階。

好寫法 vs 壞寫法
✗ 壞 (純描述)：

「As shown in Table 3, our method achieves 92.3% on dataset A and 88.7% on dataset B. Baseline achieves 87.1% on dataset A and 85.4% on dataset B. Our method outperforms baseline on both datasets.」

— 把 table 用文字念了一遍，零 insight。

✓ 好 (observation + explanation)：

Table 3 顯示三個值得注意的 pattern：

(O1) Dataset A 上的 gain (+5.2%) 顯著大於 B (+3.3%)。我們假設這源於 A 的 class 不平衡更嚴重 (Sec. 4.1 報告 long-tail ratio 28:1 vs B 的 9:1)，而我們的 re-weighting (§3.5) 主要解的就是 long-tail 問題。我們在 §4.5 進一步控制 imbalance 後驗證此假設。

(O2) 在 input length > 512 時，baseline 與 ours 的差距開始拉大。這支持我們的 sliding-window attention design 在長序列才顯出價值；對短序列 application，預期 gain 較小。

(O3) 我們的方差 (std) 比 baseline 大 30%。這可能源於 policy network 對 random seed 敏感；建議實作時用 ensemble 或 swa。

每個 observation 都有 hypothesis、且有 follow-up 或 caveat。

Discussion 的好寫法範例：

Failure case：在 chip count > 8 的 MCM 配置上，我們的 surrogate 預測誤差超過 6%，導致 MCTS 收斂到次佳解 (Fig. 9)。原因是 GP surrogate 在高維 (>40 design variable) 不擴展；改用 deep kernel 或許可改善，留待 future work。

For practitioner：當你的 MCM 在 4-chip 以下、CFD budget 在 100-1000 次之間，我們的 pipeline 是 sweet spot；超過此範圍建議仍以 expert manual loop 為主，並用本工作 surrogate 加速初篩。

不只報好消息，也誠實談 limitation。

常見誤解
誤解 1：以為 observation 是「把數字翻譯成文字」— 錯，observation 是「在數字之上找 pattern」
誤解 2：以為承認 limitation 會被審稿人攻擊 — 錯，明寫 limitation 反而會被視為誠實；reviewer 自己找出 limitation 才危險