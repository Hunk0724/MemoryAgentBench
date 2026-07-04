# Vocabulary Reference: Robust Knowledge Update for LLM Agent Memory

> **Purpose**: Single source of truth for terminology across all versions of this thesis project — English paper, Chinese abstract, slides, oral defense PPT.
>
> **Last updated**: 2026-07-04
>
> **Usage**: Before submitting any version (paper draft, slide deck, abstract), grep through this document and verify every concept in your draft matches the canonical form listed here.

---

## Usage Guidelines

### 1. 首次出現規則 (First-occurrence rule)

- 中文文件中,英文術語**首次出現時並列中文翻譯**,格式:`中文翻譯 (English term)`
- 例:「忠實寫入 (Faithful Writes)」
- 後續出現只用中文或只用英文,維持一致

### 2. 大小寫規則 (Capitalization)

- **論文主張中的 named architectural commitment** (我們命名的核心設計) 用 Title Case:**Faithful Writes**、**Query-Time KU Resolution**
- **Taxonomy 名稱** (流派) 用 Title Case:Coupled Update、Decoupled Update、Knowledge Update (KU)
- **一般概念與機制描述** 用小寫:identity grouping、temporal resolution、structural commit、temporal argmax 等

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

## 0. 研究範圍宣告 (Scope Statement) 【2026-07-04 新增】

本論文的 **KU 以既有長期記憶基準的共同定義為範圍**:辨識同一事實在記憶中的多個版本、並採用其**最新**版本 (current-value)。對應基準與其原文定義:

| Benchmark | 原文能力名 / 任務名 | 定義要點 (已對原文查證) |
|---|---|---|
| LongMemEval [9] | Knowledge Updates (五大核心能力之一) | "recognize the changes in the user's personal information and update the knowledge of the user dynamically over time" |
| MemoryAgentBench [7] | Selective Forgetting → FactConsolidation 任務 | "detect and resolve contradictions between out of date knowledge and newly acquired information";以較新加入的事實取代較舊者 |
| BEAM [11] | Knowledge Update、Contradiction Resolution (十項能力中) | 十項記憶能力表直接列名 |
| MemBench [10] | FM-ku 子集 | 使用者屬性隨時間變動 (⚠️ 待對原文 spot-check) |

**Scope 邊界 (寫作時遵守)**:
- **多值/歷史型 query** (list-all、as-of、preference-following、event-ordering 等) **不在本文實證 claim 範圍內**;design rationale 可提及設計的延伸性,但不作 claim。
- 相應地,**架構中不含衝突類型分類元件** (舊稱 P5,已移除,見禁用詞);查詢端解析 = 事實識別分群 + 時序解析兩件事。
- 「本設計考慮所有 KU 面向」這類語句**只能出現在 design rationale**,不可出現在 contribution / claim。

---

## 1. 論文核心主張與架構命名 (Core Thesis and Architecture)

### 1.1 Thesis Statement (論文主張)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Thesis statement | KU should be a query-time concern, not a write-time commitment | KU 應該是 query-time 的問題，而非 write-time 的提交決定 | 用作論述主張，不作為被命名的概念 |
| 論文標題呼應句 | *Write Faithfully, Resolve at Query Time* | (英文原樣,斜體) | 引用標題時保持英文 |

### 1.2 Named Architectural Commitments (我們的兩個 commitment)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Architectural commitment A | **Faithful Writes** | 忠實寫入 | 忠實寫入 (Faithful Writes) |
| Architectural commitment B | **Query-Time KU Resolution** | 查詢時 KU 解析 | 查詢時 KU 解析 (Query-Time KU Resolution) |

⚠️ **~~Conservative Writes~~ / ~~保守寫入~~ 已於 2026-07-04 廢止**,統一改為 **Faithful Writes / 忠實寫入**,與論文標題 *Write Faithfully* 對齊。「保守寫入」只可作為機制的口語描述 (小寫、非命名),正式命名一律 Faithful Writes。

### 1.3 Temporal Phases (寫入時 / 查詢時，作為時間階段描述)

