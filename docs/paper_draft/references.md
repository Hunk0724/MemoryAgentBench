# References v2：Paper Narrative 所有引用文獻

> v2 更新：依新的三派系（A/B/C）切分對手；加入 empirical-driven design paper 風格的 inspiration 引用；補充派系 C 細節。

---

## A. 派系 A：對話累積 + 顯式衝突機制（Write-time）

### A1. Zep / Graphiti
- **Citation**：Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). Zep: A Temporal Knowledge Graph Architecture for Agent Memory. *arXiv preprint arXiv:2501.13956*.
- **URL**：https://arxiv.org/abs/2501.13956
- **核心機制**：bi-temporal edge invalidation（4 timestamps：t_created, t_expired, t_valid, t_invalid），LLM 比對語意相近 edge，write-time
- **架構**：3-tier subgraph（Episode + Semantic Entity + Community）+ Graphiti engine
- **Benchmark**：DMR, LongMemEval（94.8% vs MemGPT 93.4% on DMR）
- **代碼**：Graphiti 開源
- **🆕 v3 註：實作對齊**
  - 我們透過 zep_cloud SDK 評估（MABench bundled），可看到 `invalid_at` 結果但無法看到偵測過程
  - Graphiti OSS 是 Zep 的官方 OSS 實作，逐字對應論文 §2.2.3
  - 若機制層級分析需要白盒，附錄補 Graphiti v0.29.1 抽樣對比
  - Evaluation 期間 Zep cloud 後端可能更新，paper 需報告 evaluation date range
- **Narrative 引用位置**：§2.1 (派系 A2 non-destructive)、§3.1（2D 表）、§5.4（元件對應）、§6.2（必比 baseline）、§6.5（disclosure）

### A1'. 🆕 Graphiti（Zep 的官方 OSS 實作）
- **Citation**：getzep/graphiti GitHub repo. https://github.com/getzep/graphiti
- **版本**：v0.29.1（2026-05 當前）
- **核心對應**：
  - `edge.invalid_at = resolved_edge.valid_at; edge.expired_at = utc_now()` 對應論文 §2.2.3 soft invalidation
  - `EntityEdge.get_between_nodes()` 對應論文 §2.2.2 candidate fetching
  - 4 個 timestamp 欄位（created_at / expired_at / valid_at / invalid_at）對應論文 §2 bi-temporal
- **用途**：作為機制層級 white-box 分析的 fallback（觸發條件：reviewer 要求機制歸因）
- **Narrative 引用位置**：§6.5（disclosure）、§9 反駁 footnote

### A2. Mem0 / Mem0g
- **Citation**：Chhikara, P., Khant, D., Aryan, S., Singh, T., & Yadav, D. (2025). Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory. *Proceedings of ECAI 2025* (arXiv:2504.19413).
- **URL**：https://arxiv.org/abs/2504.19413
- **核心機制（paper claim）**：ADD / UPDATE / DELETE / NOOP via LLM tool call，write-time；§2.2 寫「marking as invalid rather than physically removing them to enable temporal reasoning」
- **Mem0g 變體**：directed labeled graph + Neo4j 後端
- **Benchmark**：LoCoMo
- **🆕 v3 註：實作對齊（重要）**
  - 我們透過 MABench bundled v2.x 評估
  - **公開實作為 hard `DELETE r`（Cypher）**，與論文 §2.2 描述的 soft invalidation 不一致
  - **mem0 upstream v3 (2026-04, commit a488e190) 已完全移除圖記憶**（包含 graph_memory.py、所有 graph backend）
  - 我們將 vendored impl 標為「destructive write-time conflict resolution 的 representative instance」
  - upstream 放棄圖記憶本身是 industry-level 證據，支持我們對 write-time mechanism 限制的論點
- **Narrative 引用位置**：§2.1 (派系 A1 destructive)、§3.1、§5.4、§6.2、§6.5 (disclosure)、Discussion (industry evidence)

