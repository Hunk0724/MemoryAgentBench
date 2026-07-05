# References — Robust Knowledge Update for LLM Agent Memory

> **單一事實來源 (single source of truth)**：本檔以文獻總表 (literature master table) 呈現，取代舊版 references.md 的分散書目。
> **最後更新**：2026-07-04（對齊 intro v6 / related_work v2 / vocabulary v2）
> **結構**：A 分類總表(四類×用途) → B 論點層對照(論點→文獻) → C 完整書目(venue/連結/熟悉度) → D 邊界與排除 → E venue 校正/開源/閱讀序。
> **熟悉度**：T1 對手/最相關,逐段熟讀;T2 背景/基準,懂設計即可;T3 動機軸線,懂 takeaway 即可。

---

# A. 分類總表（四類 × 用途）

## 類別 1：領域 top / 始祖 / 頂會（畫版圖,不打）

| # | 論文 | Venue | 放哪章 | 熟悉度 | 一句話用途 | 查證 |
|---|---|---|---|---|---|---|
| [2] | MemGPT | arXiv 2023 (影響力=始祖) | intro passive；RW 2.1 | T2 | context window as virtual memory 原型 | ✅ |
| [12] | MemoryBank | AAAI 2024 | intro passive；RW 2.1 | T2 | retrieval-based memory 始祖;Ebbinghaus 衰減=passive | ✅ |
| [1] | A-Mem | NeurIPS 2025 | intro passive；RW 2.1 | T2 | 演化式原子筆記網路;亦作 cost/deployment 論據 | ✅ |
| [4] | MemoryOS | EMNLP 2025 | intro；RW 2.1 | T2 | Storage–Update–Retrieval–Generation 流程來源 | ✅ |

## 類別 2：跟自己最相關 + 有會議/期刊（直接對手,T1）

| # | 論文 | Venue | 放哪章 | 熟悉度 | 一句話用途 | 查證 |
|---|---|---|---|---|---|---|
| [5] | Mem0 | ECAI 2025 | intro proactive；RW 2.1；method 對照 | **T1** | Coupled Update 代表;破壞性更新=主對手 baseline | ✅ +機制文件逐行 |
| [3] | LightMem (Fang et al.) | ICLR 2026 | intro proactive；RW 2.1;case 3a | **T1** | Coupled;§5.6 自承「誤判→不可逆刪除」=最強 move | ✅ §5.6 逐字 |
| [6] | Zep | arXiv 2025 (Graphiti 業界標竿) | intro proactive；RW 2.1;method extend-from | **T1** | Decoupled 代表;我們延伸並超越(移除跨筆判斷) | ✅ +機制文件 |
| [18] | Zhang et al. (SLM memory, 亦名 LightMem) | ACL 2026 | RW 2.1;case 3a;intro 動機 | **T1** | 最近鄰:同樣小模型記憶但仍 write-time 判斷;錯誤注入=唯一 conf-accepted「write 錯→下游污染」實證 | ✅ 數字核過;⚠️ 同名 |

⚠️ **[3] 與 [18] 同名 "LightMem"**：不同論文的系統撞名。全文規則:裸名 LightMem 專指 [3];[18] 一律 "Zhang et al. [18]",首次提及加 footnote 說明同名異作。

## 類別 3a：case study 論據——「write-time 判斷錯→累積→有害」(引文獻)

| # | 論文 | Venue | 放哪章 | 熟悉度 | 一句話用途 | 查證 |
|---|---|---|---|---|---|---|
| [3] | LightMem §5.6 | ICLR 2026 | intro;RW 2.1 | T1 | 對手自承:誤判相關但不矛盾者→刪舊→不可逆丟失 | ✅ 逐字 |
| [18] | Zhang et al. 錯誤注入 | ACL 2026 | intro;RW 2.1 | T1 | noisy writes→持續污染後續檢索;MemGPT SH-F1 GPT-4o 60.16→Qwen1.5B 9.56 | ✅ Table 2/6 |
| [17] | ConflictBank | NeurIPS 2024 D&B | intro 規模效應 | T2 | 同系列小模型更堅持舊知識、難採納矛盾新資訊(新舊證據同時在場設定) | ✅ Fig.4 |

> **3a(引文獻,二手鋪墊) vs 3b(自己量,一手殺傷力)**。3b 見類別 3b 表,那才是論文真正的證據。

## 類別 3b：自己的診斷實驗（生產證據,非引文獻）

