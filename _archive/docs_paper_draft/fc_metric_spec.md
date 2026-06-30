# FC-MH Cross-Method Metric Spec

> **Date**: 2026-05-31
> **Scope**: Metric / experiment / log schema 細節 SOP, Claude Code 直接執行用。
> **Companion**: `research_narrative.md` (research framework + 3-step paper plan)

---

## §0 Sync Status — 對齊 narrative §0

```
P0 (1-2 weeks) - 完成 Step 1 + 初步 Step 2 evidence:
  □ Path A: Diagnostic 0 (1-2 days)    ★ critical
  □ Path B: Audit 1 既有 data 加分析 (1-2 days)
  □ Path C: Audit 2 Mem0g-pa 64k MH (一晚 ~4.3hr)
  □ Path D: Audit 3 our method 對齊 Plan A (1-2 weeks)

P1 (2-4 weeks) - Method iteration:
  □ Iter 0: Approach 3.1 (Self-Ask)
  □ Iter 1: + adaptive routing + FC-SH/AR
  □ Iter 2: Escalate (CoRe / SARG-style) 視需要

P2 (paper writing 前):
  □ Reader sweep at 6k
  □ 64k all methods (anchor reader)
  □ Non-FC tasks
  □ Case study materials
  □ Component sweeps
```

### 5 個 must-lock items (Claude Code 跟 user 討論定)
- TBD-A0: Diagnostic 0 scaffold prompts (Self-Ask / CoT / CoRe-style)
- TBD-1: Approach 1 (LLM rewrite chunk) prompt
- TBD-2: Approach 2 (Explicit versioning) prompt
- TBD-3.1: Approach 3.1 (Self-Ask sub-question) prompt
- TBD-classifier: Adaptive routing classifier 設計

---

## §1 Metric hierarchy

| Tier | Metric | Role | 對應 Weakness | Paper section |
|---|---|---|---|---|
| **Primary MAIN** | **M1 (Per-query EM)** | 主結果 ★ existential | All | §6.3 主表 |
| **Primary MECHANISM** | **M-DRA (D × R × A 3-way)** | W1 evidence | 1 (脫鉤) | §6.4 |
| **Primary MECHANISM** | **Per-hop retrieval × hop_position** | W2 evidence | 2 (多跳結構) | §6.4 |
| **Primary MECHANISM** | **M-inference + Diagnostic 0** | W3 evidence | 3 (memory output) | §6.4 + §3 |
| Diagnostic | M-core (CLEAN/LEAK/MISS hop-level) | M-DRA R 維度 decompose | 1 | §7 |
| Diagnostic | M-pool (Pool composition + two-store divergence) | Root cause | 1 detail | §7 |
| Required | M-claim-c (Non-FC + generalizable) | claim c | — | §6.5 |

---

## §2 GT alignment basis

### 2.1 Per-query alignment JSON schema

每 query 一份 alignment JSON (源自 MQuAKE 對應 + ground truth analysis):

```json
{
  "qa_pair_id": "...",
  "num_hops": 3,
  "query_text": "Where did the spouse of the author of Our Mutual Friend get educated?",
  "query_entities": ["Our Mutual Friend"],
  "conflict_hop_count": 3,
  "max_hop_position": 3,
  "has_hop_position_ge2": true,
  
  "hops": [
    {
      "hop_idx": 0,
      "hop_position": 1,                          // 推理順序: 1 = direct from query entity
      "cloze": "Our Mutual Friend was authored by ____",
      "gt_answer": "Charles Darwin",              // chain_new
      "old_answer": "Charles Dickens",            // chain_old (if has_pair)
      "gt_fact_text": "Charles Darwin authored Our Mutual Friend",
      "old_fact_text": "Charles Dickens authored Our Mutual Friend",
      "conflict_type": "has_pair",
      
      "entities_required": ["Our Mutual Friend"], // hop 需要的 entity to lookup
      "entities_in_query": true,                  // 字面是否含
      
      "update_gap": 39                            // supplementary metadata
    },
    {
      "hop_idx": 1,
      "hop_position": 2,                          // p≥2: derived
      "cloze": "Charles Darwin's spouse is ____",
      "gt_answer": "Amala Paul",
      "old_answer": "Emma Wedgwood",
      ...
      "entities_required": ["Charles Darwin"],    // derived from hop 1!
      "entities_in_query": false,                 // ★ key for W2
      "update_gap": 87
    }
  ]
}
```

### 2.2 hop_position 計算 (implementation)

```python
# For each hop:
def compute_hop_position(query_entities: Set[str], 
                         entities_required: Set[str]) -> int:
    if entities_required.issubset(query_entities):
        return 1
    else:
        # Find earliest hop that produces these entities
        # In MQuAKE GT, hop chain is ordered, so:
        # hop_position = hop_idx + 1 (if first hop) or recursive
        # Simplest: use hop_idx + 1 from GT chain
        return hop_idx + 1
```

[TBD-13]: rule-based first (use MQuAKE GT hop chain order directly).
[TBD-14]: `entities_required` 直接從 MQuAKE GT 取, 不用 NER。

### 2.3 update_gap dimension — supplementary only

```
v1.4: 仍 dump 在 per-hop log 作為 metadata, 不主 stratify
理由: Mem0 write-time 用語意 top-k, 跟對話位置距離弱相關, 
      hop_position + ctx_length 是更直接的 stratify 維度

可用於 supplementary analysis (e.g. "大 update_gap 條件下 hop_position 效應更顯著嗎?")
```

