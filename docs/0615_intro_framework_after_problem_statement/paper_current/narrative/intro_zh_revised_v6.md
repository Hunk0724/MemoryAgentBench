# Write Faithfully, Resolve at Query Time: Deferring Knowledge Update in LLM Agent Memory

## Introduction（v6，2026-07-04：下半段改以「有無 query」為架構支點、payoff 改為乾淨 pool；移除「不對稱性」框架）

LLM Agent (基於大型語言模型的智慧代理) 正越來越廣泛地部署於真實世界應用中，並跨越多個對話階段 (sessions) 與使用者互動 [1]。由於 LLM 本身是無狀態 (stateless) 的、僅能在固定長度的上下文視窗 (fixed-length context windows) 中運作 [2]–[4]，要在長期互動中維持連貫性，就必須仰賴一個能跨越對話輪次與階段、持續保存資訊的外部記憶模組 (external memory) [5]–[7]。然而，當記憶模組隨時間累積資料後，會出現一個無法迴避的特性：許多已儲存的事實，其時效性 (temporal validity) 會在對話過程中改變 [8, Sec. 3.2]。同一個事實因此可能在記憶中以多個不一致的版本同時存在；當查詢無差別地檢索這些版本時，系統會將過時資訊與當前資訊一併取出 [7]，導致推論被誤導。這個問題——也就是辨識同一事實的多個版本、並採用其最新版本——被稱為**知識更新 (Knowledge Update, KU)**，並已被近期的長期記憶基準 (benchmarks) 明確列為 memory agent 的核心能力：LongMemEval 將 knowledge-update 列為五大核心記憶能力之一 [9]；BEAM 的十項記憶能力中同時涵蓋 knowledge update 與 contradiction resolution [11]；MemoryAgentBench 則以 FactConsolidation 任務，在其 selective forgetting 能力下測試系統能否以較新加入的事實取代較舊者 [7]；MemBench 亦以其 FM-ku 子集涵蓋使用者屬性隨時間的變動 [10]。本文所解決的 KU，即以這些基準的共同定義為範圍。

現有的記憶增強 Agent (memory-augmented agent) 中，絕大多數對 KU 採取**被動 (passive)** 態度。它們的更新機制著重於記憶的儲存、結構或組織，而不是事實的時效性。例如，MemoryBank [12] 採用受艾賓豪斯遺忘曲線啟發的衰減機制；MemGPT [2] 與 MemoryOS [4] 將記憶組織成具有汰換策略的階層式分層架構；A-Mem [1] 則維持一個持續演化的原子筆記網路。這些設計都共同欠缺一項能力：當新進入的事實與既有記憶相互矛盾或取代既有事實時，它們不會主動偵測到這個衝突。結果是：過時與當前版本同時累積於記憶庫中，檢索時兩者一併浮現，推論模組因此無法可靠地反映世界的最新狀態。

第二類研究則讓記憶模組對 KU 採取**主動 (proactive)** 態度，在任何查詢發生之前——無論是寫入當下，或是離線整併 (offline consolidation) 時——就解析潛在的衝突。其中主要可區分為兩個次類別。第一類為**耦合更新 (Coupled Update)**，以 Mem0 [5] 與 LightMem [3] 為代表，透過單一次 LLM 呼叫同時決定操作並執行 (ADD / UPDATE / DELETE / NOOP)；LLM 在此同時扮演判斷者與執行者 (judge and operator) 的角色。第二類為**解耦更新 (Decoupled Update)**，以 Zep [6] 為代表，LLM 僅輸出類別標籤 (例如 *contradicts*、*duplicates*)，實際的記憶變更則交由確定性系統執行。這兩種設計都試圖在查詢發生之前就偵測並移除過時資訊，相較於被動派確實有所改進。然而，兩者也共享一項結構性問題：無論 LLM 是擔任判斷者或標籤產生者，上游的判斷本身仍是唯一的錯誤來源 (the sole source of error)——任何誤判都會被提交 (commit) 進記憶，並在查詢時被照單全收、不再重解。LightMem 自己在第 5.6 節中 [3, Sec. 5.6] 也明確承認：「*LLM 可能會將相關但並不矛盾的資訊誤判為衝突，進而刪除較舊的記憶項目，造成不可逆的資訊損失。*」

