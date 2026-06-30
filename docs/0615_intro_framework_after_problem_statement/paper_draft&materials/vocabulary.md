# Vocabulary Reference: Robust Knowledge Update for LLM Agent Memory

> **Purpose**: Single source of truth for terminology across all versions of this thesis project — English paper, Chinese abstract, slides, oral defense PPT.
>
> **Last updated**: 2026-06-23
>
> **Usage**: Before submitting any version (paper draft, slide deck, abstract), grep through this document and verify every concept in your draft matches the canonical form listed here.

---

## Usage Guidelines

### 1. 首次出現規則 (First-occurrence rule)

- 中文文件中,英文術語**首次出現時並列中文翻譯**,格式:`中文翻譯 (English term)`
- 例:「保守寫入 (Conservative Writes)」
- 後續出現只用中文或只用英文,維持一致

### 2. 大小寫規則 (Capitalization)

- **論文主張中的 named architectural commitment** (我們命名的核心設計) 用 Title Case:**Conservative Writes**、**Query-Time KU Resolution**
- **Taxonomy 名稱** (流派) 用 Title Case:Coupled Update、Decoupled Update、Knowledge Update (KU)
- **一般概念與機制描述** 用小寫:identity grouping、temporal resolution、structural commit、conservative write strategy 等

### 3. 縮寫 (Abbreviation)

- 縮寫首次出現時定義,例:`知識更新 (Knowledge Update, KU)`
- 後續可只用 KU

### 4. 遇到不在表中的詞

- 先查英文文獻 standard 用法,再決定中文翻譯
- 優先順序:NLP 主流會議論文 > 領域 survey > 一般 ML/AI 用詞
- 新增詞時加入下方 Change Log

### 5. 學術用詞原則 (Academic Terminology Principle)

- **避免使用非領域標準術語** (例如自創、行銷化、口語化詞彙)
- 即使該詞能精煉表達我們的觀點，若無學術文獻先例，改用領域標準描述
- 不刻意取 framework name;若論文 contribution 已能由 thesis statement + 兩個 named commitments 完整表達，就不必額外命名 framework

---

## 1. 論文核心主張與架構命名 (Core Thesis and Architecture)

### 1.1 Thesis Statement (論文主張)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Thesis statement | KU should be a query-time concern, not a write-time commitment | KU 應該是 query-time 的問題，而非 write-time 的提交決定 | 用作論述主張，不作為被命名的概念 |

### 1.2 Named Architectural Commitments (我們的兩個 commitment)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Architectural commitment A | Conservative Writes | 保守寫入 | 保守寫入 (Conservative Writes) |
| Architectural commitment B | Query-Time KU Resolution | 查詢時 KU 解析 | 查詢時 KU 解析 (Query-Time KU Resolution) |

### 1.3 Temporal Phases (寫入時 / 查詢時，作為時間階段描述)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Write-time | write-time | 寫入時 / 寫入階段 | 寫入時 (write-time) |
| Query-time | query-time | 查詢時 / 查詢階段 | 查詢時 (query-time) |

⚠️ **不再使用 "Stage 1" / "Stage 2" 編號**:這暗示框架命名 (Two-Stage)，但我們已決定不取 framework 名稱。寫入時 / 查詢時 是自然的時間階段描述，**非命名實體**。

---

## 2. 核心機制與元件詞彙 (Core Mechanism and Component Terms)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Knowledge Update | Knowledge Update (KU) | 知識更新 (KU) | 知識更新 (Knowledge Update, KU) |
| Non-destructive | non-destructive | 非破壞性 | 非破壞性 (non-destructive) |
| Robust knowledge update | robust knowledge update | 穩健知識更新 | 穩健知識更新 (robust knowledge update) |
| Speculative | speculative | 預測性 | 預測性 (speculative) |
| Cross-item | cross-item | 跨筆記憶 | 跨筆記憶 (cross-item) |
| Self-contained | self-contained, per-item | 單筆自含 | 單筆自含 (self-contained, per-item) |
| Triple | (subject, predicate, object) | 三元組 (主詞, 謂詞, 賓語) | 三元組 (subject, predicate, object) |
| Structural commit | structural commit | 結構性提交 | 結構性提交 (structural commit) |
| Structural match | (S, P) structural match | (S, P) 結構性比對 | (S, P) 結構性比對 |
| Fact identity | fact identity | 事實識別 | 事實識別 (fact identity) |
| Identity grouping | identity grouping | 事實識別分群 | 事實識別分群 (identity grouping) |
| Temporal resolution | temporal resolution | 時序解析 | 時序解析 (temporal resolution) |
| Mutation | mutation | 記憶變更 | 記憶變更 (mutation) |
| Temporal invalidation | temporal invalidation | 時序失效 | 時序失效 (temporal invalidation) |
| Unified memory bank | unified memory bank | 統一記憶庫 | 統一記憶庫 (unified memory bank) |
| (S, P) inverted index | (S, P) inverted index | (S, P) 反向索引 | (S, P) 反向索引 ((S, P) inverted index) |
| Candidate pool | candidate pool | 候選池 | 候選池 (candidate pool) |
| Inference LLM | inference LLM | 推論 LLM | 推論 LLM (inference LLM) |
| Ingestion timestamp | ingestion timestamp | 寫入時序 | 寫入時序 (ingestion timestamp) |
| Memory bank | memory bank | 記憶庫 | 記憶庫 (memory bank) |
| Query-time conflict resolution | query-time conflict resolution | 查詢時衝突解析 | (機制描述語;**僅在 RW2 連結 RAG paradigm 與 Method 連結 RW2 時使用;intro 不使用此詞**) |