---

## §3 M1: Per-query EM

```
M1(method, ctx, task) = #correct_queries / #total_queries

Verification:
  從 result file 的 agent_config 讀 ground truth
  我們 final_answer normalize → exact match GT
```

跟 method 的 task config 一致 (FC-SH / FC-MH / AR / EventQA / LRU)。

---

## §4 M-core: Context-state per-hop (DIAGNOSTIC, from M-DRA R 維度)

### 4.1 Per-hop state

對每個 has_pair hop:
- `new_present`: chain_new fact 是否在 final_context_text
- `old_present`: chain_old fact 是否在 final_context_text
- `state`:
  - `CLEAN`: new_present=true AND old_present=false
  - `LEAK`:  old_present=true
  - `MISS`:  new_present=false AND old_present=false

### 4.2 Matching tier (string match 嚴格度)

```python
def check_fact_in_context(fact_text: str, 
                          context: str,
                          tier: str = "strict") -> bool:
    if tier == "tier1_strict":
        # Exact substring match (lowercase, whitespace normalized)
        return fact_text.lower().strip() in context.lower()
    elif tier == "tier2_fuzzy":
        # Token overlap > 80%
        ...
    elif tier == "tier3_paraphrase":
        # LLM-based judge (expensive, only for spot-check)
        ...
```

Primary tier = tier1_strict (default), tier2/tier3 用於 sanity check。

### 4.3 Aggregate

```
M-core CLEAN_rate(method, ctx) = #(hops with state=CLEAN) / #(hops with has_pair)
M-core LEAK_rate(method, ctx) = #(hops with state=LEAK) / #(hops with has_pair)
M-core MISS_rate(method, ctx) = #(hops with state=MISS) / #(hops with has_pair)

加 hop_position 維度 (對應 Weakness 2):
  CLEAN/LEAK/MISS × method × ctx × hop_position

特別關注:
  Mem0/Mem0g 預期 MISS_rate at hop_position ≥2 顯著高於 hop_position=1
  Ours/HippoRAG-v2 預期相對平坦
  → 直接 evidence for W2
```

### 4.4 Method variant slots (filter design ablation)

```
filter_design ∈ {
  no_filter                    (baseline 17%)
  rescue                       (v2.0.3 default 31%)
  
  ─── Filter-only approaches ───
  approach1                    LLM-rewrite_chunk (無損 filter)
  approach2                    explicit_versioning (OLD/NEW 標)
  
  ─── Chain-materialization (借 inference-side scaffold 思路) ───
  approach3.1                  Self-Ask sub-question style (simplest, 1-2 天)
  approach3.2                  CoRe-style repetition
  approach3.3                  SARG-style chain serialize
  
  ─── Hybrid ───
  approach4                    adaptive_routing + approach3.X
}
```

不 prescribe final variant, 由 ablation 數據決定。

#### 4.4.1 Approach 1 (LLM rewrite chunk) — DRAFT prompt [TBD-1]

```
For each chunk containing chain_old fact:

SYSTEM:
"You are a precise text editor. Your task is to remove only the specified 
outdated facts from the passage while keeping ALL other content verbatim. 
Do not paraphrase, summarize, add information, or remove anything else."

USER:
"Passage:
{original_passage}

Outdated facts to remove (these are no longer current):
- {chain_old_fact_1}
- {chain_old_fact_2}

Rewrite the passage with only these outdated facts removed. Preserve all 
other sentences exactly as they appear."

Cost: 1 LLM call per affected chunk
Pros: chunk-aware, 不破壞 chunk 結構
Cons: 只解 W1/W2, 不解 W3 multi-hop inference
```

#### 4.4.2 Approach 2 (Explicit versioning) — DRAFT prompt [TBD-2]

```
Final memory output structure:

"[Conflict Resolution for current query]
The following facts identified in the retrieved memories are OUTDATED and 
should be ignored when answering:
- {chain_old_fact_1}
- {chain_old_fact_2}

The following are the up-to-date versions to use instead:
- {chain_new_fact_1}
- {chain_new_fact_2}

[Retrieved memories]
{raw_passages_unchanged}"

Cost: 0 LLM call (template only)
Pros: 透明, 利用我們高 detection confidence (Plan A verdict F1 ~94)
Cons: 純 prompt-level instruction, LLM 可能不 follow (variance 風險)
Note: W3 D variant 已測純 updated-list 失敗 (-2pp), 必須明確 OLD/NEW labelling
```

#### 4.4.3 Approach 3.1 (Self-Ask sub-question style) — DRAFT prompt [TBD-3.1] ★ Iter 0 priority

```
Pipeline:
  Step 1: From Layer 2 chain enumeration → best chain props (top-1 chain)
  
  Step 2: 1 LLM call to generate sub-questions:
  
  SYSTEM:
    "You are a question decomposer for multi-hop reasoning."
  
  USER:
    "Given this multi-hop question: {query}
     And the chain of facts needed to answer it:
       Fact 1: {chain_prop_1_text}
       Fact 2: {chain_prop_2_text}
       Fact 3: {chain_prop_3_text}
     
     Decompose the question into sub-questions, where each sub-question 
     corresponds to one fact in the chain in order.
     
     Output format:
     Q1: <sub-question>
     A1: <fact 1 text>
     Q2: <sub-question>
     A2: <fact 2 text>
     Q3: <sub-question>
     A3: <fact 3 text>"

  Step 3: Construct memory output:
  
  "[Reasoning chain for this query]
   Q1: {sub_q1}
   A1: {chain_prop_1_text}
   Q2: {sub_q2}
   A2: {chain_prop_2_text}
   Q3: {sub_q3}
   A3: {chain_prop_3_text}
   
   [Other potentially relevant memories]
   {filtered_raw_passages_with_chain_old_removed}"

Cost: 1 LLM call per query (for sub-question generation)
Pros: 同時解 W1 (filter) + W2 (chain props surface) + W3 (multi-hop guidance)
       Task-agnostic (chain 抽象通用)
Cons: 依賴 chain enumeration 品質; LLM 生 sub-question 品質
```