| 產出 | 依據 | 放哪章 |
|---|---|---|
| pool-state × Acc 交叉表(PP-New/Both/OldOnly/Missing × ✓/✗) | FC-SH + MQUAKE pair + 各 method pool 內容 | experiments §4.2(**body 主分析 🔴**) |
| backbone sweep gap 曲線(單調放大) | 大中小模型 × ours/baseline | experiments §3(**核心 empirical claim 🔴**) |
| 終態診斷 M1/EFR/IRR/BJV | baseline 記憶庫終態 + MQUAKE pair | appendix(⚪ write-time damage 量化) |
| 失因分佈(檢索漏抓/操作誤判/改寫毀損) | write-time 操作日誌 | experiments §5 case study(🟡) |

## 類別 4：稍微有關（部分概念套用/相關）

| # | 論文 | Venue | 放哪章 | 熟悉度 | 一句話用途 | 查證 |
|---|---|---|---|---|---|---|
| [21] | Astute RAG | ACL 2025 | RW 2.2 | T2 | 查詢時 cluster-and-separate 衝突解析=identity grouping 靈感 | ✅ |
| [22] | TruthfulRAG | AAAI 2026 | RW 2.2 | T2 | triple 層級查詢時衝突解析=佐證 fact-level 顆粒度 | ✅ RW 已用 |
| [19] | Least-to-Most | ICLR 2023 | method 3.1/3.4 | T3 | 任務分解降低複雜任務誤判 | ✅ |
| [20] | Decomposed Prompting | ICLR 2023 | method 3.4 | T3 | 確定性子任務交精確運算子 | ✅ |
| [7] | MemoryAgentBench | ICLR 2026 | RW 2.3;主評測 | **T1** | FC 主評測;Selective Forgetting→FactConsolidation;Appendix I 成本 | ✅ |
| [9] | LongMemEval | ICLR 2025 | RW 2.3;泛化 | T2 | KU 五大能力之一;取最新定義 | ✅ |
| [10] | MemBench | ACL 2025 Findings | RW 2.3 | T2 | FM-ku 子集 | ⚠️ FM-ku 待 spot-check |
| [11] | BEAM | ICLR 2026 | RW 2.3 | T2 | knowledge_update;出題原文「答案必須最新版本」 | ✅ 出題 prompt |
| [8] | Survey (Luo et al.) | ACL 2026 Findings | intro 開場 | T3 | §3.2 事實時效性隨時間改變 | ✅ §3.2 |
| [23] | MQUAKE | EMNLP 2023 | RW 2.3 邊界;FC 資料源 | T2 | FC 的 counterfactual pair 來源;KE 邊界 | ✅ |
| [13] | SlimLM | ACL 2025 Demo | intro 動機 | T3 | on-device 部署軸線 | ✅ |
| [14] | CoGenesis | ACL 2024 (Main) | intro 動機 | T3 | SLM 有 context 仍 lag behind LLM;privacy→on-device | ✅ |
| [15] | Middle Path (Huang et al.) | EMNLP 2025 | intro 動機 | T3 | on-premises 部署 | ✅ |
| [16] | FrugalGPT | TMLR 2024 | intro 動機 | T3 | cost-constrained→低成本 API | ✅ |

---

# B. 論點層對照（論點 → 文獻；區分「需引用的 claim」與「我方 reasoning」）

> 用途:寫作時逐句檢查——需要文獻佐證的 claim 有沒有引到、且引的是否真能從原文得到證據;屬我方 reasoning 的則**不要硬找文獻**(靠邏輯與自家實驗)。
> 不列於此=不需引用的常識背景(LLM 是什麼、stateless、context window、embedding 檢索等)。

## B.1 需要文獻佐證的論點（claim）

