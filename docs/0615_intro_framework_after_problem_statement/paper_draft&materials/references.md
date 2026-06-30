# Bibliography — Robust Knowledge Update for LLM Agent Memory

> 整理此論文 introduction 中所有引用的文獻，包含：venue、論文連結、開源狀態、在我們論文中的用途、所需熟悉度。
> 最後更新：2026-06-23

---

## Familiarity Tier 說明

| Tier | 名稱 | 熟悉度要求 | 適用情境 |
|---|---|---|---|
| **T1** | 流派核心 | 要懂 method 細節 (algorithm, architecture, 跟我們的差異) | 對手方法、unified pipeline 來源 |
| **T2** | 背景論述 | 要清楚 motivation 和定位 | KU benchmark、taxonomy framing |
| **T3** | 論點佐證 | 知道引用 context 跟 key claim 即可 | Privacy/cost 軸線 |

---

## Citation Status 速查

> 2026-06-23 重新審視所有候選引用，篩選為「intro 實際使用」與「保留作為背景但未使用」兩類。

### ✅ Intro 實際使用 (16 條，最終版)

A-Mem, MemGPT, LightMem, MemoryOS, Mem0, Zep, MemoryAgentBench, Survey 2026, LongMemEval, MemBench, BEAM, MemoryBank, SlimLM, CoGenesis, A Middle Path (Huang et al.), FrugalGPT

### ❌ 評估後不使用 (保留在此文件作 reference)

| 引用 | 不使用原因 |
|---|---|
| **MIRIX** | Multi-agent 非本研究範圍 + arXiv preprint (非 conference-accepted) |
| **Xiong et al. (cascading errors)** | arXiv preprint (under review)，無強力 conference-accepted 替代;改用結構性論證 + LightMem §5.6 quote |
| **AgentDebug** | 從 ICLR 2026 撤回 (withdrawn) |
| **SLM Future of Agentic AI (NVIDIA)** | arXiv preprint;cost-constrained 軸線已由 A-Mem + FrugalGPT 充分支撐 |

---

# T1 · 流派核心 (Methodological Foundations)

## Passive 派 (Storage-Focused Methods)

### [P1] MemoryBank — Ebbinghaus Forgetting Curve

- **Citation**: Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2024). MemoryBank: Enhancing Large Language Models with Long-Term Memory. *AAAI 2024*, 38(17), 19724–19731.
- **Venue Status**: ✅ **AAAI 2024**
- **arXiv**: https://arxiv.org/abs/2305.10250
- **GitHub**: https://github.com/zhongwanjun/MemoryBank-SiliconFriend (~700 stars)
- **用途**: Passive 派代表 — 受人類記憶遺忘曲線啟發的衰減機制
- **熟悉度**: **T1**
- **Citation Status**: ✅ 使用 (intro [12])
- **Key takeaway for us**: 經典的「sub-symbolic decay-based」passive update — 沒有對 fact validity 做 conflict detection，只用時間衰減模擬遺忘

### [P2] MemGPT — OS-style Hierarchical Memory

- **Citation**: Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., & Gonzalez, J. E. (2023). MemGPT: Towards LLMs as Operating Systems. *arXiv preprint*.
- **Venue Status**: ⚠️ **arXiv preprint** (廣為引用但未被主流會議正式接受；後續發展成 Letta 商業框架)
- **arXiv**: https://arxiv.org/abs/2310.08560
- **GitHub**: https://github.com/letta-ai/letta (formerly MemGPT, ~16k stars)
- **用途**: Passive 派代表 — 雙層記憶 (main context + archival/recall storage) + function-call retrieval
- **熟悉度**: **T1**
- **Citation Status**: ✅ 使用 (intro [2]) — 雖然是 arXiv preprint，但領域內標準引用 (~3k citations)，且 MemGPT 是 OS-style hierarchical memory 的原型
- **Key takeaway for us**: 引入 OS-style memory paging 概念，但 update 機制著重 storage organization 不處理 fact conflict

### [P3] MemoryOS — Three-Tier STM/MTM/LPM ⭐