#### 4.4.4 Approach 3.2 (CoRe-style repetition)

```
若 Approach 3.1 EM 上升但 plateau:
  - Chain section 在 context 中 repeat 2-3 次, 不同位置 (start / middle / end)
  - 解 "lost-in-the-middle" 問題
Reference: CoRe (Yu et al. NAACL 2025 Findings) — F1 +30%p
```

#### 4.4.5 Approach 3.3 (SARG-style full serialize)

```
若 3.1+3.2 仍不夠:
  - Per-query LLM 從 retrieved passages 額外抽 triples (SARG-style)
  - 跟 chain props 並聯, 更密集 chain inject
  Cost overhead: 多個 LLM calls per query
Reference: SARG (arXiv 2506.08364, 2025)
```

#### 4.4.6 Approach 4 (Adaptive routing) — [TBD-classifier]

```
Classifier 設計 (Option a 推薦起步):

Option a (rule-based):
  def classify_query_complexity(query, query_entities):
      # Parse cloze structure
      n_hops_estimate = count_nested_of_structures(query)
      # e.g. "X of Y of Z" → 3 hops; "X" → 1 hop
      
      if n_hops_estimate >= 2 or len(query_entities) >= 2:
          return "complex"
      else:
          return "simple"

Option b (LLM-based, 1 light call):
  prompt = "Is this question complex (requires multi-hop reasoning)? Answer yes/no.
            Question: {query}"

Routing decision:
  simple → Approach 1 (LLM rewrite) or 2 (versioning)
  complex → Approach 3.1 / 3.2 / 3.3

Reference: Adaptive-RAG (NAACL 2024), Graph-RAG Bottleneck (2603.14045)
我們 differentiation: 改 memory output, 不改 inference loop
```

#### 4.4.7 Decision logic

```
Iter 0 (Diagnostic 0 後): approach3.1 vs rescue baseline
  Δ EM > +5pp → Approach 3 概念 work, 進 Iter 1
  Δ ~0 或 - → 退回 Approach 1/2, 重審

Iter 1: + adaptive routing
  Routing improve FC-SH 不傷 FC-MH → keep
  Otherwise → simplify

Iter 2 (if needed):
  3.2 CoRe-style (if 3.1 plateau)
  3.3 SARG-style (if 3.2 不夠)
```

---

## §5 M-DRA — Primary mechanism metric

### 5.1 定義 (對應 narrative §7)

對每個 has_pair hop, 3-way binary classification:
- **D (Detection)**: method 是否正確偵測 chain_old/chain_new 為衝突 pair?
- **R (Retrieval)**: final context 是否乾淨 (chain_old 不在)?
- **A (Answer)**: final answer 是否正確?

### 5.2 D 維度 per-method 定義

```
Mem0:
  D = 1 if L2 LLM fired UPDATE or DELETE event with old_memory.id matching 
      the chain_old fact for THIS query during ingestion
  Source: history.db (ingestion log) — 每 ADD/UPDATE/DELETE event 都有記錄

Mem0g:
  D = 1 if (Mem0 L2 fired) OR (G4 LLM judged DELETE on graph triple)
  Source: vector path same as Mem0 + graph_memory.py G4 log

HippoRAG-v2 vanilla:
  D undefined (no conflict mechanism)
  → 不算 M-DRA, 只算 M1 / M-core

Pure long-context (LCA):
  D undefined
  → 同 vanilla

Ours:
  D = 1 if Verdict.status == "superseded" for this fact pair
  Source: verdict log
```

### 5.3 R 維度 (method-agnostic)

```
R = 1 if state ∈ {CLEAN, MISS}
R = 0 if state == LEAK (chain_old in final_context_text)

從 M-core 算 (§4)
```

### 5.4 A 維度 (method-agnostic)

```
A = 1 if M1 is_correct (final_answer normalize == gt_answer normalize)
```

### 5.5 8 cells

```
D✓R✓A✓  clean win
D✓R✓A✗  inference fail (Weakness 3 root cause)
D✓R✗A✗  retrieval fail ★ (Weakness 1, Plan A 32k 45-47% 主導)
D✓R✗A✓  recovered fail (rare)
D✗R✓A✓  serendipitous
D✗R✓A✗  silent fail
D✗R✗A✗  full fail
D✗R✗A✓  parametric win (極罕見)
```

### 5.6 Aggregate

```
P(cell | method, ctx) = #(has_pair_hops in cell) / #has_pair_hops_total

細分維度:
  M-DRA × method × ctx × n_hops (2/3/4)
  M-DRA × method × ctx × hop_position
  M-DRA × method × ctx × conflict_hop_count
```

### 5.7 跟其他 metric 的關係

```
M-DRA 8 cells (per hop)
 ├─ R 維度 → M-core CLEAN/LEAK/MISS
 ├─ Query-level "all has_pair hops with R=1" = M-detection All-CLEAN rate
 └─ P(A | R=1) = M-inference (given clean context, answer 對 ratio)
```

