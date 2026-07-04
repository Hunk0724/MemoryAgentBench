# Related Work（v2，2026-07-04，對齊 intro v5 / 無 P5 定位）

> 本章版圖設計:Related Work 只放本文**直接對話**的三條線——(2.1) 記憶系統對 KU 的處理方式(我們的對比對象)、(2.2) RAG 的查詢時知識衝突解析(我們機制的靈感來源與設定差異)、(2.3) KU 評估基準(定義本文 scope 與主評測選擇)。其餘相鄰領域(Knowledge Editing、Temporal KG、任務分解、受限部署)不開獨立小節,只在對應位置以邊界句或其他章節引用處理——詳見文末編輯註記。

---

## 2.1 記憶系統中的知識更新 (Knowledge Update in Memory-Augmented Agents)

絕大多數記憶增強 Agent 的更新機制著重於記憶的儲存、結構或組織,對 KU 採取被動 (passive) 態度——MemoryBank [12] 的遺忘曲線衰減、MemGPT [2] 與 MemoryOS [4] 的階層式分層、A-Mem [1] 的原子筆記網路,都不主動偵測新進事實與既有記憶的取代關係(詳見 Introduction)。本節聚焦於對 KU 採取主動 (proactive) 態度的方法:在任何查詢發生之前——寫入當下或離線整併時——就解析潛在的版本衝突,避免其累積於記憶庫中。依 LLM 的角色與實際記憶變更 (mutation) 之間的結構關係,主動派可分為兩個次類別。

**耦合更新 (Coupled Update)。** 以 Mem0 [5] 與 LightMem [3] 為代表:單一次 LLM 呼叫同時決定操作類型 (ADD / UPDATE / DELETE / NOOP) 並觸發其執行,LLM 同時擔任判斷者與執行者 (judge and operator)。Mem0 直接實作此模式:LLM 接收新進事實與語意相關的既有記憶,輸出操作標籤,系統就地執行——UPDATE 觸發向量與 payload 的原地覆寫、DELETE 觸發硬刪除。LightMem 依循同樣的耦合模式,但引入睡眠期批次 (sleep-time batching) 機制:測試期新記憶帶時間戳直接插入、不做即時跨筆判斷;離線批次程序週期性地喚起 LLM,對既有記憶決定 UPDATE / DELETE / IGNORE。關鍵在於,兩者共享同一個架構承諾——LLM 既判且行——因此只要 LLM 判斷如此指示,兩者都會施加破壞性變更(原地覆寫與硬刪除);離線批次只是延後了那一刀的時機,並未讓操作本身可逆。

**解耦更新 (Decoupled Update)。** 以 Zep [6] 為代表:LLM 僅對新進事實與候選既有記憶輸出類別標籤(例如 *contradicts*、*duplicates*),實際變更交由確定性系統執行——在受影響的邊上設定 bi-temporal 失效時間戳 (*invalid_at*、*expired_at*)。這個解耦有顯著的架構優點:邊的本體在儲存層被保留(就此意義上變更是非破壞性的),且執行層完全確定性(消除變更步驟的隨機性)。然而,上游 LLM 輸出的標籤仍是系統行為的唯一驅動來源:若 LLM 將「相關但不矛盾」的一對誤標為 *contradicts*,確定性系統會忠實地將較舊的邊設為失效;而 *invalid_at* 一經寫定,下游不再重新檢視——該誤判在**檢索層**等效不可逆。

**共通的結構性限制。** 無論 LLM 是判斷者兼執行者(耦合)或標籤產生者(解耦),主動派方法共享一個結構性質:任一事實的持久記憶狀態,綁定在單一次查詢前 (pre-query) 的 LLM 判斷之上,且該判斷提交後查詢時不再重解。LightMem 自己的 §5.6 討論直接承認了這一點:「*LLM 可能會將相關但並不矛盾的資訊誤判為衝突,進而刪除較舊的記憶項目,造成不可逆的資訊損失*」[3, Sec. 5.6]。這個脆弱性在受限部署下被放大——判斷品質較低的小型不可微調模型,仍以同樣的架構提交其誤判。近期以小模型驅動記憶系統的實證研究(Zhang et al. [18])直接量化了這一點:當既有記憶系統的 backbone 從前沿模型換成 1B–3B 級小模型時,依賴 LLM 判斷的記憶操作效能急遽崩潰;其錯誤注入實驗進一步顯示,寫入端的錯誤會污染記憶並持續影響後續檢索,多重錯誤疊加時系統整體崩潰。值得注意的是,即使是這類 2026 年最新、專為小模型設計的系統,其寫入端仍在查詢發生前就對語意重疊的記憶節點進行合併與改寫——查詢前的破壞性判斷至今仍是整個領域的預設設計。問題的根源不在任何單一 LLM 的準確度,而在架構模式本身。