| # | 論點(陳述句) | 文獻 | 章節 | 查證 |
|---|---|---|---|---|
| 1 | LLM Agent 跨 session 長期互動、需外部記憶維持連貫 | [1][5]–[7] | intro ¶1 | ✅ |
| 2 | 記憶中事實時效性隨對話改變、同一事實多版本並存 | [8, §3.2] | intro ¶1 | ✅ |
| 3 | 檢索會把過時與當前版本一併取出、誤導推論 | [7] | intro ¶1 | ✅ |
| 4 | **KU 是長期記憶領域公認核心能力**(非自造問題) | [7][9][10][11] | intro ¶1;RW 2.3 | ✅(四基準原文定義) |
| 5 | 被動派著重儲存/組織、不主動偵測衝突 | [2][4][12][1] | intro ¶2;RW 2.1 | ✅ |
| 6 | 主動派-耦合:單次 LLM 呼叫既判且行 | [5][3] | intro ¶3;RW 2.1 | ✅ |
| 7 | 主動派-解耦:LLM 出標籤、確定性系統執行 | [6] | intro ¶3;RW 2.1 | ✅ |
| 8 | **上游 LLM 判斷是唯一錯誤源、誤判不可逆**(對手自承) | [3, §5.6] | intro ¶3;RW 2.1 | ✅ 逐字 |
| 9 | 隱私敏感→裝置端只能用小型不可微調模型 | [13][14][15] | intro ¶4 | ✅ |
| 10 | 成本受限→依賴低成本小模型(如 GPT-4o-mini) | [1][7,§I][16] | intro ¶4 | ✅ |
| 11 | **同家族小模型更堅持舊知識、難採納矛盾新資訊** | [17] | intro ¶4 | ✅ Fig.4 |
| 12 | 小模型整合大量使用者上下文系統性落後大模型 | [14] | intro ¶4 | ✅ |
| 13 | **backbone 換小模型後記憶操作崩潰;寫入錯誤持續污染後續檢索** | [18] | intro ¶4;RW 2.1 | ✅ Table 2/6 |
| 14 | 沿用 Storage–Update–Retrieval–Generation 流程 | [4] | intro ¶6 | ✅ |
| 15 | 延續並超越解耦更新(Zep 仍查詢前判斷、我們移除) | [6] | intro ¶6;RW 2.1 | ✅ |
| 16 | 單次複雜判斷拆成窄範圍子任務、確定性交精確運算子 | [19][20] | intro ¶6;method 3.4 | ✅ |
| 17 | 採 FC 為主評測;counterfactual 來自 MQUAKE;提供 fact-level GT | [7][23] | RW 2.3;exp §1 | ✅ |

> ⭐ **#8 與 #13 是全篇最有價值的兩個引用**(對手自承缺陷 + 唯一 conf-accepted「write 錯→下游污染」實證),務必逐字/逐表精準引用、不轉述走樣。

## B.2 屬我方 reasoning，**不需**（也不應硬找）文獻的論點

| 論點 | 靠什麼支撐 |
|---|---|
| query 把「對全庫的開放式判斷」降維成「對小切片的分辨」,同一模型後者更可靠 | 邏輯論證 + backbone sweep(3b) |
| 非破壞性是敢用 deterministic argmax 的前提;破壞性方法被迫讓 LLM 慎重判斷、更依賴模型 | 邏輯論證 |
| 乾淨 pool 讓推論模型只需照抄而非裁決衝突版本 → 弱模型可用 | pool-state×Acc 交叉表(3b, §4.2) |
| write-time 判錯波及後續每一題、query-time 只損當下一題(錯誤爆炸半徑) | 邏輯論證 +(輔助)終態診斷 |
| 優勢隨 backbone 判斷力下降單調放大(可證偽預測) | backbone sweep(3b, §3) |

> ⚠️ 這些若硬掛文獻反而顯得心虛;它們是本文的貢獻,由自家實驗與邏輯承擔。

---

# C. 完整書目（venue 狀態 / 連結 / 熟悉度 / takeaway）

## C.1 記憶系統——被動派

**[2] MemGPT** — Packer, C., *et al.* (2023). *MemGPT: Towards LLMs as Operating Systems.* arXiv:2310.08560.
⚠️ arXiv preprint(廣為引用 ~3k cites,未正式接受;後為 Letta 商業框架)。GitHub: letta-ai/letta (~16k★)。**T2**。用途:passive 派、stateless+context window 論據。引用 framing 用「the MemGPT framework (Packer et al., 2023)」。

**[12] MemoryBank** — Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2024). *Enhancing LLMs with Long-Term Memory.* AAAI 2024, 38(17), 19724–19731. arXiv:2305.10250. GitHub: zhongwanjun/MemoryBank-SiliconFriend (~700★)。**T2**。用途:passive 始祖、Ebbinghaus 衰減。

**[1] A-Mem** — Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-Mem: Agentic Memory for LLM Agents.* NeurIPS 2025. arXiv:2502.12110. OpenReview: FiM0M8gcct。**T2**。用途:passive 代表 + real-world deployment + cost 證據(大量用 gpt-4o-mini)。年份統一用 NeurIPS 2025。