→ M-DRA unified, M-core / M-detection / M-inference 都是 decomposition。

### 5.8 Paper §6.4 寫作策略

```
主表: R × A 二維 (4 cells) — 跨方法公平比較 (R/A 完全 method-agnostic)
補表: D × R × A (8 cells) — 看含衝突機制方法之間的 detection 機制差異

Caveat: D 在不同方法定義不一 (Mem0 L2 / Mem0g L2+G4 / Ours Verdict),
        但都對應到同一 fact pair 的衝突偵測 binary, 大多 cases 有共識
```

### 5.9 Decision rules for Weakness 1 evidence (paper §6.4)

```
Claim 1 evidence 站得住:
  Mem0g-pa 在 32k+ P(D✓R✗A✗) ≥ 40% (Plan A 47% ✓)
  AND
  Our method 在同 ctx P(D✓R✗A✗) 顯著低 (e.g., ≤ 15%)
  AND
  Gap 對應 EM gap (our method M1 EM > Mem0g-pa M1 EM)
```

---

## §6 M-inference (Given-context EM)

### 6.1 設計

固定 reader, 把不同 method 的 final_context_text 餵給同 reader, 量 EM:

```
M-inference(method, ctx) = #correct_with_fixed_reader / #total

Setup:
  Reader: gemini-3.1-flash-lite (Plan A baseline)
  Prompt: standard "You are a helpful AI. Answer based on the memories.\n{ctx}"
  Temp: 0

對比:
  M1(Mem0, 32k)             = 39% (含 Mem0 自帶 reader 的 inference)
  M-inference(Mem0, 32k)    = ?? (用固定 reader 推 Mem0 context)
  → 差距 isolate "context 品質" vs "reader 行為"
```

### 6.2 Conditional probability

```
P(A | R=1) = P(M-inference correct | state=CLEAN)
           = "given clean context, LLM 答對的 ratio"
           = M-inference 在 R=1 subset

Plan A 已知:
  P(A | R=1):
    Mem0 MH 6k: 80%
    Mem0g-pa MH 6k: 83%
    Mem0 MH 32k: 60%
    Mem0g-pa MH 32k: 66% (+6pp vs Mem0)
```

### 6.3 Diagnostic 0 是 M-inference 的特殊版

詳 §11。

---

## §7 M-core (詳 §4)

(內容已在 §4 全完整)

---

## §8 M-pool — Pool composition + Two-store divergence audit

### 8.1 設計動機

對應 narrative §4.1: M-DRA D✓R✗A✗ 的 root cause 拆解。

兩個 sub-scale:
- Sub-scale 1: Pool composition (write-time pool quality)
- Sub-scale 2: Two-store divergence audit (Mem0g 專屬)

### 8.2 Sub-scale 1: Write-time pool composition

對每個 has_pair hop, 取對應 method 在該 fact pair 的 detection pool:

```
Mem0 detection pool:
  寫入 chain_new fact 時, L2 LLM 看到的 top-5 vector candidates
  Source: instrument ingestion to dump pool, OR 從 history.db 反推

Mem0g detection pool:
  Vector path: 同 Mem0 (top-5 vector)
  Graph path: G3 Cypher 撈到的 existing entity triples
  Union 兩個 source

Ours detection pool (query-time chain-restricted):
  Layer 3 verdict 階段, chain props ≤10 + γ opportunistic candidates
```

Per-hop log:
```json
"detection_pool_per_hop": [
  {
    "hop_index": 0,
    "fact_pair": ("chain_old_text", "chain_new_text"),
    "pool_items": ["fact text 1", "fact text 2", ...],
    "pool_size": 5,
    "chain_old_in_pool": true,
    "chain_old_rank": 3,
    "num_same_cloze_distractors": 2     // 同 cloze 但非 chain_old/new 的 distractor 數
  }
]
```

Aggregate:
```
pool_recall_chain_old(method, ctx) = #(chain_old in pool) / #has_pair_hops
pool_avg_size(method, ctx)         = avg pool size
pool_noise(method, ctx)            = avg num_same_cloze_distractors
```

[TBD-12]: M-pool dump from Mem0/Mem0g write-time — 需 instrument:
- Mem0: 在 `mem0/memory/main.py:187-323 _add_to_vector_store` L2 LLM call 前 dump top-5
- Mem0g: 同 Mem0 + 加 graph G3 search result dump in `_search_graph_db`

### 8.3 Sub-scale 2: Two-store divergence audit (Mem0g 專屬)

對每個 has_pair hop, audit Mem0g vector + graph 兩 store state:

```
vector_store_has_chain_old: bool   # vector store 內 chain_old 是否仍存在
graph_store_has_chain_old:  bool   # graph store 內 chain_old 是否仍存在
vector_store_has_chain_new: bool
graph_store_has_chain_new:  bool

diverged = (vector_has_old XOR graph_has_old) 
           OR (vector_has_new XOR graph_has_new)

Aggregate:
  divergence_rate(ctx) = #diverged_hops / #has_pair_hops
```

Predicted:
```
6k:    divergence_rate ~5-10% (vector + graph 大致一致)
32k:   divergence_rate ~20-30% (兩 store 大幅不一致)
64k+:  predict 更高
```

Diverged cases 對應 M-DRA cell:
- vector_has_old + graph_clean → vector retrieval 帶 chain_old → D✓R✗
- graph_has_old + vector_clean → graph relations 帶 chain_old (prompt-aware) → D✓R✗