- **Citation**: Kang, J., Ji, M., Zhao, Z., & Bai, T. (2025). MemoryOS of AI Agent. *EMNLP 2025*, pp. 25972–25981.
- **Venue Status**: ✅ **EMNLP 2025 Main Conference**
- **ACL Anthology**: https://aclanthology.org/2025.emnlp-main.1326/
- **arXiv**: https://arxiv.org/abs/2506.06326
- **GitHub**: https://github.com/BAI-LAB/MemoryOS (~1.7k stars)
- **用途**: ⭐ **我們 unified Storage–Update–Retrieval–Generation pipeline framing 的主要來源** — 介紹模組化 memory 設計
- **熟悉度**: **T1 (最重要)**
- **Citation Status**: ✅ 使用 (intro [4])
- **Key takeaway for us**: 三層 STM/MTM/LPM + eviction policies；架構複雜但 update module 仍是 organization-focused

### [P4] A-Mem — Agentic Memory with Zettelkasten

- **Citation**: Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). A-MEM: Agentic Memory for LLM Agents. *NeurIPS 2025*.
- **Venue Status**: ✅ **NeurIPS 2025 Poster**
- **OpenReview**: https://openreview.net/forum?id=FiM0M8gcct
- **arXiv**: https://arxiv.org/abs/2502.12110
- **GitHub (reproduction)**: https://github.com/WujiangXu/A-mem (~814 stars)
- **GitHub (system)**: https://github.com/agiresearch/A-mem
- **用途**: Passive 派代表 — dynamic note network + cross-note linking
- **熟悉度**: **T1**
- **Citation Status**: ✅ 使用 (intro [1]) — 多次引用 (real-world deployment + passive 代表 + cost-constrained evidence)
- **Key takeaway for us**: 證明 passive 派也用 cost-constrained models (paper 大量用 gpt-4o-mini)；他們的 update 動態生成 note 但仍不處理 cross-note version conflict

### [P5] MIRIX — Six Memory Components ❌

- **Citation**: Wang, Y., & Chen, X. (2025). MIRIX: Multi-Agent Memory System for LLM-Based Agents. *arXiv preprint*.
- **Venue Status**: ⚠️ **arXiv preprint** (under review)
- **arXiv**: https://arxiv.org/abs/2507.07957
- **GitHub**: https://github.com/Mirix-AI/MIRIX (~3.53k stars)
- **Project page**: https://mirix.io
- **用途**: 原本計畫作為 Passive 派代表
- **熟悉度**: **T2**
- **Citation Status**: ❌ **不使用** (2026-06-23 決定)
  - **原因**: Multi-agent 非本研究範圍 + arXiv preprint (非 conference-accepted)
  - **可能在其他章節用途**: Discussion 章節若要對比 multi-agent paradigm 可考慮提及

---

## Proactive 派 (Conflict-Aware Methods)

### [P6] Mem0 — Coupled Update with Production Focus ⭐

- **Citation**: Chhikara, P., Khant, D., Aryan, S., Singh, T., & Yadav, D. (2025). Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory. *ECAI 2025*. DOI: 10.3233/FAIA251160
- **Venue Status**: ✅ **ECAI 2025 Published** (Frontiers in AI Vol. 413, pp. 2993–3000)
- **arXiv**: https://arxiv.org/abs/2504.19413
- **GitHub**: https://github.com/mem0ai/mem0 (~30k+ stars)
- **用途**: ⭐ **Coupled Update 代表方法** — 單一 LLM call 同時決定並執行 ADD/UPDATE/DELETE/NOOP
- **熟悉度**: **T1 (對手 paper, 要熟讀 Algorithm 1)**
- **Citation Status**: ✅ 使用 (intro [5])
- **Key takeaway for us**: 是 destructive write-time commit 的最 representative case — 一旦 LLM 判錯就無可挽回

### [P7] LightMem — Coupled Update + Sleep-time ⭐

- **Citation**: Fang, J., Deng, X., Xu, H., Jiang, Z., Tang, Y., Xu, Z., ... & Zhang, N. (2025). LightMem: Lightweight and Efficient Memory-Augmented Generation. *ICLR 2026*.
- **Venue Status**: ✅ **ICLR 2026 Accepted** (announced 2026-01-26)
- **OpenReview**: https://openreview.net/forum?id=dyJ0GWpjJB
- **arXiv**: https://arxiv.org/abs/2510.18866
- **GitHub**: https://github.com/zjunlp/LightMem
- **用途**: ⭐ **Coupled Update + cost-efficient** 代表方法 — Atkinson–Shiffrin 三階段架構
- **熟悉度**: **T1 (對手 paper, §5.6 quote 是我們論述核心 rhetorical move)**
- **Citation Status**: ✅ 使用 (intro [3]) — §5.6 self-acknowledgment quote 是我們論證 cascading-error-style 主張的核心 evidence
- **Key takeaway for us**:
  - §5.6 自承: *"an LLM might incorrectly interpret [related but not contradictory pieces] as a conflict and delete the older memory entry, leading to irreversible information loss"* — 用對手自己的話支持我們的 critique
  - 跟我們 deployment scenario 高度重疊 (cost-efficient)

