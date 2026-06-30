# 2. Related Work

## 2.1 主動派對知識更新的解析方法 (Proactive Approaches to Knowledge Update)

主動派 (proactive) 方法嘗試在寫入時就解析潛在的版本衝突，以免衝突累積於記憶庫中。在這個典範下，主要可區分為兩個次類別，差別在於 **LLM 與實際記憶變更 (mutation) 的角色關係如何安排**。

**耦合更新 (Coupled Update)**。在耦合更新設計中——以 Mem0 [5] 與 LightMem [3] 為代表——一次 LLM 呼叫同時決定操作類型 (ADD / UPDATE / DELETE / NOOP) 並觸發其對記憶庫的執行。Mem0 直接實作此模式:LLM 接收一筆新進事實連同語意相關的既有 entries，輸出操作標籤，系統據此原地執行——UPDATE 對應 vector 與 payload 的就地覆寫 (in-place overwrite)，DELETE 對應硬刪。LightMem 沿用相同的耦合模式，但加入睡眠時批次 (sleep-time batching) 機制:測試時新 entries 帶時間戳直接寫入、不即時做跨筆判斷;週期性離線批次再呼叫 LLM 對既有 entries 決定 UPDATE / DELETE / IGNORE。關鍵在於，兩種方法共享同一個架構承諾——LLM 同時擔任判斷者與執行者 (judge and operator)——並因此皆對記憶庫做破壞性 mutation (原地 vector 覆寫或硬刪)。

**解耦更新 (Decoupled Update)**。解耦更新設計把 LLM 的角色從實際記憶變更中分離出來。Zep [6] 是代表方法，它把 LLM 的工作限制在僅輸出類別性關係標籤 (例如 *contradicts*、*duplicates*)，描述新進 entry 與一組候選既有 entries 的關係;確定性系統 (deterministic system) 隨後執行實際的記憶變更，透過在受影響的 edges 上設定雙時序失效時間戳 (bi-temporal invalidation timestamps:*invalid_at* 與 *expired_at*) 來實踐。這個解耦具有明顯的架構優點:edge 本體在儲存層保留 (mutation 在儲存層面是非破壞性的)，執行層則完全是確定性的 (消除了 mutation 步驟的隨機性)。然而，上游 LLM 輸出的標籤仍是系統行為的唯一驅動因素。若 LLM 把一對「相關但不矛盾」(related but not contradictory) 的記憶誤標為 *contradicts*，確定性系統便會忠實地對較舊的 edge 設定失效時間;一旦 *invalid_at* 設定後便不會再被檢視——使得這個誤判在檢索層面實際上仍是不可逆的。

**共通的結構性限制**。無論 LLM 是擔任判斷者與執行者 (耦合)，或僅作為標籤產生者 (解耦)，主動派方法都共享同一個結構性性質:任一事實的記憶狀態，被綁定在單一次寫入時的 LLM 判斷上。LightMem 自己在 §5.6 中明確承認這點:「*LLM 可能會將相關但並不矛盾的資訊誤判為衝突，進而刪除較舊的記憶項目，造成不可逆的資訊損失*」[3, Sec. 5.6]。這個脆弱性在受限部署 (constrained deployment) 場景下會被放大——較小的不可微調 LLM 產生較低品質的判斷，卻仍被不可逆地寫入。根本原因不在於 LLM 的準確度，而在於架構模式本身。

我們因此主張將 KU 解析從單一次寫入時的提交，推遲到查詢時衝突解析 (query-time conflict resolution)。我們從 RAG 文獻取經——query-time 衝突解析在 RAG 領域已被視為一個獨立的研究典範，並發展出我們可以借鑑、改造後應用至記憶累積設定的機制。

---

## 2.2 RAG 中的知識衝突解析 (Knowledge Conflict Resolution in RAG)

雖然 query-time 衝突解析在記憶 agent 領域尚未被系統性地研究，但在更廣泛的檢索增強生成 (Retrieval-Augmented Generation, RAG) 社群中，這已是一個成熟的典範。代表性的方法都採用相同操作框架:在查詢時刻處理檢索回的候選集——識別哪些 retrieved passages 一致、哪些衝突、哪些無關——然後把精煉過的 context 送給推論 LLM。

**段落層級的「群聚與分離」模式 (Cluster-and-separate at the passage level)**。Astute RAG [17] 是這個模式中最明確的具體化。它的迭代式知識整合 (iterative knowledge consolidation) 程序透過 LLM 呼叫，把一致的 retrieved passages 群聚 (cluster) 起來、把衝突的 passages 分到不同群 (separate)、把無關內容過濾掉。在每個一致性群組內，產生一個候選答案;最終答案則透過 source-aware 的比較選出——比較對象是 LLM 的內部知識 (internal knowledge) 與外部檢索回的知識。此程序可迭代多輪直到整合結果穩定。

**三元組層級的衝突解析 (Triple-level conflict resolution)**。TruthfulRAG [18] 則在更細的粒度上運作。它不把每個 retrieved passage 當作原子單位，而是從檢索內容中抽取 (head, relation, tail) 三元組，並建構一個 query-aware 的知識圖譜。衝突偵測接著在這個圖譜上的 reasoning paths 上運作，透過熵 (entropy) 為基礎的過濾找出哪些 paths 對 LLM 的參數化信念形成正當挑戰。這個方法展示了一個重要洞察:**三元組這種事實層級的表示法，是 query-time 衝突解析自然的粒度**——這個觀察被我們納入了自己的設計中。

