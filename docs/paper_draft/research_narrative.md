# Research Narrative — Multi-Hop Knowledge Update on Conversational LLM Agent Memory

> **Date**: 2026-05-31
> **Scope**: 研究主軸框架, 跟 Claude Code 對齊用。
> **Companion**: `fc_metric_spec.md` (metric / experiment / log schema 細節)

---

## §0 Sync Status — 步驟順序對應研究框架核心

> **每次更新此 narrative 跟 spec 時 sync 這一節**, 讓 Claude Code 跟自己一眼看到「目前在哪步 / 下一步是什麼 / 已 lock 什麼」。

### Framework 核心三步 (paper 三層)

```
Step 1 — Motivation evidence (paper §3):
  證明過去方法在 FC-MH 失敗的三個結構性 weakness 是真實:
    W1 Detection-retrieval 脫鉤 (Plan A: 32k 上 45-47% D✓R✗A✗)
    W2 純語意 top-k 在 multi-hop 結構失敗 (hop ≥2 抓不到)
    W3 Memory output 結構影響 LLM 多跳 inference (55% → 97% gap)

Step 2 — Direction evidence (paper §3 + §6):
  證明我們提出方向 (query-time detection coupling + chain-aware
  memory output) 初步 work

Step 3 — System + end-to-end (paper §5 + §6):
  System 整合 + 嘗試不同 method 變體
  End-to-end EM 對齊或超越 baseline
```

### Step → Action mapping (P0 → P1 → P2)

```
P0 (1-2 weeks)  完成 Step 1 + 初步 Step 2 evidence:
  Path A: Diagnostic 0       (1-2 天)    — W3 root cause
  Path B: Audit 1            (1-2 天)    — W1+W2 evidence 站得住
  Path C: Audit 2            (一晚)      — Mem0g 64k trend
  Path D: Audit 3            (1-2 週工程) — Our method 對齊 Plan A

P1 (2-4 weeks)  完成 Step 3 漸進迭代:
  Iter 0: Approach 3.1 (Self-Ask)              — 最小改動驗證方向
  Iter 1: + adaptive routing + FC-SH/AR        — generalizable claim 雛形
  Iter 2: escalate (CoRe / SARG-style)         — 視 Iter 0/1 EM

P2 (paper writing 前 2-4 weeks):
  Reader sweep at 6k
  64k all methods (anchor reader)
  Non-FC tasks (AR / EventQA)
  Case study materials
  Component sweeps
```

### Currently locked (✅) / pending data (🟡)

```
✅ §1-§4: Background, motivation, related work, three weaknesses
✅ §5.1: Design principles (4 對應 W1/W2/W3 + claim c)
✅ §5.2: Architecture overview (4 layers)
✅ §7: M-DRA metric framework
✅ §8: 3 case study directions
✅ §11: Iteration strategy

🟡 §5.3-§5.5: Final method variant lock (Diagnostic 0 後)
🟡 §6.3 numbers: Pending Audit 1+2+3
🟡 §9 paper 戰場 (6k 主 / 32k+ 主 / scope 縮): Pending Audit 後 lock
🔴 TBD prompt templates (Approach 1/2/3.1, Diagnostic 0 scaffolds)
```

### 重要決策已 lock

```
✅ Drop Zep baseline (數據不完整 33/78 partial events)
✅ Backbone: gemini-3.1-flash-lite GA, temp=0, chunk 512, text-embedding-004 (Plan A)
✅ Mem0g-pa 64k 跑, 262k 不跑 (cost prohibitive)
✅ Reader sweep 只在 6k (cost)
✅ Method named contribution 限縮在 Layer 3 (verdict) + Layer 4 (memory output)
✅ Approach 3 漸進迭代: 3.1 Self-Ask 起步, 視需要 escalate
✅ M-DRA 為 primary mechanism metric (Plan A 已驗證可用)
✅ Hard floor: end-to-end EM 仍 existential, 即使 mechanism story 完美
✅ user commitment: "無論如何重新調整系統也可以"
```

---

## §1 Background

### 1.1 LLM agent 與外部記憶

LLM-based agents 越來越仰賴外部記憶維持長期對話。代表方法:
- **Mem0** [Mem0 paper ECAI 2025]: flat-fact vector storage
- **Mem0g**: Mem0 + KG (graph-augmented)
- **Zep**: bi-temporal KG
- **MIRIX**, **HippoRAG-v2** [Gutierrez et al. ICML 2025]: entity PPR

### 1.2 記憶庫衝突: inter-context conflict

隨對話累積, 新資訊可能跟舊資訊衝突 (例如 user 第 5 session 說 "我住 Boston", 第 50 session 說 "我搬到 Tokyo")。本研究聚焦 Xu et al. [Knowledge Conflicts for LLMs: A Survey, EMNLP 2024] 分類的 **inter-context conflict**:
- 外部記憶內部不同條目間的衝突 (我們處理)
- 不是 LLM parametric memory 衝突
- 不是 retrieved context vs LLM 內部知識的衝突

**Dual nature 限制 disclosure (FC-MH 場景)**:
本研究主 benchmark FC-MH 基於 MQuAKE 構造 counterfactual chains:
- chain_old 通常符合 LLM 世界知識 (e.g. "Darwin married Emma")
- chain_new 是 counterfactual (e.g. "Darwin married Amala Paul")

這使 FC-MH **同時包含 inter-context conflict + context-memory conflict**。我們主處理前者; 後者 (counterfactual vs world knowledge) 視為 inference difficulty 的 additional cause, 用 M-inference + Diagnostic 0 量化但不主動處理。

### 1.3 場景與假設

- 增量成長對話記憶庫 (multi-turn dialogue)
- 純對話 stream, **無 explicit timestamp / edit signal / source authority signal** (只有對話順序)
- Multi-hop queries 可能跨多個有衝突的 hop
- 對應 MemoryAgentBench Selective Forgetting → FactConsolidation task

---

## §2 Motivation

### 2.1 單跳 KU 已成熟, 多跳衝突未解

**單跳 KU**: 在 LongMemEval [ref] 等 benchmark 上 Mem0 / Mem0g / Zep / HippoRAG-v2 表現都不錯。Plan A 我們重現 Mem0 6k FC-SH 92%, Mem0g-pa 6k FC-SH 79% (兩者 SH 都接近 ceiling) 支持這點。

→ Pre-hoc (write-time) 衝突機制在**單跳 + 直接 query** 場景已足夠。

**多跳衝突**: 當衝突存在於多跳推理鏈每一跳, 情況劇變。MABench FC-MH 上, Plan A 我們重現:

| Method × Task | 6k | 32k | 64k | 262k |
|---|---:|---:|---:|---:|
| LCA × SH | 96% | 91% | TBD | TBD |
| LCA × MH | 16% | 19% | TBD | TBD |
| Mem0 × SH | 92% | 90% | TBD | TBD |
| Mem0 × MH | 52% | 39% | TBD | TBD |
| Mem0g-pa × SH | 79% | 89% | TBD | TBD |
| **Mem0g-pa × MH** | **66% ⭐** | **40%** | TBD | TBD |

**Oracle ceiling (vanilla prompt)**:
- PureChain (only chain_new for THIS query, ~5 facts): **97%** ← LLM 處理乾淨 multi-hop 上限
- OracleClean-ThisChain (filter chain_old for THIS query, 保留 other-old): **55%** ← perfect filter ceiling
- OracleClean-All (filter all chain_old): **60%**
- Vanilla (無 filter): 20%

→ 現有方法在 FC-MH 跟 ceiling 之間有大 gap。OracleClean-ThisChain 55% 而非 OracleClean-All 60% 是合理 attainable ceiling, 因 other-old (165 個非 query 相關) 移不移無關緊要。55% → 97% 的 **42pp gap** 顯示**即使完美 chain_old filter**, LLM 多跳 inference 仍非 trivial。

### 2.2 三個結構性 weakness (paper §3 motivation 核心)

我們論述: 現有方法在 FC-MH 失敗**不是單一機制 bug, 是三個結構性問題同時作用**。

