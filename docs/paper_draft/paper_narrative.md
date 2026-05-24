# Paper Narrative v5：Query-time Conflict Resolution for Multi-hop Reasoning on Dynamic Conversational Memory

> v5 更新（基於文獻回顧 memory_systems_conflict_comparison.md）：
> - 對手分類軸從自創 A/B/C 派系改為**文獻認可的 pre-hoc / post-hoc**（Knowledge Conflicts Survey, Xu et al., 2024）
> - 方法架構從「3-phase 拼湊」改為**文獻認可的 Ingestion + Retrieval 雙 phase + component slots**（Mem0 §2.1 incremental processing paradigm）
> - 衝突類型雙視角對齊：inter-context conflict (Xu et al.) = Selective Forgetting × Multi-Hop (MemoryAgentBench)
> - 實證數字用 MemoryAgentBench Table 3 原始（FC-MH ≤ 5%，非 6%）
> - 新增 Observation 0：MemoryAgentBench Table 3 + Appendix K.2 prompt-fix 失敗證據
> - Mem0g 雙層 disclosure：paper claim "mark as invalid" vs vendored impl "DELETE r"
>
> v4 更新基底（baseline 對齊）：
> - 派系 A 細分 destructive vs non-destructive
> - 新增 §6.5 baselines disclosure
> - §9 反駁回應加 mem0g / Zep cloud / mem0 v3 三項
>
> v3 基底：
> - Phase 3 改為 Context Constructor refinement（fair-comparison constraint）
> - V1 prompt 降級為 ceiling analysis

---

## §0 Paper 策略定位（重要前置）

### 0.1 Paper 風格：保留彈性，不過早最佳化

我們**目前的方法相對簡單**，但**不寫死「simple-only」路線**。原因：
- 方法仍在演進中，特別是 Context Constructor (DC6) 的具體設計尚未定型，後續可能深化
- 過早鎖定「empirical-driven simple paper」風格是 premature optimization

**目前可確定的方法論**（保留）：
- 每個 design choice 必須對應到一個可量化的 observation（empirical chain）
- Paper 中 Empirical Motivation 與 Case Study 是重點章節
- Contribution 包含 problem formulation、diagnostic insight、design rationale，不只方法本身

**風格選擇延後決定**：等方法定型（特別是 DC6 Context Constructor）後，依方法複雜度選風格：
- 若方法保持簡單 → **empirical-driven design paper** 風格（Sentence-BERT、Diagnosing Retrieval vs Utilization 為參考）
- 若 DC6 引入較深設計 → **method + empirical analysis** 雙重路線

### 0.2 目標 Venue
- **首選**：ACL / EMNLP / NAACL（NLP 場對 empirical 與 method 兩種風格都友善）
- **可能**：NeurIPS / ICLR / ICML（若方法複雜度足夠）

### 0.3 勝利條件（成功標準）
- ✓ 不需要 end-to-end SOTA（只要 measurable improvement）
- ✓ 必須有清楚的 empirical motivation 章節
- ✓ 必須有 4 類 case study（見 §7）
- ✓ 必須誠實討論 failure cases
- ✓ **與 baselines 公平比較**：所有方法使用 MemoryAgentBench 內建的 vanilla system prompt 做最終 inference，差異只在「回傳給 LLM 的 memory context 內容」

---

## §1 研究問題定位

### 1.1 高層次問題
我們研究 **動態對話記憶（dynamic conversational memory）** 下的 **多跳推理（multi-hop reasoning）**，其中記憶累積過程中**同一事實會出現多個版本**，造成 **implicit knowledge conflict**（隱含衝突，無 explicit timestamp / operator / edit signal）。

### 1.2 為什麼這個問題重要
- 真實應用如：個人助理（Apple Intelligence、Google Assistant）、企業內部 agent、長期 customer support，皆為對話累積場景
- 過時知識若未解決，污染 LLM 推理 context；多跳場景下，**每一跳的衝突都會被獨立放大**
- **MemoryAgentBench (Hu et al., 2025) FC-MH 顯示所有現存方法 ≤ 6% 準確率**——這是當前明確的 open problem

### 1.3 架構性挑戰（核心邏輯鏈）

```
[前提 1] 多跳推理 → 需要多跳檢索
[前提 2] 多跳檢索必須在 retrieval phase（query 進來後才知道 hop 去哪）
   → [結論 1] 多跳檢索必然在 retrieval phase（post-hoc 時機）
[前提 3] 動態記憶中存在衝突
[前提 4] 若衝突未在 multi-hop retrieval 過程中解決，多版本知識會同時返回污染 LLM
   → [結論 2] 衝突解決必須與 multi-hop retrieval 同步在 retrieval phase（post-hoc）
```
**這是邏輯必然，不是設計品味。**

文獻依據：Knowledge Conflicts Survey (Xu et al., 2024) 的 pre-hoc / post-hoc 分類軸。

### 1.4 🔥 戰場限縮（重要）

**我們明確把戰場限縮為「KG-based memory + dynamic conversational memory + implicit conflict」**。理由：

| 理由 | 論述 |
|---|---|
| 結構必要性 | 多跳推理本質沿關係邊找下一實體；KG 提供明確關係結構，non-KG semantic embedding 在 multi-hop 是已知弱點 |
| 衝突 anchor | Fine-grained conflict detection 需 ground 到 specific entity / proposition；KG 提供 anchor，non-KG chunk 無法精確定位 |
| 場域限定合法 | T-GRAG 限 corporate reports、MemoTime 限 TKG、KEDKG 限 editing；場域限定是合法的科學選擇 |

**Paper 內必須明確寫**：「Our method is designed for KG-based memory; extending to non-KG settings is future work.」

---

## §2 文獻分類軸：Pre-hoc vs Post-hoc Conflict Resolution

> v5 更新：派系分類**直接採用 Knowledge Conflicts Survey (Xu et al., 2024) 的 pre-hoc / post-hoc 軸**，不再用自創的 A/B/C 派系。這個分類有文獻依據，reviewer 不會質疑。

### 2.1 文獻分類軸來源

**Knowledge Conflicts for LLMs: A Survey** (Xu et al., 2024) 將所有 mitigation strategies 沿 pre-hoc / post-hoc 兩個時機分類。對應到記憶系統的 Incremental Processing Paradigm：

| 維度 | Pre-hoc | Post-hoc |
|---|---|---|
| 時機 | Ingestion phase 寫入時就處理 | Retrieval phase 檢索/推論時處理 |
| 對應 paper 用語 | "extraction + update" (Mem0 §2.1) | "graph search f(α)=χ(ρ(φ(α)))" (Zep §3) |
| 優點 | 維持 KG 一致性、檢索負擔輕 | 可依 query 結構決定處理方式、保留所有歷史 |
| 侷限 | 寫入時不知未來 query 會用什麼推理鏈 | 需要承載結構（multi-hop 檢索流程） |

### 2.2 既有系統在 pre-hoc / post-hoc × multi-hop 兩軸的分布