我們因此主張將 KU 解析從查詢前的一次性提交,延後為查詢時的衝突解析:寫入端完全不做跨筆 LLM 判斷(忠實寫入,Faithful Writes),解析只在查詢觸發時、對該 query 觸及的事實進行(查詢時 KU 解析,Query-Time KU Resolution)。這延續了解耦更新的結構性精神並將其推進到極致——Zep 把變更執行從 LLM 分離,我們進一步把**跨筆判斷本身**移出查詢前階段。而查詢時衝突解析作為一種機制範式,在更廣的 RAG 文獻中已有系統性的研究基礎,下一節說明我們從中汲取與改造的部分。

## 2.2 RAG 中的知識衝突解析 (Knowledge Conflict Resolution in RAG)

查詢時衝突解析在記憶 agent 文獻中尚未被系統性研究,但在檢索增強生成 (Retrieval-Augmented Generation, RAG) 社群中已是一個成形的範式:在查詢時處理檢索回的候選集——辨識哪些段落彼此一致、哪些相互衝突、哪些無關——再將精煉後的上下文交給推論 LLM。

**段落層級的群聚與分離。** Astute RAG [21] 是此模式最明確的實例之一。其迭代式知識整併程序喚起 LLM 將一致的檢索段落群聚、將衝突的段落分入不同群、並過濾無關內容;每個一致性群內提出候選答案,最終答案再經由 LLM 內部知識與外部檢索知識的來源感知比較選出。

**Triple 層級的衝突解析。** TruthfulRAG [22] 在更細的顆粒度上運作:不把檢索段落當原子單位,而是從檢索內容抽取 (head, relation, tail) 三元組、建構 query-aware 知識圖,衝突偵測在圖上的推理路徑進行。這顯示**事實層級的三元組表示是查詢時衝突解析的自然顆粒度**——我們將此觀察納入設計。

**共通的領域假設與設定落差。** 儘管機制各異,這些 RAG 方法共享一個操作設定:每次查詢對(大致)靜態的 corpus 觸發單輪檢索,跨查詢不維持持久狀態;其處理的衝突本質上是與使用者互動歷史無關的跨來源不一致——不同來源之間、或 LLM 參數化知識與外部檢索之間的矛盾。記憶增強 Agent 面對的問題在結構上不同:記憶庫是持續成長的、使用者特定事實的儲存空間,衝突主要來自**同一事實的時間版本漂移**——使用者隨時間更新自己的資訊。因此,需要解析的不是「哪個來源較可信」,而是「同一事實的哪個版本最新」——這引入了 single-shot RAG 方法未處理的時序維度;且由於記憶跨查詢持久存在,解析必須設計成**不落地**:解析結果只服務當次查詢、用畢即棄,每次查詢都在完好的記憶上重解,任何一次的誤判才不會綁定後續查詢。

我們據此將群聚與分離的典範改造、移植到記憶累積設定:**事實識別分群 (identity grouping)** 識別檢索回的哪些候選是同一事實的不同版本(類比於 RAG 的一致性群聚,但 anchored on 事實識別而非資訊一致性,且主要以寫入時保留的 (S, P) 結構做確定性比對、LLM 僅補救結構無法涵蓋的少數案例);**時序解析 (temporal resolution)** 對每個分群以確定性的時序 argmax 選出最新版本(以寫入時序取代來源可信度作為選擇依據,LLM 全程不參與新舊判斷)。組合起來形成一個查詢時 KU 解析機制:結構上汲取 RAG 衝突解析的靈感,同時回應 KU 本質上時序性、且記憶持久存在的特性。

## 2.3 知識更新評估基準 (Knowledge Update Evaluation Benchmarks)

為實證評估 KU,我們採用長期記憶 agent 領域的既有基準。這些基準可依**衝突密度**與 **ground truth 標註顆粒度**分為兩類,這兩個性質決定了它們能有效壓力測試 KU 方法的哪個環節。

**使用者資訊 KU、衝突稀疏。** 第一類基準評估使用者特定事實的 KU——使用者陳述後又修正的個人資訊、屬性或生活事件。LongMemEval [9] 將 knowledge-update 列為五大核心記憶能力之一,在延伸對話歷史(約 115K tokens)中建立 KU 問題,每題鎖定一個使用者屬性的變動;MemBench [10] 的 FM-ku 子集採類似設計;BEAM [11] 的十項記憶能力同時涵蓋 knowledge update 與 contradiction resolution,context 長度延伸至 1M+ tokens。這些基準的結構共通點是:每個 query 鎖定一個特定事實變動、其餘對話對該事實是中性上下文——衝突密度低。因此它們主要壓力測試的是**檢索**(變動前/後的 mentions 能否被撈回),而非檢索成功後的 KU 解析機制。