#### Weakness 1: Detection-retrieval 脫鉤

現有衝突感知方法 (Mem0/Mem0g) 在寫入端 fire UPDATE/DELETE, 但 query-time retrieval 階段**不能調用 detection 結果做 filter** — 是兩個獨立 phase:

```
Write-time pipeline:
  L1 fact extract → top-5 vector search (existing memories) →
  L2 LLM 對 facts ↔ top-5 candidates 判 ADD/UPDATE/DELETE/NONE → 
  寫入 vector_store (+ Mem0g graph_store)

Query-time pipeline:
  embed(query) → vector_store.search(limit=100) → top-100 memories
  Mem0g: + graph entity extract → BM25 rerank → top-5 triples
  全部 dump 進 final prompt as bullet list

→ Write-time detect 結果 (UPDATE event 標記) 完全沒有 propagate 到 query-time retrieval
→ Query-time 純按語意 top-k 抓, 可能仍把 chain_old 抓回
```

**Plan A empirical evidence**:
- Mem0 MH 32k: D✓R✗A✗ = 45% (write-time detect 對, retrieval 漏)
- Mem0g-pa MH 32k: D✓R✗A✗ = 47%
- Mem0 32k L2 precision 崩盤 0.97 → 0.51 (over-trigger)
- Mem0 32k UPDATE-content 正確率 1.00 → 0.63

**Mem0g 額外結構性問題 — Two-store divergence**:

```
Mem0g vector path + graph path 完全平行獨立 (ThreadPoolExecutor):
  - Vector L2 LLM 看 top-5 text memories 判 ADD/UPDATE/DELETE
  - Graph G4 LLM 看 Cypher 撈的 triples 判 DELETE
  - 兩個 LLM 看到不同 "existing memory" representation, 各自決策
  - 唯一同步點 = delete_all() 全 reset

State 可能 diverge:
  Unhappy path 1 (vector L2 漏, graph G4 抓):
    Vector store: ADD 新 + 保留舊 (雙存)
    Graph store: DELETE 舊 entity → graph 乾淨
    → query 時 vector 回 [old, new], graph 回 (new), prompt 含矛盾, LLM 困惑
    → 這就是 Mem0g-pa 6k MH 仍有 17% D✓R✗A✗ 的部分原因
  
  Unhappy path 2 (graph G4 漏, vector L2 抓):
    Vector store: UPDATE 為新事實 → 乾淨
    Graph store: ADD 新 entity + 保留舊 (雙存)
    → prompt-aware variant 把 graph relations verbalize 進 prompt, 帶入舊 entity
    → 直接傷 P(A|R=1)
```

→ Mem0g 不是統一 conflict resolution, 是**兩個獨立 race**, 可能任一漏掉造成 LEAK。我們方法**單一 query-time chain-restricted scope 跨 vector + graph 統一決策**, 沒有 divergence 問題。

#### Weakness 2: 純語意 top-k 在多跳結構失敗

Multi-hop query 後 hop 的 entity 不在 query 字面:

```
Query: "Where did the spouse of the author of Our Mutual Friend get educated?"
  Query 字面 entity: {"Our Mutual Friend"}
  
Chain needed:
  hop 1: Our Mutual Friend → author = Charles Darwin (chain_new) / Dickens (chain_old)
  hop 2: Charles Darwin → spouse = Amala Paul (chain_new) / Emma (chain_old)
                          ← Darwin 不在 query 字面!
  hop 3: Amala Paul → education = Belgium (chain_new) / India (chain_old)
                       ← Amala 不在 query 字面!

純語意 top-k (Mem0/Mem0g) 行為:
  - 對 query embed → top-100 都跟 "Our Mutual Friend" + "educated" 語意接近
  - 抓到 hop 1 chain_new/old
  - 抓不到 hop 2/3 fact (Darwin / Amala 跟 query 字面語意距離遠)
  → MISS at hop ≥2

Graph-aware (HippoRAG-v2 / Ours) 行為:
  - PPR from "Our Mutual Friend" → 找到 author entity Darwin
  - PPR 從 Darwin → spouse entity Amala
  - PPR 從 Amala → education entity Belgium
  → 透過圖結構 traversal 抓到全 chain
```

#### Weakness 3: Memory output 結構影響 LLM 多跳 inference

即使 retrieval 完美 (perfect filter), LLM 多跳 inference 仍非 trivial:

```
Plan A oracle experiment:
  PureChain (only chain_new, no distractor):    97%
  OracleClean-ThisChain (filter chain_old):     55%
  → 42pp gap 來自 memory output 含 distractor 時 LLM 多跳 coordination 困難

可能根因 (待 Diagnostic 0 區分):
  (a) Multi-hop coordination 困難: LLM 即使有對的 facts 也走錯 chain
  (b) Counterfactual vs world knowledge: LLM 偏 parametric (Darwin married Emma)
  
→ 若主因 (a), inference-side scaffold 思路 (Self-Ask / IRCoT / CoT) 借鑒到
   memory output side 可能 work, 我們有設計空間
→ 若主因 (b), memory output 救不了, Claim 3 scope 要縮
```

**Plan A baseline final prompt 都是 bullet list** (Mem0 paper §A "...prioritize most recent"):
```
"You are a helpful AI. Answer based on the memories.
 - goaltender is associated with the sport of pesäpallo
 - goaltender is associated with the sport of ice hockey
 - ..."
```

→ LLM 看兩條矛盾 fact 隨機猜, **沒人在 conversational memory 場景結構化呈現多跳 chain**。Memory output 結構是有效 attack surface。

### 2.3 三個 weakness 的疊加 → cumulative collapse

```
多跳衝突 query 上同時遭遇:
  - W1 寫入端 detect 跟查詢端 filter 脫鉤
  - W2 查詢端純語意抓不到後 hop
  - W3 即使乾淨 retrieval 多跳推理仍困難

→ 累積失敗 (Plan A: All-detected per-Q 41% (Mem0) vs PureChain 97% 的巨大 gap)
```

### 2.4 研究問題

> **Multi-hop knowledge update on conversational LLM agent memory**: 在動態增長的對話外部記憶上, 對於跨多個 hop 且每 hop 可能含 chain_old/chain_new 對的 query, 設計一個**統一通用的 memory system**:
>
> - **(a)** Query-time conflict detection 跟 retrieved candidates 耦合 (解 W1)
> - **(b)** Graph 結構 traversal 找 multi-hop derived facts (解 W2)
> - **(c)** Chain-aware memory output 引導 LLM 多跳 inference (解 W3)
> - **(d)** 整套設計 task-agnostic, 在 FC-MH 外其他記憶任務 (FC-SH / AR / EventQA) 也通用

### 2.5 為何重要

多跳知識更新在實際 LLM agent 部署常見: 法律 (判例累積)、客服 (政策變化)、個人助理 (人生事件累積影響)。不處理會產生過時的多跳推論答案。

**結構觀察**:
- 靜態文件多跳檢索 (HotpotQA / MuSiQue) 已成熟 (HippoRAG-v2 97% R@5)
- 對話單跳 KU 已 work (LongMemEval-KU)
- **但兩者交集 — 對話多跳+每跳衝突 — 未解** (Plan A FC-MH 全方法 < 50% 證據)

---

## §3 Related Work

### 3.1 多跳檢索 over external memory

- **HippoRAG** [NeurIPS 2024]: PPR over entity KG
- **HippoRAG-v2** [ICML 2025]: 加 fact rerank + synonymy linking
- **PropRAG** [EMNLP 2025]: proposition-level memory + beam search, HotpotQA 97.4% R@5
- **GraphRAG** [Microsoft 2024]: community-based KG summary

**關鍵觀察**: 這些方法**沒有衝突機制**, 假設文件集合靜態一致。動態對話記憶上 chain_old leakage 28-29%。

### 3.2 含衝突機制的對話記憶 (含 Mem0g two-store divergence critique)

我們場景內有衝突機制的方法:

#### Mem0 (vector-only) 完整 pipeline