### A3. EMG-RAG（Huawei, EMNLP 2024，重要！）
- **Citation**：Wang, Z., Li, Z., Jiang, Z., Tu, D., & Shi, W. (2024). Crafting Personalized Agents through Retrieval-Augmented Generation on Editable Memory Graphs. *Proceedings of EMNLP 2024*, pp. 4891-4906.
- **URL**：https://aclanthology.org/2024.emnlp-main.281/
- **核心機制**：Editable Memory Graph + 三個 edit operation（insertion / deletion / replacement）+ RL 優化 retrieval
- **場景**：smartphone AI assistant 個人記憶
- **Narrative 引用位置**：§2.1（最早 KG 編輯方法之一）

### A4. A-MEM
- **Citation**：Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). A-Mem: Agentic Memory for LLM Agents. *NeurIPS 2025 poster* (arXiv:2502.12110).
- **URL**：https://arxiv.org/abs/2502.12110
- **核心機制**：Zettelkasten-style 動態 indexing + linking
- **代碼**：https://github.com/agiresearch/a-mem
- **Narrative 引用位置**：§2.1、§6.2（強烈建議比）

### A5. Memory-R1
- **Citation**：Yan, S., 等 (2025). Memory-R1: Enhancing Large Language Model Agents to Manage and Utilize Memories via Reinforcement Learning. *arXiv preprint arXiv:2508.19828*.
- **URL**：https://arxiv.org/abs/2508.19828
- **核心機制**：Mem0 的 ADD/UPDATE/DELETE/NOOP + RL（PPO, GRPO）
- **Narrative 引用位置**：§2.1（派系 A 的最新演進方向）

---

## B. 派系 B：多跳檢索（無衝突機制）

### B1. HippoRAG 2（我們的基底）
- **Citation**：Gutiérrez, B. J., Shu, Y., Qi, W., Zhou, S., & Su, Y. (2025). From RAG to Memory: Non-Parametric Continual Learning for Large Language Models. *Proceedings of ICML 2025* (arXiv:2502.14802).
- **URL**：https://arxiv.org/abs/2502.14802 `[CONFIRM arXiv ID]`
- **核心機制**：PPR over open KG + recognition memory + dense-sparse integration
- **架構**：offline indexing（LLM OpenIE → triples + synonyms）+ online retrieval（query-to-triple → recognition filter → PPR）
- **Benchmark**：NQ, PopQA, MuSiQue, 2Wiki, HotpotQA, NarrativeQA, LV-Eval
- **Narrative 引用位置**：§2.2、§5（基底）、§6.2（必比 baseline）

### B2. PropRAG
- **Citation**：(Author TBC). (2025). PropRAG: Guiding Retrieval with Beam Search over Proposition Paths. *Findings of EMNLP 2025*. `[CONFIRM authors and exact venue]`
- **核心機制**：兩階段 retrieval（Stage 1 exploratory PPR + Stage 2 graph-guided Beam Search over propositions）
- **超參**：B=4, L_max=3, damping factor 0.75 / 0.45
- **Benchmark**：MuSiQue, 2Wiki, HotpotQA, NQ, PopQA
- **Narrative 引用位置**：§2.2、§5（Phase 1 基礎）、§6.2（必比 baseline）

### B3. HopRAG
- **Citation**：Liu, H., Wang, Z., Chen, X., Li, Z., Xiong, F., Yu, Q., & Zhang, W. (2025). HopRAG: Multi-Hop Reasoning for Logic-Aware Retrieval-Augmented Generation. *Findings of ACL 2025*, pp. 1897-1913.
- **URL**：https://aclanthology.org/2025.findings-acl.97/
- **核心**：retrieve-reason-prune
- **Narrative 引用位置**：§2.2（派系 B 同類方法）

### B4. SYNAPSE
- **Citation**：Jiang, H., 等 (2026). SYNAPSE: Empowering LLM Agents with Episodic-Semantic Memory via Spreading Activation. *arXiv preprint arXiv:2601.02744*.
- **URL**：https://arxiv.org/abs/2601.02744
- **核心**：spreading activation graph，temporal decay + lateral inhibition
- **Narrative 引用位置**：§2.2