**[4] MemoryOS** — Kang, J., Ji, M., Zhao, Z., & Bai, T. (2025). *Memory OS of AI Agent.* EMNLP 2025, 25972–25981. aclanthology 2025.emnlp-main.1326。arXiv:2506.06326。GitHub: BAI-LAB/MemoryOS (~1.7k★)。**T2**。⭐ 用途:我們 Storage–Update–Retrieval–Generation framing 母體。

## C.2 記憶系統——主動派（直接對手）

**[5] Mem0** — Chhikara, P., Khant, D., Aryan, S., Singh, T., & Yadav, D. (2025). *Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory.* ECAI 2025, 2993–3000. DOI:10.3233/FAIA251160。arXiv:2504.19413。GitHub: mem0ai/mem0 (~30k★)。**T1(熟讀 Algorithm 1)**。用途:Coupled Update 代表、破壞性 write-time commit 最 representative case。

**[3] LightMem** — Fang, J., *et al.* (2025). *LightMem: Lightweight and Efficient Memory-Augmented Generation.* ICLR 2026. OpenReview: dyJ0GWpjJB。arXiv:2510.18866。GitHub: zjunlp/LightMem。**T1(§5.6 quote 是論述核心)**。用途:Coupled + cost-efficient;§5.6 自承不可逆丟失。
> §5.6 原文:*"an LLM might incorrectly interpret [related but not contradictory pieces] as a conflict and delete the older memory entry, leading to irreversible information loss."*

**[6] Zep** — Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* arXiv:2501.13956.
⚠️ arXiv preprint(Zep AI 商業出品)。核心引擎 Graphiti: getzep/graphiti (~5k★)。**T1(熟讀 Edge Resolution)**。用途:Decoupled 代表、我們明確 extend-from。**措辭紀律**:Zep 非破壞、失效標籤凍結→查詢時不重解=**檢索層**等效不可逆;不可寫「刪除/破壞」。paper 名用 Zep、code 用 Graphiti。

**[18] Zhang et al.（系統亦名 LightMem）** — Zhang, J., *et al.* (2026). *Lightweight LLM Agent Memory with Small Language Models.* ACL 2026, 12914–12929.
**T1**。用途:最近鄰(小模型記憶)、3a case 論據。核過:MemGPT SH-F1 GPT-4o 60.16→Qwen2.5-1.5B 9.56 (Table 2);noisy writes→"persistent downstream effects by contaminating future retrieval" (Table 6);SLM-3 Writer 在寫入當下合併/改寫重疊節點。⚠️ 同名消歧見 A 表。☐ 補 arXiv/OpenReview 連結。

## C.3 KU 評測基準

**[7] MemoryAgentBench** — Hu, Y., Wang, Y., & McAuley, J. (2026). *Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions.* ICLR 2026. OpenReview: DAGUEt4ya9。arXiv:2507.05257。GitHub: HUST-AI-HYZ/MemoryAgentBench。**T1(熟讀 FC-SH 設計)**。⭐ 主評測來源。用途:FC=selective forgetting 下的 FactConsolidation(**非籠統「列為 KU」**);Appendix I 成本;檢索一併取出過時/當前。

**[9] LongMemEval** — Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., & Yu, D. (2025). ICLR 2025. OpenReview: pZiyCaVuti。arXiv:2410.10813。**T2**。用途:KU 五大能力之一 anchor;取最新定義。可引「~30% accuracy drop across sustained interactions」stat。

**[11] BEAM** — Tavakoli, M., Salemi, A., Ye, C., Abdalla, M., Zamani, H., & Mitchell, J. R. (2026). *Beyond a Million Tokens.* ICLR 2026. OpenReview: y59hf5lrMn。GitHub: mohammadtavakoli78/BEAM。**T2**。用途:10 能力含 knowledge update + contradiction resolution;出題 prompt 明令「答案必須最新版本」。

**[10] MemBench** — Tan, H., Zhang, Z., Ma, C., Chen, X., Dai, Q., & Dong, Z. (2025). Findings of ACL 2025, 19336–19352。aclanthology 2025.findings-acl.989。arXiv:2506.21605。GitHub: import-myself/Membench。**T2**。⚠️ FM-ku 子集待對原文 spot-check。

**[8] Survey (Luo et al.)** — (2026). *From Storage to Experience.* ACL 2026 Findings(亦 ICLR Workshop MemAgents)。GitHub: FeishuLuo/Evolving-LLM-Agent-Memory-Survey。**T3**。用途:§3.2 事實時效性隨時間改變。