因此，這兩種典範 (paradigm) 暴露出一個**共通**的結構性限制：任一事實的持久記憶狀態，被綁定在單一次查詢前 (pre-query) 的 LLM 判斷之上，而該判斷一旦提交、在查詢時便不再被重新檢視——無論它正確與否。在破壞性方法 (Mem0、LightMem) 中，這個限制更被推到極端：誤判以覆寫或刪除的形式落地，被銷毀的舊版本再也無法還原；即使是非破壞性的 Zep，其失效標籤 (invalidation) 一經寫定便凍結、查詢時不再重解，使誤判在檢索層面同樣不可回頭。在**受限部署場景 (constrained deployment)** 下，這個限制會變得格外嚴重。一方面，受限部署是真實且普遍的：隱私敏感 (privacy-sensitive) 的應用程式越來越要求在裝置端進行推論 (on-device inference)，此時只有小型、不可微調 (frozen) 的語言模型才是可行的選擇，無法仰賴伺服器端的 API [13]–[15]；與此同時，成本受限 (cost-constrained) 的生產部署也越來越仰賴小型、低成本的 API 模型，例如 GPT-4o-mini [1], [7, Sec. I], [16]。另一方面，這類模型的判斷能力存在明確的**規模效應**：在知識衝突情境下，同一模型家族中參數量較小的模型更傾向堅持既有知識、更難正確採納與之矛盾的新資訊 [17]；在需要整合大量使用者上下文的任務上，小模型亦系統性地落後於大模型 [14]。更關鍵的是，近期以小模型驅動記憶系統的實證研究 [18] 直接顯示：當現有記憶系統的 backbone 從前沿模型換成 1B–3B 級小模型時，其依賴 LLM 判斷的記憶操作效能會急遽崩潰（例如 MemGPT 的 single-hop F1 自 GPT-4o 上的 60.16 跌至 Qwen2.5-1.5B 上的 9.56）；且其錯誤注入實驗進一步證明，寫入端的錯誤會污染記憶並持續影響後續檢索，並在多重錯誤疊加時使系統整體崩潰。值得注意的是，即使是 [18] 這類 2026 年最新、專為小模型設計的記憶系統，其寫入端的小模型仍在查詢發生前就對語意重疊的記憶節點進行合併與改寫——查詢前的破壞性判斷，至今仍是整個領域的預設設計。當較低的判斷品質與難以回頭的查詢前提交結合，誤判便會在記憶庫中累積、且無法還原。由於 LLM 不可微調，無法藉由改進 LLM 本身來緩解這個問題；唯一剩下的設計空間，是改變系統**如何使用** LLM——具體而言，是 LLM 在什麼階段被呼叫，以及它的判斷範圍涵蓋什麼。

主動派方法困境的根源，在於它們的 KU 判斷發生在**任何 query 之前**。在沒有 query 的情況下，系統無從得知未來會被問到哪些事實，因而被迫對**每一筆**新進事實、針對向量粗篩出的候選既有記憶，做出「是否為同一事實、是否取代、誰勝出」的預測性判斷——這是一個在資訊最少的時刻、對開放範圍的既有記憶所做、且一旦做成便提交的判斷。然而到了查詢那一刻，真正需要解析的，只有該 query 所觸及的少數事實。我們因此主張：**KU 應該在查詢時被解析，而非在寫入時被提交**——正如本文題目所言：*Write Faithfully, Resolve at Query Time*。將判斷從寫入時移到查詢時，等於把它從「沒有 query」的處境移到「有 query」的處境，而這個差別是實質的：有了 query，判斷的範圍被收斂——模型不再需要對每一筆新事實、對照整個記憶庫做開放式的判斷，而只需在該 query 檢索回的少數候選之間，分辨哪些是同一事實的不同版本。對同一個模型而言，後者是遠為簡單、也遠為可靠的判斷。