| 系統 | Pre-hoc 衝突? | Post-hoc 衝突? | Multi-hop reasoning? |
|---|---|---|---|
| **Zep** (Rasmussen et al., 2025) | ✓ Edge invalidation (non-destructive, bi-temporal) | ✗ | ✗ (BFS 廣度擴展不算 query-aware) |
| **Mem0** (NL, Chhikara et al., 2025) | ✓ ADD/UPDATE/**DELETE**/NOOP (destructive) | ✗ | ✗ |
| **Mem0g** (graph, paper claim) | ✓ "Mark as invalid rather than physically removing" (non-destructive) | ✗ | ✗ (entity-centric + semantic triplet) |
| Mem0g (vendored impl, §6.5) | ⚠️ 公開實作為 Cypher `DELETE r` (destructive) | ✗ | ✗ |
| **HippoRAG 2** (Gutiérrez et al., 2025) | ✗ (append-only) | ✗ | ✓ (PPR) |
| **PropRAG** (Wang & Han) | ✗ (append-only) | ✗ | ✓✓ (PPR + beam search) |
| **EMG-RAG** (Wang et al., 2024) | ✓ insert/delete/replace (destructive) | ✗ | ✗ |
| **A-MEM** (Xu et al., 2025) | ✓ Zettelkasten linking | ✗ | partial |
| **T-GRAG** (Li et al., 2025) | ✓ TKG generation | ✓ Explicit timestamp decomposition | ✓ |
| **MemoTime** (Tan et al., 2026) | ✓ TKG | ✓ Operator-aware | ✓ |
| **KEDKG** (Lu et al., 2025) | ✓ Edit ingestion | ✓ CDM (limited) | ✓ |
| **本研究** | ✗ | ✓ **Implicit conflict, no explicit signal** | ✓✓ (PropRAG-based) |

### 2.3 同盟論文（empirical 支持）

**Diagnosing Retrieval vs. Utilization Bottlenecks** (Yuan et al., 2026/3) 實證證明：
- Retrieval method spans 20 points；write strategy 只 spans 3-8 points
- 「current memory pipelines may discard useful context that downstream retrieval mechanisms fail to compensate for」
- **這篇 paper 等於是「post-hoc 比 pre-hoc 更重要」的獨立實證**

---

## §3 衝突類型：雙視角對齊（明確 implicit subproblem 的學術定位）

> v5 更新：本研究問題從**兩個獨立社群的視角**描述，兩者指向同一件事。這個雙視角對齊讓 paper 可以引用兩個社群的文獻，提升 contribution 的說服力。

### 3.1 視角 A：Knowledge Conflicts Survey (Xu et al., 2024)

該 survey 將 LLM 衝突分三類：context-memory / **inter-context** / intra-memory conflict。

本研究屬於 **inter-context conflict** ——衝突發生在「過去不同時間寫進記憶」的多段記憶之間。成因主要是 **outdated information**（對話場景下少見 misinformation，主要是知識自然演變）。

### 3.2 視角 B：MemoryAgentBench (Hu et al., ICLR 2026)

該 benchmark 從 cognitive science 出發，將 memory agent 能力分四類：
1. **Accurate Retrieval (AR)** — 找到正確片段
2. **Test-Time Learning (TTL)** — 部署期間吸收新技能
3. **Long-Range Understanding (LRU)** — 整合長 context 全局資訊
4. **Selective Forgetting (SF)** — 偵測並解決舊知識與新知識的矛盾，捨棄過時資訊

本研究屬於 **SF 競能**，且是 SF 中最難的子任務：**FC-MH (Selective Forgetting × Multi-Hop)**。

### 3.3 兩視角的對應關係

| Xu et al. (2024) Survey | MemoryAgentBench (2026) | 本研究 |
|---|---|---|
| Inter-context conflict | Selective Forgetting (SF) | ✓ |
| Cause: outdated information | Counterfactual edit pairs (MQUAKE) | ✓ |
| Pre-hoc / Post-hoc 分類軸 | (未強調) | ✓ 採用此軸 |
| (未強調 multi-hop) | FC-MH (SF × Multi-Hop) | ✓ 具體 target |

時序作為判定基準：越新版本越接近 ground truth（MemoryAgentBench 用 serial number 顯式編碼）。

### 3.4 Implicit Subproblem 的學術定位（雙視角下）

從**視角 A**：T-GRAG / MemoTime / KEDKG 都處理 inter-context conflict，但依賴**explicit signal**（timestamp / operator / edit）；我們處理**implicit signal**（無顯式信號，僅有 ingestion order）。

從**視角 B**：MemoryAgentBench Table 3 顯示所有主流系統在 FC-MH ≤ 5%（vs FC-SH 60%）—— **SF × Multi-Hop 是公認的 open problem**，我們的研究 directly addresses this。



---

## §4 🆕 Empirical Motivation（Paper 重點章節，~2 頁）

> 這節是 empirical-driven paper 的命脈。每個 observation 對應一個 design choice。
>
> v5 更新：新增 Observation 0（MemoryAgentBench Table 3 全面失敗）與「prompt-level fix 已被證明無效」作為宏觀證據。

### 4.0 Observation 0：MemoryAgentBench FC-MH 全面失敗（既有實證）

**MemoryAgentBench Table 3 (Hu et al., ICLR 2026, GPT-4o-mini backbone)**：

| 系統 | FC-SH | **FC-MH** | 備註 |
|---|---|---|---|
| GPT-4o (long-context) | 60.0 | **5.0** | 全 context 直餵 |
| GPT-4.1-mini (long-context) | 36.0 | **5.0** | |
| BM25 | 48.0 | **3.0** | |
| GraphRAG | 14.0 | **2.0** | |
| **HippoRAG-v2** | 54.0 | **5.0** | structure-augmented RAG 最高 |
| **Mem0** | 18.0 | **2.0** | |
| **Zep** | 7.0 | **3.0** | |
| MIRIX | 14.0 | **2.0** | agentic memory |

**關鍵觀察**：
- 所有主流系統 FC-MH ≤ 5%
- 連 long-context GPT-4o 直餵也只有 5.0：**不是 context 不夠的問題，是 reasoning 結構問題**
- O4-mini reasoning model 在 6K context 達 80，32K 降到 14：**模型有能力，但無結構支持無法 scale**

**Implication**：問題不是模型容量，是**沒有方法把衝突解決機制嵌入 multi-hop reasoning 結構**——直接 motivate 我們的 post-hoc + multi-hop 設計。

### 4.0.1 Prompt-Level Fix 已被證明無效（MemoryAgentBench Appendix K.2）

MemoryAgentBench Appendix K.2 的 overwrite policy ablation：

| Policy | FC-SH | FC-MH |
|---|---|---|
| Baseline (GPT-4.1-mini) | 36.0 | 5.0 |
| Policy A (Always Prefer Later) | 40.0 | **4.0** |
| Policy B (Conservative Negation) | 28.0 | 4.0 |

**Paper 原文**：
> "prompting cannot effectively **propagate updates through multi-step reasoning chains**."

**這直接驗證了本研究的核心主張**：必須在 **retrieval 結構**中嵌入衝突解決，**prompt-only 不夠**。