### B5. MAGMA
- **Citation**：Jiang, D., Li, Y., Li, G., & Li, B. (2026). MAGMA: A Multi-Graph based Agentic Memory Architecture for AI Agents. *arXiv preprint arXiv:2601.03236*.
- **URL**：https://arxiv.org/abs/2601.03236
- **核心**：multi-graph + policy-guided traversal
- **Narrative 引用位置**：§2.2

### B6. HippoRAG（原版）
- **Citation**：Gutiérrez, B. J., 等 (2024). HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models. `[CONFIRM venue: NeurIPS 2024]`
- **Narrative 引用位置**：§2.2（前身 work）

---

## C. 🆕 派系 C：Query-time Conflict 但限定 Explicit 子場景

### C1. T-GRAG（最近的直接競爭者）
- **Citation**：Li, D., Niu, Y., Ai, Y., Zou, X., Qi, B., & Liu, J. (2025). T-GRAG: A Dynamic GraphRAG Framework for Resolving Temporal Conflicts and Redundancy in Knowledge Retrieval. *Proceedings of the 33rd ACM International Conference on Multimedia (MM '25)*, pp. 11880-11889. (arXiv:2508.01680)
- **URL**：https://arxiv.org/abs/2508.01680
- **核心機制**：query-time temporal conflict resolution；5 元件（Temporal KG Generator + Query Decomposition + Three-layer Interactive Retriever + Source Text Extractor + LLM Generator）
- **子場景假設**：explicit timestamps + query 含 explicit time keyword
- **Benchmark**：Time-LongQA（corporate annual reports，自建）
- **Narrative 引用位置**：§2.3（派系 C 代表）、§3.4（FC-MH 適配失敗點）、§6.2（必比 baseline）

### C2. MemoTime
- **Citation**：Tan, X., 等 (2026). MemoTime: Memory-Augmented Temporal Knowledge Graph Enhanced Large Language Model Reasoning. *Proceedings of WWW 2026* (arXiv:2510.13614).
- **URL**：https://arxiv.org/abs/2510.13614
- **核心機制**：TKG-grounded reasoning；4 元件（Temporal Grounding + Tree of Time + Temporal Evidence Retrieval/Pruning + Experience Memory）
- **子場景假設**：explicit temporal operators (before/after/between) + structured TKG
- **Narrative 引用位置**：§2.3、§3.4、§6.2（強烈建議比）

### C3. KEDKG
- **Citation**：Lu, Y., Zhou, Y., Li, J., Wang, Y., Liu, X., He, D., Liu, F., & Zhang, M. (2025). Knowledge Editing with Dynamic Knowledge Graphs for Multi-Hop Question Answering. *Proceedings of AAAI 2025*, pp. 24741-24749. (arXiv:2412.13782)
- **URL**：https://arxiv.org/abs/2412.13782
- **核心機制**：dynamic KG construction + Conflict Detection and Modification (CDM) + question decomposition + entity/relation detector
- **子場景假設**：explicit edit operations + fine-tuned LLM for decomposition
- **Benchmark**：MQUAKE-CF-3K, MQUAKE-T
- **Narrative 引用位置**：§2.3、§3.4、§6.2（強烈建議比）

### C4. MeLLo
- **Citation**：Zhong, Z., 等 (2023). MQuAKE: Assessing Knowledge Editing in Language Models via Multi-Hop Questions. `[CONFIRM venue: EMNLP 2023]`
- **核心**：早期 multi-hop knowledge editing，iterative decomposition
- **Narrative 引用位置**：§2.3 附帶（KEDKG 的前輩）

### C5. PokeMQA
- **Citation**：Gu, H., Zhou, K., Han, X., Liu, N., Wang, R., & Wang, X. (2024). PokeMQA: Programmable Knowledge Editing for Multi-Hop Question Answering. *Proceedings of ACL 2024*, pp. 8069-8083.
- **Narrative 引用位置**：§2.3 附帶

### C6. CAPE-KG
- **Citation**：(Author TBC). (2025). Consistency-Aware Parameter-Preserving Knowledge Editing Framework for Multi-Hop Question Answering. *arXiv preprint arXiv:2509.18655*.
- **URL**：https://arxiv.org/html/2509.18655v1
- **核心**：改進 KEDKG 的 intent consistency
- **Narrative 引用位置**：§2.3 附帶

### C7. MADAM-RAG / RAMDocs
- **Citation**：(Author TBC). (2025). Retrieval-Augmented Generation with Conflicting Evidence. *COLM 2025*.
- **URL**：https://openreview.net/forum?id=z1MHB2m3V9
- **核心**：multi-agent debate over conflicting evidence + benchmark RAMDocs
- **Narrative 引用位置**：§2.3 附帶（document-corpus 場景）

### C8. ConflictRAG
- **Citation**：(Author TBC). (2026). ConflictRAG: Detecting and Resolving Knowledge Conflicts in Retrieval-Augmented Generation. *arXiv preprint arXiv:2605.17301*.
- **URL**：https://arxiv.org/abs/2605.17301
- **核心**：two-stage conflict detection（MLP + LLM）+ Entropy-TOPSIS + CARS metric
- **Narrative 引用位置**：§2.3 附帶

### C9. SeCon-RAG
- **Citation**：(Author TBC). (2025). SeCon-RAG: A Two-Stage Semantic Filtering and Conflict-Free Framework for Trustworthy RAG. *arXiv preprint arXiv:2510.09710*.
- **URL**：https://arxiv.org/abs/2510.09710
- **Narrative 引用位置**：§2.3 附帶

### C10. CLEAR
- **Citation**：(Author TBC). (2025). Probing Latent Knowledge Conflict for Faithful Retrieval-Augmented Generation. *arXiv preprint arXiv:2510.12460*.
- **Narrative 引用位置**：§2.3 附帶；§4.2（LLM prior bias 相關工作）

---

## D. 同盟論文（核心 Ally）

### D1. Diagnosing Retrieval vs. Utilization Bottlenecks ⭐
- **Citation**：Yuan, B., Su, Y., & Yao, K. (2026). Diagnosing Retrieval vs. Utilization Bottlenecks in LLM Agent Memory. *arXiv preprint arXiv:2603.02473*.
- **URL**：https://arxiv.org/abs/2603.02473
- **代碼**：https://github.com/boqiny/memory-probe
- **核心發現**：3x3 study（write strategy × retrieval method）on LoCoMo，**retrieval method spans 20 points（57.1%-77.2%），write strategy 只 spans 3-8 points**
- **關鍵引用句**：「retrieval method is the dominant factor」「Raw chunked storage matches or outperforms expensive lossy alternatives」
- **Narrative 引用位置**：§2.4（核心 ally）、§4 開場（empirical 先例）、§5.1 design rationale、§9 反駁回應

---

## E. Benchmarks

### E1. MemoryAgentBench（主場 benchmark）⭐⭐⭐
- **Citation**：Hu, Y., 等 (2026). Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions. *ICLR 2026* (arXiv:2507.05257).
- **URL**：https://arxiv.org/abs/2507.05257
- **Dataset**：https://huggingface.co/datasets/ai-hyz/MemoryAgentBench
- **四種能力（cognitive science 出發）**：
  1. Accurate Retrieval (AR)
  2. Test-Time Learning (TTL)
  3. Long-Range Understanding (LRU)
  4. **Selective Forgetting (SF)** ← 本研究 target
- **新增 datasets**：EventQA, FactConsolidation（含 single-hop FC-SH 與 multi-hop **FC-MH**）
- **FC-MH 構造**：基於 MQUAKE counterfactual edit pairs，每組 pair 含原始 + 改寫版本，serial number 為時序
- **🆕 Table 3 重要數字（GPT-4o-mini）**：
  - GPT-4o (long-context): FC-SH 60.0, FC-MH **5.0**
  - HippoRAG-v2: FC-SH 54.0, FC-MH **5.0**
  - Mem0: FC-SH 18.0, FC-MH **2.0**
  - Zep: FC-SH 7.0, FC-MH **3.0**
  - MIRIX: FC-SH 14.0, FC-MH **2.0**
  - **所有主流系統 FC-MH ≤ 5%**
- **🆕 Appendix K.2 重要結果**：overwrite policy 在 FC-MH 失效
  - Policy A (Always Prefer Later): FC-SH 40.0, FC-MH **4.0**
  - Paper 原文：「prompting cannot effectively propagate updates through multi-step reasoning chains」
  - **這直接驗證需要 structural 解法，prompt-only 不夠**
- **Narrative 引用位置**：§1.2（問題重要性與 5% 上限）、§3.2（視角 B）、§4.0（Observation 0）、§4.0.1（prompt-fix 失效）、§6.1（主 benchmark）、§8（contribution）

### E2. MAGIC
- **Citation**：Lee, J., Lee, K., & Kim, T. (2025). MAGIC: A Multi-Hop and Graph-Based Benchmark for Inter-Context Conflicts in Retrieval-Augmented Generation. *Findings of EMNLP 2025*, pp. 8783-8803. (arXiv:2507.21544)
- **URL**：https://aclanthology.org/2025.findings-emnlp.466/
- **關鍵引用句**：「both open-source and proprietary models struggle with conflict detection—especially when multi-hop reasoning is required」
- **Narrative 引用位置**：§1.2（multi-hop conflict 是 open problem）、§6.1（補充 benchmark）

### E3. HoH
- **Citation**：Ouyang, J., Pan, T., Cheng, M., Yan, R., Luo, Y., Lin, J., & Liu, Q. (2025). HoH: A Dynamic Benchmark for Evaluating the Impact of Outdated Information on Retrieval-Augmented Generation. *Proceedings of ACL 2025*, pp. 6036-6063.
- **URL**：https://aclanthology.org/2025.acl-long.301/
- **Narrative 引用位置**：§2 引言（outdated info 是公認問題）

### E4. STALE + CUPMem
- **Citation**：(Author TBC). (2026). STALE: Can LLM Agents Know When Their Memories Are No Longer Valid? *arXiv preprint arXiv:2605.06527*.
- **URL**：https://arxiv.org/abs/2605.06527
- **核心**：400 expert-validated conflict scenarios + CUPMem prototype（仍 write-time）
- **關鍵引用句**：「even the best evaluated model achieving only 55.2% overall accuracy」
- **Narrative 引用位置**：§2 引言、§4.1

### E5. MQUAKE 系列（KEDKG 用 + FC-MH 構造基礎）⭐
- **Citation**：Zhong, Z., Wu, Z., Manning, C. D., Potts, C., & Chen, D. (2023). MQUAKE: Assessing Knowledge Editing in Language Models via Multi-Hop Questions. *EMNLP 2023*.
- **變體**：MQUAKE-CF, MQUAKE-T
- **🆕 重要性**：
  - 是 MemoryAgentBench FC-MH 的構造基礎（counterfactual edit pairs）
  - 同時也是 KEDKG 等 knowledge editing 方法的 benchmark
  - **FC-MH 來自 MQUAKE = paper 用 MQUAKE 的 counterfactual 設計**這件事直接 motivate 我們的 DC2/3（LLM prior bias 必須處理）
- **Narrative 引用位置**：§3.4（C2 適配實驗）、§4.2（counterfactual contexts 的依據）、§6.1（FC-MH 構造）

### E6. Time-LongQA（T-GRAG 用）
- **Narrative 引用位置**：§3.4（C1 適配實驗）

### E7. LongMemEval
- **Citation**：Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., & Yu, D. (2024). LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory. *arXiv:2410.10813*.
- **Narrative 引用位置**：§6.1（對手有用此 benchmark）

### E8. LoCoMo
- **Citation**：Maharana, A., Lee, D.-H., Tulyakov, S., Bansal, M., Barbieri, F., & Fang, Y. (2024). Evaluating Very Long-Term Conversational Memory of LLM Agents. *Proceedings of ACL 2024*, pp. 13851-13870.
- **Narrative 引用位置**：§2.4（D1 用此 benchmark）

---

## F. 🆕 Empirical-Driven Design Paper 風格參考（Inspiration）

> 這節是 v2 新增，為「simple-but-effective」風格提供 inspiration 與 defense 用引用；v3 補充：**僅作為候選風格的 fallback，不寫死為主要 framing**。

### F1. Sentence-BERT
- **Citation**：Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. *Proceedings of EMNLP 2019*.
- **為何 cite**：簡單 siamese architecture + 充分 empirical analysis 風格的代表
- **Narrative 引用位置**：§0 風格定位（候選風格 fallback） + §9 反駁回應（simple-but-effective 先例）

### F2. ColBERT
- **Citation**：Khattab, O., & Zaharia, M. (2020). ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT. *Proceedings of SIGIR 2020*.
- **為何 cite**：late interaction 概念簡單，但 design rationale 與 empirical chain 嚴謹
- **Narrative 引用位置**：§0 風格定位（候選風格 fallback）

---

## F'. 🆕 Phase 3 候選方向相關引用（v3 新增）

> **重要區分**：以下文獻在我們 paper 的用法是「借鏡其 context structure / reasoning trace 形式」，**不直接採用其 inference 機制**（否則破壞 fair comparison constraint，見 narrative §5.0）。

### F'1. Self-RAG
- **Citation**：Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2024). Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. *Proceedings of ICLR 2024*.
- **用法**：self-reflective generation 是 Phase 3 方向 4 候選（compression with self-check）
- **限制**：採用其 inference 流程會破壞 fair comparison，需要小心
- **Narrative 引用位置**：§5（Phase 3 候選方向）、03 §B.5