### [P8] Zep — Decoupled Update with Knowledge Graph ⭐

- **Citation**: Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). Zep: A Temporal Knowledge Graph Architecture for Agent Memory. *arXiv preprint*.
- **Venue Status**: ⚠️ **arXiv preprint** (商業公司 Zep AI 出品，未投會議)
- **arXiv**: https://arxiv.org/abs/2501.13956
- **GitHub (核心引擎 Graphiti)**: https://github.com/getzep/graphiti (~5k+ stars)
- **用途**: ⭐ **Decoupled Update 代表方法** — LLM 只 emit categorical labels (contradicts/duplicates)，由 deterministic system 執行 graph mutation
- **熟悉度**: **T1 (對手 paper, 要熟讀 Edge Resolution 部分)**
- **Citation Status**: ✅ 使用 (intro [6]) — 雖是 arXiv preprint，但是 Decoupled Update 唯一具體代表，且是我們明確 "extend from" 的工作。Graphiti 開源 codebase 廣為使用。
- **Key takeaway for us**: Decoupled execution 減少 execution-side risk，但 LLM 給的 label 仍是 destructive commit 的 sole source of error — 跟 Coupled 共享 commit 不可逆問題

---

# T2 · 背景論述 (Contextual Foundations)

## KU Benchmarks (確立 KU 為 community 公認 core ability)

### [B1] LongMemEval — First to Define KU as Core Ability

- **Citation**: Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., & Yu, D. (2025). LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory. *ICLR 2025 Poster*.
- **Venue Status**: ✅ **ICLR 2025 Poster**
- **OpenReview**: https://openreview.net/forum?id=pZiyCaVuti
- **arXiv**: https://arxiv.org/abs/2410.10813
- **GitHub**: https://github.com/xiaowu0162/LongMemEval
- **用途**: KU 重要性的 anchor citation — 五個 core abilities 之一就是 "Knowledge Updates"
- **熟悉度**: **T2**
- **Citation Status**: ✅ 使用 (intro [9])
- **Key takeaway for us**: 引用「commercial chat assistants and long-context LLMs showing a 30% accuracy drop on memorizing information across sustained interactions」這個 stat

### [B2] MemBench — Multi-aspect Memory Evaluation

- **Citation**: Tan, H., Zhang, Z., Ma, C., Chen, X., Dai, Q., & Dong, Z. (2025). MemBench: Towards More Comprehensive Evaluation on the Memory of LLM-based Agents. *Findings of ACL 2025*, pp. 19336–19352.
- **Venue Status**: ✅ **ACL 2025 Findings**
- **ACL Anthology**: https://aclanthology.org/2025.findings-acl.989/
- **arXiv**: https://arxiv.org/abs/2506.21605
- **GitHub**: https://github.com/import-myself/Membench
- **用途**: KU benchmark 強化引用 (跟 LongMemEval/BEAM 並列)
- **熟悉度**: **T2**
- **Citation Status**: ✅ 使用 (intro [10])

### [B3] BEAM — Long-Context Memory Benchmark up to 10M Tokens

- **Citation**: Tavakoli, M., Salemi, A., Ye, C., Abdalla, M., Zamani, H., & Mitchell, J. R. (2026). Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs. *ICLR 2026 Poster*.
- **Venue Status**: ✅ **ICLR 2026 Poster**
- **OpenReview**: https://openreview.net/forum?id=y59hf5lrMn
- **Project Page**: https://mohammadtavakoli78.github.io/beam-light/
- **GitHub**: https://github.com/mohammadtavakoli78/BEAM
- **用途**: Long-term memory benchmark anchor，10 memory abilities 含 conflict resolution
- **熟悉度**: **T2**
- **Citation Status**: ✅ 使用 (intro [11])

### [B4] MemoryAgentBench — Incremental Multi-Turn Memory Evaluation ⭐