**[23] MQUAKE** — Zhong, Z., Wu, Z., Manning, C. D., Potts, C., & Chen, D. (2023). *MQuAKE: Assessing Knowledge Editing via Multi-Hop Questions.* EMNLP 2023. arXiv:2305.14795。**T2**。用途:FC 的 counterfactual 事實對來源;KE 邊界。

## C.4 RAG 查詢時衝突解析

**[21] Astute RAG** — Wang, F., Wan, X., Sun, R., Chen, J., & Arık, S. Ö. (2025). *Overcoming Imperfect Retrieval Augmentation and Knowledge Conflicts.* ACL 2025. ☐ 補連結。**T2**。用途:cluster-and-separate 查詢時衝突解析=identity grouping 靈感。

**[22] TruthfulRAG** — Liu, S., Shang, Y., & Zhang, X. (2026). *Resolving Factual-Level Conflicts in RAG with Knowledge Graphs.* AAAI 2026. ☐ 補連結。**T2**。用途:triple 層級查詢時衝突解析。

## C.5 受限部署動機（T3）

**[13] SlimLM** — Pham, T. M., *et al.* (2025). ACL 2025 System Demonstrations, 436–447。用途:on-device 軸線。
**[14] CoGenesis** — Zhang, K., Wang, J., Hua, E., Qi, B., Ding, N., & Zhou, B. (2024). **ACL 2024 Main**(非 Findings)。aclanthology 2024.acl-long.235。arXiv:2403.03129。用途:privacy→cloud+on-device;SLM 有 context 仍 lag behind。
**[15] A Middle Path** — Huang, H., *et al.* (2025). EMNLP 2025 Main, 8321–8359。DOI:10.18653/v1/2025.emnlp-main.420。用途:on-premises 部署。
**[16] FrugalGPT** — Chen, L., Zaharia, M., & Zou, J. (2024). **TMLR 2024 (Featured Certification)**。OpenReview: cSimKw5p6R。用途:cost gap「two orders of magnitude」argument。

## C.6 任務分解（method 設計原則,T3）

**[19] Least-to-Most** — Zhou, D., *et al.* (2023). ICLR 2023. arXiv:2205.10625。用途:任務分解使複雜推理可行。
**[20] Decomposed Prompting** — Khot, T., *et al.* (2023). ICLR 2023. arXiv:2210.02406。用途:模組化拆解、確定性子任務外包。

## C.7 規模效應（intro 動機,T2）

**[17] ConflictBank** — Su, Z., Zhang, J., Qu, X., Zhu, T., Li, Y., Sun, J., Li, J., Zhang, M., & Cheng, Y. (2024). *ConflictBank: A Benchmark for Evaluating Knowledge Conflicts in LLMs.* NeurIPS 2024 Datasets & Benchmarks Track. arXiv:2408.12076。**T2**。用途:Fig.4 同系列大模型 MR 較低=小模型更堅持參數化知識;⚠️ 精確化:出自「新舊證據同時在場」設定(正對應記憶檢索同撈新舊)。

---

# D. 邊界與排除文獻

## D.1 邊界文獻（劃清「我們不做什麼」,不作支持論據）

| 論文 | Venue | 決定 | 理由 |
|---|---|---|---|
| **RippleEdits** (Cohen et al.) | TACL 2024 ✅ | 僅 RW 2.3 邊界句可選引一次;**不進 3a 論據** | ripple=編輯 fact A→邏輯衍生 fact B 需跟改(跨事實傳播);我們是同一事實時序覆寫。引來當支持會被抓「引錯脈」。若引則 references 增 [24] |
| KE methods (ROME/MEMIT/AlphaEdit…) | 各頂會 | 不引 | 編輯參數 vs 維護外部記憶,展開無增益 |
| Temporal KG / bi-temporal (as-of) | — | 不進 RW;discussion 一句 | as-of 需 valid time,超 scope,RW 展開等於邀戰 |
| *Don't Ask the LLM to Track Freshness* | ⚠️ venue 待確認 | method/analysis 輔助證據,不進 RW 支柱 | argmax>LLM 挑 recency 佐證;若 preprint 依政策只作輔助 |
| Conflict-Aware Soft Prompting | project 內 | 可選;RW 2.2 並列一句或不引 | RAG 衝突線廣度;非必要 |

## D.2 已排除文獻（2026-06-23 決定,保留備查）

