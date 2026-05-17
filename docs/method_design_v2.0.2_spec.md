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

#### B.3.2.1 Algorithm

```python
def chain_restricted_verdict(
    candidate_chains: List[Chain],
    query: str,
    kg: KG,
    llm: LLM,
    enable_phase1_cache: bool = False,  # W1=False (on-the-fly); W2+=True
    K_pool: int = 10  # locked, small-pool insight
) -> Dict[str, Verdict]:
    """
    For each proposition on each chain, determine verdict.
    Pool construction has 3 sources:
      1. Phase 1 cache (if enabled): p.candidate_supersedees
      2. On-the-fly lookup: always run; supplements Phase 1 misses; primary in W1
      3. γ opportunistic: propositions from OTHER chains sharing entities
    """
    verdicts = {}
    
    for chain in candidate_chains:
        for p in chain.propositions:
            pool = set()
            
            # Source 1: Phase 1 cache (W2+)
            if enable_phase1_cache and p.candidate_supersedees:
                pool |= set(p.candidate_supersedees)
            
            # Source 2: on-the-fly lookup (always)
            pool |= dynamic_candidate_lookup(
                p, kg, tau_loose=0.7, K=20,
                before_time=p.timestamp
            )
            pool |= dynamic_candidate_lookup(
                p, kg, tau_loose=0.7, K=20,
                after_time=p.timestamp  # find potential superseders
            )
            
            # Source 3: γ opportunistic pairing
            for other_chain in candidate_chains:
                if other_chain.id == chain.id:
                    continue
                paired_props = find_corresponding_propositions(
                    p, chain, other_chain
                )
                pool |= set(paired_props)
            
            pool.discard(p)
            pool = top_K_by_relevance_to_p(pool, p, k=K_pool)
            
            if not pool:
                verdicts[p.id] = Verdict(
                    status='current',
                    confidence='low',
                    reason='no_candidates_found',
                    superseder_id=None
                )
                continue
            
            response = llm(
                build_verdict_prompt(query, chain, p, pool),
                max_tokens=300
            )
            verdicts[p.id] = parse_verdict(response, pool)
    return verdicts
```

#### B.3.2.2 Verdict prompt template (same as v2.0.1)

```
SUPERSESSION_VERDICT_PROMPT = """
You are evaluating whether a statement in a reasoning chain has been superseded 
by a later statement, in the context of answering a query.

QUERY: {query}

CANDIDATE REASONING CHAIN (in temporal order):
{chain}

FOCUS STATEMENT (to evaluate):
"{proposition_text}" (recorded at turn {chunk_idx}, position {in_chunk_pos})

POOL OF POTENTIALLY-RELATED STATEMENTS:
{pool}

Question: Is the focus statement superseded by any statement in the pool?

A statement is "superseded" only if:
  (a) The pool statement asserts an updated value for the SAME aspect as the focus 
      statement (not adding a new dimension), AND
  (b) The pool statement is more recent (later timestamp), AND
  (c) Both statements cannot simultaneously be true.

Important counter-examples (NOT supersession):
  - "User likes Apple" + "User likes Banana" — different objects, both can hold
  - "John works at Google" + "John lives in Seattle" — different attributes
  - Restating the same fact at a later time — not supersession

Output (JSON only):
{
  "verdict": "current" | "superseded" | "uncertain",
  "superseded_by": <pool statement number, or null>,
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence>"
}
"""
```

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

| Metric | Target | Stretch |
|---|---|---|
| Per-hop verdict accuracy | ≥ 80% | ≥ 90% |
| All-detected per-Q | ≥ 60% | ≥ 80% |
| Pool size median | ≤ 5 | ≤ 3 |
| LLM calls per query | < 20 | < 10 |
| High-confidence verdict precision | ≥ 95% | ≥ 98% |

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

**End of Method Design v2.0.2 Specification**

Sign-off: This document supersedes v2.0.1. Source of truth for implementation. Any method design change must update this document first before code change.

**Key learnings v2.0 → v2.0.1 → v2.0.2**:
- v2.0 → v2.0.1: Repeated pushback against rule-based shortcuts → removed easy-case detection; opportunistic γ pairing
- v2.0.1 → v2.0.2: Code-side review caught spec internal contradictions → cleanly separated proposition layer (W1) from candidate cache (W2); locked all open questions with explicit defaults; added sentinel monitoring for PropRAG attention robustness

**The architecture has converged**: minimal LLM use, clean phase boundaries, explicit invariants, falsifiable assertions, honest limitations. Ready for implementation.