**世界事實 KU、衝突高密度。** MemoryAgentBench [7] 的 FactConsolidation 子集(以下簡稱 FC)採取不同設計。MAB 將其置於 selective forgetting 能力之下,定義為「偵測並解析過時知識與新獲資訊之間的矛盾」;其對話建構自 MQUAKE [23] 的 counterfactual 編輯對——真實世界事實(如某國元首)與被編輯的反事實版本配對——並將這些編輯密集組合於整段對話中。雖然底層事實是世界知識而非使用者資訊,KU 的解析邏輯在結構上完全等價(較新版本取代較舊者),而高衝突密度將壓力直接施加在 KU 解析機制上,而不僅是檢索。此外,MQUAKE 的 counterfactual 結構提供**事實層級的 ground truth**(每個 instance 明確標註 *gt_new* 與 *gt_old* triples),使我們能對 pipeline 各階段(檢索 vs 解析 vs 推論)做細粒度的失效歸因——包括直接檢視 write-time 方法跑完後記憶庫終態中每個 conflict pair 的處理結果。基於這兩點——高衝突密度直接壓測解析機制、以及 fact-level ground truth 支持診斷歸因——我們採用 FC 的單跳子集 (FC-SH) 作為主要評估,並以使用者資訊 KU 基準(LongMemEval-KU 等)作為泛化檢驗。

**與 Knowledge Editing 的邊界。** FC 的資料來源 MQUAKE [23] 出自知識編輯 (Knowledge Editing) 文獻,該領域研究如何修改語言模型**參數化知識**中的事實並評估其漣漪效應。本文的 KU 對象與之不同:我們不修改不可微調的 LLM 本身,而是維護與解析其**外部記憶**中同一事實的多個版本。兩者共享「較新事實取代較舊」的語意,但更新的載體(參數 vs 外部記憶庫)與可行的操作空間(梯度/定位編輯 vs 讀寫記憶)根本不同;MQUAKE 在此僅作為 FC 的 counterfactual 事實對來源。

---

## References(自 [21] 起續編;[1]–[20] 見 intro v5)

[21] F. Wang, X. Wan, R. Sun, J. Chen, and S. Ö. Arık, "Astute RAG: Overcoming imperfect retrieval augmentation and knowledge conflicts for large language models," in *Proc. 63rd Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2025.

[22] S. Liu, Y. Shang, and X. Zhang, "TruthfulRAG: Resolving factual-level conflicts in retrieval-augmented generation with knowledge graphs," in *Proc. AAAI Conf. Artif. Intell.*, 2026.

[23] Z. Zhong, Z. Wu, C. D. Manning, C. Potts, and D. Chen, "MQUAKE: Assessing knowledge editing in language models via multi-hop questions," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)*, 2023.

---

## 編輯註記(不進論文;v1 → v2 的決策紀錄)

1. **編號重排**:舊版 RW 的 [17] Astute / [18] TruthfulRAG / [19] MQUAKE 與 intro v5 的 [17] ConflictBank / [18] Zhang et al. / [19] Least-to-Most 衝突,RW 引用一律改自 [21] 起。
2. **移除 Cattan et al. 2025(衝突分型)**:P5 已自架構移除,2.2 的機制傳承只剩 identity grouping(← cluster-and-separate)與 temporal resolution(← 我們自己的確定性替換),不再引 CONFLICTS taxonomy。
3. **2.1 新增 [18] 段落**:SLM-driven 系統是 2026 年最新的一線,且其錯誤注入實驗是「寫入污染持續影響後續檢索」的 conference-accepted 實證——放在共通限制段收尾,直接鋪墊受限部署動機。引用時遵守 vocabulary §6 的同名消歧規則(裸名 LightMem 專指 [3])。
4. **2.2 移除「解析決策可能依 query 而異」的舊句**:那句暗示 query-dependent operator(多投影),已決定押後不作 claim;改為「解析不落地、每次查詢重解」的 recoverability 表述,與 intro v5 的誠實邊界一致。
5. **Knowledge Editing 以邊界段處理**(2.3 末),不開獨立小節:我們只需劃清「參數 vs 外部記憶」的邊界並交代 MQUAKE 的角色,展開 KE 文獻(ROME/MEMIT/RippleEdits…)對本文定位沒有增益。
6. **Temporal KG / bi-temporal / as-of 不進 RW**:Zep 已在 2.1 代表 KG-based 記憶;as-of 查詢需要 valid time、超出本文 scope,在 RW 展開等於邀請「那你為何不做 valid time」的攻擊——留 discussion/future work 一句話即可。
7. **《Don't Ask the LLM to Track Freshness》不進 RW**:它是「argmax 優於 LLM 挑 recency」的關鍵證據,放 method/analysis 引用。☐ TODO:確認其 venue status;若為 preprint,依本專案「RW 支柱需 conference-accepted」的政策,僅作輔助證據引用。
8. **Conflict-Aware Soft Prompting(project 內 PDF)未引**:屬 RAG 衝突線的另一支(soft prompting 令模型感知衝突),與我們機制無傳承關係;若審稿人要求 RAG 線更廣,可在 2.2 首段補一句並列引用。
9. **2.1 開頭以一句話帶過 passive 派**並回指 Introduction,避免與 intro 第 2 段重複;RW 的重心放在主動派內部的結構分析(這是 intro 沒有空間展開的)。