| Concept | EN (canonical) | ZH (canonical) | 首次並列寫法 |
|---|---|---|---|
| Write-time | write-time | 寫入時 / 寫入階段 | 寫入時 (write-time) |
| Query-time | query-time | 查詢時 / 查詢階段 | 查詢時 (query-time) |
| Pre-query | pre-query | 查詢前 | 查詢前 (pre-query) |

⚠️ **不再使用 "Stage 1" / "Stage 2" 編號**:這暗示框架命名 (Two-Stage)，但我們已決定不取 framework 名稱。寫入時 / 查詢時 是自然的時間階段描述，**非命名實體**。
> 註:「查詢前 (pre-query)」用於統括「寫入當下 (Mem0、Zep) 或離線整併時 (LightMem)」兩種時機,比單用 write-time 更精確涵蓋 LightMem 的 offline batch。

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
| Temporal argmax | (deterministic) temporal argmax | (確定性的) 時序 argmax | 確定性的時序 argmax (temporal argmax) |
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
- ~~Conservative Writes~~ / ~~保守寫入~~ (作為命名) → 改用 **Faithful Writes / 忠實寫入** (2026-07-04)
- ~~conflict-type classification~~ / ~~衝突類型分類~~ / ~~P5~~ (作為架構元件) → **已自架構移除** (2026-07-04):在本文 scope 的 KU 定義下,同一事實多版本即互斥、以最新為準,衝突判斷退化為分群的直接推論,無須額外 LLM 呼叫。若日後於多值 benchmark 發現需求再回補,屆時另議命名。相關舊引用 (Cattan et al. 2025, *DRAGged into Conflicts*) 一併自 method/RW 移出,保留於 references.md 備查。
- ~~錯誤面 (error surface)~~ (作為定型概念/命名) → 非領域標準術語;改用描述性論述「誤判是否落地並持續污染後續查詢 (whether a misjudgment is committed and persists to contaminate subsequent queries)」
- ~~Two-Stage Framework~~ / ~~兩階段框架~~ / ~~Two-Stage Knowledge Update Framework~~ → 不作為 framework 命名;直接用 thesis + Faithful Writes + Query-Time KU Resolution 表達
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
| 提交 | commit (committed) | 提交 (被提交) | 提交 (commit) |
| 不可逆寫入 (限破壞性方法) | irreversibly committed | 不可逆地寫入 | ⚠️ 只用於 Mem0 / LightMem;對 Zep 用下列措辭 |
| Zep 的精確措辭 | frozen at write; not revisited downstream; effectively irreversible **at the retrieval layer** | 失效標籤一經寫定便凍結、查詢時不再重解;在**檢索層**等效不可逆 | ⚠️ 不可說 Zep「刪除」或「破壞」記憶 (它的 edge body 保留於儲存層) |
| 沿襲 B 派 | inherit from / extend Decoupled Update | 沿襲 / 延伸解耦更新 | — |
| SLM 驅動記憶系統 | SLM-driven memory system | 以小模型驅動的記憶系統 | 見 §6 [18] 命名規則 |

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
| 規模效應 | scale effect (of judgment quality) | 規模效應 | 規模效應 (scale effect) |

**⚠️ 禁用詞**:
- ~~凍結的~~ (中文翻譯腔) → 改用 **不可微調 (frozen)**
- ~~固定參數的~~ → 改用 **不可微調 (frozen)**
- ~~cascading error propagation~~ / ~~連鎖錯誤~~ → 不使用，因為強力 conference-accepted 文獻支撐不足;改用結構性論證 (「destructive commit + low judgment quality → irreversible accumulation」) 配合 LightMem §5.6 quote 作為從子流派內部來的自我承認。**註 (2026-07-04)**:[18] 的錯誤注入實驗 (noisy writes → "persistent downstream effects by contaminating future retrieval"; cascading failure 最大崩潰) 現在提供了 conference-accepted 的實證支撐,**可以引述其實驗結果**,但仍不把 cascading error propagation 當自家定型概念使用——描述 [18] 的發現時沿用其原文措辭。
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
| 任務分解 | task decomposition | 任務分解 | 任務分解 (task decomposition) |
| 精確運算子 | exact operator | 精確運算子 | 精確運算子 (exact operator) |

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

### ⚠️ [3] 與 [18] 的「LightMem」同名衝突規則 (2026-07-04)