- **Citation**: Hu, Y., Wang, Y., & McAuley, J. (2026). Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions. *ICLR 2026*.
- **Venue Status**: ✅ **ICLR 2026**
- **OpenReview**: https://openreview.net/forum?id=DAGUEt4ya9
- **arXiv**: https://arxiv.org/abs/2507.05257
- **GitHub**: https://github.com/HUST-AI-HYZ/MemoryAgentBench
- **用途**: ⭐ **我們 evaluation setup 來源 (FactConsolidation Single-Hop)**
- **熟悉度**: **T2 (要熟讀 FC-SH 子集設計)**
- **Citation Status**: ✅ 使用 (intro [7]) — 多次引用 (external memory + retrieval surfaces outdated + KU benchmark + cost-constrained §I)

### [B5] Survey 2026 — Evolution of LLM Agent Memory

- **Citation**: Luo, J., Tian, Y., Cao, C., Luo, Z., Lin, H., Li, K., ... & Ma, J. (2026). From Storage to Experience: A Survey on the Evolution of LLM Agent Memory Mechanisms. *ACL 2026 Findings*.
- **Venue Status**: ✅ **ACL 2026 Findings** (also presented at ICLR Workshop MemAgents)
- **GitHub**: https://github.com/FeishuLuo/Evolving-LLM-Agent-Memory-Survey
- **用途**: Taxonomy framing 來源 (§3.2 temporal validity)
- **熟悉度**: **T2**
- **Citation Status**: ✅ 使用 (intro [8])

---

# T3 · 論點佐證 (Constrained Deployment)

## Privacy-Sensitive Deployment

### [C1] SlimLM — On-Device Small LM

- **Citation**: Pham, T. M., Nguyen, P. T., Yoon, S., Lai, V. D., Dernoncourt, F., & Bui, T. (2025). SlimLM: An Efficient Small Language Model for On-Device Document Assistance. *ACL 2025 System Demonstrations*, pp. 436–447.
- **Venue Status**: ✅ **ACL 2025 System Demonstrations**
- **用途**: T3 — On-device deployment 軸線
- **熟悉度**: **T3**
- **Citation Status**: ✅ 使用 (intro [13])

### [C2] CoGenesis — Cloud + On-Device SLM Collaboration

- **Citation**: Zhang, K., Wang, J., Hua, E., Qi, B., Ding, N., & Zhou, B. (2024). CoGenesis: A Framework Collaborating Large and Small Language Models for Secure Context-Aware Instruction Following. *ACL 2024 Main Conference*.
- **Venue Status**: ✅ **ACL 2024 Main Conference** ⭐ (注意：是 Main Conference 不是 Findings)
- **ACL Anthology**: https://aclanthology.org/2024.acl-long.235/
- **arXiv**: https://arxiv.org/abs/2403.03129
- **GitHub**: https://github.com/TsinghuaC3I/CoGenesis
- **用途**: T3 — Privacy-sensitive collaboration framework
- **熟悉度**: **T3**
- **Citation Status**: ✅ 使用 (intro [14])
- **Key takeaway for us**: 提供「privacy → 分離 cloud LLM + on-device SLM」的 architectural pattern

### [C3] A Middle Path / SOLID — On-Premises LLM Deployment

- **Citation**: Huang, H., Li, Y., Jiang, B., Jiang, B., Liu, L., Liu, Z., Sun, R., & Liang, S. (2025). A Middle Path for On-Premises LLM Deployment: Preserving Privacy Without Sacrificing Model Confidentiality. *EMNLP 2025 Main Conference*, pp. 8321–8359.
- **Venue Status**: ✅ **EMNLP 2025 Main Conference**
- **ACL Anthology**: https://aclanthology.org/2025.emnlp-main.420/
- **arXiv**: https://arxiv.org/abs/2410.11182
- **DOI**: 10.18653/v1/2025.emnlp-main.420
- **用途**: T3 — On-premises LLM deployment 軸線
- **熟悉度**: **T3**
- **Citation Status**: ✅ 使用 (intro [15])
- **Key takeaway for us**: 確立「privacy-sensitive users require on-premises deployment」這個 framing

---

## Cost-Constrained Deployment

### [C4] FrugalGPT — Cost-Aware LLM Cascade ⭐

- **Citation**: Chen, L., Zaharia, M., & Zou, J. (2024). FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance. *Transactions on Machine Learning Research (TMLR) 2024*.
- **Venue Status**: ✅ **TMLR 2024 (Featured Certification)** ⭐
- **OpenReview**: https://openreview.net/forum?id=cSimKw5p6R
- **arXiv**: https://arxiv.org/abs/2305.05176
- **GitHub**: https://github.com/stanford-futuredata/FrugalGPT
- **用途**: T3 — Cost-constrained 部署 anchor citation
- **熟悉度**: **T3**
- **Citation Status**: ✅ 使用 (intro [16])
- **Key takeaway for us**: 引用「fees that can differ by two orders of magnitude」這個 cost gap argument