**⚠️ 禁用詞 (across the whole project)**:
- ~~Two-Stage Framework~~ / ~~兩階段框架~~ / ~~Two-Stage Knowledge Update Framework~~ → 不作為 framework 命名;直接用 thesis + Conservative Writes + Query-Time KU Resolution 表達
- ~~reconciliation~~ / ~~reconcile~~ → 改用 **conflict resolution / resolve**
- ~~雙階段~~ → 「兩階段」也不作為命名;用「寫入時 / 查詢時」自然敘述即可
- ~~解決~~ (in conflict context) → 統一用 **解析** (對應 resolution)
- ~~memory pool~~ → 改用 **memory bank** (一致性)
- ~~記憶池~~ → 改用 **記憶庫**
- ~~demand-driven~~ / ~~需求驅動~~ → 非領域標準術語，不使用;若要表達相同概念，用「at query-time, only the facts the query touches need to be resolved」這類描述性論述
- ~~Stage 1~~ / ~~Stage 2~~ (作為編號階段名稱) → 改用 "write-time" / "query-time"

---

## 3. 流派分類 (Taxonomy of Memory Update Methods)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| 對 KU 採取被動 | passive (about KU) | 被動 | 對 KU 採取被動 (passive) 態度 |
| 對 KU 採取主動 | proactive (about KU) | 主動 | 對 KU 採取主動 (proactive) 態度 |
| 主動派 sub-A | Coupled Update | 耦合更新 | 耦合更新 (Coupled Update) |
| 主動派 sub-B | Decoupled Update | 解耦更新 | 解耦更新 (Decoupled Update) |
| 耦合派 LLM 角色 | judge and operator | 判斷者與執行者 | LLM 同時擔任判斷者與執行者 (judge and operator) |
| 解耦派 LLM 角色 | labeler | 標籤產生者 | LLM 僅作為標籤產生者 (labeler) |
| 執行端 | deterministic system / policy | 確定性系統 / 策略 | 確定性策略 (deterministic policy) |
| LLM 操作集合 (Mem0) | ADD / UPDATE / DELETE / NOOP | (英文原樣) | 大寫保留 |
| LLM 類別標籤 (Zep) | contradicts / duplicates | (英文原樣) | 斜體 *contradicts* / *duplicates* |
| 誤判 | misjudgment | 誤判 | — |
| 不可逆寫入 | irreversibly committed | 不可逆地寫入 | — |
| 沿襲 B 派 | inherit from / extend Decoupled Update | 沿襲 / 延伸解耦更新 | — |

---

## 4. 限制場景 (Constrained Deployment)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| 限制部署場景 | constrained deployment | 受限部署場景 | 受限部署場景 (constrained deployment) |
| 隱私敏感 | privacy-sensitive | 隱私敏感 | 隱私敏感 (privacy-sensitive) |
| 成本受限 | cost-constrained | 成本受限 | 成本受限 (cost-constrained) |
| 凍結模型 | small, frozen LLM | 不可微調的 (frozen) 小型 LLM | 不可微調的 (frozen) 小型 LLM |
| 裝置端推論 | on-device inference | 裝置端推論 | 裝置端推論 (on-device inference) |
| 前沿模型 | frontier models | 前沿模型 | 前沿模型 (frontier models) |
| 判斷品質 | judgment quality / reliability | 判斷品質 / 可靠性 | — |
| 不可微調 | non-tunable / frozen | 不可微調 | — |