[3] Fang et al. (ICLR 2026) 的系統名為 **LightMem**;[18] Zhang et al. (ACL 2026) 的系統在其論文表格中**同樣標為 LightMem**。頂會慣例下,同名系統在文中以**作者—年份消歧**。本論文全篇規則:

- 裸名 **"LightMem" 一律專指 [3]** (它是我們點名討論的 Coupled Update 代表)。
- **[18] 永遠不用裸名指稱**;一律用「Zhang et al. [18]」或描述性指稱「近期以小模型驅動記憶系統的實證研究 [18]」/ "the SLM-driven memory system of Zhang et al. [18]"。
- 不要替 [18] 自創別名 (如 LightMem-SLM);替他人系統命名有風險。
- ☐ TODO:翻 [18] 原文確認其系統正式名稱是否確為 LightMem,或另有正式名;若另有名,更新本規則。

### 本論文 intro 使用的參考文獻 (20 條,對齊 intro v5;查證狀態 2026-07-04)

| # | 方法 / 論文 | 完整引用 | 在 intro 中的用途 | 原文查證 |
|---|---|---|---|---|
| [1] | A-Mem | Xu et al., NeurIPS 2025 | Real-world deployment、Passive 派、Cost-constrained evidence | ✅ PDF 在 project |
| [2] | MemGPT | Packer et al., 2023 (arXiv) | Stateless+context window、Passive 派 | ✅ |
| [3] | LightMem | Fang et al., ICLR 2026 | Coupled Update、§5.6 self-acknowledgment quote | ✅ §5.6 引文逐字核過 |
| [4] | MemoryOS | Kang et al., EMNLP 2025 | Passive 派、Storage–Update–Retrieval–Generation pipeline 來源 | ✅ |
| [5] | Mem0 | Chhikara et al., ECAI 2025 | External memory、Coupled Update | ✅ + mechanism 文件逐行對過 |
| [6] | Zep | Rasmussen et al., 2025 (arXiv) | External memory、Decoupled Update (we extend from) | ✅ + mechanism 文件;措辭見 §3 Zep 規則 |
| [7] | MemoryAgentBench | Hu, Wang, McAuley, ICLR 2026 | Retrieval surfaces outdated、**Selective Forgetting → FactConsolidation** (⚠️ 不可籠統寫「列為 KU 能力」)、Cost-constrained (Appendix I) | ✅ SF 定義原文核過 |
| [8] | Survey 2026 | Luo et al., ACL 2026 Findings | Temporal validity changes (§3.2 "The Temporal Validity of Knowledge") | ✅ §3.2 核過 |
| [9] | LongMemEval | Wu et al., ICLR 2025 | KU benchmark (五大核心能力明列 Knowledge Updates) | ✅ 定義原文核過 |
| [10] | MemBench | Tan et al., ACL 2025 Findings | KU benchmark (FM-ku 子集) | ⚠️ FM-ku 待對原文 spot-check |
| [11] | BEAM | Tavakoli et al., ICLR 2026 | KU benchmark (Knowledge Update + Contradiction Resolution) | ✅ 能力表核過 |
| [12] | MemoryBank | Zhong et al., AAAI 2024 | Passive 派 (Ebbinghaus 衰減) | ✅ |
| [13] | SlimLM | Pham et al., ACL 2025 Demo | Privacy-constrained → on-device | ✅ PDF 已補入 |
| [14] | CoGenesis | Zhang et al., ACL 2024 | Privacy → on-device SLM;「SLM 有 context 仍 lag behind LLM」 | ✅ 原文核過 ("still lag behind their larger counterparts") |
| [15] | Huang et al. (A Middle Path) | EMNLP 2025 | Privacy-constrained → on-premises | ✅ PDF 已補入 |
| [16] | FrugalGPT | Chen, Zaharia, Zou, TMLR 2024 | Cost-constrained → low-cost API | ✅ PDF 已補入 |
| [17] | ConflictBank | Su et al., NeurIPS 2024 D&B | 規模效應:同系列小模型 MR 較高 = 更堅持參數化知識、更難採納矛盾新資訊 | ✅ Figure 4 核過;⚠️ 該發現出自「新舊兩份證據同時在場」設定 (正對應記憶檢索同撈新舊版本、以及 FC 的 counterfactual 結構),引用時可註明此設定以更精確 |
| [18] | Zhang et al. (SLM memory) | Zhang et al., ACL 2026 | Backbone 換小模型後效能崩潰 (MemGPT SH F1: GPT-4o 60.16 → Qwen2.5-1.5B 9.56, Table 2);錯誤注入:寫入污染持續影響後續檢索 (Table 6);最新系統仍查詢前合併改寫 | ✅ 數字與引述核過;命名規則見上 |
| [19] | Least-to-Most | Zhou et al., ICLR 2023 | 任務分解 (method 設計原則引用) | ✅ PDF 已補入 |
| [20] | Decomposed Prompting | Khot et al., ICLR 2023 | 確定性子任務交精確運算子 (method 設計原則引用) | ✅ PDF 已補入 |

