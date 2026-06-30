LLM Agent (基於大型語言模型的智慧代理) 正越來越廣泛地部署於真實世界應用中，並跨越多個對話階段 (sessions) 與使用者互動 [1]。由於 LLM 本身是無狀態 (stateless) 的、僅能在固定長度的上下文視窗 (fixed-length context windows) 中運作 [2]–[4]，要在長期互動中維持連貫性，就必須仰賴一個能跨越對話輪次與階段、持續保存資訊的外部記憶模組 (external memory) [5]–[7]。然而，當記憶模組隨時間累積資料後，會出現一個無法迴避的特性:許多已儲存的事實，其時效性 (temporal validity) 會在對話過程中改變 [8, Sec. 3.2]。同一個事實因此可能在記憶中以多個不一致的版本同時存在;當查詢無差別地檢索這些版本時，系統會將過時資訊與當前資訊一併取出 [7]，導致推論被誤導。這個問題——也就是如何辨識並採用某個事實的最新版本——被稱為**知識更新 (Knowledge Update, KU)**，近期的長期記憶基準 (benchmarks) 也將其列為 memory agent 核心能力之一 [7], [9]–[11]。

現有的記憶增強 Agent (memory-augmented agent) 中，絕大多數對 KU 採取**被動 (passive)** 態度。它們的更新機制著重於記憶的儲存、結構或組織，而不是事實的時效性。例如，MemoryBank [12] 採用受艾賓豪斯遺忘曲線啟發的衰減機制;MemGPT [2] 與 MemoryOS [4] 將記憶組織成具有汰換策略的階層式分層架構;A-Mem [1] 則維持一個持續演化的原子筆記網路。這些設計都共同欠缺一項能力:當新進入的事實與既有記憶相互矛盾或取代既有事實時，它們不會主動偵測到這個衝突。結果是:過時與當前版本同時累積於記憶庫中，檢索時兩者一併浮現，推論模組因此無法可靠地反映世界的最新狀態。

第二類研究則讓記憶模組對 KU 採取**主動 (proactive)** 態度，於寫入時就解析潛在的衝突。其中主要可區分為兩個次類別。第一類為**耦合更新 (Coupled Update)**，以 Mem0 [5] 與 LightMem [3] 為代表，透過單一次 LLM 呼叫同時決定操作並執行 (ADD / UPDATE / DELETE / NOOP);LLM 在此同時扮演判斷者與執行者 (judge and operator) 的角色。第二類為**解耦更新 (Decoupled Update)**，以 Zep [6] 為代表，LLM 僅輸出類別標籤 (例如 *contradicts*、*duplicates*)，實際的記憶變更則交由確定性系統執行。這兩種設計都試圖在寫入時就偵測並移除過時資訊，相較於被動派確實有所改進。然而，兩者也共享一項結構性問題:無論 LLM 是擔任判斷者或標籤產生者，上游的判斷本身仍是唯一的錯誤來源 (the sole source of error)——任何誤判都會被不可逆地寫入記憶中。LightMem 自己在第 5.6 節中 [3, Sec. 5.6] 也明確承認:「*LLM 可能會將相關但並不矛盾的資訊誤判為衝突，進而刪除較舊的記憶項目，造成不可逆的資訊損失。*」

因此，這兩種典範 (paradigm) 暴露出一個**共通**的結構性限制:KU 的成敗完全取決於單一次寫入時的判斷，而無論該判斷正確與否，記憶庫都會被破壞性地更新。在**受限部署場景 (constrained deployment)** 下，這個限制會變得格外嚴重。隱私敏感 (privacy-sensitive) 的應用程式越來越要求在裝置端進行推論 (on-device inference)，此時只有小型、不可微調 (frozen) 的語言模型才是可行的選擇，無法仰賴伺服器端的 API [13]–[15]。與此同時，成本受限 (cost-constrained) 的生產部署也越來越仰賴小型、低成本的 API 模型，例如 GPT-4o-mini [1], [7, Sec. I], [16]。在這兩種場景下，Agent 都是在小型且不可微調的 LLM 上運作，而這類模型的判斷品質明顯低於前沿模型 (frontier models)。當品質較低的判斷與破壞性的寫入提交結合，誤判便會在記憶庫中不可逆地累積。由於 LLM 不可微調，無法藉由改進 LLM 本身來緩解這個問題;唯一剩下的設計空間，是改變系統如何使用 LLM——具體而言，是 LLM 在什麼階段被呼叫，以及它的判斷範圍涵蓋什麼。

主動派 (proactive) 方法的根本困境在於以下不對稱性:它們要求 LLM 在寫入時、不具備 query context 的情況下，對全記憶庫中所有可能的記憶配對做預測性 (speculative) 的關係判斷;任何這樣的判斷一旦寫入便不可逆。然而到了查詢階段，需要解析的只是該 query 所涉及的事實，而非整個記憶庫中所有可能的記憶配對。我們因此主張:**KU 應該是 query-time 的問題，而非 write-time 的提交決定**。基於這個主張，我們提出一個記憶架構，圍繞兩個結構性 commitment 展開:第一，**保守寫入 (Conservative Writes)** —— 寫入時不呼叫任何跨筆記憶的 LLM 判斷、所有版本都保留;第二，**查詢時 KU 解析 (Query-Time KU Resolution)** —— KU 解析只在查詢觸發時、針對 query 涉及的事實進行。我們的設計延續解耦更新 (Decoupled Update) 的脈絡——以 Zep [6] 為代表——將其結構性精神推進到極致:Zep 雖然把記憶變更 (mutation) 從 LLM 分離、由確定性系統執行，但 LLM 仍須對新進事實與既有記憶之間的關係做出類別判斷;我們則進一步完全消除寫入時所有跨筆記憶 (cross-item) 的 LLM 判斷。我們的框架延用與現有記憶增強 Agent 相同的「儲存—更新—檢索—生成 (Storage–Update–Retrieval–Generation)」統一流程 [4]，但在三個元件層級進行重新設計:不仰賴跨筆判斷的更新模組、保留所有版本的統一記憶庫，以及融入事實識別分群 (identity grouping) 與時序解析 (temporal resolution) 的檢索模組。最終的成果是一個記憶架構，其可靠性不再取決於任何跨筆寫入判斷的正確性——因為這類判斷根本不存在:記憶忠實地保留寫入的內容，而 KU 只在被 query 觸發時才解析。

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

[14] K. Zhang, J. Wang, E. Hua, B. Qi, N. Ding, and B. Zhou, "CoGenesis: A framework collaborating large and small language models for secure context-aware instruction following," in *Proc. 62nd Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2024.

[15] H. Huang *et al.*, "A middle path for on-premises LLM deployment: Preserving privacy without sacrificing model confidentiality," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)*, 2025, pp. 8321–8359.

[16] L. Chen, M. Zaharia, and J. Zou, "FrugalGPT: How to use large language models while reducing cost and improving performance," *Trans. Mach. Learn. Res.*, 2024.