### 8.4 Paper §6.5 use

Two-store divergence 是 Mem0g 結構限制的直接 metric, paper §3.2 critique 的 supporting evidence。

---

## §9 M-claim-c — Non-FC + Generalizable claim

### 9.1 公式

```
原 v1.2: 只測 "不傷其他任務" (regression ≥ -2pp)

v1.4 升級: 同一 method (含 Approach 3 chain-structured output) 在 non-FC 任務也 work

對 MABench 非 FC task:
  - AR (Accurate Retrieval)
  - EventQA (時序推理)
  - 其他

Metric:
  (a) regression(task, ctx) ≥ -2pp (basic non-regression, claim c)
  (b) advantage(task, ctx) > 0 (preferred, generalizable claim 升級)

→ 若 (a) 滿足: claim c 成立
→ 若 (b) 滿足: claim c + generalizable claim 都成立 (paper §5.5 主推)
```

### 9.2 Chain 退化處理 per task

```
FC-MH:    chain = multi-hop reasoning chain, full Approach 3 output
FC-SH:    chain = single hop, 退化為單 step (or 跳過 chain section)
AR:       chain = retrieval chain (無衝突), 純 chain step output
EventQA:  chain = temporal chain, step 按時序
```

---

## §10 整合 log schema

每個 query 一個 JSON log:

```json
{
  // === Identity ===
  "query_id": "...",
  "method": "ours-approach3.1",
  "model": "gemini-3.1-flash-lite",
  "context_length": "32k",
  "task": "FC-MH",
  
  // === Query metadata ===
  "n_hops": 3,
  "query_entities": ["Our Mutual Friend"],
  "conflict_hop_count": 2,
  "max_hop_position": 3,
  "has_hop_position_ge2": true,
  
  // === M1 ===
  "final_answer": "Belgium",
  "golden_answer": "Belgium",
  "is_correct": true,
  
  // === Critical log (M-core / M-DRA / M-inference 命脈) ===
  "final_context_text": "...",
  "context_token_count": 1234,
  
  // === M-core + M-DRA per-hop ===
  "hops": [
    {
      "hop_index": 0,
      "hop_position": 1,
      "entities_required": ["Our Mutual Friend"],
      "entities_in_query": true,
      "conflict_type": "has_pair",
      
      "new_present": true,
      "old_present": false,
      "state": "CLEAN",
      
      // M-DRA
      "D": true,
      "R": true,
      "A": true,
      "D_evidence": {
        "method_specific": "L2 UPDATE event id=42 at write_idx=146"
        // 或 "Verdict superseded for pid=23-pid=87"
      },
      
      "matched_via": "tier1_strict",
      "update_gap": 39                          // supplementary
    }
  ],
  
  // === Query-level M-DRA aggregation ===
  "num_has_pair_hops": 2,
  "drA_per_query": {
    "D_all": true,
    "R_all": true,
    "A": true,
    "DRA_cell": "D✓R✓A✓"
  },
  "all_clean": true,
  
  // === M-pool (per has_pair hop) ===
  "detection_pool_per_hop": [
    {
      "hop_index": 0,
      "fact_pair": ["...chain_old...", "...chain_new..."],
      "pool_items": [...],
      "pool_size": 5,
      "chain_old_in_pool": true,
      "chain_old_rank": 3,
      "num_same_cloze_distractors": 2
    }
  ],
  
  // === Two-store divergence (Mem0g only) ===
  "two_store_audit": {
    "vector_store_has_chain_old": false,
    "graph_store_has_chain_old": true,         // mismatch case
    "vector_store_has_chain_new": true,
    "graph_store_has_chain_new": true,
    "diverged": true
  },
  
  // === M-inference (fixed reader) ===
  "inference_with_fixed_reader": {
    "reader_model": "gemini-3.1-flash-lite",
    "prompt_variant": "standard",
    "inference_answer": "Belgium",
    "inference_is_correct": true
  },
  
  // === Diagnostic 0 (only if M-inference variant = scaffold) ===
  "diagnostic_0": {
    "scaffold": "self_ask",                    // self_ask / cot / core_repetition / baseline
    "context_source": "oracle_clean_this_chain",
    "answer": "...",
    "is_correct": true
  }
}
```

### 10.1 P0 必須補 log (priority)

```
1. final_context_text — M-core + M-DRA + M-inference 命脈
2. hops[].D, R, A + D_evidence — M-DRA 核心
3. hops[].hop_position, entities_required, entities_in_query — W2 命脈
4. detection_pool_per_hop — M-pool 命脈
5. two_store_audit (Mem0g only) — W1 內 Mem0g 額外結構問題 evidence
6. diagnostic_0 (run separately) — W3 root cause evidence
```

---

## §11 Diagnostic 0 — 完整 SOP ★

### 11.1 設計動機

對應 narrative §4.3 + §2.2 W3: 區分 Weakness 3 真實 root cause:
- Multi-hop coordination 困難 (memory output 可救)
- Counterfactual vs world knowledge (memory output 救不了)

### 11.2 公式