更重要的是，移動 KU 解析的時機並非在既有流程上外加一個模組，而是一個牽動整條流程的**根本架構改動**：判斷一旦挪到查詢時，寫入端與解析端都被迫隨之改變，這正是我們兩個結構性承諾 (structural commitment) 的來源。第一，**忠實寫入 (Faithful Writes)**——既然解析延到查詢時才發生，寫入就必須完整保留所有版本、不做任何破壞性變更（寫入時 LLM 僅進行單筆之內的結構化抽取，將事實轉為 (subject, relation, object) 三元組並附上時間戳，不進行任何跨筆記憶的 LLM 判斷）；否則查詢時將無完整的版本可供解析。第二，**查詢時 KU 解析 (Query-Time KU Resolution)**——解析只在查詢觸發時、僅對該 query 檢索回的少數候選進行；且由於這個解析是非破壞性的（它只是篩選出要餵給推論的記憶，並不變更記憶庫），我們得以放心地把「誰是最新版本」交給一個確定性的時序 argmax 決定，LLM 全程不參與新舊 (recency) 判斷。留給 LLM 的殘餘任務因此被壓到最窄：僅剩事實識別分群，而這主要由寫入時保留的 (subject, relation) 結構做確定性比對承擔，LLM 只在結構因抽取字面落差而無法涵蓋的少數案例才介入補救。值得強調的是，非破壞性正是我們敢於把判斷簡化為確定性規則的前提：破壞性的寫入方法一旦刪錯便無法挽回，反而被迫讓 LLM 慎重判斷該不該刪，使判斷更複雜、更依賴模型能力。我們的設計延續解耦更新 (Decoupled Update) 的脈絡——以 Zep [6] 為代表——並將其推進到極致：Zep 已把記憶變更 (mutation) 從 LLM 分離、交由確定性系統執行，但 LLM 仍須在查詢前對新進事實與既有記憶之間的關係做出類別判斷；我們則進一步完全消除查詢前所有跨筆記憶的 LLM 判斷。整體框架延用與現有記憶增強 Agent 相同的「儲存—更新—檢索—生成 (Storage–Update–Retrieval–Generation)」流程 [4]，但在三個元件層級重新設計：不含跨筆判斷的寫入端、保留所有版本的統一記憶庫，以及以事實識別分群 (identity grouping) 與時序解析 (temporal resolution) 構成的查詢端解析模組。

這條架構改動的直接產物，是每一次查詢送進推論 LLM 的記憶都是**乾淨的**——該事實的當前版本在場、被取代的舊版本被濾除（在分群所能達到的範圍內：結構比對為主、LLM 補救字面落差）。推論模型因此只需從乾淨的記憶中讀出答案，而不必自行在相互衝突的多個版本間裁決——這正是本方法在 backbone 判斷力薄弱時仍能運作的根源：我們把「判斷」從推論模型手上移除，改由查詢時的解析流程以確定性方式完成。相對地，過去在寫入時提交的判斷一旦出錯，該錯誤會持續存在並被後續每一個相關查詢重複撈取，而我們查詢時的解析錯誤只影響當下這一題、不向後擴散。由此我們得到一個可驗證的預測：本方法相對現有流派的優勢，應隨 backbone 判斷品質下降而**單調放大**——在判斷力充足的前沿模型上幾乎可忽略，並在受限部署 (constrained deployment) 常見的中、小型模型上顯著兌現。

---

## v6 變更摘要（相對 v5）

1. **移除「不對稱性 (asymmetry)」框架**：非本領域既有術語（我們自造），改以直接描述「判斷發生在沒有 query 的處境」。
2. **第 5 段重寫為架構支點**：核心對比收斂為「有無 query」與「每筆盲判 vs 只判當下 query 相關」；並補上 reviewer 防守關鍵——query 把「對全庫的開放式判斷」降維成「對小切片的分辨」，同一模型後者遠為可靠（回答「query 到底幫了什麼」）。
3. **第 6 段重寫為「根本架構改動 → 被迫連鎖」**：兩個 commitment 定位為「判斷挪到查詢時所強制的連鎖」，凸顯是動地基而非加房間；並織入「非破壞性是敢用 deterministic argmax 的前提」這條，把弱模型可駕馭的機制講死。
4. **payoff 改為「乾淨 pool」**（對齊 evaluation_protocol_main §4.2）：當前版本在場、舊版本被濾除，推論模型照抄即可、無需裁決 → 弱模型可用的根源。**加了誠實餘地**（分群所能達到的範圍內），呼應 case study 模式 A/B。
5. **durability 降為一句「錯誤爆炸半徑」**：write-time 判錯波及後續每一題、我們只損當下一題——定位為跨題的錯誤作用範圍，非「可回復」（依你判斷，污染/可回復為次要）。
6. **新增可證偽預測**：優勢隨 backbone 判斷力下降單調放大——直接對接 experiments 的 backbone sweep 頭條圖。
7. **未在 intro 出現具體實驗數字/模型名**（gpt-4.1-mini、has_pair 分母、46–50pp、262k 等留給 experiments），避免 intro 與 protocol 口徑衝突。

---

## References

[1] W. Xu, Z. Liang, K. Mei, H. Gao, J. Tan, and Y. Zhang, "A-Mem: Agentic memory for LLM agents," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, 2025.

[2] C. Packer *et al.*, "MemGPT: Towards LLMs as operating systems," 2023, arXiv:2310.08560.

[3] J. Fang *et al.*, "LightMem: Lightweight and efficient memory-augmented generation," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2026.

[4] J. Kang, M. Ji, Z. Zhao, and T. Bai, "Memory OS of AI agent," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)*, 2025, pp. 25972–25981.