也支撐我們的 fair-comparison constraint（§5.0）：所有對手用同 vanilla prompt 是合理的——既然 prompt-level 已被證明無效，我們的差異必須在 returned context 結構上。

### 4.1 Observation 1：Pre-hoc Conflict 的 Query-agnostic 盲點

**問題**：pre-hoc conflict mechanism 在 ingestion 時缺乏 query context，無法區分「對 query 重要的衝突」vs「對 query 無關的衝突」。

**Empirical evidence**（A1a vs A1b 實驗）：
- A1a (Per-ingestion intrinsic detection F1)：`[TODO 數據]`
- A1b (Query-driven extrinsic detection F1)：`[TODO 數據]`
- **Gap = A1a - A1b** 反映 pre-hoc 對 query-driven 衝突的 systematic blindness

**Case study taxonomy**（A1.5）：失敗 case 分類為四類：
- 類型 1：純語意衝突，新訊息詞彙與舊訊息不重疊
- 類型 2：跨多 turn 的傳遞衝突
- 類型 3：隱含衝突（需 query 才能 surface）
- 類型 4：False positive（pre-hoc 誤判為衝突但實為補充）

**Design implication**：把 conflict resolution 移到 **post-hoc (retrieval phase)**（Design Choice 1）

### 4.2 Observation 2：LLM 的 Prior Bias in Counterfactual Contexts

**問題**：MemoryAgentBench FC-MH 來自 **MQUAKE counterfactual edits**（dataset 設計與 LLM prior 衝突）。若讓 LLM 直接判斷新舊版本，LLM prior 會 override dataset fact，造成系統性偏差。

**Empirical evidence**（Ablation）：
- LLM direct judgment 在 counterfactual subset 上 F1：`[TODO 數據]`
- LLM group + code timestamp 在同 subset 上 F1：`[TODO 數據]`
- Gap 顯示 LLM prior bias 的 measurable impact

**Case study**：列 3-5 個 counterfactual case，顯示 LLM direct judgment 反向選擇

**Design implication**：LLM 只做語意分組，timestamp 用程式碼比較（Design Choice 2 + 3）

### 4.3 Observation 3：Multi-hop Conflict Propagation 效應

**問題**：多跳推理鏈上的衝突有 cascade effect——hop 1 處理錯誤會傳播到 hop 2、hop 3。獨立處理每 hop 與整體 path-aware 處理有顯著差距。

**Empirical evidence**：
- B1c (Multi-hop path recall)：raw retrieval 找全 path 的比例 `[TODO 數據]`
- Propagation analysis：hop k 出錯 → hop k+1 出錯的條件機率 `[TODO 數據]`

**Case study**：找 3-hop query 中 hop 1 衝突 → hop 2 連帶失敗的具體例子

**Design implication**：必須在 multi-hop retrieval 過程中同步處理衝突，而非 retrieval 後再過濾（Design Choice 4：PropRAG beam search 整合 conflict filter）

### 4.4 Observation 4：Context Presentation Effect under Fair-Comparison Constraint

**問題**：所有 baselines 在 MemoryAgentBench 都用同一個 vanilla system prompt（且 prompt-level fix 已被證明無效，§4.0.1）。在這個 constraint 下，**唯一可改的是「回傳什麼 context」**。同樣的 underlying evidence（即使 conflict 已被 resolve），用不同方式呈現給 LLM，下游 multi-hop reasoning 表現可能差異顯著。

**Empirical evidence**：
- D 系列實驗：
  - **Fair-version D4**：我們的 filter + vanilla prompt vs baselines + vanilla prompt
  - **Ceiling-version D2**：clean context + V1 prompt（per-hop output）→ 80%+ 上限 `[TODO 確認]`

**Case study**：相同 filtered evidence，用不同呈現格式（raw list vs 結構化 chain vs annotated）給 LLM，比較 reasoning 正確率

**Design implication**：Context Constructor component 應該專注於「在 fair-comparison constraint 下優化 context 呈現」（Design Choice 6），而不是改 inference prompt。

`[TODO 待跑實驗確認 §4.4 的 observation 是否真實存在；若不存在，DC6 需要重新定位]`

---

## §5 我們的方法（每個 choice 都有 empirical chain）

### 5.0 🔥 公平比較的 Constraint（重要前提）

為了與所有 baselines 公平比較，**我們不修改 inference 階段的 system prompt**：
- 所有方法都使用 MemoryAgentBench 內建的 vanilla system prompt 做最終 LLM inference
- 方法之間的差異**完全在「回傳給 LLM 的 memory context」**
- V1 prompt 等 inference 優化僅作為 **ceiling analysis**，不是 main result

**這個 constraint 是合理的**，因為：
1. MemoryAgentBench Appendix K.2 已證 prompt-level fix 無法解決 FC-MH（§4.0.1）
2. 改 inference prompt 會破壞與其他 baselines 的公平比較
3. 我們的 contribution 是 **結構化 retrieval 機制**，不是 prompt engineering

### 5.1 🆕 Unified Component Abstraction（文獻依據的雙 phase 架構）

v5 更新：方法架構**直接採用文獻認可的 Incremental Processing Paradigm**，不是我們自創的 3-phase 拼湊。

**文獻依據**：
- Mem0 paper §2.1: "Our architecture follows an **incremental processing paradigm**... two phases: **extraction and update**"
- MemoryAgentBench §3.2: "agents are required to take the chunks one by one, absorb them into memory, and **incrementally update the memory**"
- Zep §3: 給了 retrieval phase 的形式化定義 `f(α) = χ(ρ(φ(α))) = β`
- HippoRAG 2 §3 / PropRAG §5: 用「offline indexing + online retrieval」二分

**統一 component 槽位**：

```
Ingestion Phase:                Memory Store              Retrieval Phase:
  raw input                                                  query
    → Extraction                                              → Search (φ)
    → Update                     KG memory                    → Multi-hop Reasoning
    → (Conflict Mechanism:  ←→  (triples / propositions  ←→  → (Conflict Mechanism:
        pre-hoc, optional)        + metadata)                    post-hoc, optional)
                                                              → Rerank (ρ)
                                                              → Context Constructor (χ)
                                                                  ↓
                                                              To LLM inference
```

**每個 component 的 input/output**：

| Component | Phase | Input | Output |
|---|---|---|---|
| Extraction | Ingestion | Raw message / passage | Entity / fact / triple / proposition |
| Update | Ingestion | New units + memory | Deduped, integrated memory state |
| Conflict (pre-hoc, optional) | Ingestion | New unit + existing memory | Updated memory (with destructive or non-destructive resolution) |
| Search (φ) | Retrieval | Query | Top-K candidate units |
| Multi-hop Reasoning | Retrieval | Top-K candidates + memory graph | Reasoning paths |
| Conflict (post-hoc, optional) | Retrieval | Candidate paths + memory | Conflict-resolved candidates |
| Rerank (ρ) | Retrieval | Candidates | Ranked candidates |
| Context Constructor (χ) | Retrieval | Top-K ranked candidates | Formatted context string for LLM |