**Ingestion (per chunk)**:
```
chunk → L1 FACT_RETRIEVAL_PROMPT → LLM → JSON {"facts": [...]}
for each fact:
  embed(fact) → top-5 vector search (existing memories)
  L2 DEFAULT_UPDATE_MEMORY_PROMPT → LLM → JSON {"memory":[{event, text, ?id, ?old_memory}, ...]}
                                  each emit ∈ {ADD, UPDATE, DELETE, NONE}
  execute:
    ADD     → vector_store.create(text, emb)
    UPDATE  → vector_store.replace(id, text, emb)
    DELETE  → vector_store.remove(id)
    NONE    → noop
```
- 2 LLM calls per chunk (L1 facts + L2 decision)
- State: Qdrant collection only
- Query-time: embed(query) → top-100 (no rerank)
- 1 LLM call per query (answer)

#### Mem0g (graph-augmented) 完整 pipeline

```
chunk → 
  ┌──────────── PARALLEL (ThreadPoolExecutor) ────────────┐
  │                                                       │
  Vector path = SAME as Mem0                  Graph path: _add_to_graph
                                                G1 _retrieve_nodes_from_data
                                                  LLM call (tool) → entities + types
                                                G2 _establish_nodes_relations_from_data
                                                  LLM call → relation triples
                                                G3 _search_graph_db
                                                  Cypher query Neo4j → existing entity triples
                                                G4 _get_delete_entities_from_search_output
                                                  LLM call → which old triples conflict
                                                DELETE conflicting + MERGE new (Cypher executes)
```
- 5 LLM calls per chunk (2 vector L1/L2 + 3 graph G1/G2/G4) — 2.5x Mem0
- Latency 2-3x Mem0
- State: Qdrant + Neo4j (兩 store 完全獨立)
- Query-time: vector top-100 + graph extract + BM25 rerank top-5 triples
- 2 LLM calls per query (entity extract + answer)

#### Mem0g final prompt — as-is vs prompt-aware

**MABench-as-is** (等於 Mem0 prompt):
```
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
# relations 沒進 prompt!
```

**Prompt-aware (restore upstream cookbook pattern)**:
```
system_prompt = (
    "You are a helpful AI. Answer the question based on the facts "
    "and the relationship graph below.\n"
    f"Facts:\n{memories_str}\n\n"
    f"Relationships:\n{rels_str}\n"
)
```

#### Two-store divergence 結構性 limitation

**Code 證據** (`mem0/memory/main.py`):
```
ingestion (L160-167):
  with concurrent.futures.ThreadPoolExecutor() as executor:
      future1 = executor.submit(self._add_to_vector_store, ...)
      future2 = executor.submit(self._add_to_graph, ...)
      concurrent.futures.wait([future1, future2])

search (L489-497): 同樣 parallel future, 各自跑
全 codebase 唯一 cross-store interaction = Memory.delete_all() (L613)
```

兩 store 各自決策邏輯**完全不知道對方在幹嘛**:
- 抽取: 文本 vs entity-relation triple
- 比對: top-5 vector vs Neo4j triple
- 衝突判斷: L2 LLM (text) vs G4 LLM (triple)

→ State 可 diverge, 解 §2.2 W1 中 Mem0g 額外結構問題。

#### Mem0/Mem0g 共同 limitation

Both 都做 **pre-hoc (write-time)** 衝突處理, 而且 write-time decision 跟 query-time retrieval 脫鉤 (寫入後 retrieval 階段不能調用 detection 結果指導 filter)。

[Note: Zep 也在這 category, 但實作不透明 + audit 數據不完整 (33/78 partial events), 從主對手列表移除]

### 3.3 Pre-hoc vs post-hoc 分類

根據 Xu et al. [Knowledge Conflicts Survey, EMNLP 2024]:
- **Pre-hoc (write-time)**: Mem0, Mem0g, EMG-RAG
- **Post-hoc (retrieval/inference-time)**:
  - **Explicit signal**: T-GRAG, MemoTime, KEDKG — 用 explicit timestamp/operator/edit signal
  - **Our work**: implicit signal (只用對話順序) + conversational + multi-hop coupled

→ 我們的 differentiation 不是 "pre vs post" 二分, 而是 **post-hoc + implicit + conversational + multi-hop 四維度交集**, prior work 未覆蓋。

### 3.4 Training-free multi-hop methods (inference-side, 跟我們 memory output design 對應)

| Paper | Venue | Training-free | Key idea | 跟我們關係 |
|---|---|:---:|---|---|
| **SARG** [arXiv 2506.08364] | TMLR review 2025 | ✓ | 從 retrieved 抽 triples + graph traversal + chain serialize 進 prompt | ★ **Direct prior art** for chain materialization |
| **Adaptive-RAG** [Jeong et al.] | NAACL 2024 | classifier 訓 | Classifier route to no/single/multi-step retrieval | Adaptive triggering motivation |
| **Graph-RAG Reasoning Bottleneck** [arXiv 2603.14045] | 2026 | ✓ | Question-type routing + SPARQL CoT prompting | Routing-based adaptive triggering |
| **CoRe** [Yu et al.] | NAACL 2025 Findings | ✓ | Context repetition 解 misordered context, F1 +30% | Memory output 結構化 supporting cite |
| **EKA** [arXiv 2512.20144] | 2025 | ✓ | Align LLM with retrieval set before iterative reasoning | Training-free inference strategy |
| **LLM-Independent Adaptive RAG** [Marina et al.] | EMNLP 2025 | ✓ | 27 external features for adaptive retrieval, no LLM call | Lightweight classifier 設計參考 |
| **TSSS** [arXiv 2510.19171] | 2025 | ✓ | Template-based reasoning + retriever-based terminator | Template approach |
| **MA-RAG** [arXiv 2505.20096] | 2025 | ✓ | Multi-agent CoT decomposition | Agent-based decomposition |
| **Self-Ask** [Press et al.] | EMNLP 2023 | ✓ | Explicit sub-question decomposition prompting | Simplest representative for our Iter 0 test |
| **IRCoT** [Trivedi et al.] | ACL 2023 | ✓ | Interleave CoT + retrieval | Inference-side scaffold reference |
| **Chain-of-Action** | ICLR 2025 | ✓ | Plug-and-play actions + multi-reference faith score | Conflict verification 對應 |

**關鍵觀察**: training-free multi-hop methods 全部聚焦 **inference-side scaffold** (改 LLM 推理行為), 我們聚焦**memory-side output design** (不改 LLM, 結構化 memory output)。

**SARG 最近 prior art**, 跟我們 Approach 3 概念重疊度高, 但 sharp differentiation:
1. **Chain 來源**: SARG per-query LLM 即時抽 triples (重 cost) — 我們用預建 prop-level graph + chain enumeration (輕)
2. **Conflict-awareness**: SARG 不處理 conflict — 我們同時 chain inject + conflict filter
3. **Memory dynamics**: SARG static document QA — 我們 conversational growing memory
4. **Adaptive triggering**: SARG every query 都做 — 我們加 routing 避免 simple query over-engineering

→ 我們 **unique sweet spot**: **conflict-aware + chain-materialized + adaptive-routed + conversational memory** 四維度交集, 無 prior art 覆蓋。

### 3.5 推理端多跳 scaffold (不重複, 上表已含)

不獨立列。

### 3.6 記憶 / KU benchmark

| Benchmark | KU | Multi-hop | Multi-hop KU? |
|---|:---:|:---:|:---:|
| LongMemEval | ✓ | △ (multi-session) | ✗ |
| LoCoMo | △ (temporal) | ✗ | ✗ |
| BEAM | ✓ | ✗ | ✗ |
| MemBench | △ | △ | ✗ |
| **MABench** | ✓ FC-SH | △ | **✓ FC-MH (MQuAKE-based)** |

→ FC-MH 是唯一明確測對話多跳 KU 的 benchmark。

### 3.7 Research gap (synthesis)

未被滿足的需求三維度 (用 Plan A 數據):