### [C5] SLM Future of Agentic AI — NVIDIA Position Paper ❌

- **Citation**: Belcak, P., Heinrich, G., Diao, S., Fu, Y., Dong, X., Muralidharan, S., Lin, Y. C., & Molchanov, P. (2025). Small Language Models are the Future of Agentic AI. *arXiv preprint* (NVIDIA Research position paper).
- **Venue Status**: ⚠️ **arXiv preprint, Under Review**
- **arXiv**: https://arxiv.org/abs/2506.02153
- **Project page**: https://research.nvidia.com/labs/lpr/slm-agents/
- **用途**: 原本作為 SLM industry-position 強化引用
- **熟悉度**: **T3**
- **Citation Status**: ❌ **不使用** (2026-06-23 決定)
  - **原因**: arXiv preprint;cost-constrained 軸線已由 A-Mem [1] + MemoryAgentBench §I [7] + FrugalGPT [16] 三條 conference-accepted 引用充分支撐

---

## Error Propagation Evidence (已不使用)

### [C6] Xiong et al. — Memory Management & Experience-Following ❌

- **Citation**: Xiong, Z., Lin, Y., Xie, W., He, P., Liu, Z., Tang, J., Lakkaraju, H., & Xiang, Z. (2025). How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior. *arXiv preprint*.
- **Venue Status**: ⚠️ **arXiv preprint, Under Review** (Harvard + Michigan State + UGA)
- **arXiv**: https://arxiv.org/abs/2505.16067
- **用途**: 原本作為 cascading error 實證 evidence
- **熟悉度**: **T3**
- **Citation Status**: ❌ **不使用** (2026-06-23 決定)
  - **原因**: arXiv preprint;偏好 conference-accepted 引用
  - **替代論證**: Para 4 改用結構性論證 (low judgment quality + destructive commit → irreversible accumulation)，並透過 Para 3 已 cite 的 LightMem §5.6 quote 提供來自子流派內部的 evidence

### [C7] AgentDebug — Cascading Failure Taxonomy ❌

- **Citation**: Liu, Y., et al. (2025). Where LLM Agents Fail and How They can Learn From Failures. *arXiv preprint*.
- **Venue Status**: ⚠️ **arXiv preprint** (原投 ICLR 2026，已於 2026-01-05 **撤回 Withdrawn**)
- **OpenReview**: https://openreview.net/forum?id=PFR4E8583W (status: Withdrawn)
- **arXiv**: https://arxiv.org/abs/2509.25370
- **GitHub**: https://github.com/ulab-uiuc/AgentDebug
- **用途**: 原本作為 cascading failure taxonomy 補強引用
- **熟悉度**: **T3**
- **Citation Status**: ❌ **不使用** (2026-06-23 決定)
  - **原因**: 從 ICLR 2026 撤回 (withdrawn)，引用 withdrawn 論文有學術風險

---

# 引用優先級總表 (intro 最終版)

| Section in Intro | 主軸引用 (新編號) |
|---|---|
| Para 1: KU motivation | A-Mem [1], MemGPT [2], LightMem [3], MemoryOS [4], Mem0 [5], Zep [6], MemoryAgentBench [7], Survey [8], LongMemEval [9], MemBench [10], BEAM [11] |
| Para 2: Passive 派 | MemoryBank [12], MemGPT [2], MemoryOS [4], A-Mem [1] |
| Para 3: Proactive 派 | Mem0 [5], LightMem [3] (含 §5.6 quote), Zep [6] |
| Para 4: Constrained deployment | SlimLM [13], CoGenesis [14], A Middle Path [15] (privacy); A-Mem [1], MemoryAgentBench §I [7], FrugalGPT [16] (cost) |
| Para 5: Our method | Zep [6] (extend from), MemoryOS [4] (pipeline framing) |

---

# Important Corrections (歷史校正記錄)