### Related Work 續編引用 (自 [21] 起,見 related_work v2)

| # | 論文 | 用途 |
|---|---|---|
| [21] | Astute RAG (Wang et al., ACL 2025) | RW 2.2:RAG 查詢時衝突解析 (cluster-and-separate) |
| [22] | TruthfulRAG (Liu et al., AAAI 2026) | RW 2.2:triple 層級查詢時衝突解析 |
| [23] | MQUAKE (Zhong et al., EMNLP 2023) | RW 2.3:FC 的 counterfactual 來源;Knowledge Editing 邊界 |

⚠️ **舊版 related_work 的 [17][18][19] 編號已與 intro v5 衝突** (intro 現在用到 [20]),RW 引用一律自 [21] 起續編。

### 已從 intro 移除的引用 (保留在 references.md 作為 reference)

| 引用 | 移除原因 |
|---|---|
| MIRIX (Wang & Chen, arXiv 2025) | Multi-agent 非本研究範圍 + 非 conference-accepted |
| Xiong et al. (cascading errors, arXiv 2025) | 非 conference-accepted |
| AgentDebug (Liu et al., arXiv 2025) | 從 ICLR 2026 撤回 (withdrawn) |
| SLM Future of Agentic AI (NVIDIA arXiv 2025) | arXiv preprint;cost-constrained 軸線已由 A-Mem + FrugalGPT 充分支撐 |
| Cattan et al. 2025 (*DRAGged into Conflicts*) | **2026-07-04 移除**:P5 (衝突類型分類) 已自架構移除,此引用隨之自 method/RW 移出;若多值方向回補再議 |

### 引用位置分工 (哪些文獻放 Related Work、哪些只在其他章節引用)