```
Setup:
  Reader: gemini-3.1-flash-lite (對齊 Plan A baseline)
  Temp: 0 (deterministic)
  Context: OracleClean-ThisChain (這個 query 的 chain_old 全 filter, 保留 other-old)
  Dataset: FC-MH 100Q

Variants:
  V_baseline (vanilla prompt, 已知 baseline):
    system = "You are a helpful AI. Answer the question based on the memories.\n{ctx}"
    user = "{query}\n\nCurrent Time: 2026-XX-XX HH:MM:SS"
    Expected: ~55%
  
  V_A (Self-Ask scaffold):
    system = "You are a helpful AI. To answer the question based on the memories, 
              first decompose it into sub-questions corresponding to each reasoning hop.
              For each sub-question, identify the relevant fact from the memories and 
              answer it. Then combine sub-answers to give the final answer.
              
              Memories:
              {ctx}"
  
  V_B (CoT prompt):
    user = "{query}\n\nLet's think step by step.\n\nCurrent Time: ..."
  
  V_C (CoRe-style chain repetition):
    需要從 chain enumeration 找 chain props
    Context 內 chain props 重複 2-3 次, 不同位置 (start / middle / end)
    
    system = "You are a helpful AI. Answer based on the memories below."
    ctx = chain_props (front) + raw_memories + chain_props (middle) + raw_memories_2 + chain_props (end)

Compute:
  Δ_A = EM(V_A) - 55%
  Δ_B = EM(V_B) - 55%
  Δ_C = EM(V_C) - 55%

Decision:
  Outcome 1: max(Δ) >= 15pp
    → Multi-hop coordination 是 gap 主因
    → Memory output 結構化是有效 attack surface
    → Weakness 3 confirm, Approach 3 進場
    → 進 Iter 0 Approach 3.1 prototype
  
  Outcome 2: max(Δ) < 5pp
    → Counterfactual vs world knowledge 是主因
    → Memory output 結構化救不了
    → Weakness 3 framing 改, Approach 3 退場
    → Paper Claim 3 scope 縮到 conflict filter (Approach 1/2)
  
  Outcome 3: max(Δ) 在 5-15pp 之間
    → 部分 work
    → 進一步 case analysis 看 which sub-population benefits
    → 仍 try Approach 3 但預期有限
```

### 11.3 Cost

```
~1-2 days: 
  100Q × 4 variants × ~5s/query ≈ 30 min/variant × 4 = 2 hr 跑時間
  + implement scaffold 1 day
```

### 11.4 Output

```
Diagnostic 0 Report (1 page):
  - Baseline 55% (verify)
  - V_A: EM = ?, Δ = ?
  - V_B: EM = ?, Δ = ?
  - V_C: EM = ?, Δ = ?
  - max(Δ), recommendation (Outcome 1/2/3)
  - Top 10 cases by improvement (analyze pattern)
```

[TBD-18]: scaffold prompt 細節 (Self-Ask 措辭, CoT 是否含 "step by step" 字面, CoRe 重複位置)

---

## §12 Computation pipeline

```
跑實驗時:
  1. Method 跑每個 query, dump:
     - final_context_text
     - final_answer
     - method-internal events (UPDATE/DELETE for Mem0/Mem0g; Verdict for Ours)
  2. ★ NEW: dump detection_pool_per_hop (M-pool)
  3. ★ NEW: dump two_store_audit (Mem0g only)
  4. ★ NEW: dump diagnostic_0 (only when running Diagnostic 0 variants)

後處理 (batch, 純分析既有 result):
  5. Load alignment JSON for each query
  6. Per query: compute hop_position for each hop
  7. Per hop: compute state (CLEAN/LEAK/MISS) via check_fact_in_context
  8. Per hop: compute D / R / A → M-DRA cell
  9. Aggregate query-level: all_clean, DRA per query
  10. Aggregate method-level: 
      - M1, M-DRA × ctx, M-core breakdown
      - hop_position retrieval rate × method × ctx
      - M-pool composition × ctx
      - Two-store divergence rate × ctx
  11. M-inference: 用 fixed reader 對 final_context_text 重跑 inference (separately)

Eval scripts:
  - compute_m1.py
  - compute_m_core.py           (含 hop_position)
  - compute_m_dra.py            (3-way contingency)
  - compute_m_inference.py
  - compute_diagnostic_0.py     ★ NEW
  - compute_m_pool.py           (含 two-store divergence audit)
  - aggregate_main_table.py
  - aggregate_hop_position.py   ★ NEW
  - aggregate_two_store.py      ★ NEW (Mem0g only)
```

---

## §13 Experiment grid — staged

### 13.1 Stage 0: Plan A verified ✓ (Master Dashboard 12 cells)

Already done:
- LCA / Mem0 / Mem0g-pa × {SH, MH} × {6k, 32k}

### 13.2 ★ Stage 1: P0 Pre-framing audit (~1-2 weeks)

**Path A: Diagnostic 0** (1-2 days)
- 詳 §11
- File: compute_diagnostic_0.py
- Variants: V_baseline, V_A (Self-Ask), V_B (CoT), V_C (CoRe-style)
- Setup: gemini-3.1-flash-lite, OracleClean-ThisChain context, FC-MH 100Q
- Output: Diagnostic 0 report (1 page) — max(Δ) value, recommendation

**Path B: Audit 1** (1-2 days, 純分析既有 data)
- Files:
  - compute_m_dra.py — D × R × A 3-way contingency
  - compute_m_pool.py — pool composition + two-store divergence audit
  - compute_hop_position_retrieval.py — per-hop × hop_position
- Source: `outputs/gemini-3.1-flash-lite-{mem0,mem0g_pa}-chunk512-temp0/`
- Output: Audit 1 report 含:
  - M-DRA × method × ctx 8-cell table
  - Two-store divergence rate × ctx (Mem0g only)
  - per-hop retrieval rate × hop_position table
  - Top 20 D✓R✗A✗ case dump (raw event log + final context + answer)