[5] P. Chhikara, D. Khant, S. Aryan, T. Singh, and D. Yadav, "Mem0: Building production-ready AI agents with scalable long-term memory," in *Proc. Eur. Conf. Artif. Intell. (ECAI)*, 2025, pp. 2993–3000.

[6] P. Rasmussen, P. Paliychuk, T. Beauvais, J. Ryan, and D. Chalef, "Zep: A temporal knowledge graph architecture for agent memory," 2025, arXiv:2501.13956.

[7] Y. Hu, Y. Wang, and J. McAuley, "Evaluating memory in LLM agents via incremental multi-turn interactions," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2026.

[8] J. Luo *et al.*, "From storage to experience: A survey on the evolution of LLM agent memory mechanisms," in *Proc. ICLR Workshop Memory for Agentic Syst. (MemAgents)*, 2026.

[9] D. Wu, H. Wang, W. Yu, Y. Zhang, K.-W. Chang, and D. Yu, "LongMemEval: Benchmarking chat assistants on long-term interactive memory," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2025.

[10] H. Tan, Z. Zhang, C. Ma, X. Chen, Q. Dai, and Z. Dong, "MemBench: Towards more comprehensive evaluation on the memory of LLM-based agents," in *Findings Assoc. Comput. Linguistics: ACL 2025*, 2025, pp. 19336–19352.

[11] M. Tavakoli, A. Salemi, C. Ye, M. Abdalla, H. Zamani, and J. R. Mitchell, "Beyond a million tokens: Benchmarking and enhancing long-term memory in LLMs," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2026.

[12] W. Zhong, L. Guo, Q. Gao, H. Ye, and Y. Wang, "MemoryBank: Enhancing large language models with long-term memory," in *Proc. AAAI Conf. Artif. Intell.*, vol. 38, no. 17, 2024, pp. 19724–19731.

[13] T. M. Pham, P. T. Nguyen, S. Yoon, V. D. Lai, F. Dernoncourt, and T. Bui, "SlimLM: An efficient small language model for on-device document assistance," in *Proc. 63rd Annu. Meeting Assoc. Comput. Linguistics: Syst. Demonstrations (ACL Demo)*, 2025, pp. 436–447.

[14] K. Zhang, J. Wang, E. Hua, B. Qi, N. Ding, and B. Zhou, "CoGenesis: A framework collaborating large and small language models for secure context-aware instruction following," in *Proc. 62nd Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2024, pp. 4295–4312.

[15] H. Huang *et al.*, "A middle path for on-premises LLM deployment: Preserving privacy without sacrificing model confidentiality," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)*, 2025, pp. 8321–8359.

[16] L. Chen, M. Zaharia, and J. Zou, "FrugalGPT: How to use large language models while reducing cost and improving performance," *Trans. Mach. Learn. Res.*, 2024.

[17] Z. Su, J. Zhang, X. Qu, T. Zhu, Y. Li, J. Sun, J. Li, M. Zhang, and Y. Cheng, "ConflictBank: A benchmark for evaluating the influence of knowledge conflicts in LLM," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS) Datasets and Benchmarks Track*, 2024.

[18] J. Zhang, C. Zhang, S. Chen, Z. Huang, P. Zheng, Z. Wang, P. Guo, F. Mo, S.-H. Bae, J. Zou, J. Wei, and Y. Yang, "Lightweight LLM agent memory with small language models," in *Proc. 64th Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2026, pp. 12914–12929.

[19] D. Zhou, N. Schärli, L. Hou, J. Wei, N. Scales, X. Wang, D. Schuurmans, C. Cui, O. Bousquet, Q. Le, and E. Chi, "Least-to-most prompting enables complex reasoning in large language models," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2023.

[20] T. Khot, H. Trivedi, M. Finlayson, Y. Fu, K. Richardson, P. Clark, and A. Sabharwal, "Decomposed prompting: A modular approach for solving complex tasks," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2023.

[21] F. Wang, X. Wan, R. Sun, J. Chen, and S. Ö. Arık, "Astute RAG: Overcoming imperfect retrieval augmentation and knowledge conflicts for large language models," in Proc. 63rd Annu. Meeting Assoc. Comput. Linguistics (ACL), 2025.

[22] S. Liu, Y. Shang, and X. Zhang, "TruthfulRAG: Resolving factual-level conflicts in retrieval-augmented generation with knowledge graphs," in Proc. AAAI Conf. Artif. Intell., 2026.

[23] Z. Zhong, Z. Wu, C. D. Manning, C. Potts, and D. Chen, "MQUAKE: Assessing knowledge editing in language models via multi-hop questions," in Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP), 2023.