| 領域 | 放哪裡 | 理由 |
|---|---|---|
| 記憶系統 (passive / coupled / decoupled / SLM-driven) | **RW 2.1 (核心)** | 這是本文直接對話、對比的版圖 |
| RAG 知識衝突解析 (Astute、TruthfulRAG 等) | **RW 2.2 (核心)** | 我們機制的靈感來源 + 設定差異是定位關鍵 |
| KU 評估基準 (LongMemEval / MemBench / BEAM / MAB-FC) | **RW 2.3 (核心)** | 定義本文 scope + 說明主評測選擇 |
| Knowledge Editing (MQUAKE、model editing 一脈) | RW 2.3 內**邊界段** (2–3 句) | 只需劃清「編輯參數化知識 vs 更新外部記憶」的邊界;不開獨立小節 |
| KG / KB / Temporal KG / bi-temporal (as-of) | **不進 RW**;Zep 已代表 KG 記憶於 2.1;TKG/as-of 只在 discussion / future work 提 | as-of 需 valid time,超出本文 scope,展開反而引戰 |
| Deterministic freshness (*Don't Ask the LLM…*) | **method / analysis 的證據引用**,不進 RW | ☐ TODO:確認 venue status;若為 preprint,依本專案引用政策只作輔助證據、不作 RW 支柱 |
| 任務分解 (Least-to-Most、Decomposed Prompting) | method 設計原則引用 | 非本文對話的 sub-field |
| 受限部署 ([13]–[17]) | intro 動機層 only | 動機證據,非版圖 |
| Conflict-Aware Soft Prompting (project 內 PDF) | 可選:RW 2.2 一句帶過或不引 | 展示 RAG 衝突線廣度;非必要 |

---

## 7. 變更記錄 (Change Log)

| 日期 | 變更 | 原因 |
|---|---|---|
| 2026-06-17 | 初版建立 | 三份版本用詞不統一,需收斂為 single source of truth |
| 2026-06-23 | 移除 "demand-driven" 等 (詳見舊版) | (歷史紀錄保留,細項見 git) |
| 2026-06-23 | 移除 Two-Stage Framework 命名;新增 Section 1 | 改用 thesis + 兩個 named commitments |
| **2026-07-04** | **Conservative Writes → Faithful Writes** | 對齊論文標題 *Write Faithfully, Resolve at Query Time* 與 intro v3–v5;舊名列入禁用 |
| **2026-07-04** | **移除 conflict-type classification (P5) 作為架構元件;Cattan'25 引用退出 method/RW** | Scope 收斂至基準 KU/FC 定義 (current-value):同一事實多版本即互斥、取最新,衝突判斷退化為分群的直接推論;P5 去留交由 ablation (full vs p3+struct+freshness) 驗證,若多值方向回補再議 |
| **2026-07-04** | **新增 §0 Scope Statement** | 明定 KU = 四個基準的共同定義;多值/歷史 query 不作 claim |
| **2026-07-04** | 新增 [3]/[18] LightMem 同名衝突消歧規則 | 兩篇不同論文的系統同名;裸名專指 [3],[18] 以作者指稱 |
| **2026-07-04** | 引用表擴至 [17]–[20] 並補查證狀態;RW 引用改自 [21] 起續編 | 原文 PDF 已全數補入 project;逐條核過承重句;修正編號衝突 |
| **2026-07-04** | [7] 用途欄精確化為 Selective Forgetting → FactConsolidation | 原文查證:MAB 四大能力不含 "KU" 一詞,FC 掛在 selective forgetting 下 |
| **2026-07-04** | 新增 Zep 精確措辭規則 (§3) | 防「Zep 破壞性」過度宣稱;統一「檢索層等效不可逆」措辭 |
| **2026-07-04** | cascading 禁用詞加註 [18] 例外 | [18] (ACL 2026) 現提供 conference-accepted 錯誤注入實證,可引述其結果但不自創定型概念 |

---

## Appendix: 常見對應錯誤快速查表

寫作時最容易寫錯的對應:

| ❌ 錯誤(常見寫法) | ✅ 正確(canonical) |
|---|---|
| Conservative Writes / 保守寫入 (作為命名) | **Faithful Writes / 忠實寫入** |
| conflict-type classification / 衝突類型分類 / P5 (作為現役元件) | (已移除;查詢端 = identity grouping + temporal resolution) |
| 「Zep 破壞性地更新 / 刪除記憶」 | 「Zep 的失效標籤寫定即凍結、查詢時不再重解;檢索層等效不可逆」 |
| 裸名 "LightMem" 指 [18] | Zhang et al. [18] / 以小模型驅動的記憶系統 [18] |
| 「MAB 將 KU 列為核心能力」 | 「MAB 以 FactConsolidation 任務在 selective forgetting 能力下測試 KU」 |
| 「我們解決所有 KU 面向」(作為 claim) | (只能出現在 design rationale;claim 限 current-value KU) |
| Two-Stage Framework / 兩階段框架 | (不命名 framework;用 Faithful Writes + Query-Time KU Resolution) |
| Stage 1 / Stage 2 | write-time / query-time |
| reconciliation / reconcile | conflict resolution / resolve |
| 調和(作為動作) | 解析 |
| 基於 LLM 的代理 | LLM Agent |
| 有效性(在 KU 描述中) | 時效性 |
| 凍結的 | 不可微調 (frozen) |
| memory pool / 記憶池 | memory bank / 記憶庫 |
| demand-driven (作為定型概念) | (避免使用;改用描述性論述) |
| cascading error propagation (作為自家定型概念) | (引述 [18] 實驗結果時沿用其原文措辭) |
| system-level design (作為 abstract framing) | (避免使用;具體描述設計變數) |
| Structural extract (slide box 名) | Structural commit |
| 錯誤面 / error surface (作為命名概念) | (描述性論述:誤判是否落地並持續污染後續查詢) |