**領域共通的設定假設**。不論機制有何差異，這些 RAG 方法共享同一組操作設定:每個 query 觸發一輪 single-shot retrieval 對 (largely) 靜態的 corpus 進行;跨 query 不維持任何持久狀態 (no persistent state)。它們處理的衝突，本質上是與使用者互動歷史無關的跨來源不一致——例如不同 source 之間的矛盾，或 LLM 參數化知識與外部檢索之間的衝突。

**與記憶累積設定的根本差異**。記憶增強 Agent 面對的問題在結構上本質不同。記憶庫並非靜態 corpus，而是一個持續成長的、儲存使用者特定事實的儲存空間;衝突主要來自同一事實在時間上的版本漂移——使用者隨時間更新自己的資訊。兩個推論隨之而來:第一，**真正需要解析的不是「哪個來源較可信」，而是「同一事實的哪個版本最新」**——這引入了 single-shot RAG 方法未處理的時序維度。第二，記憶的持久本質意味著:某個 query 上的解析決策不會綁定後續所有 query;每個 query 對「最新版本」的判斷可能依其涉及的事實而不同。

我們透過兩個機制，將群聚與分離的典範改造、移植到記憶累積設定:**事實識別分群 (identity grouping)** 識別出檢索回的哪些候選描述同一事實的不同版本 (類比於 RAG 的一致性群聚，但 anchored on 事實識別而非資訊一致性);**時序解析 (temporal resolution)** 對每個分群選出最新版本 (以寫入時序 ordering 取代 source-credibility selection)。組合起來形成一個 query-time KU 解析機制，在結構上汲取 RAG 衝突解析的靈感，同時回應 KU 本質上時序有效性的特性。

---

## 2.3 知識更新評估基準 (Knowledge Update Evaluation Benchmarks)

為了實證評估 KU，我們採用長期記憶 agent 領域中既有的 benchmarks。這些 benchmarks 可大致分為兩類，差別在於衝突密度 (conflict density) 與 ground truth 標註的粒度，這兩個性質會影響它們能有效壓力測試哪些 KU 機制面向。

**使用者資訊 KU、衝突稀疏 (Sparse conflict)**。第一類 benchmarks 評估 KU 於使用者特定事實——個人資訊、屬性、生活事件，使用者陳述後又有修正。LongMemEval [9] 在約 115K tokens 的延伸對話歷史中建立 78 道 KU 問題，每題鎖定一個使用者屬性的變動。MemBench [10] 的 FM-ku 子集採用類似設計，涵蓋使用者屬性隨時間的變動。BEAM [11] 則引入 Information Update 能力，跨多領域對話、context 長度延伸到 1M+ tokens。這些 benchmarks 的結構共通點是:**每個 query 鎖定一個特定事實變動、其餘對話內容對該事實是中性 context**;衝突密度低，餘下對話對該題的解析來說基本是 clean、無干擾的。因此這些 benchmarks 主要壓力測試的是 retrieval——相關的「變動前/變動後」mentions 能否被檢索回——而非檢索成功後的 KU 解析機制。

**世界事實 KU、衝突高密度 (High conflict density)**。MemoryAgentBench [7] 中的 FactConsolidation 子集 (以下簡稱 FC) 採取了不同的設計選擇。它的對話建構自 MQUAKE [19] 的 counterfactual 編輯對 (counterfactual edit pairs)——一個真實世界事實 (例如某國的元首、某地區使用的語言) 跟一個被編輯的反事實版本配對。FC 把這些編輯密集地組合於整個對話中，使整段對話成為其 prompt 所描述的「*帶有大量新事實的知識池 (a knowledge pool with lots of new facts)*」。雖然其底層事實是世界知識而非使用者特定資訊，KU 的解析邏輯在結構上完全等價——較新的版本取代較舊的——而高衝突密度直接對 KU 解析機制 (而不僅是 retrieval) 施加壓力。

我們採用 FactConsolidation 的單跳 (single-hop) 子集 (FC-SH) 作為主要評估。這個選擇出於兩個考量。首先，**FC 的高衝突密度正好壓力測試我們設計的核心 contribution**:query-time 的事實識別分群與時序解析機制要在多組並存的版本對上運作，這正好暴露出解析在負荷下是否仍準確。其次，MQUAKE 的 counterfactual 結構提供**事實層級 (fact-level) 的 ground truth**——每個 instance 明確標註 *gt_new* 與 *gt_old* triples——這讓我們能對 pipeline 的不同階段 (retrieval vs resolution vs inference) 進行細粒度的失效歸因 (diagnostic attribution)。相對地，使用者資訊 KU benchmarks 僅提供 QA 層級的 ground truth，會將 retrieval 失敗與 resolution 失敗混淆在一起。本方法在使用者資訊 KU 上的泛化 (generalization to user-information KU) 留作未來工作。

---

## References (在 intro [1]–[16] 基礎上續編)

[17] F. Wang, X. Wan, R. Sun, J. Chen, and S. Ö. Arık, "Astute RAG: Overcoming imperfect retrieval augmentation and knowledge conflicts for large language models," in *Proc. 63rd Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2025.

[18] S. Liu, Y. Shang, and X. Zhang, "TruthfulRAG: Resolving factual-level conflicts in retrieval-augmented generation with knowledge graphs," in *Proc. AAAI Conf. Artif. Intell.*, 2026.

[19] Z. Zhong, Z. Wu, C. D. Manning, C. Potts, and D. Chen, "MQUAKE: Assessing knowledge editing in language models via multi-hop questions," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)*, 2023.