**⚠️ 禁用詞**:
- ~~凍結的~~ (中文翻譯腔) → 改用 **不可微調 (frozen)**
- ~~固定參數的~~ → 改用 **不可微調 (frozen)**
- ~~cascading error propagation~~ / ~~連鎖錯誤~~ → 不使用，因為強力 conference-accepted 文獻支撐不足;改用結構性論證 (「destructive commit + low judgment quality → irreversible accumulation」) 配合 LightMem §5.6 quote 作為從子流派內部來的自我承認
- ~~system-level design~~ (作為 abstract framework 詞) → 不使用模糊的 system-level design 概念;改用具體論述「LLM 在什麼階段被呼叫，以及它的判斷範圍涵蓋什麼」

---

## 5. 共通 NLP / Agent 詞 (Common NLP / Agent Terminology)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| LLM 代理 | LLM-based agent / LLM agent | LLM Agent | LLM Agent (基於大型語言模型的智慧代理) |
| 記憶增強代理 | memory-augmented agent | 記憶增強 Agent | 記憶增強 Agent (memory-augmented agent) |
| 無狀態 | stateless | 無狀態 | 無狀態 (stateless) |
| 上下文視窗 | (fixed-length) context window | (固定長度的) 上下文視窗 | 上下文視窗 (context window) |
| 外部記憶 | external memory | 外部記憶 | 外部記憶 (external memory) |
| 時效性 | (temporal) validity | 時效性 | 時效性 (temporal validity) |
| 不一致版本 | inconsistent versions | 不一致的版本 | — |
| 類別標籤 | categorical label | 類別標籤 | 類別標籤 (categorical label) |
| 確定性策略 | deterministic policy | 確定性策略 | 確定性策略 (deterministic policy) |
| 統一流程 | Storage–Update–Retrieval–Generation pipeline | 儲存—更新—檢索—生成流程 | 儲存—更新—檢索—生成流程 (Storage–Update–Retrieval–Generation pipeline) |
| 元件 | component / module | 元件 / 模組 | — |
| 儲存模組 | Storage module | 儲存模組 | — |
| 更新模組 | Update module | 更新模組 | — |
| 檢索模組 | Retrieval module | 檢索模組 | — |
| 推論 LLM | inference LLM | 推論 LLM | — |
| 跨對話階段 | across sessions | 跨對話階段 / 跨 session | — |
| 多輪互動 | multi-turn interaction | 多輪互動 | — |

**⚠️ 禁用詞**:
- ~~基於 LLM 的代理~~ (翻譯腔重) → 改用 **LLM Agent** 或「基於大型語言模型的 Agent」
- ~~有效性~~ (在 KU context) → 改用 **時效性** (temporal validity)
- ~~視窗~~ (單字) → 改用「上下文視窗」確保語意完整
- ~~代理~~ (單字) → 改用「Agent」或「智慧代理」

---

## 6. 文獻引用標準 (Citation Style)

### 格式

文獻首次出現時:
- 英文版:`Method [Author et al., Venue Year]`
  例:Mem0 [Chhikara et al., ECAI 2025]
- 中文版:`方法名 [Author et al., Venue Year]`
  例:Mem0 [Chhikara et al., ECAI 2025]
- 後續可只用方法名

### 本論文 intro 使用的參考文獻 (16 條，已 finalized)

| # | 方法 / 論文 | 完整引用 | 在 intro 中的用途 |
|---|---|---|---|
| [1] | A-Mem | Xu et al., NeurIPS 2025 | Real-world deployment、Passive 派、Cost-constrained evidence |
| [2] | MemGPT | Packer et al., 2023 (arXiv) | Stateless+context window、Passive 派 |
| [3] | LightMem | Fang et al., ICLR 2026 | Stateless+context window、Coupled Update、§5.6 self-acknowledgment quote |
| [4] | MemoryOS | Kang et al., EMNLP 2025 | Stateless+context window、Passive 派、Storage-Update-Retrieval-Generation pipeline 來源 |
| [5] | Mem0 | Chhikara et al., ECAI 2025 | External memory、Coupled Update |
| [6] | Zep | Rasmussen et al., 2025 (arXiv) | External memory、Decoupled Update (we extend from) |
| [7] | MemoryAgentBench | Hu, Wang, McAuley, ICLR 2026 | External memory、Retrieval surfaces outdated、KU benchmark、Cost-constrained evidence |
| [8] | Survey 2026 | Luo et al., ACL 2026 Findings | Temporal validity changes (§3.2) |
| [9] | LongMemEval | Wu et al., ICLR 2025 | KU benchmark |
| [10] | MemBench | Tan et al., ACL 2025 Findings | KU benchmark |
| [11] | BEAM | Tavakoli et al., ICLR 2026 | KU benchmark |
| [12] | MemoryBank | Zhong et al., AAAI 2024 | Passive 派 |
| [13] | SlimLM | Pham et al., ACL 2025 Demo | Privacy-constrained → on-device |
| [14] | CoGenesis | Zhang et al., ACL 2024 | Privacy-constrained → on-device |
| [15] | Huang et al. (A Middle Path) | EMNLP 2025 | Privacy-constrained → on-device |
| [16] | FrugalGPT | Chen, Zaharia, Zou, TMLR 2024 | Cost-constrained → low-cost API |