### F'2. IRCoT
- **Citation**：Trivedi, H., Balasubramanian, N., Khot, T., & Sabharwal, A. (2023). Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions. *Proceedings of ACL 2023*.
- **用法**：reasoning steps 預先計算後寫入 context（不改 inference 流程）
- **Narrative 引用位置**：§5（Phase 3 方向 5）、03 §B.5

### F'3. ReAct
- **Citation**：Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. *Proceedings of ICLR 2023*.
- **用法**：reasoning trace 作為 context 的一部分
- **Narrative 引用位置**：§5（Phase 3 候選方向）

### F'4. Chain-of-Note
- **Citation**：Yu, W., Zhang, H., Pan, X., Ma, K., Wang, H., & Yu, D. (2024). Chain-of-Note: Enhancing Robustness in Retrieval-Augmented Language Models. *arXiv preprint arXiv:2311.09210*. `[CONFIRM venue]`
- **用法**：reading notes 作為 context 標註，與 Phase 3 方向 2 / 3 直接相關
- **Narrative 引用位置**：§5（Phase 3 方向 2 / 3 主要 reference）

### F'5. Context Format / Presentation 對 LLM 推理影響的相關 paper
- `[TODO 補：搜尋「context format effect on multi-hop reasoning」「evidence presentation LLM」相關 paper]`
- 候選方向：
  - Prompt sensitivity 系列工作
  - Evidence ordering 對 RAG 影響的研究
  - Reasoning chain explicit vs implicit 比較