1. **Pre-hoc + write-time detection (Mem0/Mem0g)**:
   - 寫入端 pool 純語意, detection 跟 retrieval 階段脫鉤
   - Mem0g 還有 two-store divergence
   - **Empirical**: Mem0g-pa 6k 66% → 32k 40%, 結構性失敗

2. **多跳檢索方法 (HippoRAG-v2, PropRAG)**:
   - 完全無衝突機制
   - Chain_old leakage 28-29%

3. **Post-hoc + explicit signal (T-GRAG, KEDKG)**:
   - 需 explicit timestamp/operator
   - 純對話場景無此 signal

4. **Inference-side training-free multi-hop scaffold (SARG, Self-Ask, Adaptive-RAG, etc.)**:
   - 處理 static-document multi-hop QA
   - 不處理 conflict
   - 不處理 conversational growing memory

→ 我們的工作填補的 gap: **post-hoc (query-time) conflict resolution on implicit conversational signals, with query-aware graph-structured pool simultaneously serving conflict detection AND chain-materialized memory output**.

---

## §4 Three weaknesses — key analyses (paper §6 evidence chain)

### 4.1 Analysis 1 — Detection-retrieval 脫鉤 (Weakness 1 evidence)

**Question**: Mem0/Mem0g 失敗在 detection 機制本身, 還是 detection 跟 retrieval 階段脫鉤?

**Metric**: **M-DRA D✓R✗A✗ 比例 × ctx** (詳 §7)

**Plan A 已知數據**:
```
                    Mem0 MH 6k | Mem0g-pa MH 6k | Mem0 MH 32k | Mem0g-pa MH 32k
D✓R✓A✓ clean win    51%          65%              24%            22%
D✓R✓A✗ inference fail 13%        13%              15%            12%
D✓R✗A✗ retrieval fail 25%        17%              45% ★          47% ★
D✗R✗A✗ full fail    10%          4%               0%             1%

→ 32k 上 45-47% queries detect 對但 retrieval 漏
→ 證明失敗不在 detection 機制, 在 detection-retrieval 脫鉤
```

**Pending Audit 1** (Path B, 1-2 天):
- 對 Plan A 32k result 加 per-query case dump for D✓R✗A✗
- Two-store divergence audit (vector vs graph state inconsistency)
- L2 precision 崩盤 (0.97 → 0.51) 的具體 case 分析

**對應 method design**: Layer 3 query-time detection 直接用 retrieved candidates 作為 pool input, 避免脫鉤。

### 4.2 Analysis 2 — 純語意 top-k 在多跳結構失敗 (Weakness 2 evidence)

**Question**: Mem0/Mem0g retrieval 漏 chain_new 是因為純語意 top-k 抓不到 hop ≥2 fact 嗎?

**Metric**: **per-hop chain_new retrieval rate × hop_position**

**hop_position 定義**:
- `p=1`: hop 需要的 entity 在 query 字面 (e.g. "Our Mutual Friend")
- `p≥2`: 從前 hop 答案 derive (e.g. "Darwin", "Amala")

**Predicted**:
```
Mem0/Mem0g (純語意 top-k):
  p=1: 80-90% retrieved
  p=2: 30-50% (drop)
  p≥3: <30% (累積)

HippoRAG-v2 / Ours (graph PPR):
  p=1: ~80%
  p=2: 60-70% (flatter)
  p≥3: 50-60%
```

**Pending Audit 1** (Path B, 純分析 Plan A 既有 data, 1-2 天):
從 Plan A 既有 result + GT alignment 加 hop_position 標註 + retrieval rate 計算。

**對應 method design**: Layer 1 + Layer 2 graph PPR + chain enumeration 用 entity graph 抓 derived entity 的 fact。

### 4.3 Analysis 3 — Memory output design 對 LLM multi-hop inference 的關鍵性 (Weakness 3 evidence) ★

**Question**: 從 55% (OracleClean-ThisChain ceiling) 突破到接近 97% (PureChain), 需要什麼 memory output design?

**Diagnostic 0** (Path A, 1-2 天, critical) — 區分 root cause:

```
Setup:
  Reader: gemini-3.1-flash-lite (對齊 Plan A baseline)
  Temp: 0 (deterministic)
  Context: OracleClean-ThisChain (這個 query 的 chain_old 全 filter, 保留 other-old)
  Dataset: FC-MH 100Q

Variants:
  V_baseline (vanilla prompt, 已知 ~55%)
  V_A: + Self-Ask scaffold (system_prompt 加 "First, decompose the question into 
                            sub-questions corresponding to each reasoning hop. 
                            Then answer each step by step.")
  V_B: + CoT prompt ("Let's think step by step.")
  V_C: + CoRe-style chain repetition (chain props 在 context 內重複 2-3 次, 不同位置)

Decision criteria:
  Outcome 1: max(V_A, V_B, V_C) - 55% >= 15pp
    → Multi-hop coordination 是 gap 主因
    → Memory output 結構化是有效 attack surface
    → Weakness 3 confirm, Approach 3 motivate
  
  Outcome 2: max(Δ) < 5pp
    → Counterfactual vs world knowledge 是主因
    → Memory output 結構化救不了
    → Weakness 3 framing 改, Approach 3 退場
    → Paper Claim 3 scope 縮到 conflict filter
  
  Outcome 3: max(Δ) 在 5-15pp 之間
    → 部分 work, 細看 case
    → Approach 3 try 但預期有限

Cost: 1-2 days
```

**對應 method design**: Layer 4 chain-aware memory output design, 借鑒 inference-side scaffold 思路 (Self-Ask / IRCoT / CoT) 放在 memory side。

**Generalizable claim 進一步**: 同一 memory output design 在 non-FC 任務 (AR / EventQA) 也通用:
- AR: chain 退化為 retrieval chain (single hop or multi-hop without conflict)
- EventQA: chain 是時序 chain
- → 證明 design 不 task-specific, 是 unified memory output abstraction

### 4.4 三個分析的 unified mechanism story

```
W1 Detection-retrieval 脫鉤    W2 hop≥2 miss              W3 55→97 gap
        ↓                           ↓                          ↓
   Analysis 1                  Analysis 2                Analysis 3
   M-DRA D✓R✗A✗ × ctx          retrieval × p             Diagnostic 0
   (Plan A 已有 evidence)      (Plan A data 可分析)      (1-2 天可跑)
        ↓                           ↓                          ↓
   Case 1                      Case 2                    Case 3
   Mem0g detect ok             Darwin/Amala/Belgium      OracleClean
   retrieval leak              範例 case                   答錯 case
        ↓                           ↓                          ↓
   Method design               Method design             Method design
   Layer 3                     Layer 1+2                 Layer 4
   query-time +                graph PPR +               chain-aware
   detection-retrieval         chain enumeration          memory output
   coupling
```

### 4.5 Minimum viable evidence path

```
Step 1 (paper §3 motivation 立論):
  Analysis 1 + 2 + 3 → 證明三個 weakness 是真實結構問題
  → 已可寫 paper §3 motivation 完整論述

Step 2 (paper §6 our direction 初步):
  Initial our method test:
    - 對 D✓R✗A✗ 是否改善?
    - Approach 3 simplest variant (Self-Ask sub-question) 對 EM 是否提升?
  → 證明方向初步 work

Step 3 (paper §5+§6 method + end-to-end):
  System 整合 + ablation
  End-to-end EM 對齊 / 超越 baseline
```

→ **Step 1 + 2 完成就足夠奠定 paper 研究**。Step 3 是 method design 嘗試不同版本。

---

## §5 Method

### 5.1 Design principles (從三個 weakness 推導, locked)

```
Principle 1 (W1 對應): Query-time detection coupled with retrieval candidates
Principle 2 (W2 對應): Graph-structured traversal for multi-hop derived facts
Principle 3 (W3 對應): Chain-aware structured memory output guides LLM multi-hop
Principle 4 (claim c 對應): Task-agnostic via lightweight adaptive routing
```

### 5.2 Our method 工作 unit clarification

Our method 在 retrieval + verdict 後可給 LLM 的 signal 有三種:

