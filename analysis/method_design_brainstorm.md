# 多跳衝突機制方法設計 — Brainstorm v3

> **接續**：[fc_mh_research_overview.md](fc_mh_research_overview.md) §7
>
> **更新歷程**：
> - v0 (2026-04-29): M1–M5 method list, generic D1–D5 detection
> - v1 (2026-04-29): dimensional decomposition + Step 5 Recognition Memory
> - v2 (2026-04-29): granularity mismatch 修正 → additive structured channel (KG subgraph + passages)
> - **v3 (2026-04-29): 加 method design discipline + 加 sequential decomposition 路線（v2/v3 並存互補）**

---

## 0. Method Design Discipline（v3 新增）

### 為什麼需要

我們**沒有清楚分析出 FC-MH 的根本失敗原因**（probing prompt 引入 confound, 詳見 [overview §0.5](fc_mh_research_overview.md)）。所以方法設計**不能假設「我們知道根因，只需 fix」**，而要把每個方法當成「組合多個 component，每個 component hedge 某個可能的失敗模式」，然後用 prospective design 驗證每個 component 的 hedge 是否生效。

### Protocol

對每個方法 M，每個 component C ∈ M 必須回答：

| 問題 | 內容 |
|---|---|
| **(i) 假設的失敗模式** | C 假設 FC-MH 失敗的什麼模式？對應 H1–H5 哪個（或新假設）？ |
| **(ii) Hedge 機制** | C 的設計如何 hedge 此失敗？structural / architectural / prompt-level？ |
| **(iii) 預期提升維度** | C 預期改善哪個子集的 EM（conflict hop only / multi-hop only / counterfactual subset）？ |
| **(iv) 失敗時觀察特徵** | 若 hedge 沒效，會看到怎樣的 error pattern (E_i)？這個 pattern 對應「C 設計錯」還是「假設錯」？ |

→ 跑完實驗後，paper main result 是「component-by-component breakdown：v_X-1 給 +A pp，v_X-2 給 +B pp」，而非單一 method 的整體 EM。

---

## 1. Granularity Mismatch — v1 廢棄、v2/v3 共識的基礎

### v1 失效的核心觀察
HippoRAG-v2 retrieval unit 是 **passage（~512 tokens, ~25 facts）**，不是 triple。任何 KG-level 修改（PPR reset, forward chaining 在 KG 上 skip outdated）都被 passage granularity 稀釋 — outdated fact 仍會因 passage 含 current fact 而隨之被選入 top-K。OA1 → OA2 的 21 pp 差距已經明示 **fact-level surgical excision 才有效**。

### 共識
任何 paper-deployable 方法必須**直接干預 LLM prompt content**，不能只動 KG/PPR layer 的 ranking。v2 與 v3 各自用不同方式遵守此原則。

---

## 2. v2 — Additive Structured Channel（用 discipline 重 cast）

### 核心設計
**KG-derived chain subgraph 作為 LLM inference prompt 的 additive channel**，passages 不動。LLM 同時看到：
- (1) Standard top-K passages（保留 supporting context）
- (2) KG-derived versioned chain subgraph（每 hop 的 current/supersede 訊息）

```
Query
   ├── Standard HippoRAG retrieval ──> top-K passages ──┐
   │                                                    ├─> [LLM]
   └── KG Subgraph Extraction ──> versioned chain ─────┘
```

### Component → 失敗假設 mapping

| Component | (i) 假設失敗 | (ii) Hedge 機制 | (iii) 預期提升維度 | (iv) E_i 失敗特徵 |
|---|---|---|---|---|
| **v2-1** KG 邊版本標記 (Phase 1, OpenIE+) | LLM / 系統無法區分 current/outdated（H2 signal infer 失敗）| structural ground truth | 不直接提升 EM，是其他 component 前提；FC-MH 上 P/R ≈ 100% | OpenIE 失敗（Mem0 案例）→ 版本標記覆蓋率低 |
| **v2-2** Subgraph BFS extraction | 多跳 chain 中某 hop 的 fact 沒進 LLM context（H1 visibility）| 從 anchor BFS 走 K hops，保證 chain 主幹涵蓋 | conflict hop 子集 EM ↑ | E1 — chain 抽錯 / 不全（看 chain coverage rate） |
| **v2-3** KG-time conflict resolution（BFS 跳過 outdated edge）| 即使 fact 在 context，LLM 不信 marker 仍採信舊事實（H3 trust gap）| 結構層解，subgraph 中 outdated 不出現 | counterfactual subset EM ↑（SH 14 misfire 對照）| E2 — supersession 漏偵測 |
| **v2-4** Format A/B/C/D rendering | LLM 對結構化字串不 trust，仍從 passage 取舊事實（H3 變形）| explicit triple format + supersedes 標記 | 量化各 format LLM trust 差異 | E3 — subgraph 抽對但 LLM 答錯（subgraph vs passage 矛盾時）|
| **v2-5** Concat with passages | passages 含 outdated 干擾 | 期望 LLM 用 subgraph 當 authority | 與 v2-d (facts-only) 對比可知 passage 干擾量 | E3 子分類 — LLM trust passage > trust chain 的程度 |

