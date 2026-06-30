LLM-based agents are increasingly deployed in real-world applications [1], where they interact with users across many sessions. Because LLMs themselves are stateless and operate within fixed-length context windows [2]–[4], maintaining continuity over extended interactions requires an external memory that persists information across turns and sessions [5]–[7]. As such memory grows over time, an unavoidable property emerges: many of the stored facts have a temporal validity that changes during the conversation [8, Sec. 3.2]. The same fact may therefore appear in memory as multiple inconsistent versions, and a query that retrieves them indiscriminately returns outdated content alongside the current one [7], misleading inference. This problem—identifying and adopting the most current version of a fact—is termed **Knowledge Update (KU)**, and is identified as a core ability of long-term memory agents by recent benchmarks [7], [9]–[11].

The majority of existing memory-augmented agents are *passive* with respect to KU. Their update mechanisms target storage, structure, or organization—but not the temporal validity of facts. MemoryBank [12] manages decay through an Ebbinghaus-inspired forgetting curve; MemGPT [2] and MemoryOS [4] organize memory into hierarchical tiers with eviction policies; A-Mem [1] maintains an evolving network of atomic notes. All of these designs share a common gap: they do not detect when a newly arriving fact contradicts or supersedes an existing one. As a result, outdated and current versions accumulate together in the memory bank, and retrieval surfaces both—inference therefore cannot reliably reflect the latest state of the world.

A second line of work makes the memory module *proactive* about KU by resolving potential conflicts at write-time. Two sub-approaches are dominant. **Coupled Update** designs, exemplified by Mem0 [5] and LightMem [3], invoke a single LLM call that both decides the operation and executes it (ADD / UPDATE / DELETE / NOOP); the LLM acts as both judge and operator. **Decoupled Update** designs, exemplified by Zep [6], have the LLM emit only categorical labels (*contradicts*, *duplicates*) and let a deterministic system perform the actual mutation. Both designs improve over the passive baseline by attempting to detect and remove staleness at write-time. Both, however, share a structural property: any LLM misjudgment—whether the LLM acts as judge or as labeler—is committed irreversibly into the memory. LightMem's own discussion [3, Sec. 5.6] acknowledges this directly: *"an LLM might incorrectly interpret [related but not contradictory pieces] as a conflict and delete the older memory entry, leading to irreversible information loss."*

The two paradigms therefore expose a *shared* structural limitation: the fate of KU rests on a single write-time judgment, and the memory bank is updated destructively whether that judgment was correct or not. This limitation becomes critical under *constrained deployment*. Privacy-sensitive applications increasingly require on-device inference, where only small, frozen language models are viable alternatives to server-based APIs [13]–[15]. In parallel, cost-constrained production deployments increasingly rely on small, low-cost API models such as GPT-4o-mini [1], [7, Sec. I], [16]. In both scenarios, the agent operates with a small, frozen LLM whose judgment quality is markedly lower than that of frontier models. When this lower-quality judgment is combined with destructive write-time commits, misjudgments accumulate irreversibly in the memory bank. Since the LLM is frozen and cannot be fine-tuned, this failure mode cannot be mitigated by improving the LLM itself; the only remaining design space is how the system uses the LLM—specifically, at what stage it is invoked, and over what scope its judgment is required.

The fundamental difficulty of proactive methods lies in this asymmetry: they require LLM-based judgment over all possible memory pairings at write-time—when no query context exists—and any such judgment is irreversibly committed. At query-time, however, only the facts the query touches require resolution, not all possible pairings across the memory bank. We therefore argue that **KU should be a query-time concern, not a write-time commitment**. Based on this claim, we propose a memory architecture organized around two structural commitments: first, **Conservative Writes**—at write-time, no cross-item LLM judgment is invoked, and all versions are preserved; second, **Query-Time KU Resolution**—KU resolution is performed only when triggered by a query, and only over the facts that query touches. Our design extends the Decoupled Update line of thinking—exemplified by Zep [6]—to its structural limit: Zep separates memory mutation from the LLM and lets a deterministic system perform it, but the LLM is still required to make categorical judgments over the relation between an incoming entry and existing memory; we further eliminate cross-item LLM judgment from write-time entirely. Our framework instantiates the same unified Storage–Update–Retrieval–Generation pipeline [4] as existing memory-augmented agents, but introduces three component-level redesigns: an Update module that does not rely on cross-item judgment, a unified memory bank that preserves all versions, and a Retrieval module augmented with identity grouping and temporal resolution. The result is a memory architecture whose reliability does not depend on the correctness of any cross-item write-time judgment, because no such judgment is ever made: memory faithfully preserves what was written, and KU is resolved only when triggered by a query.

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