```
(a) HippoRAG-v2 base 的 top-N raw passages
(b) Layer 3 verdict 偵測到的 conflict prop set
    - Set of (prop_old, prop_new) tuples 已 verdict
    - 我們有 high confidence "誰新誰舊" (Plan A verdict F1 ~94)
    - ★ 但不確定這些 prop 是否真的是 query chain 所需的
(c) Layer 2 chain enumeration 結果
    - Best chain props (top-1 or top-M chains)
    - 應該包含 query 所需的 reasoning chain
    - 但 chain enumeration 可能有 noise (beam 不完美)

→ Memory output design 的問題: 怎麼結合 (a)(b)(c) 三種 signal 給 LLM
→ 不同組合 = 不同 Approach (詳 §5.4)
```

### 5.3 Architecture overview

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 1: Multi-hop retrieval infrastructure (BORROWED)         │
│ - HippoRAG-v2 base: entity PPR + fact rerank + synonymy linking│
│ - PropRAG-inspired: propositions + beam search [可選]            │
│ Output: active region (top-N props by PPR mass) + top-N passages│
└────────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────────┐
│ Layer 2: Chain enumeration                                      │
│ - Beam search over proposition paths (B=8, L=3 currently)       │
│ Output: best chain props per query                              │
└────────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────────┐
│ Layer 3: Chain-restricted supersession verdict ★ contribution  │
│ - Build small pool (≤10) of chain-relevant candidates           │
│   ★ Pool = retrieved chain candidates (couples detection with   │
│      retrieval, NOT decoupled like Mem0)                        │
│ - LLM identify only (semantic grouping, no direction)           │
│ - Mechanical direction via timestamp tuple                      │
│ - Bidirectional aggregation                                     │
│ Output: chain_old_pids set (誰新誰舊)                            │
│ [對應 Principle 1 解 W1: detection 用 retrieved candidates]     │
└────────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────────┐
│ Layer 4: Memory output design ★ contribution                   │
│ - Combines top-N passages + conflict info + chain props         │
│ - Multiple variants (§5.4) — final via ablation                │
│ [對應 Principle 3 解 W3: chain-aware structure]                  │
│ [對應 Principle 4 claim c: adaptive routing for task-agnostic]   │
└────────────────────────────────────────────────────────────────┘
```

→ Layer 1+2 borrow from prior work (HippoRAG-v2 / PropRAG-inspired)
→ Layer 3+4 是我們 named contribution

### 5.4 Memory output design — variant slots for ablation

不 prescribe final variant, 列為 ablation 由數據決定:

```
filter_design ∈ {
  no_filter                    (baseline 17%)
  rescue                       (v2.0.3 default 31%)
  
  ─── Filter-only ───
  approach1                    LLM-rewrite_chunk (無損 filter, chunk-aware)
  approach2                    explicit_versioning (OLD/NEW 標 in prompt)
  
  ─── Chain-materialization (借 inference-side scaffold 思路) ───
  approach3.1                  Self-Ask sub-question style (simplest)
  approach3.2                  CoRe-style repetition
  approach3.3                  SARG-style chain serialize
  
  ─── Hybrid ───
  approach4                    adaptive_routing + approach3.X
                               (Simple → 1/2, Complex → 3.X)
}
```

#### 5.4.1 Approach 1 (LLM rewrite chunk) — DRAFT prompt

```
[TBD-1] 待 lock 細節
Template (per chunk containing chain_old):
  "Given the following text passage and a set of facts identified as outdated 
   ({outdated_fact_list}), rewrite the passage to remove only the outdated 
   content, keeping all other content verbatim. Do not add new facts.
   
   Passage: {original_passage}
   
   Rewritten passage:"

Cost: 1 LLM call per affected chunk
Pros: chunk-aware, 不破壞 chunk 結構
Cons: 只解 W1/W2 (conflict + retrieval), 不解 W3 (multi-hop inference)
```

#### 5.4.2 Approach 2 (Explicit versioning) — DRAFT prompt

```
[TBD-2] 待 lock 細節
Insert section at top of final memory output:
  "[Conflict Resolution for this query]
   The following facts are outdated and should be ignored:
   - {chain_old_fact_1}
   - {chain_old_fact_2}
   
   The following are the up-to-date versions:
   - {chain_new_fact_1}
   - {chain_new_fact_2}
   
   [Retrieved memories below]
   {raw_passages_unchanged}"

Cost: 0 LLM call (template)
Pros: 透明, 利用我們高 detection confidence
Cons: 純 prompt-level instruction, LLM 可能不 follow (variance 風險)
      W3 D variant 已測純 updated-list 失敗 (-2pp), 必須明確 OLD/NEW labelling
```

#### 5.4.3 Approach 3.1 (Self-Ask sub-question style) — DRAFT prompt ★ priority

```
[TBD-3.1] 待 lock 細節

Pipeline:
  1. From Layer 2 chain enumeration → best chain props
  2. LLM call (1 light call) to generate sub-questions:
     
     Prompt:
       "Given this multi-hop question: {query}
        And the chain of facts needed to answer it:
          Fact 1: {chain_prop_1}
          Fact 2: {chain_prop_2}
          Fact 3: {chain_prop_3}
        
        Decompose the question into sub-questions, where each sub-question 
        corresponds to one fact in the chain. Output format:
        Q1: <sub_question>  A1: <fact>
        Q2: <sub_question>  A2: <fact>
        ..."
  
  3. Inject result into final memory output before raw passages:
     "[Reasoning chain for this query]
      Q1: {sub_q1}  A1: {chain_prop_1}
      Q2: {sub_q2}  A2: {chain_prop_2}
      Q3: {sub_q3}  A3: {chain_prop_3}
      
      [Other potentially relevant memories]
      {filtered raw passages with chain_old removed}"

Cost overhead per query: 1 LLM call ≈ 1s
Pros: 同時解 W1 (filter) + W2 (chain props surface) + W3 (multi-hop guidance)
      Task-agnostic (chain 抽象通用)
Cons: 依賴 chain enumeration 品質; LLM 生 sub-question 品質
```

#### 5.4.4 Approach 3.2 (CoRe-style repetition)

```
若 Approach 3.1 EM 上升但 plateau, 加 chain repetition:
  - 將 chain section 在 context 中 repeat 2-3 次, 不同位置 (start / middle / end)
  - 解 "lost-in-the-middle" 問題

Reference: CoRe (Yu et al. NAACL 2025 Findings) — F1 +30%p
```

#### 5.4.5 Approach 3.3 (SARG-style full serialize)

```
若 3.1+3.2 仍不夠 EM:
  - Per-query LLM 從 retrieved passages 額外抽 triples (SARG-style)
  - 跟 chain props 並聯, 更密集 chain inject
  Cost overhead: 多個 LLM calls per query

Reference: SARG (arXiv 2506.08364, 2025) — chain serialize 進 prompt
我們 differentiation: SARG 不處理 conflict, 我們同時做
                     SARG 不針對 dynamic memory, 我們專攻 conversational
```

#### 5.4.6 Approach 4 (Adaptive routing)

```
Classifier 設計 [TBD-classifier]:
  Option a (rule-based, 推薦起步):
    n_hops = parse_cloze(query)  # 從 cloze 結構 count "of X of Y of..."
    if n_hops >= 2: route = complex
    else: route = simple
  
  Option b (LLM-based, 1 light call):
    LLM(query) → "simple" / "complex"
  
  Option c (transfer from Adaptive-RAG):
    用 Adaptive-RAG 已訓 classifier (預訓 NQ/TriviaQA/HotpotQA)

Routing decision:
  simple → Approach 1 (LLM rewrite) or 2 (versioning)
  complex → Approach 3.1/3.2/3.3

→ 對應 Principle 4 task-agnostic
→ Reference: Adaptive-RAG (Jeong et al. NAACL 2024), Graph-RAG Bottleneck (2603.14045)
```

#### 5.4.7 Decision logic for final method

```
跑完 Stage 2 Iter 0 ablation 後:
  Approach 3.1 vs rescue baseline EM:
    Δ > +5pp → Approach 3 概念 work, 進 Iter 1
    Δ ~0 或 -  → 退回 Approach 1/2 ablation, 重審 Approach 3