**研究焦點**：兩個 Conflict Mechanism slot 是設計變數。**現有系統都選 pre-hoc 或 none，沒有人在 post-hoc + multi-hop 上做 implicit conflict**。

### 5.2 設計理念：Observation → Choice → Evidence

我們的方法由六個 design choices 組成：

| Design Choice | 對應 Observation | 在 component pipeline 中的位置 |
|---|---|---|
| 1. Post-hoc conflict resolution（不在 Ingestion 做） | §4.1 Pre-hoc 盲點 | Retrieval phase 的 Conflict slot |
| 2. LLM 只做語意分組 | §4.2 LLM prior bias | Conflict slot 內部 |
| 3. 程式碼比 timestamp | §4.2 LLM prior bias | Conflict slot 內部 |
| 4. PropRAG beam search 作為 Multi-hop Reasoning | §4.3 propagation | Multi-hop Reasoning slot |
| 5. Logical filter（非破壞性） | 可逆性論述 | Conflict slot 的 resolution 形式 |
| 6. Context Constructor 優化 | §4.4 presentation effect | Context Constructor slot |

### 5.3 整體架構（在 unified pipeline 上的差異點 highlight）

我們的方法在 unified component pipeline 上的具體配置：

```
[INGESTION PHASE]
  - Extraction: 沿用 PropRAG 兩步驟 LLM（entity → proposition）
  - Update: Proposition 共現 entity 形成 clique；synonym edges
  - Conflict Mechanism (pre-hoc): ★ 我們在此 slot 留空 ★
                                  （理由見 Design Choice 1）

[MEMORY STORE]
  - Proposition graph + ingestion order metadata
  - 全部保留，沒有 destructive operation

[RETRIEVAL PHASE]
  - Search: Stage 1 Exploratory PPR (α=0.75) → Top-K passages
  - Multi-hop Reasoning: Stage 2 Beam Search (B=4, L_max=3) over proposition paths
                       （Design Choice 4）
  - Conflict Mechanism (post-hoc): ★ 我們的核心貢獻 ★
       a. 對候選推理鏈每個 proposition，找候選衝突對象
       b. LLM 做衝突分組（Design Choice 2，grouping only）
       c. 程式碼比 ingestion order → 識別舊版本（Design Choice 3）
       d. Logical filter（Design Choice 5，non-destructive）
  - Rerank: 沿用 PropRAG 的 exploitative PPR
  - Context Constructor: ★ Design Choice 6 待設計 ★
       候選機制：結構化 / annotation / conflict transparency

[OUTPUT to LLM]
  - vanilla MemoryAgentBench system prompt（fair comparison §5.0）
```

### 5.4 Design Choices 的 Empirical Chain（每個 choice 對應 component slot）

#### Design Choice 1: Post-hoc Conflict Mechanism

| 維度 | 內容 |
|---|---|
| Observation | §4.1 pre-hoc 對 query-driven 衝突有 systematic blind spot |
| Choice | 把 conflict mechanism 從 Ingestion slot 移到 Retrieval slot |
| Pipeline 位置 | Retrieval Phase 中 Multi-hop Reasoning 之後，Rerank 之前 |
| Evidence | A1a vs A1b 數字差 + A1.5 失敗 taxonomy + MemoryAgentBench Table 3 全面失敗 |
| Argument | 文獻依據：Knowledge Conflicts Survey 的 pre-hoc / post-hoc 分類；MemoryAgentBench Appendix K.2 證 prompt-fix 失效 |

#### Design Choice 2: LLM 只做語意分組

| 維度 | 內容 |
|---|---|
| Observation | §4.2 Counterfactual contexts（MQUAKE-based FC-MH）中 LLM prior bias 反向干擾 |
| Choice | LLM 任務限定為「這兩個 proposition 是否在說同一件事」 |
| Evidence | Ablation: direct vs grouped 在 counterfactual subset 的 F1 差距 |
| Argument | LLM 擅長 semantic judgment，不擅長忽略 prior 信任 dataset 事實 |

#### Design Choice 3: 程式碼比 Timestamp

| 維度 | 內容 |
|---|---|
| Observation | 時序判定是 deterministic operation，無需 stochastic LLM |
| Choice | Ingestion order 用 integer comparison |
| Evidence | Ablation: code vs LLM timestamp judgment 在 noise-immune 上的差距 |
| Argument | 對 deterministic 操作用 LLM 是 over-engineering 且引入 noise |

#### Design Choice 4: PropRAG Beam Search 作為 Multi-hop Reasoning Component

| 維度 | 內容 |
|---|---|
| Observation | §4.3 Multi-hop conflict propagation 需要 explicit path |
| Choice | 用 PropRAG 的 beam search 作為 Multi-hop Reasoning component |
| Pipeline 位置 | Retrieval Phase 的 Multi-hop Reasoning slot |
| Evidence | B1c path recall + ablation: PPR-only vs PPR+BeamSearch |
| Argument | Beam search 產生 **explicit reasoning path**，每跳對應 query reasoning chain 的一個位置，自然成為「在每一跳做衝突解決」的著力點 |

#### Design Choice 5: Logical Filter（Non-destructive Resolution）

| 維度 | 內容 |
|---|---|
| Observation | 對話累積本來就 noisy，ingestion-time 判斷錯誤無法回復 |
| Choice | 保留所有版本於 KG，僅過濾返回的 top-K |
| Evidence | Case study: ingestion error recovery scenario |
| Argument | 對 evolving conversation，可逆性是 production 必需 |

#### Design Choice 6: Context Constructor Refinement

| 維度 | 內容 |
|---|---|
| Observation | §4.4 同樣 evidence 不同呈現對 LLM reasoning 影響顯著 |
| Choice | 在 fair-comparison constraint 下優化 Context Constructor，不改 inference prompt |
| Pipeline 位置 | Retrieval Phase 的 Context Constructor slot |
| Evidence | D 系列實驗：fair-version vs ceiling-version |
| Argument | Context presentation 是「方法可控、公平比較可承擔」的最後一塊；inference 階段優化屬於 future work |

**注意**：DC6 的具體機制尚未定型，候選方向見 03_open_questions §B.5。

### 5.5 元件對應（vs 主要對手，使用 unified pipeline）

