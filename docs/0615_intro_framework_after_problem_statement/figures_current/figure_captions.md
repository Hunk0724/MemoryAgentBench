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

### F_struct_backbone_6k —(weak-model regime:方法端 vs reader 端)★ 核心
**Figure.** FC-SH 6k has_pair,純 **structural(S,P)+deterministic-temporal**(關掉 LLM grouping 與 conflict-type)在四種 gemma backbone(1B/4B/12B/27B)上的兩個並排量(分母 = 74 has_pair):**Resolution Accuracy(方法端)** = resolved pool 是否隔離 NEW 版(GT_new 在、GT_old 不在,subject-scoped word-boundary),與 **End-to-End EM(方法 + reader)** = 最終答案命中 GT。用長條(非折線):x 軸為離散 model checkpoint、關係非單調,折線會誤示平滑趨勢。(4o-mini EM 參考 = 93%,其 struct store 在 Mac、Resolution 本機不可算,故略去改記於此。) **數字為新 code:normalize L1/L2 + fact-level ordinal。** **Observation.** 方法端 Resolution 隨 backbone **單調上升並在 12B→27B 飽和(58→65→92→93%,27B 不退化、甚至最高)**;End-to-End EM 則**先升後於 27B 下滑(38→73→99→88%)**。三個 regime:(i) **1B** reader 太弱,pool 對了仍答錯(drag 16 ≫ rescue 1)→ EM ≪ Res;(ii) **4B–12B** reader 忠實且用世界知識補救(rescue +7 / +5)→ EM ≥ Res,12B 近乎滿分(73/74、overall 99/100);(iii) **27B** reader 以參數先驗 **override 正確 pool**(drag 7)→ 是唯一 EM < Res 且低於 12B 之處。 **Implication.** KU 的「方法端」貢獻(structural resolution)**backbone-robust**——backbone ≥12B 即近上限、且不因更大模型而退化;端到端在 27B 的下滑**純屬 reader override**(參數知識壓過「只用 pool」指令),非方法失效。支撐核心主張:結構化 (S,P)+temporal 錨定是穩健的 KU backbone,把最終判斷全交給更強 LLM 反而引入 override 風險。

### F_L1_state_pie —(檢索層細分 / 支撐,可進 appendix)
**Figure.** 三種 vector-memory 方法在 has_pair 題的 L1 retrieved(top-100)版本-狀態分布(both / new_only / old_only / neither),跨四種長度。**ours 幾乎全為 both(新版可得);mem0+ours storage 有約一半落入 old_only / neither(新版已遺失)且隨長度增加;native mem0 全為 neither。** 破壞性 write-time 更新使新版在 retrieval 階段即已不可得。註:Zep 採 graph + raw-episode 的多顆粒儲存、兩版本多半皆保留為 valid edge,無法嚴謹對應 GT 新/舊,故此 retrieval-state 診斷僅比較 vector-memory 方法,Zep 改以 overall EM(Table 1)比較。