### 已從 intro 移除的引用 (保留在 references.md 作為 reference)

| 引用 | 移除原因 |
|---|---|
| MIRIX (Wang & Chen, arXiv 2025) | Multi-agent 非本研究範圍 + 非 conference-accepted |
| Xiong et al. (cascading errors, arXiv 2025) | 非 conference-accepted |
| AgentDebug (Liu et al., arXiv 2025) | 從 ICLR 2026 撤回 (withdrawn) |
| SLM Future of Agentic AI (NVIDIA arXiv 2025) | arXiv preprint;cost-constrained 軸線已由 A-Mem + FrugalGPT 充分支撐 |

---

## 7. 變更記錄 (Change Log)

| 日期 | 變更 | 原因 |
|---|---|---|
| 2026-06-17 | 初版建立 | 英文 intro / 中文 intro / slide 8 三份版本用詞不統一,需收斂為 single source of truth |
| 2026-06-23 | 移除 "demand-driven" / "需求驅動" 作為 canonical | 非領域標準術語;改用「at query-time, only X need to be resolved」描述性論述 |
| 2026-06-23 | 移除 "active store / archive store / two-tier" 區段 | 設計已收斂為 single-tier unified memory bank |
| 2026-06-23 | 移除 "cascading error propagation" 作為 canonical | 強力 conference-accepted 引用支撐不足;改用結構性論證 + LightMem §5.6 quote |
| 2026-06-23 | 統一 "memory pool" → "memory bank" | intro Para 4 用詞與其他段對齊 |
| 2026-06-23 | **移除 "Two-Stage Framework" / "兩階段框架" / "Two-Stage Knowledge Update Framework" 作為 framework name** | 並非 distinctive contribution (每個 memory system 都有 write/query time 兩階段);改用 thesis statement + 兩個 named architectural commitments (Conservative Writes + Query-Time KU Resolution) 來組織論述 |
| 2026-06-23 | **新增 Section 1 "論文核心主張與架構命名"** | 把 thesis、named commitments、temporal phases 三層分清楚 |
| 2026-06-23 | 移除 "Stage 1" / "Stage 2" 編號作為命名 | 跟著 Two-Stage Framework 一併移除 |
| 2026-06-23 | 補上 "memory bank"、"unified memory bank"、"(S, P) inverted index"、"candidate pool"、"ingestion timestamp" 為 canonical | 從 method section 用詞回填 vocabulary |
| 2026-06-23 | 移除 "system-level design" 模糊用詞 | Para 4 結尾原句太抽象;改用具體論述「LLM 在什麼階段被呼叫，以及它的判斷範圍涵蓋什麼」 |

---

## Appendix: 常見對應錯誤快速查表

寫作時最容易寫錯的對應:

| ❌ 錯誤(常見寫法) | ✅ 正確(canonical) |
|---|---|
| Two-Stage Framework | (不命名 framework；用 Conservative Writes + Query-Time KU Resolution) |
| Two-Stage Knowledge Update Framework | (同上) |
| 兩階段框架 | (同上) |
| 雙階段 | 兩階段 (作為描述);但**不作為 framework 命名** |
| Stage 1 / Stage 2 | write-time / query-time (自然時間階段描述) |
| reconciliation / reconcile | conflict resolution / resolve |
| 調和(作為動作) | 解析 |
| 基於 LLM 的代理 | LLM Agent |
| 有效性(在 KU 描述中) | 時效性 |
| 凍結的 | 不可微調 (frozen) |
| memory pool | memory bank |
| 記憶池 | 記憶庫 |
| demand-driven (作為定型概念) | (避免使用;改用描述性論述) |
| cascading error propagation (作為定型概念) | (避免使用;改用結構性論證) |
| system-level design (作為 abstract framing) | (避免使用;具體描述設計變數) |
| Structural extract (slide box 名) | Structural commit |