| Component | Zep (cloud SDK) | Mem0g (vendored v2) | HippoRAG 2 | PropRAG | T-GRAG | **我們** |
|---|---|---|---|---|---|---|
| Extraction | Episode → entity + fact | Triple via 2-step | Triple (LLM OpenIE) | Proposition (2-step LLM) | Timestamped doc | 沿用 PropRAG |
| Update | Entity res + edge dedup | Entity-centric | Synonym + passage edges | Clique + synonym + containment | TKG construction | 沿用 PropRAG |
| **Pre-hoc Conflict** | ✓ Bi-temporal invalidation | ⚠️ paper claims "mark as invalid"; vendored impl is Cypher `DELETE r` (§6.5) | ✗ | ✗ | ✓ TKG generation | ✗ |
| Search (φ) | Hybrid: cos + BM25 + BFS | Entity-centric + Semantic triplet | Query-to-triple + passage scoring | Stage 1 Exploratory PPR | Three-layer | 沿用 PropRAG |
| **Multi-hop Reasoning** | ✗ (BFS 算 search-level) | ✗ | ✓ PPR | ✓✓ Beam Search | ✓ Three-layer | ✓✓ Beam Search (沿用) |
| **Post-hoc Conflict** | ✗ (transferred to LLM via context) | ✗ | ✗ | ✗ | ✓ Explicit time decomp | ✓✓ **Implicit, LLM-group + code-compare** |
| Rerank (ρ) | RRF / MMR / cross-encoder | Similarity ranking | Recognition Memory | Exploitative PPR | Source extractor | 沿用 PropRAG |
| Context Constructor (χ) | Facts + date range + summaries | Plain triplets | Raw passages | Raw passages | Time-filtered | **DC6 待設計** |

**這個表的論述功能**：清楚顯示
- 我們**沒有**改 Pre-hoc Conflict slot（與 Zep / Mem0g 區隔）
- 我們**有**填 Post-hoc Conflict slot（與 HippoRAG 2 / PropRAG / T-GRAG implicit 區隔）
- 我們的 Multi-hop Reasoning slot 完全沿用 PropRAG（不爭 retrieval 創新）
- **我們的差異點集中在 Post-hoc Conflict 與 Context Constructor 兩個 slot**

註：詳細 baseline 版本資訊與 mem0g paper/impl 落差，見 §6.5

---

## §6 實驗設計

### 6.1 Benchmark
- **主場**：MemoryAgentBench FC-MH (Hu et al., ICLR 2026)
- **資料來源**：FC-MH 由 MQUAKE counterfactual edit pairs 構造，每組 pair 含原始事實 + 改寫矛盾版本（serial number = 時序）
- **既有實證（MemoryAgentBench Table 3, GPT-4o-mini）**：
  - GPT-4o (long-context): FC-SH 60.0, FC-MH **5.0**
  - HippoRAG-v2: FC-SH 54.0, FC-MH **5.0**（structure-augmented RAG 最高）
  - Mem0: FC-SH 18.0, FC-MH **2.0**
  - Zep: FC-SH 7.0, FC-MH **3.0**
  - MIRIX: FC-SH 14.0, FC-MH **2.0**
  - 所有主流系統 FC-MH ≤ 5%
- **補充考慮**：MAGIC (EMNLP 2025 Findings)
- **長 context 設定**：6K / 32K / 64K / 262K

### 6.2 對手清單（按 pre-hoc/post-hoc 軸分組）

**必比（Primary baselines）**：
1. **Zep** (Pre-hoc, non-destructive, KG + 對話累積 + bi-temporal)
2. **Mem0g** (Pre-hoc, vendored 為 destructive, KG + 對話累積)
3. **HippoRAG 2** (No conflict, multi-hop via PPR, KG)
4. **PropRAG** (No conflict, multi-hop via beam search, KG)
5. **T-GRAG** (Post-hoc explicit, TKG)

**強烈建議比（Secondary）**：
6. **Mem0** (NL variant, pre-hoc destructive DELETE)
7. **A-MEM** (Pre-hoc, Zettelkasten linking)
8. **KEDKG** (Post-hoc explicit, knowledge editing)

**可選**：MIRIX, EMG-RAG, Memory-R1, MemoTime（cite 為主）

### 6.3 實驗矩陣

**A 系列：派系 A 對手的 pre-hoc 失敗診斷**
| 編號 | 實驗 | 證據用於 |
|---|---|---|
| A1a | Per-ingestion detection F1 | §4.1 內在品質 |
| A1b | Query-driven detection F1 | §4.1 query-driven 盲點 |
| A1.5 | A1b 失敗 case taxonomy | §4.1 + §7.1 case study |
| A2 | Multi-hop path retrieval recall | §4.3 派系 A 找不齊多跳鏈 |
| A3 | Multi-hop 改造可行性論證 | 邏輯論證 |
| A4 | End-to-end QA on FC-MH | Main result |

**A4 預期結果（MemoryAgentBench Table 3 已測 + 我們補測）**：

| 方法 | FC-SH | FC-MH (Table 3) | 我們補測 FC-MH |
|---|---|---|---|
| HippoRAG-v2 | 54.0 | 5.0 | `[TODO 預期 ~5%]` |
| Mem0 | 18.0 | 2.0 | `[TODO 預期 ~2%]` |
| Mem0g | (未列) | (未列) | `[TODO 預期 ~5-10%]` |
| Zep | 7.0 | 3.0 | `[TODO 預期 ~3-5%]` |
| PropRAG | (未列) | (未列) | `[TODO 預期 ~15-25%]` |
| 我們 | (未列) | (未列) | `[TODO 目前 31%]` |

註：MemoryAgentBench Table 3 用 GPT-4o-mini；我們需確認 LLM backbone 一致以保 fair comparison。

**B 系列：派系 B 對手的「無衝突機制」失敗診斷**
| 編號 | 實驗 | 證據用於 |
|---|---|---|
| B1a | New-version recall@K | §4.3 retrieval 找到新版 |
| B1b | Old-version retrieval rate@K | §4.3 同時找回舊版（gap） |
| B1c | Multi-hop path recall | §4.3 多跳鏈完整性 |
| B2 | 加我們衝突機制後的 detection F1 | Main result |
| B3 | End-to-end QA on FC-MH | Main result |

**C 系列：派系 C 對手在 implicit 場景的失敗**
| 編號 | 實驗 | 證據用於 |
|---|---|---|
| C1 | T-GRAG 適配 FC-MH | §3.4 explicit query decomposition 失效 |
| C2 | KEDKG 適配 FC-MH | §3.4 collapse 回 pre-hoc |
| C3 | MemoTime 適配 FC-MH（可選） | §3.4 TKG 假設失效 |

**D 系列：Context Presentation 與 Fair Comparison vs Ceiling Analysis**

> 重要：D 系列分兩組——**fair 組**（同 vanilla prompt，可進 main result）vs **ceiling 組**（自訂 prompt，只作 ceiling analysis）

| 編號 | 實驗 | Prompt 是否 fair | 用途 |
|---|---|---|---|
| **Fair 組（main result 可用）** | | | |
| D-Fair-1 | Baselines 回傳 context + vanilla prompt | ✓ | 對手 baseline 數字 |
| D-Fair-2 | 我們 filter 後 context + vanilla prompt | ✓ | 我們的 main result |
| D-Fair-3 | 我們 + 結構化呈現 + vanilla prompt | ✓ | DC6 變體 1 |
| D-Fair-4 | 我們 + annotation + vanilla prompt | ✓ | DC6 變體 2 |
| D-Fair-5 | 我們 + conflict transparency + vanilla prompt | ✓ | DC6 變體 3 |
| **Ceiling 組（僅作 ceiling analysis）** | | | |
| D-Ceiling-1 | Oracle clean context + vanilla prompt | ✓（為對照） | 純 retrieval 上限 |
| D-Ceiling-2 | Oracle clean context + V1 prompt | ✗（V1 是自訂） | 純 inference 上限（~80%+）|
| D-Ceiling-3 | 我們 context + V1 prompt | ✗ | 「retrieval + inference 都優化」的上限 |