跑完 Iter 1 ablation 後:
  Adaptive routing FC-MH 是否傷 + FC-SH 是否退步:
    Routing improve FC-SH 不傷 FC-MH → keep
    Otherwise → simplify

跑完 Iter 2 (若需要):
  Approach 3.2/3.3 是否進一步 +
    Final variant 選 highest EM at 32k+ ctx
```

### 5.5 Generalizable to non-FC tasks (Principle 4 對應)

```
FC-MH (主):
  chain = multi-hop reasoning chain (從 chain_new derive)
  Approach 3 output: 顯式 multi-hop chain steps

FC-SH (退化):
  chain = single hop (chain_new only)
  Approach 3 output: 退化為 "Step 1: <sub-question> → fact" (單 step)
  Adaptive routing 通常 route 到 simple branch

AR (Accurate Retrieval, 無衝突, 可能多跳):
  chain = retrieval chain (從 ground truth derive)
  Approach 3 output: chain steps (不需 drop, 因無 chain_old)
  Adaptive routing 視 hop 數

EventQA (時序推理):
  chain = temporal reasoning chain
  Approach 3 output: chain steps 按時序排列

→ 同一框架, chain 抽象 unified
→ Claim (c) 升級: 不只 "不傷其他任務", 而是 "unified framework on all memory tasks"
```

### 5.6 Component justification — paper 寫作策略

```
Component                  Status       Paper 寫作
─────────────────────────────────────────────────────────────
Layer 1 HippoRAG-v2 base    工程選擇      Cite + transparent disclose
                                          Audit: Mem0g上加 module vs HippoRAG-v2上加
Layer 2 PropRAG-inspired   部分 cite     Cite + ablation (B/L sweep)
                                          可能 simplify to literature default
Active region top-50        工程選擇      Sweep ablation (5/20/50/100)
                                          ★ 不能保留 "工程選擇" 說法
Pool size ≤10              Mem0-inspired Sweep ablation (5/10/20)
Layer 3 Verdict             ★ contribution Sweep on prompt + pool design
Layer 4 Memory output      ★ contribution Ablation across Approach 1/2/3/4
```

→ Layer 1+2 = "standing on shoulders of giants", transparently cite。
→ Layer 3+4 = named contribution, ablation 完整 justify。
→ Active region / beam params: paper writing 前必須 sweep, 不能保留工程選擇。

---

## §6 Experiment plan

### 6.1 Setup (Plan A locked)

```
Backbone LLM:    gemini-3.1-flash-lite (Vertex ADC GA)
Embedder:        text-embedding-004 (Vertex ADC)
Chunk size:      512 (mem0/mem0g 統一; LCA dataset-default 4096 但無 ingestion 不影響)
Top-level temp:  0
Mem0 internal LLM temp: 0
Mem0 max_tokens: 16384
L1 prompt fix:   applied (mem0/mem0g 移除 2 個 rejection few-shots)
9 monkey-patches: applied (見 agent.py:280-301)
HF cache:        /home/yhchiang/MemoryAgentBench/.cache/huggingface
Trials:          1 (deterministic, no variance)

→ Paper appendix disclose:
  "Using temp=0 for deterministic EM evaluation; benchmark default 0.7 
   produces 23pp variance on FC-MH 6k across trials, motivating 
   deterministic eval."
```

**Reader sweep (cross-model robustness, 6k only due to cost)**:
- gemini-2.5-flash-lite
- gemini-2.5-flash
- gemini-3.1-flash-lite (anchor)
- gemini-3.5-flash

### 6.2 Ingestion cost reality (對 staging 影響)

```
Method            6k       32k      64k        262k
LCA               ~3 min   ~3 min   ~5 min     ~10-15 min
Mem0              ~11 min  ~53 min  ~100 min   ~400 min (~6.6 hr)
Mem0g-pa          ~30 min  ~130 min ~260 min   ~1040 min (~17 hr)
                                    (4.3 hr)   ★ prohibitive

每 ctx batch (4 cells: LCA+Mem0+Mem0g-pa × SH/MH):
  6k:    ~1.5 hr ✓ 已跑
  32k:   ~6 hr   ✓ 已跑
  64k:   ~12 hr (主要是 Mem0g-pa 8.6 hr) — anchor reader only
  262k:  ~46 hr — Mem0g-pa 不跑, LCA only ~10min × 2
```

→ Reader sweep 只在 6k (4 readers × all methods = 32 runs ≈ 8 hr 一個下午)
→ 64k 只 anchor reader
→ Mem0g-pa 262k 不跑

### 6.3 Staged execution (對齊 §0 Sync mapping)

#### Stage 0: Plan A verified ✓ (Master Dashboard 12 cells)

| Method | Task | Ctx | EM | Result file |
|---|---|---:|---:|---|
| LCA | SH | 6k | 96% | `outputs/gemini-3.1-flash-lite-temp0/...` |
| LCA | MH | 6k | 16% | 同上 |
| LCA | SH | 32k | 91% | 同上 |
| LCA | MH | 32k | 19% | 同上 |
| Mem0 | SH | 6k | 92% | `outputs/...-mem0-chunk512-temp0/` |
| Mem0 | MH | 6k | 52% | 同上 |
| Mem0 | SH | 32k | 90% | 同上 |
| Mem0 | MH | 32k | 39% | 同上 |
| Mem0g-pa | SH | 6k | 79% | `outputs/...-mem0g-promptaware-chunk512-temp0/` |
| Mem0g-pa | MH | 6k | **66% ⭐** | 同上 |
| Mem0g-pa | SH | 32k | 89% | 同上 |
| Mem0g-pa | MH | 32k | 40% | 同上 |

**Plan A 三大 finding**:

F1. SH 收斂 + Mem0g-pa SH 補回 13pp
- 6k SH: Mem0g-pa -13pp vs Mem0 (79 vs 92) — graph 是 SH 噪音
- 32k SH: Mem0g-pa -1pp vs Mem0 (89 vs 90) — 長 context 三方 ceiling

F2. MH 6k 黃金 cell — graph **+14pp** 打贏 vector ⭐
- Mem0g-pa MH 6k = 66% vs Mem0 = 52%
- Detection recall +14pp (0.76→0.90) + retrieval cleanliness P(R|D=1) +10pp (71→81)
- Graph 是 retrieval-side improvement: P(A|R=1) comparable (80% vs 83%)

F3. MH 32k graph 優勢消失 — 兩者同 ~40%
- Mem0g-pa MH 32k = 40% ≈ Mem0 = 39%
- Mechanism cancellation: graph 傷 R(-4pp) + 改善 inference(+6pp) → 相消
- 共同 fail mode = D✓R✗A✗ 45-47% (write-time detect 對但 retrieval 漏)
- Mem0 L2 precision 32k 崩盤 (0.97 → 0.51)

#### ★ Stage 1: P0 Pre-framing audit (~1-2 weeks)

**Path A: Diagnostic 0** (1-2 天, most critical)
- 詳 §4.3 + companion spec §18
- Output: 決定 Approach 3 是否進場 (Outcome 1/2/3)

**Path B: Audit 1** (1-2 天, 純分析既有 data)
- compute_m_dra.py — per-query D × R × A classification (詳 §7)
- compute_m_pool.py — pool composition + two-store divergence audit
- compute_hop_position_retrieval.py — per-hop × hop_position
- Output: §6 evidence 主表 + key cases

**Path C: Audit 2** (一晚, ~4.3hr)
- Mem0g-pa 64k MH (anchor reader)
- 加 M-DRA + M-pool dump
- Output: Mem0g 32k → 64k trend, 補完 baseline matrix

**Path D: Audit 3** (1-2 週工程)
- Our method 對齊 Plan A setup:
  - NV-Embed-v2 → text-embedding-004 (需處理 GPU env 切換)
  - preview → GA backbone
  - temp=0.7 → 0
- 跑 our method 6k / 32k MH
- 加 M-DRA + M-pool dump
- Output: 對齊 baseline 的 our method 數字, lock §9 戰場位置

#### Stage 2: Method design iteration (~2-4 weeks)

```
Iter 0 (1-2 天): Approach 3.1 (Self-Ask) initial test
  Setup: our method + Approach 3.1 chain-structured memory output
  Run: FC-MH 100Q (Plan A setup)
  Compare: vs our method rescue baseline (no chain inject)
  
  Decision:
    Δ EM > +5pp → Approach 3 概念 work, 進 Iter 1
    Δ ~0 或 - → 退回 Approach 1/2, 重審 Approach 3