| 引用 | 排除原因 |
|---|---|
| **MIRIX** (Wang & Chen, arXiv 2025, ~3.5k★) | Multi-agent 非本研究範圍 + arXiv preprint;discussion 若對比 multi-agent 可提 |
| **Xiong et al.** (cascading errors, arXiv 2025) | arXiv preprint;改用結構論證 + [3]§5.6;**註**:[18] 已提供 conf-accepted 替代,cascading 相關實證改引 [18] |
| **AgentDebug** (Liu et al., arXiv 2025) | 從 ICLR 2026 撤回(withdrawn),引用有風險 |
| **SLM Future of Agentic AI** (NVIDIA, arXiv 2025) | arXiv preprint;cost 軸線已由 [1][7§I][16] 充分支撐 |
| **Cattan et al.**(*DRAGged into Conflicts*, 2025) | **2026-07-04 移除**:P5 拿掉後失去用途;multi-value 方向回補再議 |

---

# E. 附錄：venue 校正 / 開源 / 閱讀序

## E.1 venue 校正記錄（避免重犯）

| Reference | 曾誤標 | 正確 status |
|---|---|---|
| CoGenesis | ACL 2024 Findings | ✅ ACL 2024 **Main** |
| Mem0 | 僅 arXiv | ✅ ECAI 2025 published w/ DOI |
| FrugalGPT | 不確定 | ✅ TMLR 2024 Featured Certification |
| MemGPT | 假設 ICML/ICLR accepted | ⚠️ arXiv preprint only |
| A-Mem | "(2026)" / proceedings 年 | ✅ NeurIPS **2025**(conference year) |
| AgentDebug | ICLR 2026 submission | ⚠️ Withdrawn → 不使用 |

## E.2 開源清單（直接相關流派 + benchmarks）

| Paper | GitHub | ★ | License |
|---|---|---|---|
| Mem0 | mem0ai/mem0 | 30k+ | Apache 2.0 |
| LightMem [3] | zjunlp/LightMem | 新 | MIT |
| Zep/Graphiti | getzep/graphiti | 5k+ | Apache 2.0 |
| MemoryOS | BAI-LAB/MemoryOS | 1.7k | MIT |
| A-Mem | WujiangXu/A-mem;agiresearch/A-mem | 814 | MIT |
| MemGPT/Letta | letta-ai/letta | 16k | Apache 2.0 |
| MemoryBank | zhongwanjun/MemoryBank-SiliconFriend | 700 | (check) |
| LongMemEval | xiaowu0162/LongMemEval | med | (check) |
| MemBench | import-myself/Membench | small | (check) |
| MemoryAgentBench | HUST-AI-HYZ/MemoryAgentBench | small | (check) |
| BEAM | mohammadtavakoli78/BEAM | small | (check) |
| Survey | FeishuLuo/Evolving-LLM-Agent-Memory-Survey | small | resource list |

## E.3 閱讀優先序（碩論準備）

- **必讀 T1(對手 + pipeline 母體)**:MemoryOS [4]、LightMem [3](§5.6)、Mem0 [5](Algorithm 1)、Zep/Graphiti [6](Edge Resolution)、Zhang et al. [18]、MemoryAgentBench [7](FC-SH)。
- **中度 T2**:LongMemEval [9]、A-Mem [1]、ConflictBank [17]、MQUAKE [23]、Astute RAG [21]、TruthfulRAG [22]、MemBench [10]、BEAM [11]。
- **略讀/引用即可 T3**:Survey [8]、MemGPT [2]、MemoryBank [12]、SlimLM [13]、CoGenesis [14]、A Middle Path [15]、FrugalGPT [16]、Least-to-Most [19]、Decomposed Prompting [20]。

## E.4 跨檔 TODO

- ☐ MemBench [10] FM-ku 對原文 spot-check
- ☐ *Don't Ask the LLM to Track Freshness* venue status
- ☐ [18] 同名 footnote 撰寫 + arXiv/OpenReview 連結補齊
- ☐ [21][22] 連結補齊
- ☐ 決定 RippleEdits 是否於 RW 2.3 邊界句引用(引→新增 [24])

---

# 附註

- **編號**:intro v6 用 [1]–[20];related_work v2 續編 [21]–[23];本表為兩者聯集的 single source of truth。
- **同名雙 LightMem**([3] vs [18])是本表最容易出錯處,見 A 表 ⚠️。
- **B.2 的我方 reasoning 不要硬掛文獻**——它們是貢獻,由自家實驗承擔。