### v2 變體（保留 v2 文件原 §5）

| 變體 | Subgraph 角色 | Passages 處理 | 預測 EM (P=R=0.9) |
|---|---|---|:---:|
| v2-a 並列（預設） | additive 補充 | 完全不動 | 80–92% |
| v2-b subgraph-first | 放在 prompt 最前，標為 "authoritative" | 完全不動 | 82–93% |
| v2-c subgraph-driven filter | 用 subgraph 篩 passages | 只保留含 subgraph entity 的 passages | 75–88% |
| v2-d facts-only | 用 subgraph + KG render fact list | 完全替代 passages | 90–95%（失 generalization）|

### v2 核心 trade-off
- **Pro**: 單 LLM call，原子處理，LLM 能 cross-validate passages 與 chain；HippoRAG pipeline 不動，generalization 風險低
- **Con**: 仍依賴 LLM 對 chain 的 trust（H3 gap 換位置但沒消除）；subgraph 抽錯就 silent fail

---

## 3. v3 — Iterative Sub-question Decomposition（新增）

### 動機

[diagnostic_findings.md](diagnostic_findings.md) Task B 已實測：
- per-hop standalone FC-SH 準確率 **94.5%**
- 全 chain hops 都答對（all-pass）比例 **87%**

→ **若能把 FC-MH 拆成 sequential single-hops 處理且鏈接正確，empirical ceiling 就是 87%**（沒用 oracle GT，是真實 retrieval 結果）。這個 evidence base 比 v2 subgraph 抽取質量假設更紮實。

### 核心設計

每個 hop 當成獨立 FC-SH 問題處理，用前一 hop 的 answer 構造下一 hop 的 sub-question。

```
[Query: "Who is the spouse of the author of Our Mutual Friend?"]
    │
    ▼
[v3-1: LLM Decomposer]
    chain: [Our Mutual Friend] → (author) → [?] → (spouse) → [?]
    sub-question 1: "Who is the author of Our Mutual Friend?"
    │
    ▼
[v3-2: Solve hop 1 (FC-SH pipeline)]
    HippoRAG-v2 retrieval + 衝突解析機制
    answer 1: "Charles Darwin"  (current,  not Charles Dickens)
    │
    ▼
[v3-3: LLM Sub-question Constructor]
    sub-question 2: "Who is the spouse of Charles Darwin?"
    │
    ▼
[v3-2: Solve hop 2 (FC-SH pipeline)]
    answer 2: "Emma Wedgwood"
    │
    ▼
[v3-4: Aggregator]
    final answer: "Emma Wedgwood"
```

### Component → 失敗假設 mapping

| Component | (i) 假設失敗 | (ii) Hedge 機制 | (iii) 預期提升維度 | (iv) E_i 失敗特徵 |
|---|---|---|---|---|
| **v3-1** Query Decomposer | LLM multi-hop reasoning 不穩定（H4 multiplicative compounding）| 顯式拆 chain 成 N 個 single-hop sub-question | 多跳 conflict hop 子集 EM ↑（拆後每個是 SH 級難度，已知 SH 衝突 LLM 處理較好 §13.2）| E_dec — sub-question 拆錯（chain entity 漏 / 順序錯）|
| **v3-2** Per-hop FC-SH solver | 單跳衝突解析失敗 | 用既有 FC-SH 機制（94.5% 已實測）；可外加 v2-style KG augment | per-hop accuracy（已知 94.5% baseline）| E_per_hop — 單 hop 衝突答錯（5–6% rate）|
| **v3-3** Sub-question Constructor | hop k answer 未被正確帶入 hop k+1 sub-question（H5 chain mis-anchor 變形）| 顯式用 hop k answer 構造 hop k+1 query | hop transition 穩定性 ↑ | E_chain — sub-question 用錯 entity（hop1 wrong → hop2 wrong sub-question）|
| **v3-4** Aggregator | 最終答案組合錯（chain 終點 entity 取錯 hop）| 跟 chain 終點 entity type match | 終端 hop 答案被正確取出 | E_agg — 最終取了中間 hop 答案 |