Iter 1 (1 週): Approach 3.1 + adaptive routing
  Setup: + rule-based query complexity classifier
  Run: FC-MH + FC-SH + AR (verify generalizable claim 雛形)
  
  Decision:
    Routing improve FC-SH 不傷 FC-MH → keep
    Otherwise → simplify

Iter 2 (1-2 週, 視需要):
  3.2 CoRe-style repetition (if 3.1 plateau)
  3.3 SARG-style serialize (if 3.2 不夠)
  Adaptive routing 升級 (rule → LLM-based)
```

#### Stage 3: Comprehensive evaluation (~2-3 weeks)

```
Reader sweep at 6k:
  4 readers × {LCA, Mem0, Mem0g-pa, Ours-best} × {SH, MH}
  = 32 runs ≈ 8 hr 一個下午

64k all methods (anchor reader only):
  {LCA, Mem0, Mem0g-pa, Ours-best} × {SH, MH}
  = 8 runs ≈ 12 hr (Mem0g-pa 主導)

Non-FC tasks (generalizable claim ★):
  {Ours-best, Mem0g-pa} × {AR, EventQA} × {6k, 32k}
  測 (a) regression(task, ctx) ≥ -2pp (basic non-regression, claim c)
     (b) advantage(task, ctx) > 0 (preferred, generalizable claim 升級)

262k: LCA only (~10 min × 2)
```

### 6.4 Metric framework (詳 spec)

對應三個 weakness 的 3 個 primary mechanism metrics:

- **M1 (Per-query EM)** ★ main result, existential
- **M-DRA (D × R × A 3-way)** ★ Weakness 1 evidence
- **Per-hop retrieval × hop_position** ★ Weakness 2 evidence
- **M-inference + Diagnostic 0** ★ Weakness 3 evidence
- M-core / M-pool / M-claim-c — supporting

---

## §7 M-DRA — 詳細定義 (核心 mechanism metric)

### 7.1 定義

對每個 has_pair hop, 3-way binary classification:
- **D (Detection)**: method 是否正確偵測 chain_old/chain_new 為衝突 pair?
- **R (Retrieval)**: final context 是否乾淨 (chain_old 不在)?
- **A (Answer)**: final answer 是否正確?

**D 維度 per-method 定義**:
- Mem0: L2 LLM 輸出 UPDATE/DELETE event for this fact pair → D=1
- Mem0g: L2 (vector) OR G4 (graph) 任一 fire event → D=1
- HippoRAG-v2 vanilla: D undefined (無衝突機制) → 不算 M-DRA, 只算 M1
- Ours: Verdict.status="superseded" for this pair → D=1

**R 維度**: 從 final_context_text 算, method-agnostic
- R=1 if state ∈ {CLEAN, MISS}
- R=0 if state = LEAK (chain_old in context)

**A 維度**: 從 M1 算, method-agnostic
- A=1 if is_correct

### 7.2 8 cells

```
D✓R✓A✓  clean win
D✓R✓A✗  inference fail (memory 對但 LLM 答錯, Weakness 3 root cause)
D✓R✗A✗  retrieval fail ★ (Weakness 1 root cause, Plan A 32k 45-47% 主導)
D✓R✗A✓  recovered fail (retrieval 漏但 LLM 用 parametric 救回, rare)
D✗R✓A✓  serendipitous (沒偵測也答對)
D✗R✓A✗  silent fail (沒偵測但 retrieval 意外乾淨)
D✗R✗A✗  full fail
D✗R✗A✓  parametric win (極罕見)
```

### 7.3 為何嚴謹

- **概念**: D → R → A 是因果鏈, 三維度都 binary 可定義
- **跨方法可比**: R + A method-agnostic 完全可比; D 在含衝突機制方法之間可比
- **統計顯著**: chi-square / McNemar's test 適用, 樣本量 100Q × 175 has_pair hops 足夠
- **文獻 prior art**: cascade analysis 在 IRCoT / Khattab et al. RAG decomposition 有類似 idea, 但 D/R/A 命名是新
- **Paper 寫作 caveat**: 主表用 R × A (4 cells) 跨方法公平比, 補表 D × R × A (8 cells) 看 mechanism

### 7.4 Aggregate dimensions

```
基本: M-DRA × method × ctx
細分:
  M-DRA × method × ctx × n_hops (2/3/4)
  M-DRA × method × ctx × hop_position           ← W2 相關
  M-DRA × method × ctx × conflict_hop_count     ← W1 相關
```

### 7.5 跟其他 metric 的關係

```
M-DRA 8 cells (per hop)
 ├─ R 維度 → M-core CLEAN/LEAK/MISS
 │           CLEAN = R✓
 │           LEAK  = R✗ AND chain_old in context
 │           MISS  = R✗ AND chain_new not in context
 │
 ├─ Query-level all-CLEAN = M-detection
 │   per query: all has_pair hops 都 R=1
 │
 └─ P(A | R=1) = M-inference (given clean context, answer 對 ratio)
```

→ M-DRA 是 unified mechanism metric, M-core / M-detection / M-inference 都是它的 decomposition。

### 7.6 Decision rules for Weakness 1 evidence

```
Paper §6.4 Claim 1 evidence 站得住:
  Mem0g-pa 在 32k+ P(D✓R✗A✗) ≥ 40% (Plan A 47% ✓)
  AND
  Our method 在同 ctx P(D✓R✗A✗) 顯著低 (e.g., ≤ 15%)
  AND
  Gap 對應 EM gap (our method M1 EM > Mem0g-pa M1 EM)

→ 三條件成立, claim "detection-retrieval coupling 是 my contribution 主要 mechanism"
```

---

## §8 Case studies — 3 cases for 3 weaknesses

### 8.1 Case 1 (Weakness 1): Mem0g D✓R✗A✗ — detect ok but retrieval leak

```
Query: <某個 32k MH query 屬於 D✓R✗A✗>
Method: Mem0g-pa

Dump:
  - L2 / G4 event log: 證明 detect 對 (D✓)
  - Vector store state: chain_old 是否真的 DELETE
  - Graph store state: 同上
  - 兩 store 是否一致 (two-store divergence audit)
  - Query-time retrieved top-100: chain_old 仍在 (R✗)
  - LLM final answer: 被 chain_old 誤導 (A✗)

Annotation: "Mem0g L2 fired UPDATE event correctly, but query-time vector
search still surfaced chain_old (its embedding remained competitive among 
top-100). The graph store correctly removed chain_old via G4, but its 
relations didn't make it into top-5 BM25 rerank. Result: chain_old leaks 
into final context, LLM confused."

對應 method design: Layer 3 query-time detection + Layer 1 retrieval 耦合,
                    chain_old 不會被 retrieve 回 final context。
```

### 8.2 Case 2 (Weakness 2): Mem0g MISS at hop ≥2 — Darwin/Amala/Belgium 範例

```
Query: "Where did the spouse of the author of Our Mutual Friend get educated?"
Query 字面 entity: {"Our Mutual Friend"}
Method: Mem0g-pa (vs Ours)