- **Narrative 引用位置**：§4.4 Observation 4、§5（DC6）

### F'6. Compression / Distillation 相關（候選方向 4）
- LongLLMLingua, RECOMP 等 context compression 方法
- `[TODO 補完整 citation]`
- **Narrative 引用位置**：§5（Phase 3 方向 4）

---

## G. 知識衝突 Survey 與分類

### G1. Knowledge Conflicts for LLMs: A Survey ⭐⭐⭐（核心文獻軸）
- **Citation**：Xu, R., Qi, Z., Guo, Z., Wang, C., Wang, H., Zhang, Y., & Xu, W. (2024). Knowledge Conflicts for LLMs: A Survey. *EMNLP 2024*.
- **核心貢獻**：
  - 分類三類 conflict：context-memory / **inter-context** / intra-memory
  - 分類軸：**Pre-hoc vs Post-hoc** mitigation timing
- **本研究位置**：
  - 衝突類型：**inter-context conflict** with outdated information
  - 衝突時機：**Post-hoc**（與 pre-hoc 派系 Zep/Mem0g 區隔）
- **🆕 重要性**：v5 採用此 survey 的 pre-hoc/post-hoc 分類軸取代我們自創的 A/B/C 派系，文獻依據明確
- **Narrative 引用位置**：§1（定義 conflict 類型）、§2（pre-hoc/post-hoc 分類軸）、§3.1（雙視角對齊）、§4（empirical motivation framing）