### v3 Prospective predictions

**理論上限**（per-hop 94.5% 多跳乘法）：
- 2-hop: 0.945² = 0.893
- 3-hop: 0.945³ = 0.844
- 4-hop: 0.945⁴ = 0.798
- B 實驗實測 all-pass 87%（FC-MH 全 100 題加權）

**含 v3-1/v3-3 失敗的實際預測**：

| 設計 | 預測 EM (FC-MH) | 主要 risk |
|---|:---:|---|
| v3 完整 pipeline | 75–85% | E_dec / E_chain 累積 |
| v3 + perfect decomposer (oracle) | 82–87% | E_per_hop / E_chain |
| (ref) B 實驗 all-pass | 87% | sub-question 人工拆 |

### v3 變體

| 變體 | 描述 | 用途 |
|---|---|---|
| **v3-a 標準** | LLM Decomposer + standard FC-SH solver | 主路線 |
| **v3-b oracle decomposer** | sub-questions 由 GT chain 構造（測試上限）| ablation：分離 E_dec 影響 |
| **v3-c with v2 inner** | per-hop FC-SH 內加 KG subgraph augmentation | 加強 hop 內 conflict resolution |
| **v3-d retry on inconsistency** | 若 hop k+1 retrieval 找不到 hop k entity 的鏈接，啟動 retry 機制 | 對 E_chain 有效 hedge |

---

## 4. v2 vs v3 — 互補不互斥

| 維度 | v2 (single-shot + KG augment) | v3 (sequential decomposition) |
|---|---|---|
| Failure transparency | 單一 LLM call，黑盒 | 分 N 步，可逐 hop debug |
| Error propagation | 無（同時看 chain） | 高（hop1 錯 → 鏈崩）|
| Cost (LLM calls) | 1× | 2N+1× |
| Latency | 低 | 高 |
| Empirical evidence base | subgraph 抽取質量未知 | per-hop 94.5% / all-pass 87% 已實測 |
| Hedge H1 (visibility) | structural（subgraph BFS）| architectural（per-hop retrieval 各自涵蓋）|
| Hedge H3 (trust gap) | 部分（KG 解但 passage 並列）| 較好（per-hop FC-SH 已知對 SH 衝突處理較好）|
| Hedge H4 (multiplicative) | indirect（rendering chain）| direct（顯式拆解）|
| Hedge H5 (chain mis-anchor) | indirect（顯式 chain 結構）| direct（v3-3 explicit construction）|
| Generalization 風險 | 低 | 中（decomposer 通用性待測）|
| 預測 EM (P=R=0.9) | 80–92% | 75–85% |

### Hybrid 可能性

| Hybrid | 描述 | 對哪些 E 有額外 hedge |
|---|---|---|
| **v3 + v2 inner** (= v3-c) | 每 hop FC-SH 內部加 KG subgraph augmentation | E_per_hop（hop 內衝突）|
| **v2 + v3 fallback** | v2 跑完，若 answer ambiguous / LLM uncertain 才退到 v3 | 成本最佳化 |
| **v3 with v2 final validation** | v3 答完後用 v2 KG subgraph 對 final answer 做 chain consistency check | E_chain（捕捉錯誤鏈接）|

→ **推薦先做 v3-a baseline → 看 E_dec / E_chain 比例 → 加 v2 inner（v3-c）或 v3-d retry → 與 v2-a 對照**

---

## 5. 完整 Prospective Prediction Table（v3）

| Method | 預測 EM (P=R=0.9) | 上下界 | 主要 risk |
|---|:---:|:---:|---|
| C0 baseline | 23% | — | — |
| v2-a 並列 subgraph + passages | 80–92% | OA2 (83%) ↔ Sim-OB (98%) | LLM trust passage > chain |
| v2-b subgraph-first | 82–93% | 同上 + 5pp | 同上 |
| v2-d facts-only | 90–95% | 失 generalization | 對非 FC 任務破壞 |
| **v3-a 完整 pipeline** | 75–85% | E_dec/E_chain 累積 | decomposer 不可靠 |
| v3-b oracle decomposer | 82–87% | 介於 B 實驗 all-pass | E_per_hop / E_chain |
| **v3-c v3 + v2 inner** | 80–90% | 補強 hop 內衝突 | 複雜度高 |
| v3-d retry on inconsistency | 80–88% | E_chain 修補 | 額外 LLM calls |
| (ref) OA2 modified | 83% | — | FC-overfit |
| (ref) Sim-OB | 98% | — | 不存在 |

---