| Reference | 之前的 claim | 正確的 status |
|---|---|---|
| CoGenesis | "ACL 2024 Findings" | ✅ **ACL 2024 Main Conference** (更強 venue) |
| AgentDebug | "ICLR 2026 submission" | ⚠️ **Withdrawn from ICLR 2026, now arXiv only** → 已決定不使用 |
| Mem0 | (僅標 arXiv) | ✅ **ECAI 2025 published with DOI** |
| FrugalGPT | (不確定 venue) | ✅ **TMLR 2024 Featured Certification** |
| MemGPT | (假設 ICML/ICLR accepted) | ⚠️ **arXiv preprint only** (廣為引用但未正式接受) |
| A-Mem | "(2026)" 或 "Advances in NeurIPS, 38, 17577-17604" | ✅ **正式年份為 NeurIPS 2025** (conference year)，引用統一用 2025 |

---

# Open Source 完整清單 (與我們直接相關的流派 + benchmarks)

| Paper | GitHub | Stars (approx) | License |
|---|---|---|---|
| **Mem0** | github.com/mem0ai/mem0 | 30k+ | Apache 2.0 |
| **LightMem** | github.com/zjunlp/LightMem | (新) | MIT |
| **Zep (Graphiti)** | github.com/getzep/graphiti | 5k+ | Apache 2.0 |
| **MemoryOS** | github.com/BAI-LAB/MemoryOS | 1.7k | MIT |
| **A-Mem (NeurIPS code)** | github.com/WujiangXu/A-mem | 814 | MIT |
| **A-Mem (system)** | github.com/agiresearch/A-mem | (separate) | MIT |
| **MemGPT/Letta** | github.com/letta-ai/letta | 16k | Apache 2.0 |
| **MemoryBank** | github.com/zhongwanjun/MemoryBank-SiliconFriend | 700 | (check) |
| **CoGenesis** | github.com/TsinghuaC3I/CoGenesis | small | (check) |
| **FrugalGPT** | github.com/stanford-futuredata/FrugalGPT | small | (check) |
| **LongMemEval** | github.com/xiaowu0162/LongMemEval | (medium) | (check) |
| **MemBench** | github.com/import-myself/Membench | small | (check) |
| **MemoryAgentBench** | github.com/HUST-AI-HYZ/MemoryAgentBench | small | (check) |
| **BEAM** | github.com/mohammadtavakoli78/BEAM | small | (check) |
| **Survey 2026** | github.com/FeishuLuo/Evolving-LLM-Agent-Memory-Survey | small | (resource list) |

---

# Reading Priority for 你 (Master's Thesis Preparation)

## Week 1: 必讀 (對手 papers + unified pipeline 來源)
1. **MemoryOS** (EMNLP 2025) — 我們的 pipeline framing 母體
2. **LightMem** (ICLR 2026) — 對手代表 + §5.6 quote
3. **Mem0** (ECAI 2025) — Coupled Update 代表
4. **Zep / Graphiti** (arXiv) — Decoupled Update 代表

## Week 2: 中度閱讀 (passive 派 + KU benchmark)
5. **MemoryAgentBench** (ICLR 2026) — KU benchmark + 我們 evaluation setup 來源
6. **LongMemEval** (ICLR 2025) — KU 定義 anchor
7. **A-Mem** (NeurIPS 2025) — Passive 派 + cost evidence

## Week 3: 略讀 (背景 + 論點佐證)
8. **Survey 2026** — taxonomy 章節 §3.2
9. **MemGPT** — OS-style memory anchor
10. **MemoryBank** — Ebbinghaus decay anchor

## 引用即可 (T3 references — 不需深讀)
- Privacy: SlimLM, CoGenesis, A Middle Path
- Cost: FrugalGPT

---

# Notes & Caveats

- **MemGPT 的引用注意**: 因為它是 arXiv preprint 而非 conference paper，正式 thesis 中要小心 framing。可以引用為「the MemGPT framework (Packer et al., 2023)」而非「the MemGPT paper accepted at...」。
- **Zep / Graphiti 區分**: Zep 是 paper 名稱，Graphiti 是 underlying engine 的 GitHub repo 名稱。引用時 paper 名用 Zep，code reference 用 Graphiti。Zep 雖是 arXiv preprint 但是 Decoupled Update 唯一具體代表，且我們明確 "extend from"，所以保留引用。
- **Mem0 的雙身分**: arXiv 上是 preprint，但 ECAI 2025 已正式 published with DOI — 引用時用 ECAI version。
- **A-Mem 年份**: 統一用 NeurIPS 2025 (conference year)，不用 proceedings 出版年。
- **如未來找到 cascading error 的 conference-accepted 文獻**：可考慮加回 Para 4。目前的論證已用結構性敘述充分支撐。