Dump:
  - Hop chain: Our Mutual Friend → Darwin → Amala Paul → Belgium
  - Mem0g top-100: 大部分都是 "Our Mutual Friend" / "educated" 語意相關
    其中沒有 Darwin spouse 相關 fact (hop 2 entity not in query)
  - Mem0g final answer: India (parametric guess)
  
  - Ours retrieval: Layer 1 PPR from "Our Mutual Friend" → Darwin entity
                    → Layer 2 chain enumeration carries Darwin/Amala
                    → 抓到 hop 2/3 chain_new fact
  - Ours final answer: Belgium

Annotation: "Pure semantic top-k cannot reach hop ≥2 entities that aren't 
mentioned in the query surface. Graph PPR traverses through entity edges 
even when semantic similarity is weak. This is structural advantage of 
graph traversal over flat semantic search."

對應 method design: Layer 1 PPR + Layer 2 chain enumeration.
```

### 8.3 Case 3 (Weakness 3): OracleClean 答錯 — multi-hop coordination

```
Setup: OracleClean-ThisChain context (chain_old all filtered) but LLM still 失敗
Query: <某個 4-hop FC-MH query>

Dump:
  - Context: 含 chain_new + 其他 query chain_new (no chain_old for this query)
  - LLM answer: 走錯 hop, 例如把 hop 2 fact 跟 hop 3 facts 混淆
  
Diagnostic 0 evidence:
  - 給同 context + Self-Ask scaffold → 答對
  - → 證明問題是 multi-hop coordination, 不是知識本身

Annotation: "Even with chain_old removed, LLM struggles to coordinate 
across 3-4 hops in flat bullet-list memory output. When chain is explicitly 
surfaced as step-by-step structure (Approach 3.1 chain-structured output), 
LLM can follow the chain correctly. This is why memory output design 
matters beyond just filtering."

對應 method design: Layer 4 chain-aware memory output (Approach 3.X).
```

### 8.4 Stratified sampling

```
Target 16-20 cases:
  - 5-7 cases per Weakness (Claim 1/2/3)
  - 維度 1 (主): cross-method 結果對比 (Ours win / Mem0g win / All lose)
  - 維度 2: hop_position pattern (all p=1 / mix / all p≥2)
  - 維度 3: conflict_hop_count (1 / 2-3 / 4)
  - 維度 4: ctx (6k vs 32k vs 64k)
```

---

## §9 Strategic framing — 戰場位置 (Pending P0 數據 lock)

**Existential**: M1 EM 在某 ctx 必須贏 Mem0g-pa, paper 才站得住。

**Plan A baseline**:
- 6k MH Mem0g-pa = 66% ★ 強對手
- 32k MH Mem0g-pa = 40%

**Three scenarios** (pending Audit 0+1+2+3 + Iter 0):

```
情境 A: Ours 全 ctx 都贏 + Diagnostic 0 確認 Approach 3 work
  Paper main story: "整套 design 解三個 failure mode, 通用各記憶任務"
  - §6.3 主表 Ours 全 ctx EM 顯著高
  - §6.4 M-DRA: Ours 大幅降低 D✓R✗A✗
  - §6.4 hop_position: Ours hop ≥2 retrieval rate 高
  - §6.4 M-inference: Approach 3 突破 55% ceiling
  - §6.5 generalizable claim: 非 FC 任務也 work

情境 B: 6k 輸 / 32k+ 贏 + Diagnostic 0 條件 work
  Paper main story "advantage emerges at scale"
  - 主推 W1 (脫鉤在 32k+ 明顯)
  - W3 退為 secondary contribution
  - 6k 段 disclose: Mem0g-pa graph 在 6k 強, 但隨 ctx 失效

情境 C: Diagnostic 0 不 work (Approach 3 退場)
  Paper 縮 scope 到 conflict resolution
  - W1+W2 為主, W3 改用 inference-side scaffold cite
  - Memory output design 退回 Approach 1 / 2 純 filter

情境 D: 全方位輸
  必須重設計 (符合 user commitment "無論如何重新調整系統也可以"):
  - 換 base (Mem0g 上加我們 module)
  - 重新定義 problem scope
```

→ 戰場位置不預設, **由 P0 audit + Iter 0 數據決定**。

---

## §10 跟 Claude Code 對齊的核心訊息

> Paper 三步:
>
> 1. **Step 1 (Motivation)**: 證明三個結構性 weakness 真實
>    → P0 Path A (Diagnostic 0) + Path B (Audit 1 M-DRA / pool / hop_position) 完成
>
> 2. **Step 2 (Direction)**: 證明 query-time + chain-aware memory output 方向初步 work
>    → Path D (Audit 3 our method 對齊) + Iter 0 (Approach 3.1 prototype) 完成
>
> 3. **Step 3 (Method)**: 嘗試不同 method 變體, end-to-end 對齊或超越 baseline
>    → Iter 1+2, Stage 3 comprehensive
>
> **Step 1+2 完成就足夠奠定 paper 研究**, Step 3 是嘗試版本問題。
>
> 任何代碼改動 / 實驗應對應 Step 1/2/3 之一, 否則不該做。

---

## §11 Iteration strategy — 漸進迭代 method

### 11.1 原則: 最小改動最快迭代

```
Iter 0 (1-2 天): Approach 3.1 (Self-Ask sub-question, 最簡單代表)
  - 用 chain enumeration 結果
  - 1 個 LLM call 生 sub-questions
  - Inject 進 final memory output
  
  Decision: 
    Δ EM > +5pp → Approach 3 概念 work, 進 Iter 1
    Δ ~0 或 - → 退回 Approach 1/2, 重審

Iter 1 (1 週): Approach 3.1 + adaptive routing
  - 加 rule-based classifier (n_hops from cloze)
  - Simple → Approach 1 純 filter
  - Complex → Approach 3.1
  - 測 FC-MH + FC-SH (verify generalizable claim 雛形)
  
  Decision:
    Routing improve FC-SH 不傷 FC-MH → keep
    Otherwise → simplify

Iter 2 (1-2 週, 視情況): Escalate
  - Approach 3.2 CoRe-style repetition (if 3.1 plateau)
  - Approach 3.3 SARG-style serialize (if CoRe 不夠)
  - Adaptive routing 升級 (rule → LLM-based)
```

### 11.2 Hard floor: end-to-end EM 是 existential

```
即使 mechanism story 完美:
  - Plan A Mem0g-pa MH 6k = 66% 是強對手
  - 我們對齊 Plan A 後 MH 6k 必須有 path 接近或超過
  
若 Iter 0/1 後 EM 仍 < 50% 全 ctx:
  → 系統設計重審 (對應 user commitment "無論如何重新調整也可以")
  → 考慮: 換 base (Mem0g 上加 module)?
        重新定義 problem scope?
```

### 11.3 為何漸進迭代是正確策略

```
1. 最小改動最快驗證概念 — 1-2 天就知道方向是否對
2. 失敗也 cheap — 不會花 1 個月發現走錯路
3. 每步都有可發 paper 的 evidence (即使 escalate 到 3.3 都有 ablation 故事)
4. 平行 P0 audit, 不阻擋
```

---

## §12 TBD master list

### 12.1 P0 (本週/下週) ★ critical
- TBD-A0 ★: Diagnostic 0 (Path A, 1-2 天)
- TBD-A1: Audit 1 (Path B, 1-2 天, 純分析既有 data)
- TBD-A2: Audit 2 (Path C, 一晚 ~4.3hr)
- TBD-A3: Audit 3 (Path D, 1-2 週工程)
- TBD-3.1: Approach 3.1 prompt template lock

### 12.2 P1 (P0 後)
- Iter 0: Approach 3.1 on our method
- Iter 1: + adaptive routing
- TBD-1: Approach 1 prompt 措辭
- TBD-2: Approach 2 prompt 措辭
- TBD-classifier: Adaptive routing classifier 設計

### 12.3 P2 (paper submission 前)
- TBD-3.2/3.3: CoRe / SARG-style escalate (視 Iter 結果)
- TBD-4: All [ref] placeholders → actual citations
- TBD-5: Component sweep ablations (active region, beam params, pool size)
- TBD-6: Non-FC task results (AR / EventQA) — claim c + generalizable
- TBD-7: Case study materials (16-20 cases)

---

**End of research narrative**
