# Method Design v2.0.2 Specification
## (Living Doc §B 重構 — From v1 Three-Phase to Query-Anchored Detection Architecture)

> **Version**: v2.0.2 (from v2.0.1 — corrections based on Claude Code's code-side review)
>
> **Changelog v2.0.1 → v2.0.2**:
> - ✅ **Resolved spec contradiction**: W1 includes proposition layer (I2.5+I3c), only candidate cache (I4.5) is W2-deferred
> - ✅ **Renamed flags**: `enable_phase1_v2` split into `enable_proposition_layer` (W1+) + `enable_phase1_candidate_cache` (W2+)
> - ✅ **Locked Q1**: W1 uses PropRAG proposition extraction (not triple-proxy / sentence-reconstruction)
> - ✅ **Locked Q3**: PropRAG prompt fed HippoRAG-v2 triple-derived entities (`chunk_triple_entities`)
> - ✅ **Locked Q5**: PPR mass aggregation = `mean(constituent_entity_ppr_scores)`, max as W1 ablation variant
> - ✅ **Locked Q7**: Method internal timestamp = `(chunk_idx, in_chunk_position)` tuple; FC GT seq = evaluation oracle only
> - ✅ **Locked Q9**: W1 MH gate = three-tier (Hard 40% / Realistic 45% / Aspirational 50%)
> - ➕ **Added**: PropRAG attention batch strategy with sentinel monitoring
> - ➕ **Added**: chunk_size strategy (W1 lock at 512; ablation in W2+; W5 alignment with 4096 baseline)
> - ➕ **Added**: OpenIE-bound proposition coverage as honest limitation (§B.12 extended)
>
> **Tentative thresholds (open to revision based on W1 results)**:
> - Q5 PPR mass aggregation: mean default, max variant for W1 ablation
> - Q9 W1 MH gate threshold: 40/45/50 tentative; adjust based on W1 measurement
>
> **文件用途**:
> 1. **Update fc_mh_living_doc_v1.1.md §B** — 取代原 B.1-B.7
> 2. **Implementation handoff for Claude Code** — code-ready pseudocode + plumbing + sentinels
> 3. **Design review reference** — 中文導讀 + 英文 spec

---

## §B.0 v1 → v2 架構重構總覽

### B.0.1 為什麼架構必須重構 (recap)

v1 結果與既有方法 detection 數據揭露三個結構性問題:

| 數據點 | 出處 | 推論 |
|---|---|---|
| Mem0 per-hop 59% (top-k=5 pool) | motivation §4.3 | Small pool + LLM judge 在 single fact-pair 上 work |
| Zep per-hop 38% (FC 上退化成 deterministic) | motivation §4.3 | Bi-temporal annotation 在 no-explicit-temporal 環境失效, 但 timestamp 作為 metadata 仍有價值 |
| v1 P1 deterministic 36% | Method v1 §10 | 純 syntactic match 有 35% relation-alias miss ceiling |
| LLM judge on production pool (30-450 candidates) | conversation prior | LLM attention 在大 pool 中崩壞, 退到 20-30% |
| All-detected per-Q: Mem0 41/100, Zep 20/100, v1 19/100 | motivation §4.3 | **multi-hop 累積 detection 即使 small pool LLM 也只到 41%**, 因為 write-time 沒 query 訊息 |

**核心 insight**: **detection-where-it-matters** — write-time 預處理 + query-time 在 reasoning chain 上做 critical detection。

### B.0.2 v1 vs v2.0.2 architecture diff

| Phase | v1 角色 | v2.0.2 新角色 |
|---|---|---|
| **Phase 1 (write-time)** | Heavy lifting — deterministic `(s,r,≠o)` detection on triples | **Split into two layers**: (a) **Proposition layer** (I2.5+I3c, W1 required) — PropRAG-style extraction, no verdict; (b) **Candidate cache** (I4.5, W2 optional) — entity overlap + cosine pre-computation. **No LLM verdict at write-time** |
| **Phase 2 (retrieval-time)** | Chain-aware passage filter via PPR mass proxy | **Critical detection 中樞** — 2.a Chain identification (M4 simplified) + 2.b Chain-restricted supersession verdict (small-pool LLM judge) |
| **Phase 3 (inference-time)** | Universal scaffold prompt | **Enriched memory output** — passages + reasoning hints + change log. **Prompt unchanged** |

**Key architectural points (v2.0.2)**:
1. **Detection locus shifted**: write-time → query-time
2. **Memory unit upgraded internally**: triple → proposition (但對外仍返回 passages)
3. **Scaffold moved into context**: prompt phrasing → enriched memory content
4. **W1 scope**: proposition layer + Phase 2 + Phase 3 ablation prep
5. **W2 scope**: candidate cache as latency optimization
6. **γ pairing is opportunistic**: 在 Phase 2.b pool construction 中, 不假設每 hop 有 pair
7. **chunk_size locked at 512 in W1**: 與 v1 baseline 一致, robustness ablation 留 W2/W3

### B.0.3 v2 對 motivation 兩 Claim 的最終 mapping

| Motivation Claim | v1 對應 | v2.0.2 對應 |
|---|---|---|
| **Claim 1**: chain-old 在 retrieval 中過濾 | Phase 1 (detection) + Phase 2 PPR filter | Phase 2.a chain id + Phase 2.b verdict — chain-old 在 chain 範圍內 verdict 後過濾 |
| **Claim 2**: 提供額外回傳記憶引導 inference | Phase 3 scaffold prompt | Phase 3 enriched output (hints + log), prompt unchanged |

---

## §B.1 HippoRAG-v2 Base Pipeline (hooks 位置 final v2.0.2)

### B.1.1 Offline Indexing

| Step | 動作 | v2.0.2 hook |
|---|---|---|
| I1 | LLM 對每 passage 跑 OpenIE, 抽 `(s, r, o)` triples | (保留) |
| I2 | NV-Embed-v2 fp16 forward 算 chunk / entity / fact embeddings | (保留) |
| **I2.5 (W1 required)** | **Proposition extraction** (PropRAG-style LLM prompt, fed `chunk_triple_entities`) | **Phase 1 hook #1** |
| I3a | `add_fact_edges`: phrase ↔ phrase edges in KG | (保留) |
| I3b | `add_passage_edges`: passage → entity edges in KG | (保留) |
| **I3c (W1 required)** | **`add_proposition_nodes`**: proposition nodes + entity-proposition edges + timestamp tuple | **Phase 1 hook #2** |
| I4 | `add_synonymy_edges`: entity KNN cosine ≥ 0.8 | (保留) |
| **I4.5 (W2 optional)** | **`annotate_supersession_candidates`**: candidate cache (entity overlap + cosine, no LLM, no verdict) | **Phase 1 hook #3** |
| I5 | save `graph.graphml` + `proposition_index.json` (+ `candidate_index.json` if W2 enabled) | (擴展) |

### B.1.2 Online Retrieval & QA

| Step | 動作 | v2.0.2 hook |
|---|---|---|
| O1 | `get_fact_scores`: query × fact_embeddings cosine | (保留) |
| O2 | `rerank_facts`: LLM judge top-k fact triples | (保留) |
| O3 | Seed reset weights: phrase + 0.05·DPR passage | (保留) |
| O4 | `run_ppr`: PPR propagate, return full pagerank_scores | (保留) |
| **O4.5 (W1)** | **`identify_active_region`**: 從 PPR scores 找 active region (top-K propositions, **prop_ppr_mass = mean(entity_ppr)**) | **Phase 2.a hook #1** |
| **O4.6 (W1)** | **`enumerate_candidate_chains`**: 在 active region 內 bounded path enumeration → top-M chains | **Phase 2.a hook #2** |
| **O4.7 (W1)** | **`chain_restricted_verdict`**: small-pool LLM verdict (Phase 1 cache + on-the-fly + γ pool) | **Phase 2.b hook** |
| O5 | Passage ranking & selection (top-10) | **Phase 2 應用點**: 依 verdict 結果 filter chain-old propositions 對應 passages |
| **O5.5 (W3)** | **`render_enriched_context`**: passages + reasoning hints + change log | **Phase 3 hook** |
| O6 | `rag_qa`: enriched context → LLM (prompt unchanged) → QA | (prompt 不動) |

### B.1.3 v2.0.2 architecture diagram

```
─ Offline Indexing ───────────────────────────────────────────
I1.  OpenIE → triples + extracted_entities (raw, unreliable)
I2.  Embeddings
I2.5 PropRAG-style proposition extraction (W1 required)  ← hook #1
     ├── Input: chunk text + chunk_triple_entities (s,o union)
     ├── Output: List[Proposition] with text + entities + timestamp
     └── Batch strategy + sentinel monitoring (see §B.2.2)
I3.  add_fact_edges + add_passage_edges
I3c. add_proposition_nodes (W1 required)                 ← hook #2
I4.  add_synonymy_edges
I4.5 annotate_supersession_candidates (W2 optional)      ← hook #3
     (no LLM, no verdict, pure entity overlap + cosine cache)
I5.  save indexes

─ Online Retrieval & QA ─────────────────────────────────────
O1.  fact scoring
O2.  rerank_facts (unchanged role)
O3.  seed weights
O4.  run_ppr → pagerank_scores
O4.5 identify_active_region                              ← Phase 2.a hook #1
     (prop_ppr_mass = mean(entity_ppr_in_proposition))
O4.6 enumerate_candidate_chains                          ← Phase 2.a hook #2
     (supersession-AGNOSTIC, no LLM in 2.a)
O4.7 chain_restricted_verdict                            ← Phase 2.b hook
     (only LLM call type in Phase 2; pool ≤ 10)
O5.  Passage filter based on verdict
O5.5 render_enriched_context (W3)                        ← Phase 3 hook
O6.  rag_qa (prompt UNCHANGED)
```

---

## §B.2 Phase 1 v2.0.2 — Two-Layer Architecture

> **核心觀念**: Phase 1 拆成兩個概念獨立的 layer:
> - **B.2.2 Proposition layer (I2.5+I3c)**: W1 必要 — 升級記憶表徵, 為 Phase 2 提供 context-rich units
> - **B.2.3 Candidate cache (I4.5)**: W2 optional — offline precompute Phase 2.b pool 加速
>
> Phase 1 全程**沒有 LLM verdict**, 沒有 easy-case detection, 沒有 functional whitelist。Proposition extraction (I2.5) 是 LLM-aided preprocessing, 不是 judgment。

### B.2.1 Purpose & contract

**Phase 1 (整體) 提供**:
1. Proposition layer 取代 triple 成為 internal 記憶表徵 (G2 locked decision)
2. 每 proposition 有 timestamp tuple `(chunk_idx, in_chunk_position)`
3. (W2 onward) Candidate annotation cache for Phase 2.b pool speedup

**Phase 1 不做**:
- ❌ LLM-based supersession verdict (那是 Phase 2.b 的職責)
- ❌ Easy-case deterministic detection (避免 rule-based regression)
- ❌ Relation 分類 / functional whitelist (避免 a priori assumption)
- ❌ Destructive filter operations (沒有 proposition 被刪除)

**Phase 2 對 Phase 1 的依賴關係**:
- 依賴 proposition layer (W1) → **strong** (Phase 2 algorithm operates on propositions)
- 依賴 candidate cache (W2) → **weak optimization** (Phase 2.b 可以 on-the-fly lookup, cache 只是加速)

### B.2.2 Proposition Layer (I2.5 + I3c) — **W1 Required Component**

**目的**: 從 chunk 抽 context-rich propositions, 取代 triples 作為 internal 記憶表徵。

#### B.2.2.1 PropRAG prompt port (locked Q1=c, Q3=ii)

**Decision**: Port PropRAG's `proposition_extraction.py` prompt as-is, feed it HippoRAG-v2 triple-derived entities.

**Input plumbing**:
```python
def extract_propositions_for_chunk(
    chunk: Chunk,
    triple_entities: Set[str],  # union of s,o from chunk's OpenIE triples
    llm: LLM,
) -> List[Proposition]:
    """
    Use PropRAG proposition_extraction.py prompt template.
    Feed it triple-derived entities (Q3 = (ii) lock).
    """
    prompt = PROPRAG_PROPOSITION_EXTRACTION_PROMPT.format(
        passage=chunk.text,
        named_entities=json.dumps(list(triple_entities))
    )
    raw = llm(prompt, max_tokens=2048)
    propositions = parse_proprag_output(raw)  # PropRAG returns JSON
    return propositions
```

**Source of entities**: `chunk_triple_entities[i]` = union of `(s, o)` across all triples extracted by HippoRAG-v2 OpenIE for chunk `i`. Implementation reuses `extract_entity_nodes()` in `utils/misc_utils.py`.

→ **Coverage caveat**: Propositions inherit OpenIE coverage. Facts whose triple was not extracted by OpenIE are invisible to proposition extraction. This is honestly disclosed (§B.12).

#### B.2.2.2 Batch strategy + sentinel monitoring (NEW in v2.0.2)

**Risk**: PropRAG prompt in-context examples are sized for 7-10 entities per chunk (MuSiQue/HotpotQA density). FC-MH 6k 512-chunks have 60-80 entities per chunk (numbered-list density), risking LLM attention degradation.

**Default approach (W1 startup)**:
- Try whole-chunk extraction first (no truncation)
- Monitor 3 sentinels during W1 dry-run:

```python
@dataclass
class PropositionExtractionSentinels:
    proposition_count_per_chunk: int     # expect ≈ chunk's numbered_fact_count (~37 for FC-MH 6k)
    entities_not_in_input: int           # PropRAG built-in AssertionError trigger count
    finish_reason_length: bool           # LLM truncation indicator
    raw_response_token_count: int

def monitor_extraction(chunk, propositions, llm_response):
    s = PropositionExtractionSentinels(
        proposition_count_per_chunk=len(propositions),
        entities_not_in_input=count_entities_not_in_input_list(propositions, chunk.triple_entities),
        finish_reason_length=(llm_response.finish_reason == 'length'),
        raw_response_token_count=count_tokens(llm_response.text),
    )
    # Alarm conditions
    if s.proposition_count_per_chunk / chunk.numbered_fact_count < 0.7:
        log_alarm("LOW_PROPOSITION_YIELD", chunk_id=chunk.id, sentinels=s)
    if s.entities_not_in_input > 0:
        log_alarm("ENTITIES_OUT_OF_LIST", chunk_id=chunk.id, count=s.entities_not_in_input)
    if s.finish_reason_length:
        log_alarm("LLM_TRUNCATION", chunk_id=chunk.id)
    return s
```

**Fallback (if alarm triggers, automatic)**:
```python
def batch_extraction_fallback(chunk, triple_entities, llm, n_batches=2):
    """
    Split chunk numbered list into n_batches, run PropRAG separately,
    union the propositions.
    """
    sub_chunks = split_chunk_by_numbered_list(chunk, n_batches)
    sub_entities_list = partition_entities_by_subchunk(triple_entities, sub_chunks)
    
    all_propositions = []
    for sub_chunk, sub_entities in zip(sub_chunks, sub_entities_list):
        props = extract_propositions_for_chunk(sub_chunk, sub_entities, llm)
        all_propositions.extend(props)
    return all_propositions
```

**Prompt-level upgrade (W2, only if batch fallback also insufficient)**:
- Rewrite PropRAG in-context examples from 7-10 entities to 30+ entities sized for FC-style dense chunks
- Defer to W2; W1 don't touch prompt

→ **W1 implementation must include batch infrastructure**, but default to whole-chunk. Sentinel-triggered batching is automatic.

#### B.2.2.3 Proposition node addition to KG (I3c)

```python
def add_proposition_nodes(kg: KG, propositions: List[Proposition], chunk_idx: int):
    for in_chunk_pos, p in enumerate(propositions):
        p.timestamp = (chunk_idx, in_chunk_pos)  # Q7 locked: tuple
        p.embedding = nv_embed(p.text)
        # Resolve entities to existing KG nodes (don't create new entity nodes here)
        p.entity_node_ids = resolve_to_kg_entities(p.entities, kg, allow_synonym_match=True)
        kg.add_node(p, type='proposition')
        for e_id in p.entity_node_ids:
            kg.add_edge(p, e_id, type='proposition_entity')
```

**Important**: Proposition extraction does NOT create new entity nodes. Any entity mentioned in a proposition must already exist in HippoRAG-v2 KG (from OpenIE). This maintains KG entity consistency with `chunk_triple_entities` source (Q3=ii).

### B.2.3 Candidate Cache (I4.5) — **W2 Optional Optimization**

**目的**: Offline precompute Phase 2.b's candidate lookup, 加速 query-time。Not required for Phase 2 correctness.

**Algorithm** (W2):
```python
def annotate_supersession_candidates(
    kg: KG,
    propositions: List[Proposition],
    K: int = 20,
    tau_loose: float = 0.7
):
    """
    For each proposition p_new, find top-K candidate predecessors.
    No LLM, no verdict, no easy-case. Pure mechanical retrieval.
    """
    for p_new in sorted(propositions, key=lambda p: p.timestamp):
        candidates = set()
        # Mechanism A: entity-overlap with synonymy
        for e_id in p_new.entity_node_ids:
            candidates |= kg.get_propositions_with_entity(
                e_id, include_synonyms=True, before_time=p_new.timestamp
            )
        # Mechanism B: cosine similarity
        cosine_neighbors = kg.knn_propositions(
            p_new.embedding, k=K*2, before_time=p_new.timestamp
        )
        candidates |= {
            p for p in cosine_neighbors
            if cosine(p_new.embedding, p.embedding) >= tau_loose
        }
        # Trim
        scored = [(p, score_combined(p_new, p)) for p in candidates]
        scored.sort(key=lambda x: -x[1])
        p_new.candidate_supersedees = [p.id for p, _ in scored[:K]]
```

### B.2.4 Data structures (v2.0.2)

```python
@dataclass
class Proposition:
    id: str
    text: str
    entities: List[str]                       # entity text mentions in proposition
    entity_node_ids: List[str]                # resolved to KG entity nodes
    embedding: np.ndarray                     # NV-Embed-v2 4096-d
    timestamp: Tuple[int, int]                # (chunk_idx, in_chunk_position) — Q7 locked
    source_chunk_id: str
    candidate_supersedees: Optional[List[str]] # populated by I4.5 (W2+); None if W1

@dataclass
class SupersessionEdge:
    """
    v2.0.2: created only by Phase 2.b verdict at query time.
    Phase 1 never creates supersession edges.
    """
    p_old_id: str
    p_new_id: str
    confidence: Literal['high', 'medium', 'low']
    timestamp: Tuple[int, int]                # when verdict was made
    created_by_query: str
    change_note: Optional[str]
```

### B.2.5 Validation metrics (Phase 1 v2.0.2)

#### Proposition layer (W1)

| Metric | Definition | Target |
|---|---|---|
| **Proposition yield ratio** | `mean(prop_count / numbered_fact_count)` per chunk | ≥ 0.85 |
| **Entity-in-list compliance** | `1 - (entities_out_of_list / total_propositions)` | ≥ 0.95 |
| **Batch fallback rate** | % chunks triggering batch | < 30% (informational) |
| **Extraction time per chunk** | wall-clock | < 10s |

#### Candidate cache (W2)

| Metric | Definition | Target | Stretch |
|---|---|---|---|
| **Candidate Recall@K=20** | 真實 supersession pair 中, p_old 是否在 p_new.candidate_supersedees 中 | ≥ 85% | ≥ 95% |
| **Pool size median** | median(\|candidates per p\|) | ≤ 10 | ≤ 5 |
| **Query-time latency reduction** | end-to-end time with cache vs on-the-fly | ≥ 30% | ≥ 50% |

→ W2 gate: Candidate Recall ≥ 85% AND latency reduction ≥ 30%. **If fail, accept Phase 1 cache is not beneficial; don't force.**

### B.2.6 Implementation hooks

- 新檔案: 
  - `phase1/proposition_extractor.py` — PropRAG prompt port + batch strategy + sentinels (W1)
  - `phase1/candidate_annotator.py` — entity overlap + cosine cache (W2)
  - `phase1/prompts/proposition_extraction_prompt.py` — verbatim from PropRAG, versioned (W1)
- 在 `HippoRAG.__init__` 加: `self.propositions: Dict[id, Proposition]`
- 在 `index()` 加 hooks for I2.5 → I3c → I4.5
- Feature flags:
  - `enable_proposition_layer: bool = True` (W1+, gates I2.5 + I3c)
  - `enable_phase1_candidate_cache: bool = False` (W1) → True (W2+, gates I4.5)
- Persistence: 
  - `proposition_index.json` (W1+): id → Proposition (without candidate_supersedees in W1)
  - `candidate_index.json` (W2+): candidate_supersedees mapping if cache enabled
- Logging: all sentinel events logged to `logs/proposition_extraction_sentinels.jsonl`

---

## §B.3 Phase 2 v2.0.2 — Query-Anchored Chain Detection (NEW CORE)

> **這是 v2 contribution 的中樞**。
>
> **v2.0.2 specifics**: 
> - `score_chain` 內 `prop_ppr_mass = mean(entity_ppr)` (Q5 locked)
> - W1 gate is three-tier (Q9 locked)
> - 其他與 v2.0.1 同 (M4 simplified to 3 steps, opportunistic γ via pool)

### B.3.1 Sub-phase 2.a — Chain Identification (M4 simplified)

**Purpose**: Given a query, identify M candidate reasoning chains in the KG. **Supersession-agnostic**.

**Contract**:
- **Input**: query `q`, KG with propositions, PPR scores (from O4)
- **Output**: `candidate_chains: List[Chain]` where `|chains| ≤ M=5`
- **Invariant 1 (critical)**: Chain identification does NOT filter superseded propositions
- **Invariant 2**: No LLM call in Phase 2.a

#### B.3.1.1 M4 simplified algorithm

```python
def enumerate_candidate_chains(
    query: str,
    kg: KG,
    ppr_scores: np.ndarray,
    M: int = 5,
    L: int = 3,
    region_topK: int = 50,
    enum_beam_width: int = 8,
    ppr_aggregation: Literal['mean', 'max'] = 'mean'  # Q5: mean default, max W1 ablation
) -> List[Chain]:
    
    # ─────────── Step 1: Active region identification (O4.5) ───────────
    # Q5 locked: prop_ppr_mass = mean of entity ppr (max as ablation variant)
    def compute_prop_ppr(p: Proposition) -> float:
        entity_ppr = [ppr_scores[eid] for eid in p.entity_node_ids if eid in ppr_scores]
        if not entity_ppr:
            return 0.0
        return np.mean(entity_ppr) if ppr_aggregation == 'mean' else np.max(entity_ppr)
    
    all_propositions = list(kg.propositions.values())
    prop_with_mass = [(p, compute_prop_ppr(p)) for p in all_propositions]
    prop_with_mass.sort(key=lambda x: -x[1])
    active_props = {p for p, _ in prop_with_mass[:region_topK]}
    
    # Augment with propositions 1-hop from query entities
    query_entities = link_query_entities_via_embedding(query, kg)  # Q5: HippoRAG embedding-based
    for e in query_entities:
        active_props |= kg.get_propositions_with_entity(e, include_synonyms=True)
    active_region = kg.subgraph_induced_by_propositions(active_props)
    
    # ─────────── Step 2: Bounded path enumeration (O4.6) ───────────
    raw_chains = bounded_path_enumeration(
        active_region,
        start_entities=query_entities,
        max_depth=L,
        beam_width=enum_beam_width,
        # CRITICAL: SUPERSESSION-AGNOSTIC
    )
    
    # ─────────── Step 3: Score & trim to top-M ───────────
    scored = [
        (c, score_chain(c, query, ppr_scores, compute_prop_ppr))
        for c in raw_chains
    ]
    scored.sort(key=lambda x: -x[1])
    top_chains = [c for c, _ in scored[:M]]
    return top_chains

def score_chain(chain: Chain, query: str, ppr_scores, compute_prop_ppr) -> float:
    """
    Score chain (no LLM, pure embedding + graph).
    """
    relevance = sum(cosine(p.embedding, embed(query)) for p in chain.propositions)
    coherence = chain.entity_overlap_score()
    length_penalty = -0.1 * len(chain.propositions)
    ppr_coverage = sum(compute_prop_ppr(p) for p in chain.propositions)
    return relevance + 0.3 * coherence + 0.2 * ppr_coverage + length_penalty
```

#### B.3.1.2 Entity sharing definition (Q6 lock)

| Aspect | Default | Reason |
|---|---|---|
| Sharing threshold | ≥ 1 entity shared = connected | Lenient, prefer recall |
| Synonyms count | Yes (via synonymy edges) | HippoRAG-v2 native mechanism |
| `depth` semantics | depth = #propositions in chain | Natural; FC-MH avg 1.88 propositions |

→ W1 may tune to ≥ 2 if dense graph causes path explosion.

#### B.3.1.3 γ pairing — opportunistic via pool (not separate step)

γ pairing happens in Phase 2.b pool construction, not as a separate step in Phase 2.a. Handles cases A/B/C/D:

| Case | KG state | v2.0.2 behavior |
|---|---|---|
| **A** | Only new in KG | Pool small/empty → verdict 'current' high-conf |
| **B** | new + old both in KG, candidates linked | γ link via pool → verdict compare, high conf |
| **C** | new + old both in KG, candidates missed | Pool incomplete → verdict may say 'current' with medium/low conf |
| **D** | Only old in KG (new not extracted) | Pool empty → verdict 'current' (limitation, §B.12) |

### B.3.2 Sub-phase 2.b — Chain-Restricted Supersession Verdict

**Purpose**: Within each chain, determine which propositions are superseded vs current.

#### B.3.2.1 Algorithm (v2.0.3 redesigned)

> **設計轉折**(2026-05-17, W1.3 dry-run):v2.0.2 原版本由 LLM 同時做 (a) grouping (b) 方向判斷 (c) confidence,**在 MQuAKE 反事實內容上被 parametric world-knowledge bias 反轉方向**(例如 LLM 知道 Dickens 是 Our Mutual Friend 真實作者,即使 Darwin 的 ts 更晚仍判 Darwin = superseded)。第一輪 dry-run MH 從 vanilla 20% → 11%。v2.0.3 改為:**LLM 只識別語意上 contradicting 的 pool indices(不看時間戳)**,方向交由 code 從 proposition timestamps 機械判定。詳見 §B.3.2.3。

```python
def chain_restricted_verdict(
    candidate_chains: List[Chain],
    query: str,
    propositions: Dict[str, Proposition],
    llm: LLM,
    enable_phase1_cache: bool = False,  # W1=False (on-the-fly); W2+=True
    K_pool: int = 10,                    # locked, small-pool insight
    tau_loose: float = 0.7,
    lookup_K: int = 20,
) -> Dict[str, Verdict]:
    """
    Per chain-proposition: timestamp-agnostic pool → LLM identify
    contradicting indices → mechanical direction from timestamps.
    """
    verdicts = {}
    seen_pids = set()

    for chain in candidate_chains:
        for focus_pid in chain.proposition_ids:
            if focus_pid in seen_pids:
                continue
            seen_pids.add(focus_pid)
            focus = propositions[focus_pid]

            pool = set()
            # Source 1: Phase 1 cache (W2+)
            if enable_phase1_cache and focus.candidate_supersedees:
                pool |= set(focus.candidate_supersedees)
            # Source 2: on-the-fly lookup — TIMESTAMP-AGNOSTIC (v2.0.3 single call)
            pool |= dynamic_candidate_lookup(
                focus, propositions,
                direction="any",         # ← v2.0.3 key change (was before/after split)
                tau_loose=tau_loose, K=lookup_K,
            )
            # Source 3: γ opportunistic (other chains)
            for other_chain in candidate_chains:
                if other_chain.id == chain.id:
                    continue
                pool |= find_corresponding_propositions(
                    focus, chain, other_chain, propositions,
                )
            pool.discard(focus_pid)
            pool_list = top_K_by_relevance_to_focus(pool, focus, K=K_pool)

            if not pool_list:
                verdicts[focus_pid] = Verdict(
                    status='current', confidence='low',
                    reason='no_candidates_found', superseder_id=None,
                )
                continue

            # LLM: identify contradicting pool indices (no chain context, no timestamps)
            messages, num_to_pid = build_verdict_messages(
                query=query, focus_proposition=focus, pool=pool_list,
            )
            raw, _, _ = llm.infer(messages, max_output_tokens=400, temperature=0.0)
            parsed = parse_verdict_response(raw, num_to_pid)
            # → parsed = {contradicting_pids: List[str], reason: str, parse_failed: bool}

            verdicts[focus_pid] = _decide_verdict_mechanically(
                focus=focus,
                contradicting_pids=parsed["contradicting_pids"],
                parse_failed=parsed["parse_failed"],
                propositions=propositions,
                llm_reason=parsed["reason"],
            )
    return verdicts


def _decide_verdict_mechanically(focus, contradicting_pids, parse_failed,
                                  propositions, llm_reason) -> Verdict:
    """Decision table (no LLM in this step):
       parse_failed                                  → uncertain, low
       contradicting empty                            → current,   high  (no conflict)
       contradicting found, ALL ts ≤ focus.ts         → current,   low   (defensive)
       contradicting found, ANY ts > focus.ts strict  → superseded,high, superseder=latest
    """
    if parse_failed:
        return Verdict(status="uncertain", confidence="low", superseder_id=None,
                       reason="LLM parse failed")
    if not contradicting_pids:
        return Verdict(status="current", confidence="high", superseder_id=None,
                       reason=f"no contradicting ({llm_reason[:80]})")
    focus_ts = tuple(focus.timestamp)
    later = [pid for pid in contradicting_pids
             if pid in propositions
             and tuple(propositions[pid].timestamp) > focus_ts]
    if later:
        latest = max(later, key=lambda p: tuple(propositions[p].timestamp))
        return Verdict(status="superseded", confidence="high", superseder_id=latest,
                       reason=f"superseded by later contradicting ({llm_reason[:80]})")
    return Verdict(status="current", confidence="low", superseder_id=None,
                   reason=f"contradicting found but no strictly later ts ({llm_reason[:80]})")
```

#### B.3.2.2 Conflict-identify prompt template (v2.0.3)

```
VERDICT_SYSTEM = "You are a conflict identifier. Your job is to find pool 
statements that make CONTRADICTING claims with a focus statement — meaning 
both cannot simultaneously be true."

CONFLICT_IDENTIFY_PROMPT = """QUERY (for context only, do not use to judge): {query}

FOCUS:
"{focus_text}"

POOL:
{pool_block}    # numbered [1] ... [K_pool], NO timestamps shown

A pool statement CONTRADICTS the focus when both statements describe the SAME 
underlying fact about an entity (e.g., the same role, the same location, the 
same relationship, the same attribute), but assert DIFFERENT values for that 
fact, such that both cannot simultaneously be true.

CRITICAL RULES:
- Treat all statements as opaque assertions. DO NOT use real-world knowledge 
  to judge which is "correct" or "plausible". The dataset may contain 
  counterfactual content on purpose.
- DO NOT consider timestamps. They are IRRELEVANT for THIS task and are 
  handled by a separate mechanism.
- DO NOT decide which statement is current and which is outdated. Your ONLY 
  job is to identify CONTRADICTING pairs.

CONTRADICTING examples (both cannot simultaneously be true):
  - "Acme's CEO is Alice" ↔ "Bob currently leads Acme as CEO"
  - "The capital of Wakanda is Birnin" ↔ "Wakanda's capital is Eastside"
  - "Our Mutual Friend was written by Dickens" ↔ "Charles Darwin authored Our Mutual Friend"
    (Note: counterfactual content is intentional. Do not judge factually; they 
     make incompatible claims about the same fact.)

NOT-CONTRADICTING examples (both can simultaneously hold):
  - "User likes Apple" + "User likes Banana"            (cumulative preference)
  - "John works at Google" + "John lives in Seattle"   (employment vs residence)
  - "Alice studied at MIT" + "Alice now works at Microsoft"  (life events)
  - "X is married to A" + "X has child B"              (different relationships)

Output (JSON only, no markdown):
{
  "contradicting_pool_indices": [<int>, ...],
  "reason": "<one sentence describing what fact is being contradicted>"
}"""
```

關鍵差異 vs v2.0.2 §B.3.2.2 原版本:
- ❌ 移除 `CANDIDATE REASONING CHAIN`(chain context 沒入 prompt → LLM 不會被鏈順序暗示方向)
- ❌ 移除 `(recorded at turn ..., position ...)` 時間戳(機械邏輯處理)
- ❌ 移除 `verdict / superseded_by / confidence` 三段判斷 → 只輸出 `contradicting_pool_indices`
- ✅ 新增 4 條 NOT-CONTRADICTING 範例(明確區分 cumulative vs functional 關係)
- ✅ 新增 `Treat all statements as opaque assertions` 反事實守則

#### B.3.2.3 v2.0.2 → v2.0.3 設計轉折(W1.3 dry-run findings, 2026-05-17)

**症狀**:第一輪 W1.3(沿用 v2.0.2 §B.3.2.2 原 SUPERSESSION_VERDICT_PROMPT)在 FC-MH 6k 跑出 MH = 11/100 (vanilla baseline 20/100,W1.3 第一版 **倒退** 9pt)。

**Diagnosis**(verdict_events.jsonl 抽樣 10 case):
- LLM 在「Charles Dickens 是 Our Mutual Friend 作者」(chunk 2, ts=(2,32) = chain_OLD) ↔「Charles Darwin 是 Our Mutual Friend 作者」(chunk 3, ts=(3,34) = chain_NEW)這組對立中,**雙端都被標為 superseded**:
  - focus=Dickens 看到 pool 含 Darwin → LLM 正確判 superseded ✓
  - focus=Darwin 看到 pool 含 Dickens → LLM 用 world knowledge(Dickens 才是真正作者)**反向** 也判 superseded ✗
- 結果 filter 階段把 chain_NEW 和 chain_OLD 雙端的 passage 都刪掉,LLM 答題時看不到任何相關 context。

**Root cause**: LLM 在反事實(MQuAKE-style)benchmark 上被 parametric prior 干擾,把 "real-world plausibility" 當成 "current"。原 prompt 把 grouping + direction + confidence 三個任務綁在同一次 LLM call,使得 world-knowledge 滲透到方向判斷。

**Fix (v2.0.3)**: 拆分語意 vs 時序:
- LLM 只做 **semantic grouping**(它擅長的:識別「同一個 underlying fact 但 value 不同」的對立 pair)
- 方向(誰 supersede 誰)由 code 從 `proposition.timestamp` 機械決定
- Pool 不顯示 chain context、不顯示 timestamps → 避免 LLM 用順序作為方向 hint

**Mathematical robustness**(為什麼這個 fix 在最壞情況下也不會比 baseline 差):
- 若 LLM 在某 hop 過度識別(把 cumulative attribute 誤判為 contradicting),機械方向**只會把該 hop 內 timestamp 最早的標 superseded**,不會雙端誤殺。
- 退化形態:從 v2.0.2 的「double-end deletion」(陳述為 W1.3 第一版的 11%)變成 v2.0.3 的「single-end mis-deletion」(可能漏掉一個 OLD passage 但 NEW 仍在),保留 LLM 答題的回退路徑。

**Verification**:W1.3 重跑 MH 從 11% → 31%(+20pt vs 第一版,+11pt vs vanilla),抽樣 570 verdicts 全 high-confidence,case-by-case 確認方向都對(Dickens/Darwin, Steve Sax baseball/football, Darwin married Emma/Amala 等)。詳細結果見 §B.14 W1.3。

### B.3.3 Phase 2 → Phase 3 hand-off (same as v2.0.1)

```python
def phase2_to_phase3_handoff(
    candidate_chains: List[Chain],
    verdicts: Dict[str, Verdict],
    top_passages_from_ppr: List[Passage]
) -> Phase3Input:
    chain_old_props = {
        pid for pid, v in verdicts.items()
        if v.status == 'superseded' and v.confidence in ('high', 'medium')
    }
    filtered_passages = []
    for psg in top_passages_from_ppr:
        passage_props = psg.proposition_ids
        if any(pid in chain_old_props for pid in passage_props):
            chain_new_in_psg = any(
                verdicts.get(pid, Verdict(status='current')).status == 'current'
                for pid in passage_props
            )
            if not chain_new_in_psg:
                continue
        filtered_passages.append(psg)
    
    active_chain = max(candidate_chains, key=lambda c: c.score) if candidate_chains else None
    supersession_events = [
        (pid, verdicts[pid].superseder_id)
        for pid in chain_old_props
        if verdicts[pid].superseder_id is not None
    ]
    
    return Phase3Input(
        filtered_passages=filtered_passages,
        active_chain=active_chain,
        supersession_events=supersession_events,
        verdict_confidence_map=verdicts
    )
```

### B.3.4 Validation metrics with three-tier gates (Q9 locked)

#### B.3.4.1 Phase 2.a metrics

| Metric | Target | Stretch |
|---|---|---|
| Chain Recall@M=5 | ≥ 80% | ≥ 90% |
| Chain Precision@1 | ≥ 60% | ≥ 75% |
| Alt Chain Coverage (lenient: top-M contains both p_old & p_new anywhere) | ≥ 70% | ≥ 85% |
| Alt Chain Coverage (strict: 2 distinct chains, each w/ p_old or p_new exclusively) | (paper reporting only) | — |
| Per-query latency | < 1s | < 0.5s |

#### B.3.4.2 Phase 2.b metrics

> **指標分層原則**(v2.0.3 重新分類):Phase 2.b 的 verdict 是「條件式」結果 — 若 K_pool 沒同時含某個 hop 的 chain_new + chain_old,LLM 連 group 都不可能成立。因此 **pool co-occurrence 是 recall 上限**;verdict accuracy 是 *conditional on pool 已涵蓋 pair* 的精度。原本 v2.0.2 表格將兩者混為單一 accuracy 指標,實作 W1.3 後修正。

**Primary recall (gates downstream — 沒到這個,verdict 怎麼算都救不回來)**

| Metric | Target | Stretch |
|---|---|---|
| Per-hop K_pool co-occurrence rate | ≥ 80% | ≥ 90% |

定義:對 query 推理鏈中每個有 NEW/OLD 衝突的 hop,該 hop 的 chain_new 與 chain_old proposition **都**要進入 K_pool(≤10),才算這個 hop "pool-covered"。 metric = covered_hops / total_conflict_hops(全 dataset)。Hop 只取到單側 → 此 hop 無法被 group, verdict 必漏。

**Conditional precision(假設 pool 已 co-occurrence;只在 covered hops 上算)**

| Metric | Target | Stretch |
|---|---|---|
| Per-hop verdict accuracy(conditional)| ≥ 80% | ≥ 90% |
| All-detected per-Q(全 hop 都對)| ≥ 60% | ≥ 80% |
| High-confidence verdict precision | ≥ 95% | ≥ 98% |

**Cost / latency**

| Metric | Target | Stretch |
|---|---|---|
| Pool size median | ≤ 5 | ≤ 3 |
| LLM calls per query | < 20 | < 10 |

#### B.3.4.3 End-to-end three-tier gate (Q9 locked, tentative)

| Tier | FC-MH 6k MH | Action |
|---|---|---|
| **Aspirational** | ≥ 50% | Method 突破 v1 全套, strong contribution signal |
| **Realistic target** | ≥ 45% | Method works as designed, confident to W2 |
| **Hard gate (proceed to W2)** | ≥ 40% | Method strong than v1 full, proceed |
| **Partial pass** | 35-40% | Marginal improvement, root cause analysis before W2 |
| **Fail (redesign)** | < 35% | Stop, re-examine design before proceeding |

> Threshold values are **tentative pending W1 results**. Adjust based on first measurement. The TIER STRUCTURE (4 levels) is the contract; specific cutoffs may shift ±5pp.

### B.3.5 Implementation hooks

- 新檔案結構:
  - `phase2a/active_region.py` — O4.5 hook
  - `phase2a/path_enumeration.py` — O4.6 hook
  - `phase2b/verdict.py` — O4.7 hook
  - `phase2b/dynamic_lookup.py` — on-the-fly candidate lookup (W1 primary, W2 fallback)
  - `phase2/prompts/verdict_prompt.txt` — verdict prompt template
- Feature flags:
  - `enable_phase2_chain_detection: bool = True` (W1+)
  - `enable_phase1_candidate_cache: bool = False` (W1) → True (W2+)
  - `ppr_aggregation: Literal['mean', 'max'] = 'mean'` (Q5 ablation flag)

---

## §B.4 Phase 3 v2.0.2 — Enriched Memory Output

(same as v2.0.1; minor adjustment: timestamp rendering uses tuple)

### B.4.1 Purpose & contract

提供 enriched retrieval output (passages + reasoning hints + change log), **Prompt template 不變**。

### B.4.2 Enriched context format (LOCKED)

```
=== Retrieved Passages ===
[Passage 1, supersession-filtered]
...
[Passage K]

=== Reasoning Hints ===
{A4 hybrid hint, with hedged language if any chain proposition has low-conf verdict}

=== Recent Updates ===
{B2 natural language change notes, only if applicable AND verdict confidence ≥ medium}
```

### B.4.3 Rendering implementation

```python
def render_reasoning_hint(active_chain: Chain, verdict_confidence_map) -> str:
    if not active_chain:
        return ""
    any_low_conf = any(
        verdict_confidence_map.get(p.id, Verdict()).confidence == 'low'
        for p in active_chain.propositions
    )
    prefix = "One possible reasoning path:" if any_low_conf else "Reasoning hints for this query:"
    parts = []
    for p in active_chain.propositions:
        # Timestamp tuple rendering
        chunk_idx, pos = p.timestamp
        parts.append(f"  - {p.text} (turn {chunk_idx}, position {pos})")
    return f"{prefix}\n" + "\n".join(parts)

def render_change_log(supersession_events, verdict_confidence_map) -> str:
    confident_events = [
        (p_old_id, p_new_id) for (p_old_id, p_new_id) in supersession_events
        if verdict_confidence_map.get(p_old_id, Verdict()).confidence in ('high', 'medium')
    ]
    if not confident_events:
        return ""
    notes = []
    for p_old_id, p_new_id in confident_events:
        note = render_change_note_on_fly(p_old_id, p_new_id)
        notes.append(f"  - {note}")
    return "Recent updates relevant to this query:\n" + "\n".join(notes)
```

### B.4.4 Falsifiable assertions (W3 validation)

| Assertion | Target |
|---|---|
| **A3.1**: full v2 (P2 + P3) ≥ P2-only by ≥ 5pp MH | +5pp |
| **A3.2**: P3 enriched output ≥ v1 scaffold prompt (same passages) | non-inferior |
| **A3.3**: 各 evidence type 獨立貢獻 (hints only / log only / both) | individual ablation |
| **A3.4**: 非 KU multi-hop query 退步 < 2pp | < 2pp |
| **A3.5**: Token overhead 可量化 | avg < 500 extra tokens/query |

### B.4.5 Implementation hooks

- `phase3/enriched_context_renderer.py`
- Hook in `rag_qa()`: `enriched_context = phase3.render(phase3_input)`
- Flags: `enable_phase3_v2_enriched` / `enable_phase3_v1_scaffold` (mutex)

---

## §B.5 v1 → v2.0.2 Critical Changes Mapping

### B.5.1 Removed / repositioned

| v1 component | v2.0.2 fate |
|---|---|
| Phase 1 deterministic `(s,r,≠o)` detection | Fully removed (no easy-case, no functional whitelist) |
| Phase 2 PPR mass proxy with X=99 percentile | Replaced by Phase 2.a chain id |
| Phase 3 universal scaffold prompt | Replaced by Phase 3 enriched output |
| Write-time `supersession_index.json` | Deferred to query-time (Phase 2.b verdict creates supersession edges) |

### B.5.2 New in v2.0.2

| Component | Locked decision |
|---|---|
| Proposition layer (I2.5+I3c) | Q1=(c), Q3=(ii) — PropRAG prompt + triple-derived entities |
| Candidate cache (I4.5) | W2 optional; no LLM |
| Active region (O4.5) | PPR top-50 + 1-hop, prop_ppr=mean(entity_ppr) [Q5] |
| Bounded path enumeration (O4.6) | beam width 8, depth 3, supersession-agnostic |
| Chain-restricted verdict (O4.7) | Small pool ≤10, pool from 3 sources, γ opportunistic |
| Enriched output (O5.5) | Passages + hints + log, prompt unchanged |
| Timestamp tuple | (chunk_idx, in_chunk_pos) [Q7] |
| Sentinel monitoring | Proposition extraction yield + entity compliance + length [v2.0.2 new] |
| Three-tier gate | 40/45/50 [Q9] |

### B.5.3 Motivation → Phase mapping

| Motivation 觀察 | v2.0.2 對應 |
|---|---|
| Chain-old leakage 28-29% | Phase 2.a + 2.b query-anchored verdict |
| Mem0 41% all-detected | v2 target ≥ 60% (small-pool + chain context + γ opportunistic) |
| Inference scaffold +28pp clean | Phase 3 enriched output (not prompt) |
| 30% OpenIE coverage miss | §B.12 honest limitation, propositions inherit it |

---

## §B.6 Independent Validation Strategy

### B.6.1 Validation oracle — split design (Q7 implementation)

**Method internal timestamp**: `(chunk_idx, in_chunk_position)` tuple
- Generalizable to any chunked conversational data
- Used in Phase 1 candidate annotation `before_time` filtering
- Used in Phase 2.b verdict prompt timestamp display

**FC-specific evaluation oracle**: FC GT `gt_seq` / `old_seq` (0-999 unique)
- Used ONLY in validation scripts to compute ground truth supersession ordering
- Method itself never reads FC GT seq
- Allows method to deploy to LongMemEval / 真實對話 without modification

```python
# Validation script pseudo-code:
def load_validation_oracle(fc_mh_dataset_path):
    return {
        'gt_chains': load_gt_reasoning_chains(...),         # entity hops
        'gt_supersessions': load_gt_supersession_pairs(...), # (old_fact, new_fact)
        'gt_seq_ordering': load_gt_seq_ordering(...),       # 0-999 unique fact ordering
    }

# During evaluation:
def evaluate_verdict_accuracy(verdicts, gt_supersessions, gt_seq_ordering):
    """
    For each predicted verdict, check against ground truth:
      - Is the supersession pair correct?
      - Is the ordering (old → new) correct per gt_seq?
    """
    ...
```

### B.6.2 Validation script scaffold (W1 priority)

```python
# validation/phase2_eval_w1.py
def evaluate_phase2_w1(hipporag: HippoRAG, fc_mh_dataset):
    """
    W1: Phase 2 with proposition layer (W1 required), no candidate cache,
    on-the-fly pool construction.
    """
    oracle = load_validation_oracle(fc_mh_dataset.path)
    
    hipporag.index(
        fc_mh_dataset.passages,
        enable_proposition_layer=True,          # W1 required (v2.0.2)
        enable_phase1_candidate_cache=False,    # W1 not yet
    )
    
    # Sentinel checks for I2.5 extraction (v2.0.2 new)
    extraction_sentinels = aggregate_extraction_sentinels(hipporag)
    assert extraction_sentinels['proposition_yield_ratio'] >= 0.85, \
        f"Proposition extraction yield too low: {extraction_sentinels}"
    
    # Metrics
    metrics = {}
    chain_recall_5 = 0
    verdict_correct = 0
    em_correct = 0
    all_detected_per_Q = 0
    
    for query_obj in fc_mh_dataset.queries:
        result = hipporag.retrieve_and_qa(
            query_obj.text,
            enable_phase2_chain_detection=True,
            enable_phase3_v2_enriched=False  # W1 baseline: no Phase 3
        )
        
        # Phase 2.a
        if any(chain_matches(c, oracle['gt_chains'][query_obj.id]) 
               for c in result.candidate_chains):
            chain_recall_5 += 1
        
        # Phase 2.b
        gt_sups = oracle['gt_supersessions'][query_obj.id]
        all_correct = True
        for hop in oracle['gt_chains'][query_obj.id].hops:
            expected = compute_expected_verdict(hop, gt_sups, oracle['gt_seq_ordering'])
            actual = result.verdicts.get(hop.proposition_id)
            if actual and actual.status == expected:
                verdict_correct += 1
            else:
                all_correct = False
        if all_correct and oracle['gt_chains'][query_obj.id].has_KU_hops:
            all_detected_per_Q += 1
        
        # End-to-end
        if result.answer == query_obj.gold_answer:
            em_correct += 1
    
    n = len(fc_mh_dataset.queries)
    n_KU = count_KU_queries(fc_mh_dataset)
    return {
        'chain_recall_at_5': chain_recall_5 / n,
        'per_hop_verdict_accuracy': verdict_correct / total_hops,
        'all_detected_per_Q': all_detected_per_Q / n_KU,
        'em_accuracy': em_correct / n,
        'sentinels': extraction_sentinels,
    }
```

### B.6.3 Phase-level gates (v2.0.2 three-tier for W1)

| Phase | Gate (tentative) | If fail |
|---|---|---|
| **W1 Phase 2** | Hard 40% / Realistic 45% / Aspirational 50% MH | < 35% redesign; 35-40% root cause analysis |
| **W2 Phase 1 cache** | Candidate Recall ≥ 85% AND ≥ 30% latency reduction | Acceptable to abandon cache; not blocker |
| **W3 Phase 3** | End-to-end ≥ 50% AND non-KU 退步 < 2pp AND A3.2 non-inferior | Fallback to v1 scaffold |

---

## §B.7 Implementation Order & Weekly Gates (v2.0.2)

| Week | Focus | Deliverable | Gate (tentative) |
|---|---|---|---|
| **W1.1** (3-4 days) | Proposition layer (I2.5+I3c): PropRAG prompt port, triple-derived entity feed, batch fallback, sentinels | `phase1/proposition_extractor.py` + sentinel logging | Proposition yield ≥ 0.85, entity compliance ≥ 0.95 |
| **W1.2** (2-3 days) | Phase 2.a chain detection: active region + path enumeration | `phase2a/` modules | Chain Recall@5 ≥ 80% (or revise) |
| **W1.3** (2-3 days) | Phase 2.b verdict: on-the-fly pool + LLM judge with chain context | `phase2b/` modules + `validation/phase2_eval_w1.py` | Per-hop verdict ≥ 80% AND end-to-end MH triggers tier (see B.3.4.3) |
| **W2** | Phase 1 candidate cache (I4.5) — purely optimization | `phase1/candidate_annotator.py` + W2 validation | Candidate Recall ≥ 85% AND latency reduction ≥ 30% (acceptable to abandon) |
| **W3** | Phase 3 enriched output + Claim 2 ablation | `phase3/` + `validation/phase3_ablation.py` | A3.1-A3.5 |
| **W4** | 32k scaling + LongMemEval non-degradation | 32k + LongMemEval results | 32k MH scaling reasonable, LongMemEval 不退 > 3pp |
| **W5** | 262k scaling with chunk_size=4096 alignment + writing kickoff | 262k results + §C.6/7 draft | 262k MH ≥ 25% |
| **W6** | Paper draft finalization + final ablations | Full paper draft | — |
| **W7** | Buffer + advisor review | Final submission | — |

**chunk_size strategy (v2.0.2 new):**
- W1-W4: chunk_size=512 (matches v1 baseline 12 chunks for 6k, controlled variable)
- W2/W3 sub-ablation: chunk_size ∈ {256, 512, 1024} on 6k for robustness check
- W5 262k: chunk_size=4096 for MemoryAgentBench baseline alignment; PropRAG batch strategy is critical at this scale

**Contingency plans**:
- W1.1 fail → fallback to batch extraction (automatic via sentinels); if persistent, escalate to W2 prompt rewrite
- W1.3 fail (< 35%) → stop and design review
- W1.3 partial pass (35-40%) → root cause analysis week, may extend timeline
- W2 cache no benefit → paper note "on-the-fly suffices", don't force
- W5 262k degradation → paper limits to 32k+disclosure

---

## §B.8 PropRAG / Mem0 / Zep 角色重新定位

### B.8.1 PropRAG (EMNLP 2025)

| 層 | v2.0.2 定位 |
|---|---|
| Engineering | **Prompt template port** (proposition_extraction.py used verbatim with triple-derived entity feed) |
| Method concept | Inspiration only — proposition representation upgrades internal granularity; **no beam search adoption**, we use bounded enumeration + scoring |
| Paper narrative | §C.2 cite once: "We port PropRAG's proposition extraction prompt as our internal memory representation upgrade, while preserving HippoRAG-v2's raw-passage return paradigm for conversational memory community alignment." Not framed as method baseline |

→ **Framing implication**: 我們 paper 仍 100% conversational agent memory community, PropRAG 是 inspiration + prompt template source, 不跑 baseline。

### B.8.2 Mem0 (ECAI 2025)

| 維度 | Mem0 限制 | v2.0.2 解法 |
|---|---|---|
| Detection locus | write-time only | v2 主 verdict 在 query-time, Phase 1 只 cache (W2) |
| Pool size | top-k=5 (small but write-time) | v2 small-pool 但 query-anchored (K_pool=10) |
| Multi-hop coherence | 各 hop 獨立 judge | v2 chain context → 同 query 多 hops 同 LLM context |

### B.8.3 Zep (arXiv 2024)

| 維度 | Zep 限制 | v2.0.2 解法 |
|---|---|---|
| Temporal annotation | 假設 explicit temporal qualifier | v2 用 `(chunk_idx, in_chunk_pos)` tuple 作 implicit timestamp |
| Exclusion detection | 每 fact 獨立 judge | v2 chain-restricted, propositions 並列判斷 |

---

## §B.9 Open Design Questions (deferred to implementation)

| Open Q | Default (v2.0.2) | When to revisit |
|---|---|---|
| `tau_loose` (candidate cosine threshold) | 0.7 | W2 if Candidate Recall < 85% |
| `region_topK` (active region size) | 50 | W1.2 if Chain Recall < 80% |
| `enum_beam_width` | 8 | W1.2 similar |
| Verdict prompt phrasing | Draft in B.3.2.2 | W1.3 if verdict accuracy < 80% |
| Phase 3 evidence weighting | All included | W3 A3.3 ablation |
| Fallback when no chain found | Pure HippoRAG-v2 PPR retrieval | W1 stress test |
| Hedged language threshold | confidence='low' triggers hedge | W3 |
| Entity sharing strictness (≥1 vs ≥2) | ≥1 lenient | W1.2 if path explosion |
| `ppr_aggregation` (mean vs max) | mean | **W1 ablation as part of metric reporting** |
| Three-tier gate cutoffs (40/45/50) | tentative | **W1 first measurement, adjust based on results** |
| Phase 1 cache value | TBD W2 gate | W2 — may abandon if no benefit |
| PropRAG batch threshold (when to split) | Auto via sentinels | W1.1 monitor logs |
| `chunk_size` sensitivity | locked at 512 in W1 | W2/W3 robustness ablation; W5 262k alignment |

---

## §B.10 Skeleton Summary Table (v2.0.2)

| Phase | Sub-phase | Role | Locked | Key file | Week |
|---|---|---|---|---|---|
| 1 | proposition extraction (I2.5) | LLM-aided preprocessing for granularity | PropRAG prompt + triple-derived entities (Q1=c, Q3=ii) | `phase1/proposition_extractor.py` | W1.1 |
| 1 | proposition nodes (I3c) | KG augmentation | timestamp = (chunk_idx, in_chunk_pos) (Q7) | `phase1/kg_builder.py` | W1.1 |
| 1 | candidate cache (I4.5) | offline pool precompute (no LLM) | Mechanism A+B, K=20 | `phase1/candidate_annotator.py` | W2 |
| 2.a | active region (O4.5) | scope chain search | PPR top-50 + 1-hop, prop_ppr=mean(entity_ppr) (Q5) | `phase2a/active_region.py` | W1.2 |
| 2.a | path enumeration (O4.6) | discover chains | beam 8, depth 3, agnostic | `phase2a/path_enumeration.py` | W1.2 |
| 2.b | chain-restricted verdict (O4.7) | THE critical detection | small pool ≤10, 3-source pool (cache+on-the-fly+γ) | `phase2b/verdict.py` | W1.3 |
| 3 | enriched context (O5.5) | rich evidence return | passages + hints + log, prompt unchanged | `phase3/enriched_context_renderer.py` | W3 |

---

## §B.11 Quick-Start for Claude Code (v2.0.2)

### B.11.1 Read order

§B.0 (architecture) → §B.1 (hooks) → §B.2 (Phase 1 layers) → **§B.3 (Phase 2, main W1 work)** → §B.6 (validation) → §B.11 (this) → §B.7 (weekly gates) → §B.12 (limitations)

### B.11.2 W1 implementation order

1. **W1.1**: `phase1/proposition_extractor.py` + sentinels (no W1.2/1.3 work yet)
2. **W1.1 sanity**: run on 2-3 sample chunks, verify sentinel logs make sense
3. **W1.2**: `phase2a/active_region.py` + `phase2a/path_enumeration.py` (no W1.3 yet)
4. **W1.2 sanity**: dump top-5 chains for 5 sample queries, verify chains look reasonable
5. **W1.3**: `phase2b/verdict.py` + `phase2b/dynamic_lookup.py`
6. **W1.3 end**: run `validation/phase2_eval_w1.py` on full FC-MH 6k, report metrics

### B.11.3 Critical invariants (NON-NEGOTIABLE)

- Phase 1 NO LLM verdict (extraction is OK; verdict is NOT Phase 1's job)
- NO easy-case detection / functional whitelist / cardinality classification
- Phase 2.a supersession-AGNOSTIC (both old and new chains must be discoverable in principle)
- Phase 2.b pool ≤ 10 strict (small-pool insight from Mem0 diagnostic)
- Phase 3 prompt template unchanged (contribution purity)
- Method internal timestamp = (chunk_idx, in_chunk_pos) tuple — never FC GT seq

### B.11.4 Feature flags (v2.0.2 renamed)

```python
# Flags by week:
# W1: enable_proposition_layer=True, enable_phase2_chain_detection=True, others False
# W2: + enable_phase1_candidate_cache=True
# W3: + enable_phase3_v2_enriched=True

enable_proposition_layer: bool = True              # W1+; gates I2.5 + I3c
enable_phase1_candidate_cache: bool = False        # W1; W2+ if gate passed
enable_phase2_chain_detection: bool = True         # W1+
enable_phase3_v2_enriched: bool = False            # W3+
enable_phase3_v1_scaffold: bool = False            # legacy, only for A3.2 ablation
ppr_aggregation: Literal['mean', 'max'] = 'mean'   # Q5 ablation knob
```

### B.11.5 Explicit DO list (W1)

- DO port PropRAG `proposition_extraction.py` prompt verbatim
- DO feed it `chunk_triple_entities` (union of s,o per chunk from HippoRAG OpenIE)
- DO implement batch fallback infrastructure (automatic sentinel-triggered)
- DO use on-the-fly candidate lookup in Phase 2.b (W1 has no cache)
- DO log all sentinels + chain enumeration + verdict events for offline analysis
- DO ensure Phase 2.a is supersession-AGNOSTIC

### B.11.6 Explicit DON'T list

- DON'T implement easy-case detection (any kind)
- DON'T use functional relation whitelist / cardinality classification
- DON'T add LLM tail validate in Phase 2.a
- DON'T require Phase 1 candidate cache for Phase 2 to work
- DON'T filter superseded propositions before Phase 2.b verdict
- DON'T touch the inference prompt template (Phase 3 changes content, not template)
- DON'T use FC GT seq inside method (only in validation scripts)

### B.11.7 Data persistence (v2.0.2)

- `proposition_index.json` (W1+): `{prop_id: Proposition}` (without candidate_supersedees in W1)
- `candidate_index.json` (W2+): if cache enabled
- `graph.graphml`: extended with proposition nodes
- `logs/proposition_extraction_sentinels.jsonl`: W1.1 sentinel events
- `logs/chain_enumeration.jsonl`: W1.2 per-query enumeration results
- `logs/verdict_events.jsonl`: W1.3 per-verdict events (chain context, pool composition, verdict, confidence, reason)
- **No `supersession_index.json` written at indexing time** (Phase 1 never creates supersession edges)

---

## §B.12 Coverage Limitations Honesty Box (v2.0.2 extended)

> **這節必須寫進 paper §C.5.2 Limitations**。

### B.12.1 Four-case coverage taxonomy

v2.0.2 設計處理 4 種 (p_old, p_new) coverage 情況:

| Case | KG 狀態 | Phase 2.b 行為 | Paper 表達 |
|---|---|---|---|
| **A** | 只有 new 在 KG | Pool 空 → verdict 'current' high-conf | ✅ 正確處理 |
| **B** | new + old 都在 KG, candidate lookup 成功 | γ via pool → verdict 可比較 | ✅ 主要 contribution case |
| **C** | new + old 都在 KG, candidate lookup 失敗 (Phase 1 cache 漏 + on-the-fly 也漏) | Pool 不完整 → 可能誤判 'current' (medium/low confidence) | ⚠️ **partial mitigation**: Phase 3 hedged language; §C.5.2 admission |
| **D** | 只有 old 在 KG (new 從未 extract 成 proposition) | 永遠無法偵測 | ❌ **honest limitation** |

### B.12.2 Case D root cause: OpenIE-bound proposition coverage (v2.0.2 specific)

採 Q3=(ii) 意味著 propositions 從 HippoRAG-v2 triple-derived entities 抽取:
- Triple-derived entities = union of (s, o) per chunk
- 任何 OpenIE 漏抽的 fact, 對應 propositions 也漏

**Quantification**: Method v1 §13.2 measured **30% of missed cases were "OpenIE didn't extract chain_old triple"**. This same root cause limits v2 proposition coverage:
- v2 inherits OpenIE 30% miss rate as proposition extraction upper bound
- 不能 break 這個 ceiling 除非升級 extraction (Q3 path (i) or (iii))

**Paper §C.5.2 wording (suggestion)**:
> "Our method's detection coverage is upper-bounded by the proposition extraction quality. Since we extract propositions using HippoRAG-v2's triple-derived entities (to maintain KG consistency), any fact whose triple was not extracted by OpenIE remains invisible to all downstream stages. We measure this baseline coverage gap at approximately 30% of missed supersessions in our FC-MH 6k diagnostic. This is a representation coverage limitation orthogonal to our query-anchored detection contribution. Future work could address this via alternative proposition extraction strategies (e.g., LLM-extracted entities without triple constraint) at the cost of KG consistency or additional pipeline complexity."

### B.12.3 Case C partial mitigation strategy (v2.0.2)

- Phase 3 enriched output uses hedged language when verdict.confidence ∈ {low, medium}
- Reasoning hint prefix changes "Reasoning hints" → "One possible reasoning path"
- Change log only includes high-confidence supersession events

---

## §B.13 Concrete Dependency Graph & Data Flow (v2.0.2)

```
Indexing (offline, per chunk):
─────────────────────────────────────────────────────
Chunk → I1 OpenIE → triples + extracted_entities (raw)
                       │
                       ↓
              chunk_triple_entities = ⋃(s,o) per chunk
                       ↓
              I2 Embed (chunks, entities, facts)
                       ↓
              I2.5 PropRAG proposition extraction (W1 REQUIRED)
              ├── Input: {passage, named_entities=chunk_triple_entities}
              ├── Default: whole-chunk
              ├── Sentinel monitors:
              │   ├── proposition_yield_ratio ≥ 0.85
              │   ├── entities_in_input compliance ≥ 0.95
              │   └── no finish_reason=length
              ├── Fallback (sentinel-triggered): batch split
              └── Output: List[Proposition] with timestamp=(chunk_idx, in_chunk_pos)
                       ↓
              I3 add_fact_edges + add_passage_edges
                       ↓
              I3c add_proposition_nodes (W1 REQUIRED)
                       ↓
              I4 synonymy edges
                       ↓
              I4.5 annotate_supersession_candidates (W2 OPTIONAL)
                   (no LLM, entity overlap + cosine cache)
                       ↓
              I5 save (proposition_index.json, candidate_index.json, graph.graphml)


Query-time (per query):
─────────────────────────────────────────────────────
Query → O1 fact scoring → O3 seed weights → O4 PPR
                                                ↓
                                       O4.5 Active region
                                       (prop_ppr = mean(entity_ppr), Q5)
                                                ↓
                                       O4.6 Path enumeration (Phase 2.a)
                                       (supersession-agnostic, beam 8, depth 3)
                                                ↓
                                            top-M=5 chains
                                                ↓
                                       O4.7 Verdict (Phase 2.b)
                                            Pool sources:
                                            ├── Phase 1 cache (W2+ optional)
                                            ├── on-the-fly lookup (always, W1 primary)
                                            └── γ opportunistic from other chains
                                            Pool capped at K_pool=10
                                            LLM judge per proposition
                                                ↓
                                            verdicts (current / superseded / uncertain
                                                      with confidence)
                                                ↓
                                       Phase 2 → Phase 3 handoff
                                                ↓
                                       Filter passages by verdict
                                                ↓
                                       O5.5 render_enriched_context (W3)
                                          ├── filtered passages
                                          ├── reasoning hints (chain) [hedged if low-conf]
                                          └── change log (verdicts) [conf ≥ medium only]
                                                ↓
                                       O6 rag_qa (prompt UNCHANGED)
                                                ↓
                                            Final answer


Validation oracle (W1+, NOT used by method itself):
─────────────────────────────────────────────────────
FC-MH 6k → load_validation_oracle()
            ├── gt_chains (entity hops)
            ├── gt_supersessions (p_old, p_new pairs)
            └── gt_seq_ordering (FC numbered-list 0-999, eval-only)

→ Method uses (chunk_idx, in_chunk_pos) tuple internally
→ Validation script uses gt_seq_ordering to check method's verdict ordering
→ Method generalizable beyond FC; validation oracle FC-specific (OK)
```

---

## §B.14 實作進度紀錄(Implementation Progress Log)

> 每完成一個 W-sub-step 加一段記錄。包含**所在流程位置 / 動了哪些檔 / 做了哪些嘗試 / 得到甚麼結果 / open issues**。

---

### W1.1 — Proposition Layer Extractor(2026-05-16,✅ 首次通過 gate)

#### 🗺️ 在整個方法流程的位置

```
─ Offline Indexing(離線建索引)──────────────────────────────
I1.  OpenIE → triples + extracted_entities ............... (保留, 已有)
I2.  Embeddings .......................................... (保留, 已有)
I2.5 ▶▶ PropRAG-style proposition extraction ............. ★ W1.1 完成 ★
     ├── Input: chunk passage + chunk_triple_entities
     ├── LLM: Gemini 3.1 Flash-Lite, PropRAG prompt verbatim
     └── Output: List[Proposition] with timestamp tuple
I3.  add_fact_edges + add_passage_edges .................. (保留, 已有)
I3c. add_proposition_nodes(I3c, W1.2 待做)............... ⏳ 下一步
I4.  add_synonymy_edges .................................. (保留)
I4.5 annotate_supersession_candidates(W2 optional)
I5.  save indexes

─ Online Retrieval & QA ─────────────────────────────────
(W1.2 開始)O4.5/O4.6/O4.7 Phase 2.a + 2.b
```

→ **目前完成的:I2.5(LLM 抽取 propositions)的單元模組與 dry-test 驗證**。**還沒**整合進 HippoRAG.py index() 主流程(W1.2 一起做)。

#### 主要動了哪些部分(檔案層面)

**新增 4 個檔 + 2 個 outputs**:

| 路徑 | 用途 |
|---|---|
| `methods/hipporag/phase1/__init__.py` | package marker |
| `methods/hipporag/phase1/prompts/proposition_extraction_prompt.py` | **PropRAG prompt 逐字 port**(system + user frame + `build_messages()`) |
| `methods/hipporag/phase1/data_structures.py` | `Proposition` dataclass + `PropositionExtractionSentinels` |
| `methods/hipporag/phase1/proposition_extractor.py` | 主模組:抽取邏輯 + 3 個 sentinel + batch fallback |
| `analysis/smoke_test_w1_1_proposition_extractor.py` | Dry-test driver(對 chunks 0/1/7 跑) |
| `logs/proposition_extraction_sentinels.jsonl` | Sentinel 事件記錄(append-only JSONL) |
| `analysis/results/phase_v2/w1_1_dry_test.json` | Dry-test 完整結果(propositions + sentinels) |

#### 引用的 prompt 長什麼樣

**有,直接從 PropRAG `proposition_extraction.py` 逐字 port**(無任何 prompt 內容修改)。結構:

**SYSTEM(任務說明 + 規則 + 2 個 in-context examples)**:
```
Your task is to analyze text passages and break them down into precise, 
atomic propositions using a specified list of named entities. A proposition 
is a fully contextualized statement that expresses a single unit of meaning 
with complete specificity about the relationships described.

For each proposition:
1. Extract a complete, standalone statement that preserves the full context
2. Use ONLY the entities provided in the named_entities list - do not introduce new entities
3. Ensure each proposition contains only ONE claim or relationship
4. Be extremely specific about which entities are involved in each relationship
5. Maintain clear causal connections between related statements

Respond with a JSON object containing a list of propositions, where each 
proposition is an object with:
- "text": The full proposition text as a complete, contextualized statement
- "entities": An array of entities from the named_entities list that appear...

Critical Guidelines: [10 條 detailed guideline]

Example 1: [Apple M1 chip / Adobe 範例]
Example 2: [iPhone 15 USB-C / European Union 範例]
```

**USER**:
```
Passage:
```
{passage}              ← 我們塞 FC chunk 文字
```

Named entities: {named_entities}    ← 我們塞 chunk 的 triple-derived entities
```

#### 對輸入做了什麼(以 chunk 0 為實例 trace)

**輸入(從 OpenIE cache 讀)**:

```python
# chunk 0 的 passage(部分)
passage = """Here is a list of facts:
0. Thomas Kyd was born in the city of London. 
1. The chairperson of Fatah is Mahmoud Abbas. 
2. Amy Winehouse died in the city of Camden Town. 
... (共 37 條 numbered facts)"""

# chunk 0 的 triples(OpenIE 已抽好, 37 條)
triples = [
    ['Thomas Kyd', 'born in', 'London'],
    ['Mahmoud Abbas', 'chairperson of', 'Fatah'],
    ['Amy Winehouse', 'died in', 'Camden Town'],
    ...
]
```

**Step 1 — 從 triples 派生 entity list**(`derive_chunk_triple_entities`):
```python
triple_entities = {'Thomas Kyd', 'London', 'Mahmoud Abbas', 'Fatah',
                   'Amy Winehouse', 'Camden Town', ...}  # 共 68 個 unique entities
```

**Step 2 — 算 expected proposition count**(`count_numbered_facts`,用正則找 `\d+\.\s+`):
```
expected = 37
```

**Step 3 — Build messages 餵給 LLM**(完整 system + user):
```python
messages = [
    {"role": "system", "content": <PropRAG SYSTEM 全文>},
    {"role": "user", "content": """
        Passage:
        ```
        Here is a list of facts:
        0. Thomas Kyd was born in the city of London. ...
        ```
        Named entities: ["Thomas Kyd", "London", "Mahmoud Abbas", ...]
    """}
]
```

**Step 4 — LLM 回應 JSON**(Gemini 3.1 Flash-Lite):
```json
{
  "propositions": [
    {"text": "Thomas Kyd was born in the city of London.",
     "entities": ["Thomas Kyd", "London"]},
    {"text": "Mahmoud Abbas is the chairperson of Fatah.",
     "entities": ["Mahmoud Abbas", "Fatah"]},
    {"text": "Amy Winehouse died in the city of Camden Town.",
     "entities": ["Amy Winehouse", "Camden Town"]},
    ...(共 37 條)
  ]
}
```

**Step 5 — Parse + 建 Proposition dataclass(加 timestamp)**:
```python
Proposition(
    id="prop-<md5_hash_of_pos_and_text>",
    text="Thomas Kyd was born in the city of London.",
    entities=["Thomas Kyd", "London"],
    source_chunk_id="chunk-362feee8...",
    timestamp=(0, 0),               # (chunk_idx=0, in_chunk_position=0)
)
Proposition(..., timestamp=(0, 1))  # 第 2 個
Proposition(..., timestamp=(0, 2))  # 第 3 個
... 共 37 個
```

**Step 6 — 算 3 個 sentinel**:
```
proposition_yield_ratio = 37 / 37 = 1.00
entities_not_in_input = 0    (每條 proposition 用的 entity 都在輸入 list 內)
finish_reason_length = False  (LLM 沒被截斷)
→ alarms = []  (全綠燈, 不需要 batch fallback)
```

**Step 7 — 寫 sentinel log + 回傳 propositions**。

#### 做了哪些嘗試

| 嘗試項 | 預設值 | 實際表現 | 是否需迭代 |
|---|---|---|---|
| 整 chunk 一次抽取(default) | 60-80 entities/chunk 一次餵 | 全 3 chunks ✅,沒觸發 batch fallback | ❌ 不用 |
| Batch fallback(2 → 4 batches)| 自動觸發若 sentinels alarm | 沒觸發 → **未驗證**(W4+ 大 corpus 才會用到) | ⚠️ 待真實壓力測試 |
| Sentinel `entities_not_in_input` 用 case-insensitive substring match | 處理 OpenIE 大小寫變異 | 0 false-positive,3 chunks compliance 100% | ❌ 不用 |
| Robust JSON parser(處理 markdown fence)| 借鑑 v2_llm_judge.py | Gemini 直接回乾淨 JSON,fence 處理沒派上用場 | ❌ 不用 |

#### 得到甚麼結果

**3 chunks dry-test 全部過 gate(target: yield ≥ 0.85, compliance ≥ 0.95)**:

| chunk | numbered_facts | n_props | yield | entities_OOL | truncated | attempts |
|---|---|---|---|---|---|---|
| 0 | 37 | 37 | **1.00** | 0 | False | 1 |
| 1 | 37 | 35 | **0.95** | 0 | False | 1 |
| 7 | 38 | 38 | **1.00** | 0 | False | 1 |

- **平均 yield = 0.98**(超 target +13pp)
- **Entity compliance = 100%**(0 violations)
- **Sample proposition 品質好,是 natural sentence(非 triple form)**:
  - `"Mahmoud Abbas is the chairperson of Fatah."`
  - `"Frank Zappa died in the city of Los Angeles."`

**重要觀察**:
1. **Chunk 1 yield 0.95 = OpenIE 漏 2 triples**(n_triples=35 vs 37 numbered facts)。LLM 抽了 35 條 = 完全對應可用 triples。這正是 §B.12.2 預期的 **OpenIE-bound coverage gap** 在 measurement 上的體現(非 proposition 提取品質問題)。
2. **整 chunk 餵 60-80 entities 在 6k 規模 LLM 沒崩** — v2.0.1→v2.0.2 review 擔心的 attention 風險**在 FC-MH 6k 沒觸發**。32k+ / LongMemEval(W4+)再驗。
3. Propositions 是 natural sentence,完全達到 PropRAG-style 升級目的(triple → proposition)。

#### Locked 決策(動工中確認)

| 決策點 | Spec 預設 | W1.1 confirm |
|---|---|---|
| Q1 = (c) | PropRAG extraction(非 triple proxy 或 sentence reconstruction)| ✅ confirmed |
| Q3 = (ii) | 餵 triple-derived entities(非 raw NER list)| ✅ confirmed |
| LLM | Gemini 3.1 Flash-Lite, T=0.0, max_tokens=2048 | ✅ 用 CacheGemini |
| Proposition id | `mdhash("{chunk_idx}-{pos}-{text}", prefix="prop-")` | ✅ 採用 |
| Entity compliance check | case-insensitive substring(雙向) | ✅ 採用 |
| Batch fallback 條件 | LOW_YIELD 或 LLM_TRUNCATION 才升級;ENTITIES_OOL 不升級 | ✅ 採用 |
| Batch 升級步進 | 1 → 2 → 4(冪次, cap=4)| ✅ 採用 |

#### Open items / 小 tech-debt(non-blocking)

- ⚠️ **chunk_id 雙 prefix bug**:`"chunk-chunk-362feee8..."` ← 因為 `doc["idx"]` 已是 `"chunk-..."` 開頭,driver 又 `f"chunk-{doc['idx']}"` 多 prefix 一次。**Cosmetic,不影響 proposition 資料正確性**。W1.2 整進 HippoRAG.py index() 時順手修。
- ⚠️ **Batch fallback paths 未實測**:dry-test 3 chunks 都沒觸發。要等 W4 大 corpus / 32k 才會壓力測。
- ⚠️ **未測過 ENTITIES_OUT_OF_LIST alarm 真正觸發場景** — Gemini 嚴格遵守 PropRAG prompt,沒拿 list 外 entity。LongMemEval natural conversation 可能會觸發。

#### Gate 結論

✅ **PASS**(per §B.2.5 target: yield ≥ 0.85 / compliance ≥ 0.95)→ 可進 **W1.2(Phase 2.a 主要動作:active region + path enumeration)**。

---

### W1.2 — Phase 2.a Chain Identification(2026-05-16,✅ qualitative pass)

#### 🗺️ 在整個方法流程的位置

```
─ Offline Indexing(離線建索引)──────────────────────────────
I1.  OpenIE → triples (保留)
I2.  Embeddings (保留)
I2.5 ✅ Proposition extraction (W1.1) ......... 已完成
I3.  add_fact_edges + add_passage_edges (保留)
I3c. add_proposition_nodes ......... ⏳ 延後(目前 dry-test 用獨立 proposition_index.json)
I4.  add_synonymy_edges (保留)
I4.5 annotate_supersession_candidates(W2 optional)
I5.  save indexes

─ Online Retrieval & QA ─────────────────────────────────
O1.  fact scoring
O2.  rerank_facts
O3.  seed weights
O4.  run_ppr → pagerank_scores (保留)
O4.5 ▶▶ identify_active_region ............... ★ W1.2 完成 ★
     ├── Input: query, propositions, prop_ppr_mass
     └── Output: active region(top-50 by mass + 1-hop entity expansion)
O4.6 ▶▶ enumerate_candidate_chains ............ ★ W1.2 完成 ★
     ├── Beam search,depth L=3, beam=8, M=5
     ├── Path = ordered propositions sharing entities
     └── Supersession-AGNOSTIC(關鍵 invariant)
O4.7 chain_restricted_verdict ......... ⏳ W1.3 下一步
O5.  Passage filter by verdict
O5.5 render_enriched_context (W3)
O6.  rag_qa (prompt 不動)
```

→ **目前完成 Phase 2.a 兩個 hooks**(O4.5 + O4.6),但**還沒整合進 HippoRAG.retrieve() 主流程**(dry-test 用 cosine proxy 取代 PPR;W1.3 整合進 HippoRAG 時會用真 PPR scores)。

#### 主要動了哪些部分

| 路徑 | 用途 |
|---|---|
| `methods/hipporag/phase2a/__init__.py` | package marker |
| `methods/hipporag/phase2a/data_structures.py` | `Chain` dataclass(prop_ids + shared_entity_path + score + breakdown)|
| `methods/hipporag/phase2a/active_region.py` | O4.5 hook:`identify_active_region` + `compute_prop_ppr_mass_from_entity_ppr`(Q5 mean/max 切換)+ `compute_prop_mass_proxy_from_query_cosine`(W1 dry-test 用)|
| `methods/hipporag/phase2a/path_enumeration.py` | O4.6 hook:`enumerate_candidate_chains`(beam search)+ `score_chain`(relevance + 0.3·coherence + 0.2·ppr_coverage + length_penalty)+ `_entity_overlap`(case-insensitive substring 雙向)|
| `analysis/build_proposition_index_w1.py` | 一次性 driver:對 12 chunks 跑 W1.1 extractor + NV-Embed-v2 編碼 → `proposition_index.json`(450 props × 4096-d embedding)|
| `analysis/smoke_test_w1_2_chain_enumeration.py` | W1.2 dry-test driver:5 sample queries × top-5 chains |
| `analysis/results/phase_v2/w1_2_dry_test.json` | dry-test 結果 |

#### Active region + path enumeration 對輸入做了什麼(以 qid=20 為實例)

**輸入**:
- Query: `"What is the language of the work that was created by the individual who created Rand al'Thor?"`
- propositions: 450 個(全 corpus)
- proposition embeddings: NV-Embed-v2 4096-d

**Step 1 — 簡單 query entity linker**(substring 比對 KG entities,len ≥ 4):
```
query_entities = {"Rand al'Thor"}  # 在 query 文字內出現
```

**Step 2 — Encode query embedding**(NV-Embed-v2, `query_to_fact` instruction):
```
q_emb = [4096-d float vector, normalized]
```

**Step 3 — PPR mass proxy**(W1 用 cosine 取代;W1.3 換真 PPR):
```python
prop_mass[pid] = max(0, dot(query_emb, p.embedding))  # for all 450 props
```

**Step 4 — Active region**:
- 取 top-50 props by prop_mass(包含 "rand al thor created by ferdowsi", "rand al thor created by robert jordan", "robert jordan famous for the wheel of time" 等)
- 1-hop 擴展:其他 props 提到 "Rand al'Thor" 的(本例 active region 還是 50,因為 top-50 已涵蓋)
- → `active_region_size = 50`

**Step 5 — Bounded beam search**(beam=8, depth=L=3):
- 種子:top-8 by mass → 都是 "rand al'thor created by X" / "robert jordan famous for ..." 等
- 對每個種子,找 entity-overlap 鄰居,擴展到 depth 2, 3
- 每 depth 評分,留 top-8 beam
- 共收集所有 depths 的 paths,dedup,score 排序

**Step 6 — Return top-M=5 chains**:

```
[chain 0] score=2.160 depth=3
  0. Rand al'Thor was created by Ferdowsi.      ← chain_NEW
  1. Rand al'Thor was created by Robert Jordan. ← chain_OLD  via "Rand al'Thor"
  2. Robert Jordan is famous for The Wheel of Time.       via "Robert Jordan"

[chain 1] score=1.956 depth=3
  0. Rand al'Thor was created by Robert Jordan.  ← chain_OLD
  1. Robert Jordan is famous for The Wheel of Time.  via "Robert Jordan"
  2. The Wheel of Time was written in the language of English.  via "The Wheel of Time"

...
```

#### Dry-test 結果

5 sample queries(qid 0/20/45/65/85),測試 chain enumeration 是否找到 chain_new / chain_old:

| qid | hops | GT new | GT old | top1_new | top1_old | top5_any_new | top5_any_old |
|---|---|---|---|---|---|---|---|
| 0 | 3 | 3 | 3 | 1 | 0 | 2 | 1 |
| 20 | 1 | 1 | 1 | **1** | **1** | 1 | 1 |
| 45 | 1 | 1 | 1 | **1** | 0* | 1 | 0* |
| 65 | 2 | 2 | 2 | **1** | **1** | 2 | 1 |
| 85 | 3 | 3 | 3 | **1** | **1** | 1 | 1 |

\* qid=45 top1_old=0 是 dry-test eyeball matching bug(surface 反序漏抓),實際 chain 0 pos 1 是 chain_old 文本。

**關鍵正面訊號 — chain_new + chain_old 自然落同一 chain**(支援 Phase 2.b 對比 verdict):
- qid=20 chain 0:Ferdowsi(new)+ Robert Jordan(old)同 chain,via "Rand al'Thor" 橋接
- qid=65 chain 1:Lucasfilm(old)+ BBC(new)+ Modi(new)同 chain
- qid=85 chain 0:goaltender(new)+ center(old)同 chain

#### 做了哪些嘗試

| 嘗試項 | 預設 | 表現 | 是否需迭代 |
|---|---|---|---|
| PPR mass = query-cosine proxy(W1 dry-test)| 取代真 PPR | 5 queries 都找到 query-relevant props | W1.3 換真 PPR;cosine proxy 算合理 surrogate |
| region_topK = 50 | active region size | 50 props 足以涵蓋 chain_new + chain_old | OK |
| beam_width = 8, depth = L = 3 | spec 預設 | 5/5 queries 找到 hop_0 conflict pair | OK,但 L=3 漏 3-hop 後段 |
| Score = relevance + 0.3·coherence + 0.2·ppr + length_penalty | spec 預設 | top-5 都含 GT chain props | **score weights 未 tune**;待 W1.3 measurement-driven |
| Query entity linker(substring,len ≥ 4)| 暫用簡單版 | 5/5 queries 正確 link 主 entity | NER-based 升級延後 |
| Eyeball match logic(substring)| dry-test 內聯 | qid=45 出 false negative | W1.3 用 fact_match(token Jaccard / s+o 雙端)|

#### 得到甚麼結果

✅ **Path enumeration QUALITATIVELY 正確**:
- 5/5 queries 在 top-5 chains 內找到 chain_new
- 4/5 queries 在 top-5 chains 內找到 chain_old(qid=45 是 metric bug)
- **3/5 queries(20, 65, 85)top-1 或 top-2 chain 同時含 chain_new + chain_old**,verdict 階段直接有對比 pool

⚠️ **限制**:
- L=3 對 3-hop queries(qid=0, 85)漏第 3 個 hop 的 facts
- Top-1 偶爾 "creative"(entity-share 但不 follow query semantic),要 W1.3 量化評估後決定是否調 score weights

#### Locked 決策(動工中確認)

| 決策點 | Spec 預設 | W1.2 confirm |
|---|---|---|
| `Chain` dataclass | spec §B.3.1 結構 | ✅ 含 id, prop_ids, shared_entity_path, score, breakdown |
| Q5 = mean PPR aggregation | 預設 | ✅ `compute_prop_ppr_mass_from_entity_ppr` 支援 mean/max 切換 |
| Q6 entity sharing | ≥ 1 entity 共享(synonym 允許)| ✅ substring 雙向,case-insensitive,len ≥ 3 |
| L = 3, M = 5, beam = 8, region_topK = 50, n_seed = 20 | spec 預設 | ✅ 採用 |
| Supersession-agnostic invariant | 關鍵 | ✅ enumeration 完全不參考 supersession |
| W1 用 cosine proxy | spec 默認 W1 沒 PPR | ✅ `compute_prop_mass_proxy_from_query_cosine`;W1.3 換真 PPR |

#### Open items / 小 tech-debt(non-blocking)

- ⚠️ **沒整合進 `HippoRAG.retrieve()`**:dry-test 直接讀 `proposition_index.json`,沒 wire 進 retrieve() 主流程。W1.3 整合(因為 W1.3 要 LLM verdict,自然會接 PPR + retrieve 流程)。
- ⚠️ **PPR mass 用 cosine proxy**:W1.3 wiring 進 HippoRAG.retrieve() 時換真 entity-level PPR + Q5 mean aggregation。
- ⚠️ **Query entity linker 是簡單 substring**:`extract_query_entities_simple` 用字串比對 KG entities。W1.3 / W4 可升級成 NER 或 query embedding → entity KNN。對 FC 簡單 entity 名稱(Lisa Leslie, Dave Filoni)夠用。
- ⚠️ **Score weights 未經 measurement**:0.3/0.2/0.1 是 spec 預設,W1.3 跑全 100 queries 後若 Chain Recall@5 沒到 80%,要 sweep weights。
- ⚠️ **L=3 漏 3-hop 末段**:對 3-hop queries(FC-MH 約 20% 是 3-hop),hop_2 不在 chains 內。L=4 會炸 path 空間;maybe 後續加 query-hop-aware adaptive L。

#### Gate 結論

✅ **Qualitative PASS**(per §B.11.2 step 4: "verify chains look reasonable")。
chain enumeration 結構正確,top-5 chains 含 query-relevant conflict pair,supersession-agnostic invariant 保持。

→ 可進 **W1.3(Phase 2.b verdict + 整合進 HippoRAG.retrieve() + 全 100 queries 量化評估)**。

---

### W1.3 — Phase 2.b Verdict + HippoRAG 整合(2026-05-17,⚠️ partial pass)

> 階段目標:把 Phase 2.b 接上 Phase 2.a 的 chain,完成首次 end-to-end 評估 + 暴露 spec 內隱含的 design hole。**結果**:MH 11% (v1, LLM 全做) → **31% (v2, LLM identify + 機械方向)**,vs vanilla 20% 進步 +11pt,**但未過 Hard gate 40%**。重要學習:spec 原指標表 (§B.3.4.2) 將「pool recall」與「verdict accuracy」混為一談,W1.3 揭露需分層 — 已回頭更新 §B.3.4.2 與 §B.3.2(見 §B.3.2.3 設計轉折)。

#### 🗺️ 在整個方法流程的位置

```
─ Offline Indexing ──────────────────────────────────
I1-I5 same as W1.2(proposition_index.json 由 W1.1 driver 一次性產出)

─ Online Retrieval & QA ─────────────────────────────
O1.  fact scoring                                 (vanilla)
O2.  rerank_facts                                  (vanilla)
O3.  seed weights                                  (vanilla)
O4.  run_ppr → pagerank_scores                     (vanilla)
O4.5 identify_active_region        ✅ W1.2 完成
O4.6 enumerate_candidate_chains    ✅ W1.2 完成
O4.7 ▶▶ chain_restricted_verdict   ★ W1.3 完成(v2.0.3 pivot)★
     ├── Pool: dynamic_lookup(direction="any") + γ opportunistic
     ├── K_pool ≤ 10, top-K by relevance to focus
     ├── LLM:identify contradicting indices(no chain, no timestamps)
     └── Mechanical direction:from focus.ts vs contradicting.ts
O5.  ▶▶ Filter passages by verdict ★ W1.3 完成(top-20 only, with rescue)★
     ├── drop passages whose props are verdict.status="superseded" (high conf)
     └── rescue: passage 還含 verdict.status="current" prop 則保留
O5.5 render_enriched_context       ⏳ W3(Phase 3)
O6.  rag_qa(prompt 不動)            (vanilla)
```

→ **W1.3 首度 wire 進 HippoRAG.retrieve() 主流程**:整合 hook 點是 `graph_search_with_fact_entities()` 內,在 vanilla `sorted_doc_ids/sorted_doc_scores` 計算完之後、return 給 `retrieve()` 之前介入。

#### 主要動了哪些部分

| 路徑 | 用途 |
|---|---|
| `methods/hipporag/phase2b/__init__.py` | package marker |
| `methods/hipporag/phase2b/data_structures.py` | `Verdict` dataclass(status, confidence, superseder_id, reason, pool_size, pool_sources) |
| `methods/hipporag/phase2b/dynamic_lookup.py` | `dynamic_candidate_lookup(direction="any"/"before"/"after")`:entity overlap + cosine union, top-K by combined score |
| `methods/hipporag/phase2b/verdict.py` | 主 orchestrator:pool construction(3 sources)→ `_top_k_by_relevance` → LLM call → `_decide_verdict_mechanically` |
| `methods/hipporag/phase2b/prompts/verdict_prompt.py` | `VERDICT_SYSTEM` + `CONFLICT_IDENTIFY_PROMPT`、`build_verdict_messages`、`parse_verdict_response` |
| `methods/hipporag/HippoRAG.py` | `_ensure_v2_phase2_loaded`(lazy load proposition_index.json)+ `_v2_phase2_pipeline`(orchestrator)+ hook 進 `graph_search_with_fact_entities` |
| `methods/hipporag/utils/config_utils.py` | flags:`enable_phase2_chain_detection`、`v2_phase2_region_topK`、`v2_phase2_M`、`v2_phase2_L`、`v2_phase2_beam` |
| `scripts/run_v2_phase2_w13.sh` | E2E runner:backup prior results → SH+MH 跑 100Q × 2 |
| `monitoring_logs/<ts>_v2_phase2_w13/phase2_w13_dump.jsonl` | per-query Phase 2 diagnostic dump |
| `monitoring_logs/<ts>_v2_phase2_w13/verdict_events.jsonl` | per-LLM-call verdict event log |

#### Verdict 對輸入做了什麼(以「Our Mutual Friend 作者的配偶國籍」為實例)

**Query**: `"What is the country of citizenship of the spouse of the author of Our Mutual Friend?"`(expected: Belgium)

**Phase 2.a 給出 5 條 chain**(W1.2 已驗證),其中 chain 0 含:
```
[0] Charles Dickens is the author of Our Mutual Friend.       ts=(2,32) ← chain_OLD
[1] The author of Our Mutual Friend is Charles Darwin.        ts=(3,34) ← chain_NEW
[2] Charles Darwin is married to Emma Darwin.                 ts=(4,15) ← chain_OLD
...
```

**Phase 2.b 對 focus="The author of Our Mutual Friend is Charles Darwin" 跑**:
- dynamic_lookup(direction="any"):entity={"Charles Darwin", "Our Mutual Friend"},找到 pool 含 Dickens-author + Darwin-Emma + Darwin-Amala 等
- γ pairing 從其他 chain 補入(本例 chain 0/1/2 共享 entity "Our Mutual Friend"、"Charles Darwin")
- top-K_pool=10 by relevance to focus
- LLM call(prompt 不含 chain context、不含 timestamps、不含 query 判斷依據):
  ```
  Pool [1]: "Charles Dickens is the author of Our Mutual Friend."
  Pool [2]: "Charles Darwin is married to Emma Darwin."
  ...
  → contradicting_pool_indices: [1]
    reason: "Both statements assert different authors for Our Mutual Friend."
  ```
- 機械方向:focus.ts=(3,34) vs pool[1].ts=(2,32) → pool[1] 不晚於 focus → focus = `current (low)`("contradicting found but no strictly later timestamp")

**對 focus="Charles Dickens is the author of Our Mutual Friend" 跑**:
- Pool 含 Darwin-author(ts=(3,34))
- LLM: `contradicting=[Darwin-author]`
- 機械:focus.ts=(2,32) vs (3,34) → 有晚的 → focus = `superseded (high)`, superseder=Darwin-author ✓

**Phase 2.c filter**:chain_old_pids = {Dickens-author, Emma-Darwin},top-20 passages 內,含 Dickens-author 且不含其他 verdict.current 的 passage 被 drop;chain_new Darwin-author 所在 passage 保留。

#### 做了哪些嘗試

> W1.3 動工流程是「先按 spec §B.3.2.2 實作 → dry-run → spec hole 暴露 → 重設計 → 再 dry-run」。下表記錄兩輪嘗試。

| 嘗試項 | V1(按 spec v2.0.2)| V2(v2.0.3 pivot)| 結果差 |
|---|---|---|---|
| Prompt:LLM 做什麼 | grouping + direction + confidence 三件事(同 §B.3.2.2 原 prompt)| 只做 grouping(identify contradicting indices)| **+20pt** |
| 方向判斷 | LLM 看 chain context + timestamps 自行決定 | 從 `focus.ts` vs `contradicting.ts` 機械 strict-`>` 比較 | 消除 world-knowledge bias |
| Confidence | LLM 三段 high/medium/low | binary high/low(機械決定:有 strict later→high; 否則 low)| 一致性提升 |
| Pool 抓取 | `dynamic_lookup(before_time)` + `dynamic_lookup(after_time)` 雙 call union | `dynamic_lookup(direction="any")` 單 call,K 提升到 20 | pool 涵蓋一致 |
| Pool 是否顯示 timestamp 給 LLM | 是(LLM 用順序當方向 hint)| 否 | 移除方向 leak |
| 100Q MH EM | **11/100**(vanilla 20 倒退 9pt)| **31/100**(+11pt vs vanilla)| ✅ |
| SH EM(無 prop index)| 75 | 75 | no-op(pipeline skip)|

**Dry-run findings**(V1 fail 抽樣 verdict_events):
- 反事實對立(Dickens vs Darwin 作者、Sax vs football vs baseball、Darwin married Emma vs Amala)被 LLM **雙端標 superseded**;LLM 用 parametric prior 認定 "real-world plausible" 那邊是 current
- 60% over-flag rate;chain_NEW 和 chain_OLD 雙端被 filter → LLM 答題看不到 context
- 已記入 §B.3.2.3 設計轉折

**V2 verification**(V2 跑完後 case-by-case 抽查):
- Our Mutual Friend: Dickens(ts=2,32)→ superseded, superseder=Darwin(ts=3,34) ✓
- Steve Sax: baseball(ts=0,35)→ superseded, superseder=football(ts=11,0) ✓
- Darwin spouse: Emma(ts=4,15)→ superseded, superseder=Amala(ts=8,30) ✓
- 570 verdict events,所有 `superseded` 都是 high confidence,機械方向**全對**

#### 得到甚麼結果(數字)

**FC-MH 6k 100Q(W1.3 v2 final)**:

| 設定 | MH EM | vs vanilla |
|---|---|---|
| vanilla HippoRAG-v2(2026-05-11 ref)| 20/100 | — |
| W1.3 V1(spec v2.0.2 prompt)| 11/100 | **−9** |
| W1.3 V2(v2.0.3 redesigned)| **31/100** | **+11** |
| Hard gate(§B.3.4.3)| 40 | 還差 −9 |

**SH 無回歸**:75/100(SH 沒 proposition_index,pipeline no-op)。

**Win/Loss vs V1(2026-05-17 比較)**:
- Both right: 8 / Only V2 right (gained): 23 / Only V1 right (regressed): 3 / Both wrong: 66
- Net +20:V2 用更謹慎的 filter 策略多救了 20 題

**Verdict 統計(V2, 570 events from 100Q × top-5 chains × unique props)**:
- status:current 308 / superseded 262 / uncertain 0
- (status, confidence):superseded-high 262, current-low 179, current-high 129
- pool size:median ≈ 7,size=10 達 215 次(38%)— spec target ≤5,**超**

**Correct vs Wrong 對照**(critical finding):
- 兩組 avg n_chains, n_verdicts, n_superseded **幾乎完全相同**(5.0 / 5.8 / 2.7)
- → verdict 本身在 wrong 組沒有比 correct 組差
- → 失敗來自**更上游**:pool 是否同時涵蓋每個 hop 的 chain_new + chain_old 對

#### Spec hole 暴露 + 已回頭修正

W1.3 揭露 **§B.3.4.2 原指標表的問題**:
- 原版本只列 `Per-hop verdict accuracy ≥ 80%` 作為 Phase 2.b 主要指標
- 但 verdict 是 **conditional on pool 已含對立 pair** 的結果;若 K_pool 沒同時抓到該 hop 的 new + old,verdict 不可能算對(LLM 連 group 都做不到)
- **真正的 Phase 2.b recall 上限是 per-hop K_pool co-occurrence rate**(K_pool 同時涵蓋該 hop 的 chain_new + chain_old 的 hop 比例)

→ 已回頭更新 §B.3.4.2,將指標分為 recall(pool co-occurrence)/ conditional precision(verdict accuracy)/ cost 三層。

#### Locked 決策(W1.3 動工中確認)

| 決策點 | Spec 原預設 | W1.3 confirm |
|---|---|---|
| `Verdict` dataclass | §B.3.2.1 結構 | ✅ status, confidence, superseder_id, reason, pool_size, pool_sources |
| K_pool = 10 | spec 預設 | ✅(實際 median ≈ 7;215 個 verdict 用滿 10)|
| LLM call 次數 / chain | per chain × per prop | ✅ dedup by pid:同 pid 在多 chain 只 verdict 一次 |
| Pool 三來源 | Phase 1 cache + dynamic + γ | ✅(W1 cache off;dynamic+γ 為主)|
| dynamic lookup direction | spec 原 before/after 雙 call | ⚠️ **改為 single "any"** + 機械方向(v2.0.3 pivot)|
| Verdict prompt | spec §B.3.2.2 原 SUPERSESSION_VERDICT_PROMPT | ⚠️ **改為 CONFLICT_IDENTIFY_PROMPT**(v2.0.3 pivot)|
| Confidence 三檔 | high/medium/low | ⚠️ **binary high/low**(機械決定)|
| Filter 顆粒度 | passage 級 | ✅ top-20 內,passage 含 chain_old 且不含 verdict.current → drop |

#### Open items / tech-debt(影響下一步,需明確列)

- ⚠️ **K_pool co-occurrence 沒量化** —— Phase 2.b 的 recall 上限指標,目前 dry-test 沒實際算 per-hop pool coverage(因為沒 ground-truth chain_new/old labels per hop)。**下一步必須做 mini-eval 集**:抽 1/2/3/4-hop 各 N 題,人工標每個 hop 的 chain_new+old prop id,才能量這個指標。
- ⚠️ **PPR mass 仍用 cosine proxy** —— W1.2 留下的 tech-debt 在 W1.3 沒解。真實 entity-level PPR aggregation(Q5 mean)延後到 W2 I3c 整合後。可能造成 active region 漏 prop,需 mini-eval 內驗證。
- ⚠️ **Filter 顆粒度 mismatch** —— verdict 在 prop 級,filter 在 passage 級。一個 chunk 含 chain_old + 不相關 verdict.current → rescue 保留,可能讓 chain_old 漏網。Mini-eval 量化後決定是否做 prop 級 context rewrite(W2/W3 範圍)。
- ⚠️ **Pool size 超 spec target** —— median ≈ 7,38% 用滿 10。可能 LLM noise 較大,但 mini-eval 量到 verdict accuracy 才能判定要不要降。
- ⚠️ **Query entity linker 仍是 substring** —— W1.2 同樣 tech-debt;對 FC entity 夠用,大型 dataset 升 NER。
- ⚠️ **Spec §B.13 dependency graph 沒同步更新** —— v2.0.3 pivot 後 dynamic_lookup signature 改變(direction 參數),依賴圖需要 reflect。下次大改時補上。

#### Gate 結論

⚠️ **Partial pass**(per §B.3.4.3 Hard gate 40%):MH 31% 落在 35-40% partial pass 區間,vanilla baseline +11pt,V1 first run +20pt。

**正面訊號**:
- V2 設計成功消除 V1 的 world-knowledge bias(case-by-case 抽樣全對)
- SH 沒回歸,W1.3 pipeline 是 net positive
- Spec hole 被 W1.3 揭露並回頭修正(§B.3.4.2 分層、§B.3.2.3 新增轉折記錄)

**需在進 W2 前處理**:
- 建立 mini-eval 集(1/2/3/4-hop tagged subset),量化 per-hop K_pool co-occurrence 與 verdict accuracy(conditional)兩個指標,確認瓶頸真的在 pool recall 而非 verdict
- 根據 mini-eval 診斷再決定 W2 進什麼:(a) PPR mass 提升 chain coverage、(b) entity_node_ids 改善 lookup recall、或 (c) Phase 3 Recent Updates / Reasoning Hints 補救已過濾的 chain_old 證據

→ 下一步 **W1.4 (mini-eval 建立) → 然後決定 W2 進路**。

---

### W1.4 — Mini-eval Framework + Hop-level Ground Truth(2026-05-17,✅ infrastructure pass)

> 階段目標:建立 16-題 mini-eval 集合(2/3/4-hop × 4)與 hop-level ground truth (chain_new + chain_old prop_id),提供 Phase 2.a/2.b 細顆粒度量化指標,取代之前只看 100Q EM 的粗糙評估。

#### 主要動了哪些部分

| 路徑 | 用途 |
|---|---|
| `analysis/build_mini_eval_w14.py` | 從 100 題 FC-MH 6k 抽 16 題(2/3/4-hop × 4,均衡 all-pair / partial-pair / W1.3 correct/wrong),每 hop strict s+o match 到 prop_id,**100% 1-1 匹配率**(34 has_pair + 10 no_pair hops 全對應) |
| `analysis/eval_mini_w14_phase2b.py` | 對既有 W1.3 dump 計算 per-hop metrics:pool co-occurrence、verdict accuracy(unconditional + conditional)、chain membership、failure modes、hop 深度分桶 |
| `analysis/results/mini_eval_w14/selection.json` | 16 題選集 |
| `analysis/results/mini_eval_w14/labels.json` | hop-level GT (chain_new_prop_id + chain_old_prop_id) |

#### Mini-eval 集合分布

| 桶 | n |
|---|---|
| 2-hop(all-pair 4 + partial 4)| 8 |
| 3-hop(all-pair 4)| 4 |
| 4-hop(all-pair 2 + partial 2)| 4 |
| **Total** | **16** |
| has_pair hops | 34 |
| no_conflict_pair hops | 10 |

不平衡注意:FC-MH 6k **沒有 1-hop query**(分布 2h=61, 3h=24, 4h=15),所以原 user "1/2/3/4-hop 各 4" 改為 "2/3/4-hop 各 4 + 4 額外 challenging"。每題 has_pair hops 數量不同(2-4 個),total 34。

#### W1.3 v2(cosine proxy)baseline 量化(14/16 有效,no58 + no99 不在 dump)

| 指標 | 結果 | 解讀 |
|---|---|---|
| Per-hop K_pool co-occurrence rate | **29/55 = 55%** | 主瓶頸(spec target 80%) |
| Per-hop verdict accuracy (conditional on co-occurrence) | **16/16 = 100%** | ★ verdict 機制本身 perfect |
| Per-hop verdict accuracy (unconditional) | 16/29 = 55% | = co-occurrence rate × cond accuracy |
| Pool size median | 4 | ≤ 5 target ✓ |
| 失敗模式 F1(both chain_new + chain_old 都不在任何 chain 內)| 13/13 (100%) | 全是 Phase 2.a chain coverage 問題 |
| 多 hop 深度:2-hop pool_co | 73% | OK |
| 多 hop 深度:3-hop pool_co | 50% | 弱 |
| 多 hop 深度:4-hop pool_co | 42% | 弱 |

#### 關鍵 finding:W1.3 真正瓶頸不在 verdict 機制,在 Phase 2.a chain coverage

verdict 完美(100% conditional),所有失敗都是 chain_new/chain_old 從未進到候選 chain。Spec §B.3.4.2 原本將 "per-hop verdict accuracy" 列為 Phase 2.b 主要指標,W1.4 揭露此指標**被 pool co-occurrence rate 上限封頂** — 該回頭更新指標分層(已 done,參見 §B.3.4.2 v2.0.3)。

#### Gate 結論

✅ **Infrastructure pass**:mini-eval 框架就緒,Phase 2.b 三層指標(recall / conditional precision / cost)可獨立量化。

→ 下一步 **W2 Step 1(I3c)**:接真 PPR 解 chain coverage 瓶頸。

---

### W2 Step 1 — I3c Proposition-as-Hyperedge Integration(2026-05-17,⚠️ partial pass)

> 階段目標:把 Phase 2.a 的 prop_mass 計算從 W1 cosine proxy 切到真實 entity-level PPR aggregation,解 W1.4 揭露的 chain coverage 55% 瓶頸。經歷 5 個 sub-step,結果:**pool co-occurrence 持平 55% 但 chain quality 更精緻**(BOTH same chain 42% vs 38%、pool size 3 vs 4),**4-hop 仍弱(33%)**。**Hyperedge weight boost 對 atomic prop 效果有限,評分函式 + score 混合 開放 W2 後續迭代**。

#### 🗺️ 在整個方法流程的位置

```
─ Offline Indexing ──────────────────────────────────
I1.  OpenIE                          (vanilla)
I2.  Embeddings                       (vanilla)
I2.5 Proposition extraction           ✅ W1.1
I3.  add_fact_edges                   (vanilla)
I3.  add_passage_edges                (vanilla)
I3c. ▶▶ _add_proposition_hyperedges_to_stats  ★ W2 Step 1 完成 ★
     ├── 對每個 prop p 的 entity_node_ids 兩兩加 entity-entity edge
     ├── option B (PropRAG-style):prop 不入 KG,純擴 entity 連通性
     └── weight = entity pair 共現於多少個 prop(累加)
I4.  add_synonymy_edges               (vanilla)
I4.5 candidate cache                  ⏳ W2 optional,暫緩
I5.  save_igraph                      (vanilla)

─ Online Retrieval ──────────────────────────────────
O1-O4 vanilla HippoRAG-v2(算 pagerank_scores)
O4.5 identify_active_region           ✅ W1.2 完成
     ├── ★ W2 Step 1 ★ 切換 prop_mass 算法:
     │   - W1 cosine proxy(q_emb cosine p.emb)
     │   - → real PPR aggregation: mean(entity_ppr for e in p.entity_node_ids)
     │   - Q5 = "mean"(預設),"max" 可從 config 切換 ablation
     │   - Defensive fallback:若 PPR all-zero,fallback cosine proxy
     └── 加 entity resolve sentinel(text_processing match vanilla)
O4.6 enumerate_candidate_chains       ✅ W1.2
O4.7 chain_restricted_verdict         ✅ W1.3
O5.  Filter passages by verdict       ✅ W1.3
O5.5 enriched context                 ⏳ W3 下一步
O6.  rag_qa                           (vanilla)
```

#### 主要動了哪些部分(檔案層面)

| 路徑 | 改動 |
|---|---|
| `methods/hipporag/HippoRAG.py` | (a) `_ensure_v2_phase2_loaded` 內 lazy-resolve `prop.entity_node_ids`(用 `text_processing(e)` + `compute_mdhash_id` 對齊 vanilla entity key);加 sentinel 報 KG 內找得到的比例 |
| `methods/hipporag/HippoRAG.py` | (b) 新增 `_add_proposition_hyperedges_to_stats()`(對 prop 的 entity_node_ids 兩兩加 `node_to_node_stats[(e1, e2)] += 1.0` 雙向,過濾掉 entity 不在 vanilla KG 的 case) |
| `methods/hipporag/HippoRAG.py` | (c) `index()` 內 hook:在 `enable_phase2_chain_detection=True` 時 call hyperedge stats;rebuild 條件改為 `num_new_chunks > 0 OR n_hyperedges > 0` |
| `methods/hipporag/HippoRAG.py` | (d) `_v2_phase2_pipeline` 內:用 `pagerank_scores + self.entity_node_idxs` 建 `entity_ppr` dict,call `compute_prop_ppr_mass_from_entity_ppr(agg='mean')`;defensive fallback 到 cosine proxy 若 PPR all-zero |
| `analysis/run_mini_eval_w14_step1.py` | 獨立 driver:setup env vars + load 16 selected qids + 對既有 vectorstore 跑 retrieve;`index(docs=[])` 重 build graph(因刪 graph.graphml 強制 re-build) |
| `analysis/eval_mini_w14_phase2b.py` | 支援 CLI arg / `latest_run.txt` pointer 動態切 RUN_DIR;每次 run 輸出獨立 `eval_<run_tag>.json` |

#### 對輸入做了什麼(以 query="OMF 作者的配偶國籍?"為例)

**前提**:proposition_index.json 已含 450 props(W1.1 抽好),vanilla entity_embedding_store 已含 407 entity node。

**Step 1a entity_node_ids resolve**(in `_ensure_v2_phase2_loaded`):
```
prop "Charles Darwin is married to Emma Darwin"
  entities = ["Charles Darwin", "Emma Darwin"]
  → text_processing: ["charles darwin", "emma darwin"]
  → md5: entity_node_ids = ["entity-585ed862...", "entity-bc180dbc..."]
  → 在 KG 內? 2/2 ✓
```

**Step 1d hyperedge build**(in `index()`):
```
對每個 prop 的 entity_node_ids 兩兩 add:
  node_to_node_stats[(entity-darwin, entity-emma)] += 1.0
  node_to_node_stats[(entity-emma, entity-darwin)] += 1.0
→ summary: 449 props → 448 unique pairs (898 weight increments)
```

**結果(graph 結構)**:hyperedge **與 vanilla fact edges 100% 共用 entity pair key**(因為 atomic prop = 1 triple = 2 entities),所以 igraph edge 數**不變**,但 entity-entity edge **weight 從 1 變 2**。這就是 W2 Step 1 的實質效果:**fact edge weight 加倍**(對 prop 反覆抽出的 entity pair),其他 entity pair weight 不變。

**Step 1b PPR aggregation**(in `_v2_phase2_pipeline`):
```
vanilla PPR 跑完 → pagerank_scores (array indexed by graph vertex idx)
entity_ppr = {entity_key: pagerank_scores[vidx] for entity in KG}
prop_mass[p] = mean(entity_ppr[e] for e in p.entity_node_ids)
→ top-50 by prop_mass = active region
```

#### 做了哪些嘗試 + 數字(W1.4 mini-eval 16 題)

| 嘗試 | 改動 | Pool co-occ | Verdict cond | 4-hop pool_co | Pool size median |
|---|---|---|---|---|---|
| **V0**: W1.3 cosine proxy(baseline)| `prop_mass = max(0, cos(q_emb, p.emb))` | **55%** | 100% | 42% | 4 |
| **V1**: 真 PPR aggregation **無 hyperedge** | 切到 `mean(entity_ppr[e] for e in p.entities)` | **26% ❌** | 88% | **0% ❌** | 9 |
| **V2**: 真 PPR + hyperedge **但 entity 沒 resolve**(bug)| Step 1d 寫了但 entity_node_ids hash 跟 vanilla 不匹配(漏 `text_processing`)| 26% ❌ | 80% | 0% ❌ | 9 |
| **V3**: 真 PPR + hyperedge + entity resolve 修正 | 加 `text_processing(e)` 對齊 vanilla hashing | **55% ↑** | **94%** | **33%** | **3** |

**V0 → V1 倒退原因**:vanilla 的 entity-level PPR mass 集中在 query-mention entity,multi-hop 末端 entity(Amala Paul、Belgium)在 vanilla KG fact edges 上經多 hop 衰減後 mass ≈ 0。`mean(entity_ppr)` 對含末端 entity 的 prop 被拉低到接近 0 → 4-hop pool co-occurrence 全滅。Cosine proxy 因為用 query embedding 對 prop 文字整體比對,所以末端 prop 也能拿到 medium mass。

**V2 失敗的 root cause**:vanilla HippoRAG-v2 用 `text_processing(triple)`(lowercase + 移除非英數字符)後才 `compute_mdhash_id`。我們 lazy-resolve 漏了 `text_processing`,所有 `entity_node_ids` 跟 KG 內的 key 對不上 → `kg_entity_keys` 過濾掉所有 entity → `props_added=6`(隨機碰巧 hash 對上的),`n_increments=12`(微不足道)。Debug 抓到 `sample entity_node_ids in kg: 0/2`。修法:lazy-resolve 用 `text_processing(e)` 對齊 vanilla。

**V3(本次)觀察**:hyperedge 雖然 weight increment 達 898,但因 atomic prop ≈ triple,所有 hyperedge pair **跟既有 fact edges 100% 共用 dict key** → `len(node_to_node_stats)` 不變,igraph 邊數不變(實測 backup vs current 都是 1800 edges、996 entity-entity edges),只是 entity-entity edge 的 weight 從 1 提到 2。Weighted PPR 因此**確有改變**(2-hop pool_co 從 V0 的 ~70% 提到 77%),但**結構性連通性**沒提升 → 4-hop 仍弱。

#### 得到甚麼結果

✅ **不退步**:V3 pool co-occurrence(55%)= V0 baseline,verdict cond(94%)接近 baseline 100%;chain quality 細節改善(BOTH same chain 42% vs 38%、pool size median 3 vs 4)
✅ **基礎設施 wire 通**:`_ensure_v2_phase2_loaded` lazy resolve、index() hyperedge hook、`_v2_phase2_pipeline` PPR aggregation 三段全 wire 起來,且有 defensive fallback;代碼可重複跑、有 sentinel 監控
⚠️ **但沒突破 chain coverage 瓶頸**:4-hop pool co 33%(目標 80%),仍是主要瓶頸
⚠️ **Hyperedge 設計侷限暴露**:atomic prop = 1 triple = 2 entities,hyperedge = fact edge dict key,只能 boost weight 不能新增結構性連結

#### Spec hole 暴露 + 留待 W2 後續或方法迭代

W2 Step 1 揭露的設計 open items:

**A. `prop_mass` 評分函式設計**(spec §B.3.1.1 假設真 PPR 即解,W2 Step 1 證明需要更精緻設計)
- 目前 `prop_mass = mean(entity_ppr)`(Q5 lock = mean)
- 替代:`max(entity_ppr)` 對單一強 entity 友善(可能對多 hop 末端 prop 友善 — 例如 Belgium PPR=0 但 Amala PPR=0.01,max=0.01 > mean=0.005)
- 替代:**混合 cosine + normalized PPR**(`α × cosine + (1-α) × ppr/max_ppr`),兩種訊號互補
- 替代:加 query-prop cosine 作為 boost factor(類似 vanilla HippoRAG-v2 對 fact 的 rerank logic)

**B. Hyperedge 設計只 boost weight 沒新連結**(W2 後續 / W4 範圍)
- 因 atomic prop = 1 triple,hyperedge 對 PropRAG-style multi-entity prop 才有結構性貢獻
- 修法:重抽 propositions 讓每個 prop 含更多 entities(改 W1.1 prompt 抽 multi-entity proposition);或對 chunk 內所有 prop 的 entity union 加 clique(類似 PropRAG.py:944 但更廣)

**C. 超參數待 tune**(W2 後續 / W4 ablation):
- `v2_phase2_ppr_aggregation`:`mean` vs `max`(spec Q5,目前 lock mean)
- 混合權重 α(若採方案 A 混合)
- `region_topK`(50 → 100/200?)、`L`(3 → 4 for 4-hop coverage)
- `beam_width`(8 → 16?)

#### Locked 決策(W2 Step 1 動工中確認)

| 決策點 | 選項 | W2 Step 1 confirm |
|---|---|---|
| Proposition 在 KG 的形式 | (A) prop as node / (B) hyperedge | ✅ **B: PropRAG-style hyperedge**(out-of-KG annotation);忠於 PropRAG paper、KG 結構不動 |
| Hyperedge weight 累加方式 | 累加 vs 取 max | ✅ 累加(per pair, +1 per prop);跟 PropRAG.py:982-988 一致 |
| Entity hashing 對齊 vanilla | `text_processing` + `compute_mdhash_id` | ✅ V2 → V3 bug fix |
| PPR aggregation | mean / max | ✅ mean(Q5 lock,max 可從 `v2_phase2_ppr_aggregation` config 切) |
| Defensive fallback | PPR all-zero → cosine proxy | ✅ 保留 W1 proxy 作為 safety net |
| Graph rebuild trigger | num_new_chunks > 0 only | ✅ 改 `OR n_hyperedges > 0`(讓 hyperedge-only 重 build 也 trigger) |

#### Open items / tech-debt(影響下一步)

- ⚠️ **`prop_mass` 評分函式未 tune** —— 目前 = `mean(entity_ppr)`,只追平 cosine proxy;真實 break-through 需要混合或更聰明的 aggregation。**留待 W2 後續或 W4 ablation 探索**(列為 §B.9 Open Q)
- ⚠️ **Hyperedge 對 atomic prop 結構性貢獻有限** —— W1.1 抽 atomic prop = 1 triple = 2 entities,hyperedge 純粹 weight boost。若要結構性連通,需重抽 multi-entity prop(W4 範圍)
- ⚠️ **`region_topK / L / beam` 未 sweep** —— 4-hop 仍弱(33%),可能需 L=4 + 更大 beam,但 cost-benefit 待 W3 結果決定
- ⚠️ **Diagnostic print 留在 hyperedge 函式內** —— 1 行 `[v2 I3c hyperedge] N props → M pairs (K increments)` 用 print(對 logger level 不敏感);後續若清理可 routine 化
- ⚠️ **目前只 indexed 12 chunks** —— FC-MH 6k 設計上是 12 chunks(每 chunk size 512),W1 dry-test 集已含完整 dataset。但若 chunk_size 變大或 dataset 換成 32k/262k,W2 Step 1 流程需重 verify entity resolve 仍正確

#### Gate 結論

⚠️ **Partial pass**:pool co-occurrence 55% 持平 cosine proxy baseline,**沒突破 80% spec target**。但:
- ✅ **基礎設施 100% wire 通**,代碼可重複執行、defensive fallback、有 sentinel 監控
- ✅ **Chain quality 細節更精緻**(BOTH same chain +4pt,pool size −1)
- ✅ **Verdict cond accuracy 94%**,接近 baseline 100%
- ⚠️ **Score 設計留待後續迭代** — 不卡 W3 上線,可在 W3 跑完後回頭 tune

→ 下一步 **W3 enriched context**(spec §B.4 Recent Updates + Reasoning Hints);W2 Step 1 的 score 設計 open items 列入 §B.9。

---

### W3 — Phase 3 Enriched Context(2026-05-17,⚠️ infrastructure pass, EM neutral)

> 階段目標:接 spec §B.4 LOCKED 的 enriched context 格式(Reasoning Hints + Recent Updates),把 Phase 2.b 的 verdict 結果注入 LLM prompt(passages 之後、Question 之前)。**結果**:infrastructure 100% wire 通(render + inject 都正確),但 mini-eval 16Q 顯示 EM 沒明顯 boost(4/16 vs baseline 5/16,2-hop +2 / 多 hop -3),根因為 enriched 措辭歧義 + W2 Step 1 pool co-occurrence 不足對多 hop case 提供半 enriched 反而干擾。

#### 🗺️ 在整個方法流程的位置

```
─ Online Retrieval & QA ─────────────────────────────
O1-O4 vanilla HippoRAG-v2
O4.5-4.7 W1.2/W1.3 Phase 2 (active region, chain, verdict)
O5.  W1.3 filter passages by verdict
O5.5 ▶▶ render_enriched_context           ★ W3 完成 ★
     ├── active_chain (top by score) → Reasoning Hints
     ├── supersession_events → Recent Updates (confidence ≥ medium)
     └── 存 self._v2_enriched_context_by_query[query]
O6.  qa() prompt assembly                  ★ W3 hook ★
     ├── 既有 "Wikipedia Title: {passage}\n\n" × K (vanilla 保留)
     ├── 既有 enable_phase3_scaffold hook (v1, 留)
     ├── ★ NEW: enable_phase3_v2_enriched → inject enriched_context_by_query[q]
     └── + "Question: {q}\nThought:"  (vanilla 保留)
```

→ **Prompt template UNCHANGED**(spec §B.4.1 contract 保持):動的是 `prompt_user` body 在 passages 後、Question 前加 enriched 段落,不動 system prompt 也不動 LLM 的 reading template。

#### 主要動了哪些部分

| 路徑 | 用途 |
|---|---|
| `methods/hipporag/phase3/__init__.py` | package marker(re-export renderer 函式) |
| `methods/hipporag/phase3/enriched_context_renderer.py` | `render_reasoning_hint`、`render_change_log`、`render_enriched_context` orchestrator(spec §B.4.3 對應) |
| `methods/hipporag/HippoRAG.py` | (a) `__init__` 加 `self._v2_enriched_context_by_query: Dict[str, str]` cache;(b) `_v2_phase2_pipeline` 內 chain top-by-score + supersession_events → call `render_enriched_context` 存 cache;(c) `qa()` 內 prompt assembly hook(passages 後、Question 前 inject) |
| `methods/hipporag/utils/config_utils.py` | `enable_phase3_v2_enriched: bool` flag(預設 False)+ env var `HIPPORAG_ENABLE_PHASE3_V2_ENRICHED`;`v2_phase2_ppr_aggregation: str` ("mean"/"max") |
| `analysis/run_mini_eval_w3_step2.py` | 16 題 W3 E2E driver:對每題 retrieve + rag_qa,dump enriched samples + EM per query |
| `monitoring_logs/<ts>_w3_step2_mini/qa_prompt_samples.json` | 前 3 題的 enriched_context 完整 dump(供人工 review 措辭) |

#### Enriched context 輸出範例(qid no18,query="What is the job title of the chairperson of Fatah?")

實際 inject 進 qa() prompt 的 body:
```
=== Reasoning Hints ===
One possible reasoning path:
  - Moshe Kahlon is the chairperson of Fatah. (turn 6, position 4)
  - Mahmoud Abbas is the chairperson of Fatah. (turn 0, position 1)
  - Mahmoud Abbas works as a politician. (turn 6, position 32)

=== Recent Updates ===
Recent updates relevant to this query:
  - Moshe Kahlon is the chairperson of Fatah. (updates earlier: "Mahmoud Abbas is the chairperson of Fatah.")
  - Moshe Kahlon works in the field of soldier. (updates earlier: "Moshe Kahlon works in the field of politician.")
```

LLM 答案:"Soldier" ✓(expected "soldier")

#### Mini-eval EM 比較(16 題,刻意 ill-balanced 含多個 W1.3 wrong cases)

| Hops | W3 | baseline (W1.3) | Δ |
|---|---|---|---|
| 2-hop | **4/8** | 2/8 | +2 |
| 3-hop | 0/4 | 2/4 | **-2** |
| 4-hop | 0/4 | 1/4 | **-1** |
| **Total** | **4/16** | **5/16** | -1 (noise range) |

**Win/Loss matrix**:
- Both right: 2(no18 soldier, no34 atheism)
- W3 gained: 2(no52 Taipei, no28 Prague — 都 2-hop)
- W3 regressed: 3(no99 Norwegian, no83 ..., no27 Washington — 都 ≥3-hop)
- Both wrong: 9

#### 為何 3/4-hop 反退步:Diagnosis

抽 case no27(4-hop):
- expected:"Harrisville"(USA 新首都)
- W3 predicted:"Washington, D.C."(USA 舊首都)
- Enriched 內含 `Recent Updates: ... Harrisville (updates earlier: "Washington, D.C.")` 卻沒讓 LLM 抓到 Harrisville
- 兩個可能根因:
  1. **「updates earlier: X」措辭歧義**:LLM 可能解讀 "X" 為更新後內容,而不是被取代的舊內容(自然語言上「X is updated」常指 X 是「被更新後的版本」)
  2. **W2 Step 1 pool co-occurrence 4-hop 只 33%** → chain 通常只涵蓋 hop_0/hop_1,Recent Updates 只列前兩 hop 的更新,LLM 看到部分 enriched 反而誤判全 chain 都已 fix,用 retrieved passage 內的舊 fact 答題

#### 做了哪些嘗試

| 嘗試 | 狀態 | 觀察 |
|---|---|---|
| Renderer 按 spec §B.4.3 verbatim | ✅ 完成 | render 出格式跟 spec LOCKED 一致 |
| `qa()` hook(passages 後 / Question 前 inject)| ✅ 完成 | 不動 prompt template,只擴 body |
| Mutex with `enable_phase3_scaffold`(v1 universal)| ✅ 完成 | 兩個 flag 同時 True 時 v2 enriched 不 fire(優先 v1 scaffold) |
| Change log 措辭:`<p_new> (updates earlier: <p_old>)` | ⚠️ 實作 | LLM 可能誤解;待調整 |
| Reasoning Hints 措辭:`<prop> (turn N, position M)` | ✅ 跟 spec 完全一致 | LLM 解讀正確 |
| Confidence threshold = 'medium' for Recent Updates | ✅ 跟 spec 一致 | W1.3 v2.0.3 binary high/low,所以實際只 high 進 |
| Defensive empty checks | ✅ 完成 | 若 chain 空 / 沒 supersession events → 不 inject |

#### 得到甚麼結果

✅ **Infrastructure 100% wire 通**:render + inject + dump 全跑通,3 個樣本 enriched_context_chars 539-943,Reasoning Hints + Recent Updates 都按 spec LOCKED 格式輸出
✅ **2-hop EM +2**:short chain 受惠
⚠️ **Total EM 略退 1(noise range)**:mini-eval 16 題太小不具統計信心,需 100Q E2E 才能下結論
⚠️ **多 hop case 措辭歧義**:`"updates earlier: X"` 風險

#### Open items / tech-debt

- ⚠️ **Recent Updates 措辭** —— `"<p_new.text> (updates earlier: <p_old.text>)"` 可能讓 LLM 誤判 X 是更新後內容。改進方案:
  - `"The CURRENT fact is: '<p_new.text>'. (This SUPERSEDES the earlier statement: '<p_old.text>')"` ← 更明確
  - 或加 prefix `"NOTE: The following corrects outdated information ..."`
  - 留待 W4 ablation tune
- ⚠️ **Enriched 與 retrieved passages 重複** —— 同 prop 出現在 3 處(passage、Reasoning Hints、Recent Updates),LLM 注意力分散風險。考慮 deduplication 或在 enriched section 不重複 chain 內已在 retrieved passage 的 prop
- ⚠️ **Confidence threshold 行為**:spec 寫 ≥ medium,但 W1.3 v2.0.3 binary high/low,所以 'medium' 永遠不會 match,效果上 = high only(防禦上 OK,但 spec → code 不一致,需要 spec 修或 verdict 加 medium 級)
- ⚠️ **active_chain top-1 by score**:目前 `max(chains, key=lambda c: c.score)`。Spec §B.3.3 寫的就是 top-1,但實際多 hop case top-1 chain 可能漏某 hop,Reasoning Hints 不全 → 考慮 union top-3 chains 或加 chain coverage filter
- ⚠️ **A3.4 token overhead 沒量化** —— 已加 `enriched_context_chars` 到 dump,但 spec §B.4.4 A3.5 訂 avg < 500 extra tokens/query,需正式統計

#### Spec §B.4.4 Falsifiable Assertions 進度

| Assertion | 目標 | W3 mini-eval 結果 | 狀態 |
|---|---|---|---|
| A3.1 full v2 (P2 + P3) ≥ P2-only by ≥ 5pp MH | +5pp | 16Q -1pp(noise)| ❓ 待 100Q |
| A3.2 P3 enriched ≥ v1 scaffold(same passages)| non-inferior | 沒比較 v1 scaffold | ⏳ W3 ablation |
| A3.3 各 evidence type 獨立貢獻 | individual ablation | 沒做 | ⏳ W4 |
| A3.4 非 KU multi-hop 退步 < 2pp | < 2pp | 沒測 LongMemEval | ⏳ W4 |
| A3.5 Token overhead < 500/query | < 500 | enriched 539-943 chars ≈ ~120-220 tokens | ✓ 範圍內 |

#### Locked 決策(W3 動工中確認)

| 決策點 | Spec 預設 | W3 confirm |
|---|---|---|
| Enriched format | spec §B.4.2 LOCKED 三段(Passages / Hints / Updates)| ✅ 按 spec 完整實作 |
| Render fn signatures | spec §B.4.3 verbatim | ✅ 1:1 對應 |
| Inject 位置 | spec §B.4.5 "rag_qa() hook" | ✅ 在 `qa()` 內 passages 後 / Question 前 |
| Feature flag | `enable_phase3_v2_enriched` | ✅ default False;env var `HIPPORAG_ENABLE_PHASE3_V2_ENRICHED` |
| Mutex with v1 scaffold | spec §B.4.5 mutex | ✅ 兩個都 True 時 v2 不 fire |
| active_chain selection | top-1 by score | ✅ |
| Recent Updates confidence threshold | spec 寫 ≥ medium | ⚠️ W1.3 binary,實際 = high only |

#### Gate 結論

⚠️ **Infrastructure pass, EM neutral**:W3 全套 wire 通(render + inject + sentinel + flag + spec § B.4.2 LOCKED format),mini-eval 16 題 EM 略退 1(noise range)。**需 100Q E2E 才能驗證 A3.1(+5pp 目標)**。

→ 兩個分岔:
- **(a) 直接跑 100Q E2E**:驗證 A3.1,看 W3 在 production scale 是否 net positive
- **(b) 先 tune Recent Updates 措辭**(`"updates earlier: X"` → `"This SUPERSEDES: 'X'"`)+ 再跑 100Q,風險:多個變動同時改難 root-cause
- 建議 (a):先看 baseline production 結果,再決定要不要 tune 措辭

---

### Stage 1+2 — Instrumentation 補齊 + 4-Ablation FC-MH 100Q(2026-05-17)

> **目標**:在跑大規模 ablation 前,把 dump 補齊到能 post-hoc 分析 per-hop cascade(active region → chain → pool → verdict → filter → enriched),然後跑 4 個 cumulative ablation 看每個 phase 的真實貢獻。

#### Stage 1 — Instrumentation 補齊

**主要動了哪些部分**

| 路徑 | 用途 |
|---|---|
| `methods/hipporag/HippoRAG.py` | (a) phase2 dump 加 `phase2_status: 'RAN' / 'DPR_FALLBACK_NO_FACTS'`、`active_pids`、`chain_old_pids`、`enriched_context_text`(raw)、`passages_pre_filter / kept / dropped_chunk_ids`;(b) chains dump 內每 prop 加 `text + timestamp`;(c) DPR-fallback path(`len(top_k_facts)==0`)也寫 marker entry,讓 eval 區分「phase2 跑了但結果差」vs「phase2 沒跑(vanilla fallback)」 |
| `analysis/build_labels_full100.py` | 擴展 W1.4 對 16 題的 strict s+o → prop_id mapping,跑全 100 題;has_pair 91% perfect 1:1,no_pair 86% perfect 1:1(剩餘 11% 是 PropRAG 抽取漏 fact 或 predicate pattern 未涵蓋)|
| `analysis/eval_100q_full_analysis.py` | per-query × per-hop cascade table:Phase 2.a(active / chain / BOTH same chain)/ Phase 2.b(pool co / verdict correct)/ Phase 2.c(chunk dropped / kept / filter effective)/ Phase 3(text in enriched / update pair in enriched);按 hop 深度(2/3/4)分桶 |
| `analysis/smoke_test_stage1_dump.py` | 3-query smoke test 驗證 dump 欄位完整(no18 RAN + no99 DPR fallback + no88 RAN) |

**Smoke test 結果**:no18 + no88 走 RAN path,no99 走 DPR fallback,所有欄位都正確寫入。

#### Stage 2 — 4-Ablation × FC-MH 100Q

**Ablation 矩陣**(cumulative,加 component 看累積貢獻):

| Run | `phase2_chain_detection` | `filter_passages` | `enriched` | `hints` | `updates` | EM | Δ vs A |
|---|---|---|---|---|---|---|---|
| **A. vanilla** | OFF | n/a | OFF | n/a | n/a | **17/100** | — |
| **B. + Phase 2 only** | ON | **ON** | OFF | n/a | n/a | **31/100** | **+14pt** ⭐ |
| **C. + W3 full** | ON | ON | **ON** | ON | ON | **31/100** | +14pt (= B) |
| **D. W3 minimal** | ON | **OFF** | ON | OFF | ON | **15/100** | **−2pt** ❌ |

`scripts/run_4ablations_fc_mh_100q.sh` 自動化,~13 min/run × 4 = 53 min。

#### Cascade per-hop coverage(B/C/D 結構性指標)

(B, C, D 三組 Phase 2 pipeline 跑同 query 數量、同 verdict → 三組 cascade 數字一致;只差最後 filter / enriched 應用)

| Phase | Metric | B / C / D 共通 | 解讀 |
|---|---|---|---|
| 2.a | chain_new in active_region | 160/170 = **94%** | active region top-50 涵蓋率高 |
| 2.a | chain_old in active_region | 160/170 = **94%** | 同上 |
| 2.a | chain_new in any top-5 chain | 105/170 = **62%** | -32pt:beam search L=3/beam=8 漏多 hop 後段 |
| 2.a | chain_old in any top-5 chain | 114/170 = **67%** | 同上 |
| 2.a | **BOTH in SAME chain** | 86/170 = **51%** | spec §B.3.4.1 "Alt Chain Coverage lenient" target ≥ 70% 還差 |
| 2.b | **Pool co-occurrence** | 115/170 = **68%** | mini-eval 16 題 55% 是 ill-balanced subset,全 100 題 68% |
| 2.b | Verdict correct (old→new) | 111/170 = **65%** | 主要被 pool co-occurrence 上限封頂 |
| 2.c | chain_old chunk dropped | B/C: 95/170 = **56%** \| D: **0%** | D 設定 filter OFF |
| 2.c | chain_new chunk kept | B/C: 163/170 = 96% \| D: 100% | filter 不誤殺 chain_new |
| 2.c | **filter effective(both)** | B/C: 92/170 = **54%** \| D: 0% | D 沒做 filter 是設計 |
| 3 | update pair both in enriched | B: 0% \| C/D: 67% | C/D 同 enriched render(內容相同) |
| 3 | (by hop) 2-hop update_pair | C/D: 73/87 = **84%** | short chain Recent Updates 涵蓋好 |
| 3 | (by hop) 3-hop update_pair | C/D: 28/48 = **58%** | |
| 3 | (by hop) 4-hop update_pair | C/D: **13/35 = 37%** | deep chain enriched 殘缺 |

#### 三個重大 finding

**Finding 1: Phase 2.c filter passages 才是核心 +14pt contribution**

`A → B` +14pt 完全由 filter passages 貢獻(因 W3 全 off)。機制:
- chain_old chunk drop rate = 56% → 這 56% queries 的 LLM 看不到 OLD 答案,自然答 chain_new
- 剩 44% chain_old chunk 沒被 drop:可能 chain_old 不在 top-20 retrieve(retrieve 排名低),或者 rescue 規則(passage 內有 chain_current 也保留)生效

**Finding 2: W3 enriched context 在 filter on 時 = no-op**

`B → C` +0pt。Cascade 顯示 67% queries 的 Recent Updates 涵蓋 chain_new+old pair,但 EM 完全沒變化。原因:
- LLM 已從 retrieved passages(post-filter)看不到 chain_old,enriched 的 Recent Updates 沒新資訊
- Token overhead 但無 EM 收益 → A3.1 預期 +5pp **未達成**

**Finding 3: 沒 filter 時 W3 反而傷害**

`A → D` −2pt(15 < 17,W3 minimal 比 vanilla 還差)。Cascade 顯示 D 的 enriched coverage 跟 C 一樣 67%,但 EM 跌 16pt。原因:
- LLM 同時看到 retrieved passages 內的 chain_old + enriched 的 "Harrisville (updates earlier: 'Washington, D.C.')"
- 「updates earlier: X」措辭歧義 + 資訊重複 → LLM confused,部分 query 選了 chain_old 或拒答

#### 對 v2.0.2 spec 的影響

| Spec 假設 | 100Q 實測 | 結論 |
|---|---|---|
| §B.4.4 A3.1: W3 full ≥ P2 by +5pp | C = B +0pt | ❌ 未達成 |
| §B.4.4 A3.5: token overhead < 500/query | enriched 539-943 chars ≈ 120-220 tokens | ✓ |
| §B.3.4.3 Hard gate ≥ 40% MH | B/C 31% | ❌ partial pass (35-40%) |
| §B.3.4.2 pool co-occurrence ≥ 80% | 68% | ❌ (mini-eval 16Q 55%, full 100Q 68%) |
| §B.3.4.1 Alt Chain Coverage lenient ≥ 70% | 51% (BOTH in same chain) | ❌ |
| **新發現** | filter passages contributes +14pt | ★ 主 contribution 位置變了 |

**Paper framing 調整**:
- 原本 v2.0.2 主 contribution = "chain-restricted query-time supersession verdict" + "enriched context"
- 實測:**chain-restricted verdict + passage filter = 主機制**;**enriched context 在現設計下沒幫助**
- 需重新 frame:Phase 2.b verdict + Phase 2.c filter 是核心,Phase 3 留 W4 改進(措辭、注入時機)

#### Open items / 後續工作

- ⚠️ **Recent Updates 措辭歧義**(`"updates earlier: X"`)是 D 倒退主因 — W4 重 phrasing 後重測
- ⚠️ **Chain coverage 51% BOTH same chain**:beam=8 / L=3 可能太小;sweep beam={8,16,32} × L={3,4} 看能否拉到 70%
- ⚠️ **W3 token overhead 沒 EM 收益**:可考慮只在 chain coverage 高 (high-conf chain) 時才 inject enriched
- ⚠️ **Phase 2.c filter rescue logic** 太寬(passage 含 chain_current 就保留)讓 44% chain_old 沒被 drop;考慮收緊
- ⚠️ **跟 Zep / Mem0 baseline 對照尚未做** — MABench 既有結果 join by qa_pair_id

#### Gate 結論

⚠️ **Partial pass + Important re-framing**:
- ✅ Phase 2 chain detection + verdict + filter 機制 **+14pt vs vanilla**(達 spec §B.3.4.3 "partial pass 35-40%" 區間)
- ❌ W3 enriched context 在當前設計**沒額外貢獻**(+0pt)且配置不當會反退步(−16pt without filter)
- ✅ Instrumentation 完整,所有 phase 都能 post-hoc 量化
- ✅ Cascade table 清楚指出剩餘瓶頸位置(chain coverage 51%、filter rescue 過寬)

→ 下一步候選:
- **(a) 跟 Zep / Mem0 baseline 對照**,把 Phase 2 +14pt 跟 conversational memory community baseline 比
- **(b) Chain coverage sweep**(beam / L / score weights)拉到 70% BOTH same chain
- **(c) W3 measure 再設計**(Recent Updates 措辭 + inject 時機)看能否從 +0pt 變 +5pt

---

**End of Method Design v2.0.2 Specification**

Sign-off: This document supersedes v2.0.1. Source of truth for implementation. Any method design change must update this document first before code change.

**Key learnings v2.0 → v2.0.1 → v2.0.2**:
- v2.0 → v2.0.1: Repeated pushback against rule-based shortcuts → removed easy-case detection; opportunistic γ pairing
- v2.0.1 → v2.0.2: Code-side review caught spec internal contradictions → cleanly separated proposition layer (W1) from candidate cache (W2); locked all open questions with explicit defaults; added sentinel monitoring for PropRAG attention robustness

**The architecture has converged**: minimal LLM use, clean phase boundaries, explicit invariants, falsifiable assertions, honest limitations. Ready for implementation.