### G2. Knowledge Conflict 早期 benchmarks
- WikiContradict (Hou et al., 2024)
- ConFiQA
- FaithEval (Ming et al., 2024)
- AmbigDocs (Lee et al., 2024)
- **Narrative 引用位置**：§2 附帶（single-hop conflict 工作）

---

## H. RAG / 多跳推理基礎

### H1. RAG 原作
- **Citation**：Lewis, P., 等 (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.
- **Narrative 引用位置**：§2 引言

### H2. Personalized PageRank
- **Citation**：Haveliwala, T. (2002). Topic-Sensitive PageRank. *Proceedings of WWW 2002*.
- **Narrative 引用位置**：§5（HippoRAG 的 PPR 演算法基礎）

### H3. 多跳 QA benchmarks
- MuSiQue (Trivedi et al., 2022)
- 2WikiMultihopQA (Ho et al., 2020)
- HotpotQA (Yang et al., 2018)
- **Narrative 引用位置**：§6 baseline 報告數據時

### H4. Dense X Retrieval / Proposition
- **Citation**：Chen, T., 等 (2024). Dense X Retrieval: What Retrieval Granularity Should We Use? `[CONFIRM venue]`
- **Narrative 引用位置**：§5（proposition 作為記憶單元的依據）

---

## I. 其他輔助對手（cite 為主）

### I1. LightMem
- **Citation**：Fang, J., 等 (2026). LightMem: Lightweight and Efficient Memory-Augmented Generation. *ICLR 2026* (arXiv:2510.18866).
- **核心**：Atkinson-Shiffrin model + soft updates
- **Narrative 引用位置**：§2.1 附帶（concurrent work）

### I2. MIRIX
- **Citation**：Wang, Y., & Chen, X. (2025). MIRIX: Multi-Agent Memory System for LLM-Based Agents. *arXiv preprint arXiv:2507.07957*.
- **Narrative 引用位置**：§2.1 附帶

### I3. AgeMem
- **Citation**：(Author TBC). (2026). Agentic Memory: Operations as Tools. `[CONFIRM]`
- **Narrative 引用位置**：§2.1 附帶

### I4. AriGraph
- **Citation**：Anokhin, P., 等 (2024). AriGraph: Learning Knowledge Graph World Models with Episodic Memory for LLM Agents. *Proceedings of IJCAI 2025* (arXiv:2407.04363).
- **Narrative 引用位置**：§2.1 附帶

### I5. MemGPT
- **Citation**：Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., & Gonzalez, J. E. (2024). MemGPT: Towards LLMs as Operating Systems. *arXiv preprint arXiv:2310.08560*.
- **Narrative 引用位置**：§2 引言

### I6. MemoryOS
- **Citation**：Kang, 等 (2025). Memory OS of AI Agent. *Proceedings of EMNLP 2025*.
- **URL**：https://aclanthology.org/2025.emnlp-main.1318.pdf
- **Narrative 引用位置**：§2 引言

### I7. GraphRAG
- **Citation**：Edge, D., 等 (2024). From Local to Global: A Graph RAG Approach to Query-Focused Summarization. *arXiv preprint arXiv:2404.16130*.
- **Narrative 引用位置**：§2 引言

### I8. RAPTOR
- **Citation**：Sarthi, P., 等 (2024). RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval. *ICLR 2024*.
- **Narrative 引用位置**：§2 引言

---

## J. 整理規則與待辦

### 引用格式建議
- NLP 場（ACL/EMNLP/NAACL）：用 ACL Anthology bib
- ML 場（NeurIPS/ICLR/ICML）：用作者-年份標準
- arXiv only：標 *arXiv preprint arXiv:XXXX*

### 待確認資訊
所有 `[CONFIRM ...]` 標記需要：
1. 從 ACL Anthology / OpenReview / DBLP 確認作者與 venue
2. 從原始 PDF 確認 page numbers
3. 確認最新 arXiv 版本號

### Project 內現有的 PDF（請優先驗證）
- `Zep_A_Temporal_Knowledge_Graph_Architecture_for_Agent_Memory.pdf`（→ A1）
- `Mem0_Building_ProductionReady_AI_Agents_with_Scalable_LongTerm_Memory_3.pdf`（→ A2）
- `HippoRAG_2_From_RAG_to_Memory_NonParametric_Continual_Learning_for_Large_Language_Models.pdf`（→ B1）
- `PropRAG_Guiding_Retrieval_with_Beam_Search_over_Proposition_Paths.pdf`（→ B2）
- `Evaluating_Memory_in_LLM_Agents_via_Incremental_MultiTurn_Interactions.pdf`（→ E1 MemoryAgentBench）
- `LongMemEval_Benchmarking_Chat_Assistants_on_LongTerm_Interactive_Memory_2.pdf`（→ E7）
- `Knowledge_Conflicts_for_LLMs_A_Survey.pdf`（→ G1）

### v4 → v5 變動 Summary（文獻軸對齊，依 memory_systems_conflict_comparison.md）
- ✓ **G1 Knowledge Conflicts Survey 升級為 ⭐⭐⭐ 核心文獻軸**：採用其 pre-hoc/post-hoc 分類取代自創 A/B/C 派系
- ✓ **E1 MemoryAgentBench 升級為 ⭐⭐⭐**：venue 改為 ICLR 2026；補 Table 3 完整數字（FC-MH ≤ 5%）；補 Appendix K.2 prompt-fix 失敗證據
- ✓ **E5 MQUAKE 升級為 ⭐**：明確標註為 FC-MH 構造基礎，與 LLM prior bias 議題連結
- ✓ 對手分類用 pre-hoc / post-hoc 軸取代 A/B/C 派系
- ✓ Mem0g 的 paper claim "mark as invalid" 與 vendored impl "DELETE r" 雙層 disclosure

### v3 → v4 變動 Summary（baseline 對齊 disclosure）
- ✓ A1 (Zep) 加註：cloud SDK vs Graphiti OSS 的選擇說明
- ✓ A1' 新增 Graphiti 作為 Zep 的官方 OSS 實作引用
- ✓ A2 (Mem0/Mem0g) 加註：v2 vendored 是 hard delete，與論文 §2.2 描述不一致；mem0 upstream v3 已移除圖記憶
- ✓ 派系 A 細分為 A1 destructive (mem0g vendored) / A2 non-destructive (Zep, A-MEM)
- ✓ Disclosure 語調：「representative instance of [our category]」而非「對手實作偏離論文」

### v2 → v3 變動 Summary
- ✓ 對手切分從兩派系（A/B）改為三派系（A/B/C）
- ✓ §F「empirical-driven 風格參考」鬆綁，標註為「候選風格 fallback」
- ✓ 新增 §F'「Phase 3 候選方向相關引用」：Self-RAG, IRCoT, ReAct, Chain-of-Note 等
- ✓ 派系 C 補充細節：子場景假設、適配 FC-MH 的失敗點
- ✓ 同盟論文 D1 升級為 ⭐
- ✓ 知識衝突 Survey 升級為 ⭐