**Path C: Audit 2** (一晚, ~4.3hr)
- Cmd: Mem0g-pa 64k MH (anchor reader)
- 加 M-DRA + M-pool + two-store dump
- Output: 32k → 64k trend

**Path D: Audit 3** (1-2 weeks 工程)
- Tasks:
  - NV-Embed-v2 → text-embedding-004 (需 GPU env 處理)
  - preview → GA backbone
  - temp=0.7 → 0
  - 跑 our method 6k / 32k MH
- 加 M-DRA + M-pool + Diagnostic 0 同 instrument
- Output: 對齊 baseline 的 our method 數字

### 13.3 Stage 2: Method design iteration (~2-4 weeks)

```
Iter 0 (1-2 days): Approach 3.1 (Self-Ask) on our method
  Setup: our method + Approach 3.1 chain-structured memory output
  Run: FC-MH 100Q (Plan A setup)
  Compare: vs our method rescue baseline
  
  Decision:
    Δ EM > +5pp → Approach 3 概念 work, 進 Iter 1
    Δ ~0 或 - → 退回 Approach 1/2, 重審 Approach 3

Iter 1 (1 week): Approach 3.1 + adaptive routing
  Setup: + rule-based query complexity classifier
  Run: FC-MH + FC-SH + AR
  
  Decision:
    Routing improve FC-SH 不傷 FC-MH → keep
    Otherwise → simplify

Iter 2 (1-2 weeks, 視需要): 
  3.2 CoRe-style repetition
  3.3 SARG-style serialize
  Adaptive routing 升級 (rule → LLM-based)
```

### 13.4 Stage 3: Comprehensive evaluation (~2-3 weeks)

```
Reader sweep at 6k:
  4 readers × {LCA, Mem0, Mem0g-pa, Ours-best} × {SH, MH}
  = 32 runs ≈ 8 hr

64k all methods (anchor reader):
  {LCA, Mem0, Mem0g-pa, Ours-best} × {SH, MH}
  ≈ 12 hr

Non-FC tasks (generalizable claim ★):
  {Ours-best, Mem0g-pa} × {AR, EventQA} × {6k, 32k}

262k: LCA only (~10 min × 2)
```

---

## §14 Strategic decision logic (對齊 narrative §9)

### 14.0 Diagnostic 0 結果 → Approach 3 進場決策

```
Outcome 1: max(Δ) >= 15pp
  → Approach 3 (chain-structured) 主推
  → Paper §5.4 強推 Approach 3
  → Iter 0 直接 prototype

Outcome 2: max(Δ) < 5pp
  → Approach 3 退場
  → Paper §5.4 退回 Approach 1 / Approach 2
  → Paper Claim 3 scope 縮小到 conflict filter

Outcome 3 (5-15pp):
  → 部分 work, case 分析看 sub-population
  → Approach 3 仍 try 但預期 EM gain 有限
```

### 14.1 跑完 Path A/B/C/D + Iter 0 後的情境

```
情境 A: Ours 全 ctx 都贏 + Diagnostic 0 確認 Approach 3 work
  → ✅ Core claim 完全成立, paper §3 + §6 完整 evidence chain
  → Paper main story: "三個 design 解三個 failure mode, 通用各任務"
  → §6.3 主表 Ours 全 ctx EM 顯著高
  → §6.4 M-DRA: Ours 大幅降低 D✓R✗A✗

情境 B: 6k 輸 / 32k+ 贏 + Diagnostic 0 條件 work
  → Paper main story "advantage emerges at scale"
  → 主推 W1 (脫鉤在 32k+ 明顯) + W2
  → W3 退為 secondary contribution

情境 C: Diagnostic 0 不 work
  → Approach 3 退場
  → Paper scope 縮到 conflict + retrieval (W1+W2)

情境 D: 全方位輸
  → 重設計 (換 base / 重新定義 problem scope)
```

→ 戰場位置不預設, 由 P0 audit + Iter 0 數據決定。

### 14.2 該不該換 base

```
若 Mem0g-pa 6k 66% 對手太強, 可能考慮:
  Option X: 我們在 Mem0g 上加 module (利用 Mem0g 已有 graph + 補上 query-time verdict)
  Option Y: 我們在 HippoRAG-v2 上加 module (現在的 base)

決策依據:
  跑 Stage 2 Iter 0 後對比 EM
  若 HippoRAG-v2 base + 我們 module 顯著高於 Mem0g + 我們 module → keep base
  否則考慮換 base
```

---

## §15 Prior art alignment (5-paper survey)