**論述**：
- D-Fair-1/2 對比 → 我們方法 vs baselines 的 fair main result
- D-Fair-2 vs D-Fair-3/4/5 → DC6 的 ablation（不同 context format）
- D-Ceiling-1/2 對比 → 「retrieval」與「inference」對最終 accuracy 的相對貢獻
- D-Ceiling-3 → paper 末端 discussion：若解除 fair constraint，方法的潛在上限

**Reviewer 角度**：D-Fair 組是 main result（不可妥協 fair）；D-Ceiling 組只在 Analysis section 出現作為 future direction 的依據。

**Ablation 系列：design choices 的個別貢獻**
| 變體 | 配置 | 對應 Design Choice |
|---|---|---|
| Full | All components | 全套 |
| -post-hoc | Move conflict to Ingestion (pre-hoc) | DC1 |
| -LLM grouping | Embedding cosine threshold | DC2 |
| -code timestamp | LLM direct judgment | DC2 + DC3 |
| -beam search | Top-K semantic only | DC4 |
| -logical filter | Destructive delete | DC5 |
| -Context Constructor | Vanilla concat | DC6 |

### 6.4 核心 Metrics（三層結構，跨實作公平比較）

> 設計原則：metrics 必須**跨越實作細節**（mem0g hard delete / Zep soft invalidate / 我們 logical filter 都能算同一組 metric）。

#### Layer 1：Detection Metrics（最小可比較點）

定義「方法認為哪些 propositions 是衝突」為 unified output，無論該方法是要刪 / invalidate / filter：

```
Detection Recall = 真衝突中被識別的比例
Detection Precision = 識別為衝突中真衝突的比例
Detection F1 = 兩者調和平均

【兩個維度】
- A1a: Per-ingestion intrinsic F1（內在偵測品質）
- A1b: Query-driven extrinsic F1（限定在 query 推理鏈上的偵測品質）

【關鍵 finding】
A1a - A1b 的 gap 即為「pre-hoc 對 query-driven 衝突的 systematic blind spot」（§4.1）
```

#### Layer 2：Retrieval-side Metrics（揭露機制差異，三個獨立 metrics）

> 這三個 metrics **互相不能互推**，必須一起呈現才能診斷機制失敗點。具體 case 示例見 03_open_questions §A.3。

```
New-version recall@K（per-hop, 越高越好）
  = 推理鏈上「最新版本 proposition」是否在返回的 top-K
  → 測「該找的找不找到」

Old-version retrieval rate@K（per-conflicting-pair, 越低越好）
  = 推理鏈相關的「舊版本」是否（也）在 top-K
  → 測「不該找的有沒有也撈回來」

Multi-hop path recall@K（per-query, all-or-nothing）
  = 整條推理鏈 [p1, p2, ..., pk] 是否完整在 top-K
  → 測「多跳鏈完整性」
```

**為什麼三個都需要**：

| 失敗模式 | New-ver recall | Old-ver rate | Path recall | 對應對手 |
|---|---|---|---|---|
| 找齊新版本但污染舊版本 | 高 | 高 | 中-高 | 派系 B raw retrieval |
| 多跳找不齊（即使無污染） | 中 | 低 | 低 | 派系 A single-hop + delete |
| 機制不觸發（無關 query） | 低 | 低 | 低 | 派系 C 適配 FC-MH |
| 理想 | 高 | 低 | 高 | 我們的方法（預期） |

#### Layer 3：End-to-end Metrics（最終表現，公平戰場）

```
QA Accuracy on FC-MH
  - 拆 single-hop vs 2-hop vs 3-hop sub-accuracy
  - 所有方法用 vanilla MemoryAgentBench system prompt
  - 差異只在「回傳給 LLM 的 context」

Per-Hop Resolution Rate（補充）
  = 每跳衝突是否被正確處理

All-Hops Resolution Rate（補充）
  = 整題 query 所有跳都正確的比例
```

#### 三層 metrics 的論述角色

| Layer | 角色 | Reviewer 信任度的貢獻 |
|---|---|---|
| Layer 1 (Detection F1) | 跨實作公平的子任務 | 「問題定義公平」 |
| Layer 2 (Retrieval 3 metrics) | 機制層級診斷 | 「機制分析有深度」 |
| Layer 3 (End-to-end) | 公平戰場最終結果 | 「結果有意義且 reproducible」 |

**這個三層設計確保**：即使對手實作有版本爭議，**Layer 1 的子任務比較**仍然可信（因為跨越了實作細節），保護了我們的核心 claim。

#### Cost Metrics（補充）

```
Latency per query
LLM calls per query
Cost ratio vs Zep / Mem0g baselines
```

`[TODO 數據見 03 §A.5]`

---

### 6.5 🆕 Baselines: Versions and Representativeness（透明 disclosure）

> 這節是必要的 reproducibility disclosure，但用「**we use as representative instances**」語調，不主動暴露落差作為弱點。

#### Paper 主文寫法（簡潔版，~150 words）

> 「For reproducibility, all baselines are evaluated using their MemoryAgentBench-bundled implementations at the snapshot of evaluation date [TODO]. Specifically, we use:
> - **Mem0g**: the v2.x graph variant bundled in MemoryAgentBench (prior to mem0 v3 in April 2026 which removed graph memory functionality). We treat this implementation as a representative instance of *destructive pre-hoc conflict resolution*.
> - **Zep**: evaluated via its hosted cloud API (zep_cloud SDK). Results reflect backend versions during our evaluation window of [date range]. We treat Zep as a representative instance of *non-destructive pre-hoc conflict resolution* (visible via `invalid_at` field).
> - **HippoRAG v2**: the official implementation bundled in MemoryAgentBench.
> - **T-GRAG**: re-implemented from the official codebase, adapted to FC-MH with ingestion-order as timestamp signal (see §C.1 for adaptation details).
>
> All retrieved contexts are archived for downstream auditability.」

#### Mem0g 落差的具體 disclosure（in footnote）

> [footnote] The publicly available mem0 v2.x graph implementation performs hard deletion of contradicted edges (Cypher `DELETE r`), whereas the paper's §2.2 describes soft invalidation. We treat this implementation as a representative instance of destructive pre-hoc methods. Our analysis (§4.1, §7.1) of pre-hoc blind spots applies to both destructive (mem0g) and non-destructive (Zep) variants of pre-hoc conflict resolution.

#### 為什麼這個寫法 work
- ✓ 不寫「我們發現對手實作偏離論文」（避免主動扣分）
- ✓ 寫「we treat as representative instance of [our category]」（把對手實作當成我們分類的證據）
- ✓ Footnote 中 disclosure 細節（足夠 reviewer 抓但不放主文 spotlight）
- ✓ 順帶引用 mem0 v3 移除圖記憶（強化 Discussion 章節的 industry-evidence）