## 6. 實驗順序（v3 修正）

### Phase α — v3-a baseline（empirical 上限驗證）
理由：v3-a 的 evidence base 紮實（B 實驗 87% empirical）；先跑這個確認 paper 主路線可行
- Implementation: LLM decomposer + per-hop FC-SH (HippoRAG-v2 + 既有衝突機制) + sub-question constructor
- Predicted EM: 75–85%
- Diagnostic: E_dec / E_per_hop / E_chain / E_agg 分布

### Phase β — v2-a 並列 subgraph（對照組）
- Implementation: KG versioning + subgraph BFS + Format A rendering + concat
- Predicted EM: 80–92%
- Diagnostic: E1 / E2 / E3 分布

### Phase γ — v3-c (v3 + v2 inner) 整合
若 Phase α 顯示 E_per_hop 大（hop 內衝突還是難），加 v2 KG subgraph 補強
若 Phase α 顯示 E_chain 大（鏈接 mis-anchor），加 v3-d retry

### Phase δ — Generalization ablation
v3-a / v2-a 跑 InfBench_sum / Detective_QA / Recsys

### Phase ε — Imperfect detection ablation
故意把 Phase 1 detection 降到 P/R = {0.6, 0.7, 0.8, 0.9}，看 v2/v3 degradation 曲線

---

## 7. Paper Framing（v3 修正）

### Main thesis 候選

| 候選 | 強調 |
|---|---|
| **A. KG-Derived Chain Augmentation for Multi-hop Knowledge Update** | v2-only |
| **B. Sequential Sub-question Decomposition with Versioned KG for Multi-hop Knowledge Update** | v3-only |
| **C. Decomposable Multi-hop Knowledge Update: Comparing Single-shot Augmentation and Sequential Decomposition** | v2 + v3 比較 |
| **D. Multi-hop Knowledge Update over Versioned Knowledge Graphs: Empirical Study of Chain Augmentation vs. Sub-question Decomposition** | 完整 + empirical 強調 |

→ 推薦 **D**：強調 paper 的 empirical contribution（用 B 實驗 87% 與 OA2 83% 當錨點），同時呈現兩條路線的 trade-off 而非預設哪條贏。

---

## 8. Open Questions（v3 累積）

1. **(v2)** Subgraph rendering 用什麼格式 LLM 最 trust（Format A/B/C/D）
2. **(v2)** Subgraph 與 passages 矛盾時 LLM trust 哪邊
3. **(v3)** Query decomposer 對 non-templated query 的通用性（FC-MH templated, LongMemEval 不一定）
4. **(v3)** E_dec / E_chain 的真實比例（沒實測前是預估）
5. **(共通)** Phase 1 detection precision 在非 FC dataset 的退化（ingest order = recency 是 FC artifact）
6. **(共通)** 對其他 4 類 memory task (summarization / Recsys / ICL) 的 generalization
7. **(新)** v2 vs v3 在 counterfactual subset (SH 14 misfire 案例) 上的差異 — 何時 sequential 比 single-shot 好？
8. **(新)** Decomposer 在 4-hop+ 上的失敗模式 — 4-hop 理論上限只 0.945⁴ ≈ 80%，是否值得做更深的 chain？

---

## 9. 與舊 v0 / v1 的對應

| 舊概念 | v3 對應 |
|---|---|
| v0 M1 chain-only filter | (廢棄，granularity issue) |
| v0 M2 bilateral chain | v2-a (subgraph 含兩版本標記) |
| v0 M3 per-hop subgraph | v2-c (subgraph-driven passage filter) |
| v0 M4 adaptive | v2-b + 機制 (authority instruction) |
| v0 M5 chain-block prompt | v2-4 Format choice |
| v1 Dim 0 (detection source) | v2-1 / v3 都用 (Phase 1) |
| v1 Dim 1 (chain awareness) | v2-2 BFS / v3-1 decomposition |
| v1 Dim 2 (conflict handling) | v2-3 KG-time / v3-2 per-hop |
| v1 Dim 3 (PPR mod) | (廢棄，granularity) |
| v1 C2 Step5 RM extend | 仍可作為 baseline contribution，獨立於 v2/v3 |
| v1 C4 Forward chaining (replace passages) | (廢棄，granularity) |

---

*版本：v3（2026-04-29 — 加 method design discipline + 加 sequential decomposition 路線）*
*待 iterate：(a) v3-1 decomposer prompt schema；(b) v3-3 sub-question constructor 實作；(c) Format A vs D ablation 範例 (v2)；(d) HippoRAG-v2 codebase 上的修改點 walkthrough*