```
Layer 1 (multi-hop infra):
  HippoRAG-v2 [Gutierrez et al. ICML 2025] — direct cite, base
  PropRAG-inspired [PropRAG EMNLP 2025] — 部分借鑒 (propositions + beam search)

Layer 2 (chain enumeration):
  PropRAG-inspired beam search

Layer 3 (conflict-aware verdict):
  ★ Our named contribution (chain-restricted small pool LLM verdict)
  類似但不重疊: 
    Mem0 L2 (write-time pool judgment) — write-time, 我們 query-time
    Chain-of-Action [ICLR 2025] (conflict between answer vs retrieved)

Layer 4 (structured memory output):
  ★ Our named contribution (memory-side chain materialization + conflict-aware + adaptive)
  
  Prior art cite:
    SARG [arXiv 2506.08364, 2025] — chain serialize 進 prompt
      Diff: SARG per-query LLM 抽 triples + 無 conflict
            Ours 預建 prop graph + conflict-aware + conversational memory
    
    CoRe [Yu et al. NAACL 2025 Findings] — context repetition
      Diff: CoRe 解 misordered, 不解 conflict
      
    Adaptive-RAG [Jeong et al. NAACL 2024] — query complexity routing
      Diff: Adaptive-RAG 改 inference loop, ours 改 memory output
    
    Graph-RAG Reasoning Bottleneck [arXiv 2603.14045, 2026] — question-type routing
      Diff: 改 inference prompt, ours 改 memory structure
    
    EKA [arXiv 2512.20144, 2025] — align LLM with retrieval set
      Diff: EKA 改 iterative RAG planning, ours single-pass memory
    
    Self-Ask [Press et al. EMNLP 2023] — explicit sub-question decomposition
      Diff: Self-Ask 改 inference prompt, ours 把這個結構放 memory output
```

→ Paper §3 用此表清楚 disclose cite + differentiate。

---

## §16 Implementation questions [TBD]

| # | 項目 | Section | 預設 / 狀態 |
|---|---|---|---|
| TBD-A0 | Diagnostic 0 scaffold prompts | §11 | DRAFT 已給 |
| TBD-1 | Approach 1 prompt (LLM rewrite) | §4.4.1 | DRAFT |
| TBD-2 | Approach 2 prompt (versioning) | §4.4.2 | DRAFT |
| TBD-3.1 | Approach 3.1 prompt (Self-Ask) | §4.4.3 | DRAFT |
| TBD-3.2 | Approach 3.2 implementation (CoRe) | §4.4.4 | 待 Iter 1 |
| TBD-3.3 | Approach 3.3 (SARG-style) | §4.4.5 | 待 Iter 2 |
| TBD-classifier | Adaptive routing classifier | §4.4.6 | Rule-based first |
| TBD-12 | M-pool dump from Mem0/Mem0g write-time | §8 | Instrument needed |
| TBD-13 | hop_position 計算 | §2.2 | rule-based |
| TBD-14 | entities_required source | §2.1 | MQuAKE GT |
| TBD-18 | Diagnostic 0 scaffold prompts 措辭 | §11.2 | DRAFT |

---

## §17 To-do for Claude Code (對齊 narrative §0 Sync mapping)

```
P0 (this 1-2 weeks):

  □ Path A: ★ Diagnostic 0 (1-2 days)
    File: compute_diagnostic_0.py
    Implementation:
      - V_baseline (vanilla prompt) — verify ~55%
      - V_A (Self-Ask scaffold) — 改 system_prompt
      - V_B (CoT) — user prompt 加 "Let's think step by step"
      - V_C (CoRe-style) — chain props 重複 2-3 次
    Run: FC-MH 100Q × 4 variants, fixed reader, OracleClean-ThisChain context
    Output: Diagnostic 0 report (1-page) — max(Δ) value, Outcome 1/2/3
    Decision: Outcome 1 → Iter 0; Outcome 2 → Approach 3 退場

  □ Path B: Audit 1 (1-2 days, 純分析)
    Files: 
      compute_m_dra.py — D × R × A 3-way contingency
      compute_m_pool.py — pool composition + two-store divergence audit
      compute_hop_position_retrieval.py — per-hop × hop_position
    Source: outputs/gemini-3.1-flash-lite-{mem0,mem0g_pa}-chunk512-temp0/
    Output: Audit 1 report 含:
      - M-DRA × method × ctx 8-cell table
      - Two-store divergence rate × ctx (Mem0g only)
      - per-hop retrieval rate × hop_position table
      - Top 20 D✓R✗A✗ case dump

  □ Path C: Audit 2 (一晚, ~4.3hr)
    Cmd: Mem0g-pa 64k MH (anchor reader) 
    Instrument: 加 M-DRA + M-pool + two-store dump
    Output: 32k → 64k trend

  □ Path D: Audit 3 (1-2 weeks, 工程)
    Tasks:
      - NV-Embed-v2 → text-embedding-004 (需 GPU env 處理)
      - preview backbone → GA backbone
      - temp=0.7 → temp=0
      - 跑 our method 6k / 32k MH
      - 加 M-DRA + M-pool + Diagnostic 0 同 instrument

P1 (P0 後, ~2-4 weeks):
  
  □ Iter 0: Approach 3.1 (Self-Ask) on our method
    File: 在 our method final memory output 階段加 chain-materialization branch
    [TBD-3.1]: prompt template lock
    Output: EM 對比 vs rescue baseline (Plan A setup)
    Decision: Δ EM > +5pp → continue Iter 1; < 0 → 退回 Approach 1/2
  
  □ Iter 1: + adaptive routing
    [TBD-classifier]: rule-based first
    Run: FC-MH + FC-SH + AR

  □ Iter 2 (視需要): Approach 3.2 (CoRe) or 3.3 (SARG-style)

P2 (paper writing 前, ~2-4 weeks):
  - Reader sweep 6k
  - 64k all methods
  - Non-FC tasks (AR / EventQA)
  - Component sweeps (active region top-N, beam B/L, pool size)
  - Case study materials (16-20 cases)
```

---

## §18 跟 Claude Code 對齊的核心訊息 (對齊 narrative §10)

> Paper 三步:
>
> 1. **Step 1 (Motivation)**: 證明三個結構性 weakness 真實 (Mem0/Mem0g 在 FC-MH 失敗的 root cause)
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

**End of FC metric spec**