#### 對應的 supplementary material 準備
- 所有 retrieved JSON archive 在 supplementary
- 評估時程明確標註
- mem0g commit hash / Zep cloud evaluation date range 都記錄

---

## §7 🆕 Case Study 設計（Paper 重點章節，~1.5 頁）

> 四類 case study 是 empirical-driven paper 的命脈。

### 7.1 Type 1: Write-time 失敗 Taxonomy

**目的**：證明 pre-hoc 不只是「準度不夠」，是「對某類衝突原理性盲」

**方法**：從 A1.5 的失敗 case 中 manual annotation 30-50 個 case，分類為：
- 類型 A：純語意衝突（詞彙不重疊）
- 類型 B：跨多 turn 的傳遞衝突
- 類型 C：隱含衝突（需 query 才能 surface）
- 類型 D：False positive（pre-hoc 誤判）

**輸出**：每類比例 + 2-3 個 representative case 詳細展示

### 7.2 Type 2: LLM Prior Bias Case

**目的**：證明 Design Choice 2/3 不是 paranoia，是 measurable phenomenon

**方法**：
- 篩出 FC-MH 中與 LLM prior 不符的 case（如 counterfactual 設計）
- 比較「LLM direct judgment」vs「LLM-group + code-compare」的判斷
- 列 3-5 個 case，展示 LLM 如何被 prior 反向拉走

**輸出**：accuracy 差距 + qualitative analysis

### 7.3 Type 3: Multi-hop Conflict Propagation

**目的**：證明 §4.3 propagation effect，並為 Design Choice 4 提供 case 依據

**方法**：
- 找 3-hop query 中 hop 1 與 hop 2 都有衝突的 case
- 展示「獨立 hop 處理」vs「path-aware 處理」的結果差距
- 量化 propagation：hop k 錯 → hop k+1 錯的條件機率

**輸出**：3 個典型 case + 數據

### 7.4 Type 4: 我們方法的 Failure Case（誠實節）

**目的**：誠實列出我們仍失敗的 case，提升 paper credibility

**預期類別**：
- 衝突分組失敗（LLM 沒識別出兩個 proposition 在說同一件事）
- 時序資訊不足（兩 fact 都很舊或時序模糊）
- 多重衝突（一事實 3+ 版本）
- DC6 Context Constructor 失敗（即使 conflict 已解，呈現方式不利推理）

**輸出**：每類 1-2 case + 比例 + 對 future work 的指引

---

## §8 貢獻聲明（重寫為 Empirical-Driven 風格）

即使 end-to-end 不是 SOTA，仍有以下七個獨立 contribution：

1. **Problem Formulation**：將 post-hoc conflict resolution 切分為 explicit 與 implicit 兩個子問題，明確 implicit subproblem 為 unexplored research gap
2. **Diagnostic Empirical Findings**：
   - 4.1 Write-time mechanism's query-agnostic blind spot（A1a vs A1b gap）
   - 4.2 LLM prior bias in counterfactual contexts（quantified）
   - 4.3 Multi-hop conflict propagation effect
3. **First Method in Scenario**：第一個結合 proposition-based beam search 與 post-hoc implicit conflict resolution，且第一個在 MemoryAgentBench FC-MH 上突破 5% 上限
4. **Empirical-Grounded Design Rationale**：每個 design choice 都有對應的 empirical observation 與 ablation 證據（非 ad-hoc）
5. **Safer LLM Usage Pattern**：「LLM semantic grouping + code-based timestamp」hybrid 避免 LLM prior bias，可推廣到其他 noisy / counterfactual 場景
6. **Non-destructive Conflict Resolution**：logical filter 保留所有版本，比破壞性 invalidation 更可逆
7. **Case Study Taxonomy**：pre-hoc 失敗模式的系統分類為後續研究提供 baseline understanding

---

## §9 預期反駁與回應

| 反駁 | 回應 |
|---|---|
| 「Post-hoc 比 pre-hoc 貴」 | (a) 作用範圍小（top-K）；(b) lazy evaluation；(c) 可逆性容錯。Cost analysis 在 §6 D-Fair-2 |
| 「T-GRAG/MemoTime/KEDKG 已做 post-hoc」 | 他們處理 explicit 子問題；我們處理 implicit 子問題（§3.4 子問題切分） |
| 「方法看起來簡單」 | (a) 風格未鎖死 simple-only（§0.1）；(b) Context Constructor (DC6) 仍在演進；(c) 每個 design choice 都有 empirical chain，非 ad-hoc |
| 「為什麼不比 non-KG 方法」 | 戰場明確限縮 KG（§1.4）；non-KG 是 future work；理由：multi-hop 需 structural relations |
| 「為什麼不也用 V1 prompt 改進 inference？」 | 改 inference prompt 破壞與其他 baselines 的公平比較（§5.0）；MemoryAgentBench Appendix K.2 已證 prompt-fix 在 FC-MH 失效 |
| 「FC-MH 6% 上限是 baseline 太弱」 | MemoryAgentBench 已測 RAG/long-context/commercial memory 多種 SOTA；Table 3 顯示所有方法 FC-MH ≤ 5% |
| 「LLM 分組 + code timestamp 是 trivial」 | Ablation 證明 vs LLM direct 的差距；對應 counterfactual contexts (MQUAKE-based) 必需設計 |
| 「Case study 是 cherry-picking」 | Taxonomy 來自 systematic annotation；提供 selection criteria 與每類比例 |
| 「Context Constructor (DC6) 看起來工作量小」 | 在 fair-comparison constraint 下，context refinement 是「方法可控、最後一塊可改的空間」；若解除 constraint 變成另一篇 paper |
| 🆕 「mem0g 你跑的 v2 是 hard delete，論文宣稱 mark as invalid，公平嗎？」 | 我們的核心對比是 pre-hoc vs post-hoc，不是 destructive vs non-destructive 的細節。Hard delete 與 mark as invalid 都是 pre-hoc、都缺 query context，**都受 A1a vs A1b gap 影響**。為完整性我們也比 Zep（其 cloud SDK 顯示 soft invalidate），結果同方向 |
| 🆕 「為什麼 Zep 用 cloud SDK 而非 Graphiti OSS？」 | (a) 主結果是「方法是否能解 implicit 衝突」，黑盒夠用；(b) 機制層級分析需白盒時，附錄補 Graphiti 抽樣對比；(c) 所有 Zep 回傳 JSON 已 archive |
| 🆕 「mem0g vendored 是 fork v2 不是論文 spec」 | 我們在 §6.5 / footnote 明確 disclose；mem0 upstream v3（2026-04, commit a488e190）已完全移除圖記憶，工業界本身已放棄這個方向 |

---

## §10 Wins / Losses 表格（暫定預期；待實驗確認）

> 取代原本的單純 win/lose scenarios。Reviewer 信任度的關鍵：**不是聲稱全贏，而是清楚標出 boundary**。

**暫定預期表（待數據填入；現在這些 cell 是預期方向，不保證是最終結果）**：

