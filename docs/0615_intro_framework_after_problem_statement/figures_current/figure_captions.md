# Figure captions(三段論:what / observation / implication)

> 圖面只保留 axis label + legend + data label;判讀與 implication 一律寫在 caption。
> 皆為 single deterministic run(gpt-4o-mini, temperature 0),故無 error bar。

---

### F_robust_haspair —(主結果 / result)
**Figure.** 在 MemoryAgentBench FC-SH 的 knowledge-update(has_pair)題上,五種方法在四種 conversation-history length(6k–262k)的 exact-match accuracy。**ours 在所有長度皆最高、且幾乎不隨長度衰退(92→86→91→88%);而直接以 full context 餵 LLM 的 gpt-4o-mini 隨長度單調崩壞(88→31%),Zep 與 mem0+ours storage 居中且同樣下滑,native mem0 因幾乎抽取不到 fact 而全程接近 0。** 這顯示 ours 的 KU 正確率對 history length 具 robustness,而依賴 full-context 或 write-time 更新的方法都隨規模惡化 → 我們的設計在長對話記憶情境更具 scalability。

### F_bank_recall —(過去為何輸 / why prior approaches fail)★ 核心
**Figure.** 三種 vector-memory 方法的 memory-bank GT-recall(掃描整個 store、而非 top-k retrieval),衡量衝突 fact 的「新版本是否仍存在於記憶庫中」,對 conversation-history length 作圖。**ours 的記憶庫幾乎完整保有新版(100→92%);破壞性的 mem0+ours storage 僅存約一半且隨長度惡化(51→41%);native mem0 的庫為空(0%)。關鍵:破壞性 baseline 的 bank-level recall(L0)與其 retrieved-level recall(L1, top-100)在每個長度完全相等。** L0==L1 證明正解的遺失發生在 **write-time**(記憶庫本身就沒有新版),而非 retrieval;write-time 的破壞性 knowledge-update 一旦誤判即不可逆,任何下游 retrieval / resolution 都無法挽回——這是「忠實寫入、不在 write-time commit」的直接證據。

### F_ours_L1L2_pie —(我們為何贏 / why ours wins)★ 核心
**Figure.** ours 在 has_pair 題上,retrieval 後(L1, top-100)與 query-time resolution 後(L2, final context)的版本-狀態(version-state)分布,跨四種長度。**L1 幾乎都是 both(新舊版本皆檢索到,92–100%);經 query-time 的 identity grouping → conflict-type 分類 → temporal resolution 後,L2 大多收斂為 new_only(70–86%),只保留新版。** 此圖量化了「將 knowledge-update 延遲到 query-time」的價值——把 both 確定性地解析成 new_only;而這是破壞性 baseline 無法做到的:它在 write-time 已刪掉一版,L1 根本沒有 both 可供解析。

### F_em_vs_ceiling —(recall 上限 vs 實際表現 / 兩道關卡)★ 核心
**Figure.** 三種 vector-memory 方法在 FC-SH has_pair 的實際 exact-match accuracy(solid, EM achieved)與 recall ceiling(dashed,衝突 fact 的新版本是否存在於最終 answer context;ours 取 query-time resolution 後的 L2,mem0 與 mem0+ours storage 無 query-time resolution 故取 retrieved L1)。**mem0+ours storage 的 EM 幾乎貼著其 ceiling(~41–51%)——它已接近自身上限,瓶頸在 ceiling(write-time 的破壞性更新使新版不在記憶庫/context),而非 inference;ours 的 ceiling 高(87–100%)且 EM 逼近之。**(native mem0 因幾乎抽取不到 fact、ceiling 與 EM 皆 ~0、不具資訊量,故此圖不列入。) 這說明:正確記憶可得(recall ceiling)是答對的必要條件、決定表現上限;能否把上限轉為正確答案則取決於 query-time resolution。ours 同時做到「保守寫入撐高 ceiling」與「query-time resolution 逼近 ceiling」,而破壞性 baseline 的低 ceiling 在 write-time 即已封死。

### F_ablation —(貢獻拆解 / additive ablation)
**Figure.** FC-SH has_pair 在 6k / 32k 的 additive ablation,逐步隔離兩個設計貢獻:(a) native mem0 → (b) 固定 ours 的 extraction + mem0 破壞性更新 → (c) ours(保守寫入 + query-time resolution)。**(a)→(b) 將 has_pair 從 0/3 提升至 46/45(忠實 extraction 讓 fact 進得了記憶庫);(b)→(c) 再從 46/45 提升至 92/86(query-time resolution 救回破壞性更新丟失的另一半)。** 兩個 delta 各對應一個貢獻;其中 +46/+41pp 純粹來自「把 KU 延到 query-time」,顯示非破壞寫入 + query-time 解析才是正確率的主要來源。

### F_L1_state_pie —(檢索層細分 / 支撐,可進 appendix)
**Figure.** 三種 vector-memory 方法在 has_pair 題的 L1 retrieved(top-100)版本-狀態分布(both / new_only / old_only / neither),跨四種長度。**ours 幾乎全為 both(新版可得);mem0+ours storage 有約一半落入 old_only / neither(新版已遺失)且隨長度增加;native mem0 全為 neither。** 破壞性 write-time 更新使新版在 retrieval 階段即已不可得。註:Zep 採 graph + raw-episode 的多顆粒儲存、兩版本多半皆保留為 valid edge,無法嚴謹對應 GT 新/舊,故此 retrieval-state 診斷僅比較 vector-memory 方法,Zep 改以 overall EM(Table 1)比較。