| 場景類型 | 我們 | 最強對手 | Δ | 預期 Insight |
|---|---|---|---|---|
| 1-hop implicit conflict | `[TODO]` | Zep `[TODO]` | + | Query-time 對 implicit 有優勢 |
| 2-hop implicit conflict | `[TODO]` | PropRAG `[TODO]` | ++ | 多跳放大 implicit conflict 影響 |
| 3-hop implicit conflict | `[TODO]` | T-GRAG `[TODO]` | +++ | 深度多跳即使 post-hoc 對手也失效 |
| Counterfactual (LLM prior 衝突) | `[TODO]` | Mem0g `[TODO]` | + | DC2/3 hybrid 的 robustness |
| No-conflict baseline | `[TODO]` | HippoRAG 2 `[TODO]` | ≈ | 無衝突場景無 overhead/loss |
| Explicit timestamp queries | `[TODO]` | T-GRAG `[TODO]` | -/≈ | T-GRAG 在自己場景仍強（誠實承認） |

**這個表格的論述功能**：
- 不聲稱全贏（reviewer 不會懷疑）
- 「輸 / 持平」的 cell 對應對手場景優勢（承認對手在其場景的 validity）
- 每個 cell 都有對應 insight，不只是數字

**論述定位**：我們不是在打倒所有對手，是在**填補一個特定的空白**（dynamic conversational + implicit + multi-hop + KG）。

### 10.1 不同實驗結果情境下的 paper angle

| 情境 | Paper angle |
|---|---|
| Detection F1 + End-to-end 都贏 | 全面 SOTA + empirical insight |
| Detection F1 贏，End-to-end 微輸 | 機制優越 + Context Constructor (DC6) 改進空間（誠實） |
| Detection F1 微輸，End-to-end 贏 | 系統綜合效益 + robustness |
| 三層 metrics 不同表現 | 機制分析 + boundary discovery（最有 insight）|
| 兩者微輸 | Problem formulation + diagnostic findings + design rationale + 可逆性 |

**目前狀態**：實作 31% > Zep 28%。最壞情境「微輸但機制贏」仍可發表。

---

## §11 Paper Structure 完整版本

```markdown
# Title: Diagnosing and Resolving Implicit Conflicts in Multi-Hop Reasoning
#        over Dynamic Conversational Memory

## Abstract (~200 words)
[TODO 簡述：implicit subproblem、empirical findings、簡單方法、結果、case study]

## 1. Introduction (~1.5 pages)
- §1 問題與重要性
- §2 三派系切分概覽 + 同盟證據
- §3 我們的位置（implicit subproblem）
- §8 貢獻聲明（精簡 4 點）

## 2. Related Work (~1 page)
- §2.1 派系 A
- §2.2 派系 B
- §2.3 派系 C（重點區隔 explicit vs implicit）

## 3. Empirical Motivation (~2 pages) ★ 重點章節
- §4.1 Write-time blind spot
- §4.2 LLM prior bias
- §4.3 Multi-hop propagation

## 4. Method (~1.5 pages) ★ 縮短
- §5.1 設計理念
- §5.2 整體架構（圖）
- §5.3 五個 design choices

## 5. Experiments (~3 pages)
- §6.1 Setup
- §6.2 對手清單
- §6.3 主結果（A4/B3/D4 主表）
- §6.4 Ablation

## 6. Analysis & Case Study (~1.5 pages) ★ 重點章節
- §7.1 Write-time 失敗 taxonomy
- §7.2 LLM prior bias case
- §7.3 Propagation case
- §7.4 Failure case（誠實節）
- Cost analysis

## 7. Discussion & Limitations (~0.5 page)
- §1.4 Scope: KG-based memory
- §9 反駁回應
- Future: non-KG extension, complex conflict types

## 8. Conclusion (~0.3 page)
```

---

## §12 關鍵句型範本

**Intro 第二段（核心邏輯鏈）**：
> Multi-hop retrieval is inherently query-dependent—without a query, there is no notion of "next hop." Consequently, in dynamic memory where conflicts persist, **conflict resolution must occur at the retrieval phase (post-hoc) and be tightly coupled with multi-hop reasoning**. This is not a design choice but a logical necessity. Our framing follows the pre-hoc/post-hoc taxonomy from the knowledge conflict literature (Xu et al., 2024).

**Related Work 三派系區隔**：
> Existing memory systems can be characterized along two axes: **conflict mechanism timing** (pre-hoc at ingestion vs. post-hoc at retrieval, following Xu et al. 2024) and **multi-hop reasoning support**. Pre-hoc systems (Zep, Mem0g, EMG-RAG) lack query context for disambiguation. Multi-hop systems without conflict mechanisms (HippoRAG 2, PropRAG) leak stale information. Recent post-hoc systems (T-GRAG, MemoTime, KEDKG) target explicit conflict subproblems via timestamps, operators, or edits. **None addresses the implicit conflict subproblem** that emerges in dynamic conversational memory.

**Empirical Motivation 開場**：
> Rather than proposing a complex method first, we begin by characterizing three empirical phenomena that any solution must address. Each phenomenon, in turn, motivates a specific design choice in our method.

**Method 開場（強調 empirical chain）**：
> Our method is the minimal design that addresses the three phenomena identified in §3. Each component is motivated by a specific empirical observation; we deliberately avoid additional complexity that cannot be justified by measurable improvement.

**Case Study 章節開場**：
> To complement aggregate metrics, we present case study taxonomies that reveal *why* prior methods fail and *when* our method succeeds. All cases are sampled via systematic annotation, with selection criteria documented in Appendix [X].

**Conclusion 收尾**：
> The implicit conflict subproblem of post-hoc conflict resolution remains largely unexplored. We provide both an empirical characterization of this subproblem and a minimal method that addresses it. Our findings suggest that **design simplicity, when grounded in empirical observation, can outperform unprincipled complexity** in this scenario.

---

## §13 不可妥協的紅線（從 03 同步）

無論 advisor 如何建議，以下不可犧牲：

1. **Conflict Mechanism 必須在 Retrieval Phase (post-hoc)**——否則整個 thesis 崩盤
2. **LLM 不直接 invalidate / delete**——與派系 A 的關鍵區隔
3. **MemoryAgentBench FC-MH 必須是主 benchmark**——6% → 31% 故事的根基
4. **必須比 T-GRAG**——否則無法 claim implicit subproblem 位置
5. **Ablation 必須包含 §5.3 DC2（LLM grouping vs direct）**——是 §4.2 observation 的證據
6. **§3 與 §6 必須是 paper 重點章節**——empirical 與 case study 風格的命脈
7. **🆕 Main result 必須用 vanilla MemoryAgentBench system prompt**——所有方法公平比較；V1 prompt 等 inference 優化只進 Appendix / Ceiling Analysis
8. **🆕 Context Constructor (DC6) 只動 context 不動 inference prompt**——破壞此原則 = 破壞 fair comparison = paper 主結果失效

---

> 下一步：把 §4 / §5 / §6 中所有 `[TODO]` 數據填上（見 03_open_questions.md §A），完整實作 §7 Case Study Plan（見 03 §H）。
