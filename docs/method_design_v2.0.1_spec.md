# Method Design v2.0.1 Specification
## (Living Doc §B 重構 — From v1 Three-Phase to Query-Anchored Detection Architecture)

> **Version**: v2.0.1 (from v2.0 — corrections based on conversation 2026-05-16 round 2)
>
> **Changelog v2.0 → v2.0.1**:
> - ❌ **Removed**: Phase 1 easy-case deterministic detection (functional whitelist regression to rule-based)
> - ✅ **Changed**: γ pairing from mandatory to **opportunistic** — handles cases where new/old pair is absent
> - ✅ **Reordered**: Implementation sequence flipped to **Phase 2 first** (standalone with on-the-fly candidate lookup), Phase 1 as optimization (W2)
> - ❌ **Removed**: Phase 2.a Step 4 LLM tail validate (over-engineering, top-M scoring is sufficient)
> - ➕ **Added**: §B.12 Coverage limitations honesty box (case D acknowledgment)
>
> **文件用途**:
> 1. **Update fc_mh_living_doc_v1.1.md §B** — 取代原 B.1-B.7 (B.1 base method 保留)
> 2. **Implementation handoff for Claude Code** — 含 pseudocode, data structure, hook 位置, validation script outline
> 3. **Design review reference** — 中文導讀 + 英文 spec, 每個 sub-component 標 ✅ locked / 🟡 open

---

## §B.0 v1 → v2 架構重構總覽

### B.0.1 為什麼架構必須重構 (recap)

v1 結果與既有方法 detection 數據揭露三個結構性問題:

| 數據點 | 出處 | 推論 |
|---|---|---|
| Mem0 per-hop 59% (top-k=5 pool) | motivation §4.3 | Small pool + LLM judge 在 single fact-pair 上 work |
| Zep per-hop 38% (在 FC 上退化成 deterministic) | motivation §4.3 | Bi-temporal annotation 在 no-explicit-temporal 環境失效, 但 timestamp 作為 metadata 仍有價值 |
| v1 P1 deterministic 36% | Method v1 §10 | 純 syntactic match 有 35% relation-alias miss ceiling |
| LLM judge on production pool (30-450 candidates) | conversation prior | LLM attention 在大 pool 中崩壞, 退到 20-30% |
| All-detected per-Q: Mem0 41/100, Zep 20/100, v1 19/100 | motivation §4.3 | **multi-hop 累積 detection 即使 small pool LLM 也只到 41%**, 因為 write-time 沒 query 訊息 |

**核心 insight**: 寫入時嘗試一次解決所有 supersession 是錯誤的 problem framing。**正確 framing 是 detection-where-it-matters**: 把 critical detection 推到 query time, 限定在 query reasoning chain 上做 small-pool LLM judge。

### B.0.2 v1 vs v2 architecture diff (v2.0.1 updated)

| Phase | v1 角色 | v2 新角色 |
|---|---|---|
| **Phase 1 (write-time)** | Heavy lifting — deterministic `(s,r,≠o)` detection on triples, 標 superseded metadata | **Pure annotation only** — proposition extraction + candidate annotation (entity overlap + cosine, no LLM, no verdict) + timestamps. **沒有 easy-case detection, 沒有 rule-based shortcut**。Phase 1 是 Phase 2 的 offline cache, 不是必要 component |
| **Phase 2 (retrieval-time)** | Chain-aware passage filter via PPR mass proxy (X=99 percentile) | **Critical detection 中樞** — split 成 2.a Chain identification (M4 simplified) + 2.b Chain-restricted supersession verdict (small-pool LLM judge with chain context + timestamps) |
| **Phase 3 (inference-time)** | Universal scaffold prompt ("list intermediate entities consistently") | **Enriched memory output** — return passages + reasoning hints (A4 hybrid form) + change log (B2 natural language). **Prompt unchanged** |

**Key architectural changes**:
1. **Detection locus shifted**: write-time → query-time (Phase 1 只是 cache, 不是判斷源頭)
2. **Memory unit upgraded internally**: triple → proposition (但對外仍返回 passages)
3. **Scaffold moved into context**: prompt phrasing → enriched memory content
4. **Chain explicitly discovered**: PPR mass proxy → M4 simplified (PPR region + bounded path enum)
5. **γ pairing is opportunistic**: 不假設每 hop 都有 old/new pair, 找到就用, 找不到 verdict fallback to single-prop judgment
6. **Implementation order flipped**: Phase 2 standalone first, Phase 1 added as optimization

### B.0.3 v2 對 motivation 兩 Claim 的最終 mapping

| Motivation Claim | v1 對應 | v2 對應 |
|---|---|---|
| **Claim 1**: chain-old 在 retrieval 中過濾 | Phase 1 (detection) + Phase 2 PPR mass filter | Phase 2.a chain id + Phase 2.b verdict — chain-old 在 chain 範圍內 verdict 後過濾 |
| **Claim 2**: 提供額外回傳記憶引導 inference | Phase 3 universal scaffold prompt | Phase 3 enriched memory output (reasoning hints + change log), prompt unchanged |

**Claim 2 reframe 的關鍵**: contribution 完全在 memory method 側 (return 什麼 evidence), 不在 prompt engineering 側。對應 conversational memory 社群慣例 (Zep return facts, Mem0 return memories), 不引入 prompt-engineering confound。

---

## §B.1 HippoRAG-v2 Base Pipeline (保留, hooks 位置更新)

> 我們所有 v2 改動仍是在 HippoRAG-v2 既有 pipeline 的特定 step 動刀。

### B.1.1 Offline Indexing
| Step | 動作 | v2 hook |
|---|---|---|
| I1 | LLM 對每 passage 跑 OpenIE, 抽 `(s, r, o)` triples | (保留) |
| I2 | NV-Embed-v2 fp16 forward 算 chunk / entity / fact embeddings | (保留) |
| **I2.5 (新)** | **Proposition extraction** (LLM-aided, 從 chunk 抽含 context 的 propositions) | **Phase 1 v2 hook #1** |
| I3a | `add_fact_edges`: phrase ↔ phrase edges in KG | (保留) |
| I3b | `add_passage_edges`: passage → entity edges in KG | (保留) |
| **I3c (新)** | **`add_proposition_nodes_and_edges`**: proposition nodes + entity-proposition edges | **Phase 1 v2 hook #2** |
| I4 | `add_synonymy_edges`: entity KNN cosine ≥ 0.8 | (保留) |
| **I4.5 (新, optional W2)** | **`annotate_supersession_candidates`**: 對每個 proposition 算 candidate supersedee set (entity overlap + cosine, **no LLM, no verdict, no easy-case**) + timestamps | **Phase 1 v2 hook #3** — W2 才實作, W1 跳過 |
| I5 | save `graph.graphml` + `proposition_index.json` (+ `candidate_index.json` if W2 done) | (擴展) |

### B.1.2 Online Retrieval & QA
| Step | 動作 | v2 hook |
|---|---|---|
| O1 | `get_fact_scores`: query × fact_embeddings cosine | (保留) |
| O2 | `rerank_facts`: LLM judge top-k fact triples | (保留, 不再用於 supersession filter) |
| O3 | Seed reset weights: phrase + 0.05·DPR passage | (保留) |
| O4 | `run_ppr`: PPR propagate, return full pagerank_scores | (保留) |
| **O4.5 (新)** | **`identify_active_region`**: 從 PPR scores 找 active region (top-K propositions + query entity 1-hop) | **Phase 2.a hook #1** |
| **O4.6 (新)** | **`enumerate_candidate_chains`**: 在 active region 內 bounded path enumeration → top-M chains by relevance score | **Phase 2.a hook #2** |
| **O4.7 (新)** | **`chain_restricted_verdict`**: 對 chains 上每個 proposition 做 small-pool LLM verdict (chain context + timestamps + γ opportunistic pairing) | **Phase 2.b hook** |
| O5 | Passage ranking & selection (top-N) | **Phase 2 應用點**: 依 verdict 結果 filter chain-old propositions 對應 passages |
| **O5.5 (新)** | **`render_enriched_context`**: 組裝 passages + reasoning hints + change log | **Phase 3 hook** |
| O6 | `rag_qa`: enriched context → LLM (prompt unchanged) → QA | (prompt 不動, content 由 O5.5 決定) |

### B.1.3 v2 architecture diagram (v2.0.1)

```
─ Offline Indexing ─────────────────────────────────────────────
I1.  OpenIE → triples
I2.  Embeddings
I2.5 Proposition extraction (NEW)         ← Phase 1 hook #1
I3.  add_fact_edges + add_passage_edges
I3c. add_proposition_nodes (NEW)          ← Phase 1 hook #2
I4.  add_synonymy_edges
I4.5 annotate_supersession_candidates     ← Phase 1 hook #3 (W2 OPTIONAL)
     (no LLM, no verdict, no easy-case)
I5.  save indexes

─ Online Retrieval & QA ───────────────────────────────────────
O1.  fact scoring
O2.  rerank_facts (unchanged role)
O3.  seed weights
O4.  run_ppr → pagerank_scores
O4.5 identify_active_region (NEW)         ← Phase 2.a hook #1
O4.6 enumerate_candidate_chains (NEW)     ← Phase 2.a hook #2
O4.7 chain_restricted_verdict (NEW)       ← Phase 2.b hook
     (only LLM call type in Phase 2)
O5.  Passage filter (依 verdict)
O5.5 render_enriched_context (NEW)        ← Phase 3 hook
O6.  rag_qa (prompt unchanged)
```

---

## §B.2 Phase 1 v2 — Pure Annotation Only (NO LLM, NO Verdict)

> **v2.0.1 change**: 完全移除 easy-case detection。Phase 1 只負責 proposition extraction + candidate annotation + timestamps。沒有任何 verdict 動作, 不依賴 relation 分類或 functional whitelist。

### B.2.1 Purpose & contract

**目標**: Offline 預算工作, 為 Phase 2 加速:
1. 抽 proposition (升級記憶顆粒度)
2. 為每個 proposition 算 candidate supersedee set (Phase 2.b pool 的 offline cache)
3. 標時間戳 metadata (Zep 啟發, 給 Phase 2.b verdict 用)

**沒做的事 (intentional)**:
- ❌ 不做 LLM judge (cost 都推到 query time)
- ❌ 不做 easy-case deterministic detection (避免 rule-based regression)
- ❌ 不做 relation 分類 (避免 a priori cardinality assumption)
- ❌ 不過濾任何 proposition (沒有 destructive op)

**Contract**:
- **Input**: passages (chunks, 帶 turn / chunk_idx ordering)
- **Output**:
  - Proposition nodes (含 entities, text, timestamp, source_chunk_id, embedding)
  - Per-proposition `candidate_supersedees: List[ProposalRef]` (Recall-oriented pre-filter)
- **Invariant**: Phase 1 永遠不下 supersession verdict; verdict 是 Phase 2.b 的唯一職責
- **Failure mode**: Phase 1 漏抓 candidate → Phase 2.b dynamic_lookup at query time 補救 (Phase 1 是 cache, 不是 single source of truth)

**Phase 1 不是必要的 (critical re-framing)**:
- Phase 2 可以**不靠 Phase 1** 運作 — 把 candidate lookup 完全推到 query time (on-the-fly)
- Phase 1 的價值是 offline precompute, **減少 query latency**, 不是 correctness 前提
- 這也是為什麼 implementation order 是 Phase 2 first, Phase 1 second (W2 optimization step)

### B.2.2 Algorithm (v2.0.1 simplified)

```python
# I2.5 Proposition extraction (per chunk) — UNCHANGED from v2.0
def extract_propositions(chunk: str, llm: LLM) -> List[Proposition]:
    """
    Use PropRAG-inspired prompt to extract context-rich propositions.
    Each proposition: entity-relation-attribute or event with qualifiers.
    Reference: PropRAG (EMNLP 2025) Appendix A.3 prompt template.
    """
    prompt = PROPOSITION_EXTRACTION_PROMPT.format(chunk=chunk)
    raw = llm(prompt)
    propositions = parse_propositions(raw)
    for p in propositions:
        p.embedding = nv_embed(p.text)
        p.entities = link_entities(p.text)  # 用 HippoRAG-v2 既有 NER + synonymy
        p.timestamp = chunk.turn_idx  # 或實際時間, FC-MH 用 turn idx
    return propositions

# I3c Add proposition nodes to KG
def add_proposition_nodes(kg: KG, propositions: List[Proposition]):
    for p in propositions:
        kg.add_node(p, type='proposition')
        for e in p.entities:
            kg.add_edge(p, e, type='proposition_entity')

# I4.5 Annotate supersession candidates
# v2.0.1: NO easy-case detection, NO LLM judge, pure mechanical retrieval
def annotate_supersession_candidates(
    kg: KG,
    propositions: List[Proposition],
    K: int = 20,           # top-K candidate per proposition
    tau_loose: float = 0.7 # cosine threshold (open, tunable in W2)
):
    """
    For each new proposition p_new arriving at time t_new:
      1. Mechanism A (entity-overlap retrieval):
         - Find all propositions sharing at least one entity with p_new
           (via direct entity match OR synonymy edges)
         - Restrict to propositions where timestamp < t_new
      2. Mechanism B (proposition embedding cosine):
         - Find top-K propositions with cosine >= tau_loose, before t_new
      3. Union → candidate set
      4. Trim to top-K by combined score (entity overlap count + cosine)
      
    NO LLM judge.
    NO supersession edge addition.
    NO verdict.
    Just store candidate_supersedees list as offline cache for Phase 2.b.
    """
    for p_new in sorted(propositions, key=lambda p: p.timestamp):
        candidates = set()
        # Mechanism A
        for e in p_new.entities:
            candidates |= kg.get_propositions_with_entity(
                e, include_synonyms=True, before_time=p_new.timestamp
            )
        # Mechanism B
        cosine_neighbors = kg.knn_propositions(
            p_new.embedding, k=K*2, before_time=p_new.timestamp
        )
        candidates |= {
            p for p in cosine_neighbors 
            if cosine(p_new.embedding, p.embedding) >= tau_loose
        }
        
        # Trim to top-K by combined score
        scored = [
            (p, score_combined(p_new, p))  # entity_overlap_count + cosine_sim
            for p in candidates
        ]
        scored.sort(key=lambda x: -x[1])
        p_new.candidate_supersedees = [p for p, _ in scored[:K]]
    
    # That's it. No further action. No supersession edges added at write-time.
```

### B.2.3 Data structures (v2.0.1 simplified)

```python
@dataclass
class Proposition:
    id: str
    text: str
    entities: List[Entity]
    embedding: np.ndarray             # NV-Embed-v2 4096-d
    timestamp: int                    # turn_idx or actual time
    source_chunk_id: str
    candidate_supersedees: List[str]  # IDs (Phase 1 cache; can be empty if Phase 1 not run)
    triple_form: Optional[Triple]     # backward-compat extraction attempt (informational only)

@dataclass
class SupersessionEdge:
    """
    v2.0.1: only created by Phase 2.b verdict at query time.
    Phase 1 does NOT create supersession edges.
    """
    p_old_id: str
    p_new_id: str
    confidence: Literal['high', 'medium', 'low']
    timestamp: int                      # when verdict was made
    created_by_query: str              # which query triggered this verdict
    change_note: Optional[str]          # for Phase 3 B2 rendering
```

### B.2.4 Validation metrics (Phase 1 v2 independent, W2 only)

| Metric | Definition | Target | Stretch |
|---|---|---|---|
| **Candidate Recall@K=20** | 真實 supersession pair 中, p_old 是否在 p_new.candidate_supersedees 中 | ≥ 85% | ≥ 95% |
| **Pool size median** | median(\|p.candidate_supersedees\|) | ≤ 10 | ≤ 5 |
| **Indexing cost overhead** | extra time per chunk (vs vanilla HippoRAG-v2) | < 2x baseline | < 1.5x |
| **Latency reduction at query time** | end-to-end FC-MH MH query time with Phase 1 cache vs without | ≥ 30% reduction | ≥ 50% |

→ **Phase 1 v2 gate (W2)**: Candidate Recall ≥ 85% AND pool median ≤ 10 AND latency reduction ≥ 30%。**若 Phase 1 達 gate, 留下作為 query-time optimization**; 若沒達 gate, 可暫不啟用 (Phase 2 仍能 standalone 運作)。

### B.2.5 Implementation hooks

- 在 `HippoRAG.__init__` 加: `self.propositions: Dict[id, Proposition]`
- 在 `index()` 後加 hooks for I2.5 → I3c → I4.5 (I4.5 受 `enable_phase1_cache` flag 控制)
- 新檔案: `phase1/proposition_extractor.py`, `phase1/candidate_annotator.py`
- Feature flag: `enable_phase1_v2` (W1 default False — Phase 2 standalone), `enable_phase1_cache` (W2 default True after gate)
- Persistence: `proposition_index.json` (id → Proposition with candidate_supersedees) next to `graph.graphml`

---

## §B.3 Phase 2 v2 — Query-Anchored Chain Detection (NEW CORE)

> **這是 v2 contribution 的中樞**。Phase 2 分成兩個 sub-phase: 2.a chain identification, 2.b chain-restricted supersession verdict。
>
> **v2.0.1 changes**: 
> - 移除 Step 4 LLM tail validate (over-engineering)
> - γ pairing 從 mandatory chain-level 改為 **opportunistic proposition-level** (在 verdict 階段於 pool 中加入其他 chain 的對應 proposition)
> - 支援 standalone mode (不依賴 Phase 1, on-the-fly candidate lookup)

### B.3.1 Sub-phase 2.a — Chain Identification (M4 simplified)

**Purpose**: Given a query, identify M candidate reasoning chains in the KG. **Supersession-agnostic** — find both old and new chains for downstream verdict.

**Contract**:
- **Input**: query `q`, KG `G` with propositions (and Phase 1 candidate annotations if enabled), PPR scores (from O4)
- **Output**: 
  - `candidate_chains: List[Chain]` where `|chains| ≤ M=5`
  - Each chain has: ordered list of propositions, mapped passages, chain score
- **Invariant 1 (critical)**: Chain identification does NOT filter superseded propositions. Both old chain and new chain must be discoverable in principle.
- **Invariant 2**: No LLM call in Phase 2.a. Pure graph + embedding operations.

#### B.3.1.1 M4 simplified algorithm (3 steps, v2.0.1)

```python
def enumerate_candidate_chains(
    query: str,
    kg: KG,
    ppr_scores: np.ndarray,
    M: int = 5,                # default chain count (locked)
    L: int = 3,                # max depth in hops (locked)
    region_topK: int = 50,     # propositions in active region (open, tunable)
    enum_beam_width: int = 8   # path enum beam (open, tunable)
) -> List[Chain]:
    
    # ─────────── Step 1: Active region identification (O4.5) ───────────
    # Use HippoRAG-v2 PPR mass to define "where to look"
    active_props = kg.get_top_propositions_by_ppr_mass(
        ppr_scores, k=region_topK
    )
    # Augment with propositions 1-hop from query entities
    query_entities = link_query_entities_via_embedding(query, kg)  # Q5: HippoRAG-v2 embedding-based
    for e in query_entities:
        active_props |= kg.get_propositions_with_entity(e, include_synonyms=True)
    active_region = kg.subgraph_induced_by_propositions(active_props)
    
    # ─────────── Step 2: Bounded path enumeration (O4.6) ───────────
    # Find paths in active_region. Path = sequence of propositions sharing entities.
    raw_chains = bounded_path_enumeration(
        active_region,
        start_entities=query_entities,
        max_depth=L,
        beam_width=enum_beam_width,
        # CRITICAL: SUPERSESSION-AGNOSTIC — no filtering by supersession status
    )
    # raw_chains may include both chain_with_OLD and chain_with_NEW
    
    # ─────────── Step 3: Score & trim to top-M ───────────
    scored = [
        (c, score_chain(c, query, ppr_scores))
        for c in raw_chains
    ]
    scored.sort(key=lambda x: -x[1])
    top_chains = [c for c, _ in scored[:M]]
    
    # NO Step 4 LLM tail validate (removed in v2.0.1).
    # Rationale: top-M by relevance score should already be query-relevant.
    # If 1-2 irrelevant chains slip in, Phase 2.b verdict on them is wasted
    # compute but doesn't corrupt verdicts on relevant chains.
    
    return top_chains

def score_chain(chain: Chain, query: str, ppr_scores) -> float:
    """
    Score chain by:
    - Sum of proposition-query cosine
    - Path coherence (consecutive propositions sharing entities)
    - Path length penalty
    - PPR mass coverage
    NO supersession penalty — Phase 2.b's job, not Phase 2.a's.
    """
    relevance = sum(cosine(p.embedding, embed(query)) for p in chain.propositions)
    coherence = chain.entity_overlap_score()
    length_penalty = -0.1 * len(chain.propositions)
    ppr_coverage = sum(ppr_scores[p.id] for p in chain.propositions)
    return relevance + 0.3 * coherence + 0.2 * ppr_coverage + length_penalty
```

#### B.3.1.2 Note on γ pairing (moved to Phase 2.b)

In v2.0, γ pairing was a separate Step 3 in Phase 2.a, trying to pair chains at the chain level. In v2.0.1, **γ pairing is opportunistic and happens at verdict time (Phase 2.b)** via pool construction. This is simpler and handles cases A/B/C/D uniformly:

| Case | Description | v2.0.1 Behavior |
|---|---|---|
| **A** | Only new fact in KG (no old) | Pool empty or no candidate → verdict "current" with high confidence |
| **B** | Both old and new in KG, Phase 1 (or on-the-fly) found candidate | γ link via candidate pool → verdict can compare, high confidence |
| **C** | Both in KG but candidate lookup missed | Pool incomplete → verdict may say "current" with medium confidence; dynamic lookup at query time mitigates |
| **D** | Only old in KG (new never extracted) | Pool empty → verdict "current" (incorrect but unavoidable; see §B.12) |

→ γ pairing is no longer a separate algorithmic step; it's a property of pool construction in Phase 2.b.

### B.3.2 Sub-phase 2.b — Chain-Restricted Supersession Verdict

**Purpose**: Within each chain, determine which propositions are superseded (chain-old) vs current (chain-new). Output = filter signal for downstream passage selection.

**Contract**:
- **Input**: `candidate_chains` (from Phase 2.a), `query`, KG
- **Output**: For each proposition on each chain, `Verdict(status, confidence, superseder_id?)`
- **Critical sub-invariant**: Pool size per LLM call ≤ 10 (the Mem0 small-pool insight)
- **Phase 2 standalone mode**: When Phase 1 not run, candidate lookup happens on-the-fly here

#### B.3.2.1 Algorithm (v2.0.1, supports standalone + cached modes)

```python
def chain_restricted_verdict(
    candidate_chains: List[Chain],
    query: str,
    kg: KG,
    llm: LLM,
    enable_phase1_cache: bool = True,
    K_pool: int = 10  # max pool size for LLM verdict (locked, small-pool insight)
) -> Dict[str, Verdict]:
    """
    For each proposition on each chain, determine verdict using LLM judge
    with chain context, timestamps, and a small candidate pool.
    
    Pool construction has 3 sources:
      1. Phase 1 cache (if enabled): p.candidate_supersedees
      2. On-the-fly lookup: dynamic candidate retrieval (used in standalone mode 
         or as supplement to Phase 1 cache)
      3. γ opportunistic pairing: propositions from OTHER chains sharing entities
    """
    verdicts = {}
    
    for chain in candidate_chains:
        for p in chain.propositions:
            # ─── Pool construction ───
            pool = set()
            
            # Source 1: Phase 1 cache
            if enable_phase1_cache and hasattr(p, 'candidate_supersedees'):
                pool |= set(p.candidate_supersedees)
            
            # Source 2: On-the-fly lookup (always run, supplements Phase 1 misses)
            pool |= dynamic_candidate_lookup(
                p, kg, tau_loose=0.7, K=20,
                before_time=p.timestamp
            )
            # Also look for SUPERSEDERS (propositions after p that may supersede it)
            pool |= dynamic_candidate_lookup(
                p, kg, tau_loose=0.7, K=20,
                after_time=p.timestamp
            )
            
            # Source 3: γ opportunistic pairing (propositions from OTHER chains)
            for other_chain in candidate_chains:
                if other_chain.id == chain.id:
                    continue
                paired_props = find_corresponding_propositions(
                    p, chain, other_chain
                )  # entity-overlap based matching
                pool |= set(paired_props)
            
            # ─── Pool trim (small-pool insight) ───
            pool.discard(p)  # exclude self
            pool = top_K_by_relevance_to_p(pool, p, k=K_pool)
            
            # ─── Verdict ───
            if not pool:
                # Case A or D: no candidates
                verdicts[p.id] = Verdict(
                    status='current',
                    confidence='low',
                    reason='no_candidates_found',
                    superseder_id=None
                )
                continue
            
            # LLM judge on small pool with full chain context
            response = llm(
                build_verdict_prompt(query, chain, p, pool),
                max_tokens=300
            )
            verdict = parse_verdict(response, pool)
            verdicts[p.id] = verdict
    
    return verdicts

def find_corresponding_propositions(
    p: Proposition, 
    chain: Chain, 
    other_chain: Chain
) -> List[Proposition]:
    """
    Find propositions in other_chain that may be 'alternative versions' of p.
    Heuristic: same entity overlap, similar position in chain structure.
    
    Returns empty list if no correspondence (γ case A/D).
    """
    candidates = []
    for q in other_chain.propositions:
        # Heuristic: high entity overlap AND not identical
        entity_overlap = len(set(p.entities) & set(q.entities))
        if entity_overlap >= 1 and q.id != p.id:
            candidates.append(q)
    return candidates
```

#### B.3.2.2 Verdict prompt template (v2.0.1)

```
SUPERSESSION_VERDICT_PROMPT = """
You are evaluating whether a statement in a reasoning chain has been superseded 
by a later statement, in the context of answering a query.

QUERY: {query}

CANDIDATE REASONING CHAIN (in temporal order):
{chain}

FOCUS STATEMENT (to evaluate):
"{proposition_text}" (recorded at turn {proposition_timestamp})

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

**Note on prompt**: This is Phase 2.b memory-method-side prompt, NOT the inference prompt. The inference prompt (O6) remains unchanged.

### B.3.3 Phase 2 → Phase 3 hand-off

```python
def phase2_to_phase3_handoff(
    candidate_chains: List[Chain],
    verdicts: Dict[str, Verdict],
    top_passages_from_ppr: List[Passage]
) -> Phase3Input:
    """
    Build the structured evidence to feed Phase 3.
    """
    # Identify chain-old propositions (verdict says superseded with confidence ≥ medium)
    chain_old_props = {
        pid for pid, v in verdicts.items() 
        if v.status == 'superseded' and v.confidence in ('high', 'medium')
    }
    
    # Filter passages: drop those primarily containing chain-old propositions
    filtered_passages = []
    for psg in top_passages_from_ppr:
        passage_props = psg.proposition_ids
        if any(pid in chain_old_props for pid in passage_props):
            # Skip if passage contains chain-old AND not 'rescued' by also containing chain-new
            chain_new_in_psg = any(
                verdicts.get(pid, Verdict(status='current')).status == 'current' 
                for pid in passage_props
            )
            if not chain_new_in_psg:
                continue  # drop
        filtered_passages.append(psg)
    
    # Pick highest-scoring chain as active chain for Phase 3 hint
    active_chain = max(candidate_chains, key=lambda c: c.score) if candidate_chains else None
    
    # Collect supersession events for change log
    supersession_events = [
        (pid, verdicts[pid].superseder_id)
        for pid in chain_old_props
        if verdicts[pid].superseder_id is not None
    ]
    
    return Phase3Input(
        filtered_passages=filtered_passages,
        active_chain=active_chain,
        supersession_events=supersession_events,
        verdict_confidence_map=verdicts  # for Phase 3 hedged language decisions
    )
```

### B.3.4 Validation metrics (Phase 2 independent)

#### B.3.4.1 Phase 2.a (chain identification) metrics

| Metric | Definition | Target | Stretch |
|---|---|---|---|
| **Chain Recall@M=5** | FC-MH GT chain 是否在 top-5 chains | ≥ 80% | ≥ 90% |
| **Chain Precision@1** | top-1 chain == GT chain | ≥ 60% | ≥ 75% |
| **Alt Chain Coverage** | KU queries 中, top-5 chains 是否同時含 GT chain_new 與 chain_old | ≥ 70% | ≥ 85% |
| **Per-query latency** | wall-clock 平均 chain id time | < 1s (no LLM in 2.a) | < 0.5s |

#### B.3.4.2 Phase 2.b (verdict) metrics

| Metric | Definition | Target | Stretch |
|---|---|---|---|
| **Per-hop verdict accuracy** | On GT chains, per-proposition verdict correct rate | ≥ 80% | ≥ 90% |
| **All-detected per-Q** | Query 中所有 KU hops 都正確判 verdict | ≥ 60% | ≥ 80% |
| **Pool size median** | per LLM call | ≤ 5 | ≤ 3 |
| **LLM calls per query** | Total Phase 2.b LLM calls | < 20 | < 10 |
| **High-confidence verdict precision** | When verdict.confidence='high', accuracy | ≥ 95% | ≥ 98% |

→ **Phase 2 gate (combined, W1 end)**: Chain Recall@5 ≥ 80% AND Per-hop verdict ≥ 80% AND end-to-end FC-MH MH ≥ 50% (vs v1 37%)。三者皆達標才進 Phase 3 設計 (W3).

### B.3.5 Implementation hooks

- 新檔案結構:
  - `phase2a/active_region.py` — O4.5 hook
  - `phase2a/path_enumeration.py` — O4.6 hook
  - `phase2b/verdict.py` — O4.7 hook (含 dynamic_candidate_lookup, find_corresponding_propositions, build_verdict_prompt)
  - `phase2/prompts/verdict_prompt.txt` — verdict prompt template (versioned)
- `HippoRAG.retrieve()` 主流程加 O4.5-O4.7 hooks
- Feature flags: 
  - `enable_phase2_chain_detection` (master, controls O4.5-O4.7)
  - `enable_phase1_cache` (W2: speeds up Phase 2.b pool construction; default False in W1)
- W1 mode: `enable_phase2_chain_detection=True, enable_phase1_cache=False` (standalone, on-the-fly only)
- W2 mode: both True (Phase 1 cache active)

---

## §B.4 Phase 3 v2 — Enriched Memory Output

### B.4.1 Purpose & contract

**目標**: 提供更豐富的 retrieval output, 讓 LLM 在 inference 時拿到 (a) supersession-filtered passages, (b) active reasoning chain hint, (c) supersession change log。**Prompt template 完全不變**, 變動只在 context content。

**Contract**:
- **Input**: `Phase3Input` from Phase 2 handoff
- **Output**: enriched context string, plugged into existing `rag_qa` prompt's `{context}` field
- **Invariant**: Prompt template (system + user instruction) **不變**。Phase 3 contribution 純粹在 context content design。

### B.4.2 Enriched context format (LOCKED)

```
=== Retrieved Passages ===
[Passage 1, supersession-filtered]
[Passage 2, supersession-filtered]
...
[Passage K]

=== Reasoning Hints ===
{A4 hybrid hint, generated from active chain — use hedged language if verdict confidence is low}

=== Recent Updates ===
{B2 natural language change notes, only if applicable AND verdict confidence ≥ medium}
```

**A4 hybrid hint generation** (from active chain):

```python
def render_reasoning_hint(active_chain: Chain, verdict_confidence_map) -> str:
    """
    Render the active chain as natural language hint.
    Hedge language if any proposition has low-confidence verdict.
    """
    if not active_chain:
        return ""  # graceful degradation
    
    # Check verdict confidence for chain propositions
    any_low_conf = any(
        verdict_confidence_map.get(p.id, Verdict()).confidence == 'low'
        for p in active_chain.propositions
    )
    
    prefix = "One possible reasoning path:" if any_low_conf else "Reasoning hints for this query:"
    
    parts = []
    for p in active_chain.propositions:
        parts.append(f"  - {p.text} (turn {p.timestamp})")
    return f"{prefix}\n" + "\n".join(parts)
```

**B2 change log generation** (only for medium+ confidence supersession):

```python
def render_change_log(
    supersession_events: List[Tuple[PropId, PropId]],
    verdict_confidence_map
) -> str:
    """
    Render supersession events as natural language.
    Only include events where verdict confidence is medium+ (avoid misleading LLM).
    """
    confident_events = [
        (p_old_id, p_new_id) for (p_old_id, p_new_id) in supersession_events
        if verdict_confidence_map.get(p_old_id, Verdict()).confidence in ('high', 'medium')
    ]
    if not confident_events:
        return ""
    
    notes = []
    for p_old_id, p_new_id in confident_events:
        # On-the-fly natural language rendering (no Phase 1 pre-rendering needed in v2.0.1)
        note = render_change_note_on_fly(p_old_id, p_new_id)
        notes.append(f"  - {note}")
    return "Recent updates relevant to this query:\n" + "\n".join(notes)
```

### B.4.3 Falsifiable assertions for Phase 3 (待 W3 實驗驗證)

| Assertion | Target | Notes |
|---|---|---|
| **A3.1**: full v2 (P2 + P3) ≥ P2-only by ≥ 5pp MH | +5pp | 主 contribution |
| **A3.2**: P3 enriched output ≥ v1 scaffold prompt (same passages) | non-inferior | 證明 Claim 2 reframe 站得住 |
| **A3.3**: 各 evidence type 獨立貢獻 (hints only / log only / both) | individual ablation | 為 §C.6 paper 拆 contribution |
| **A3.4**: 非 KU multi-hop query 退步 < 2pp | < 2pp | 對 MuSiQue / 2Wiki / FC-SH |
| **A3.5**: Token overhead 可量化 | avg < 500 tokens extra/query | cost-efficiency 證據 |

### B.4.4 Implementation hooks

- 新檔案: `phase3/enriched_context_renderer.py`
- Hook in `rag_qa()` before LLM call: `enriched_context = phase3.render(phase3_input)`
- Feature flags:
  - `enable_phase3_v2_enriched` (default True in W3+)
  - `enable_phase3_v1_scaffold` (legacy, for A3.2 ablation)
  - 兩者互斥 (不能同時 True)

---

## §B.5 v1 → v2 Critical Changes Mapping (v2.0.1 updated)

### B.5.1 什麼被移除/重新定位

| v1 component | v2.0.1 fate | 原因 |
|---|---|---|
| Phase 1 deterministic `(s,r,≠o)` detection | **完全移除** (沒有 easy-case shortcut, 沒有 functional whitelist) | Rule-based 路徑被 reject (user pushback 2x); 所有 verdict 統一在 Phase 2.b |
| Phase 2 PPR mass proxy with X=99 percentile | **取代** by Phase 2.a chain identification | PPR mass 不等於 query reasoning chain |
| Phase 3 universal scaffold prompt | **取代** by Phase 3 enriched output | Prompt engineering confound contribution purity |
| `supersession_index.json` (v1 schema) | **延後創建** — Phase 1 不再寫 supersession edges; 所有 supersession edges 由 Phase 2.b query-time verdict 創建 | 對應 detection-where-it-matters principle |

### B.5.2 什麼是 v2.0.1 新加

| v2 component | 對應 design decision | 主要 inspiration |
|---|---|---|
| Proposition extraction | G2 granularity choice | PropRAG (inspiration only) |
| Candidate annotation (no LLM, no easy-case) | Lightweight cache | Mem0 small-pool insight reversed (push LLM to query-time) |
| Active region identification | M4 step 1 | HippoRAG-v2 native PPR |
| Bounded path enumeration | M4 step 2 | Cleanroom (graph algorithm) |
| Opportunistic γ pairing (via pool) | Pool source 3 in Phase 2.b | Cleanroom (our novel mechanism, no chain-level pairing) |
| Chain-restricted verdict | New core (single LLM call type in Phase 2) | Mem0 small-pool insight applied query-anchored |
| Enriched output (hints + log) | Claim 2 reframe | Conversational memory norm (Zep facts, Mem0 memories) |
| Hedged language for low-confidence | Phase 3 robustness | Handles case C/D gracefully |

### B.5.3 Motivation → v2.0.1 Phase mapping (final)

| Motivation 觀察 | v1 對應 | v2.0.1 對應 |
|---|---|---|
| Chain-old leakage 28-29% (§4.2) | Phase 2 PPR filter | Phase 2.a + 2.b query-anchored verdict |
| +34pp chain_old vs +5pp other_old (§2.A) | Query-aware via PPR mass | Query-aware via explicit chain id + verdict |
| Phase 1 36% detection ceiling (§4.1) | bottleneck | not a bottleneck — verdict moved to Phase 2.b |
| Mem0 41% all-detected (§4.3) | 比 our v1 高 | v2 target ≥ 60% (small-pool + chain context + γ opportunistic) |
| Inference scaffold +28pp clean / +8 dirty (§2.B) | Phase 3 prompt | Phase 3 enriched output (content, not prompt) |

---

## §B.6 Independent Validation Strategy

> **核心原則**: 每 phase 都能獨立評估, 不依賴下游 phase 跑通才能 measure。**v2.0.1 重點變化**: Phase 2 標準的端對端 validation 可以**不靠 Phase 1** 跑 (standalone mode), 因此 W1 即可開始驗證 Phase 2 core mechanism。

### B.6.1 Validation oracle: FC-MH 6k GT reasoning chain

FC-MH 6k 每個 query 由 MQuAKE 構造已知:
- Ground-truth reasoning chain (entity hops)
- Ground-truth supersession pairs (OLD fact, NEW fact)
- Ground-truth answer

**Use across phases**:
- Phase 1 GT: supersession pairs → candidate recall, pool size (W2)
- Phase 2.a GT: reasoning chain → chain recall, alt chain coverage (W1)
- Phase 2.b GT: per-hop supersession → verdict accuracy (W1)
- Phase 3 ablation: end-to-end MH accuracy (W3)

### B.6.2 Validation script scaffold (Claude Code 直接可實作)

```python
# validation/phase2_eval.py (W1 priority)
def evaluate_phase2_standalone(hipporag: HippoRAG, fc_mh_dataset):
    """
    Phase 2 standalone mode validation.
    Phase 1 cache disabled — Phase 2 does on-the-fly candidate lookup.
    """
    gt_chains = load_gt_reasoning_chains(fc_mh_dataset)
    gt_supersessions = load_gt_supersession_pairs(fc_mh_dataset)
    
    # Run indexing without Phase 1 cache
    hipporag.index(
        fc_mh_dataset.passages,
        enable_phase1_v2=True,        # proposition extraction only
        enable_phase1_cache=False     # NO candidate pre-computation
    )
    
    # Phase 2.a metrics
    chain_recall_at_5 = 0
    chain_precision_at_1 = 0
    alt_coverage = 0
    
    # Phase 2.b metrics
    verdict_correct = 0
    verdict_total = 0
    all_detected_per_Q = 0
    pool_sizes = []
    llm_call_counts = []
    
    # End-to-end metric
    em_correct = 0
    
    for query_obj in fc_mh_dataset.queries:
        query = query_obj.text
        gt_chain = gt_chains[query_obj.id]
        gt_sups = gt_supersessions[query_obj.id]
        
        # Run full Phase 2 pipeline
        result = hipporag.retrieve_and_qa(
            query,
            enable_phase2_chain_detection=True,
            enable_phase3_v2_enriched=True
        )
        
        # Phase 2.a metrics
        if any(chain_matches(c, gt_chain) for c in result.candidate_chains):
            chain_recall_at_5 += 1
        if result.candidate_chains and chain_matches(result.candidate_chains[0], gt_chain):
            chain_precision_at_1 += 1
        if is_KU_query(query_obj):
            if has_gt_old_and_new_chain(result.candidate_chains, gt_chain, gt_sups):
                alt_coverage += 1
        
        # Phase 2.b metrics
        all_hops_correct = True
        for hop in gt_chain.hops:
            expected_verdict = compute_expected_verdict(hop, gt_sups)
            actual_verdict = result.verdicts.get(hop.proposition_id)
            if actual_verdict and actual_verdict.status == expected_verdict:
                verdict_correct += 1
            else:
                all_hops_correct = False
            verdict_total += 1
        if all_hops_correct and gt_chain.has_KU_hops:
            all_detected_per_Q += 1
        
        pool_sizes.extend(result.metadata.pool_sizes)
        llm_call_counts.append(result.metadata.llm_call_count_phase2)
        
        # End-to-end EM
        if result.answer == query_obj.gold_answer:
            em_correct += 1
    
    n = len(fc_mh_dataset.queries)
    n_KU = count_KU_queries(fc_mh_dataset)
    return {
        # Phase 2.a
        'chain_recall_at_5': chain_recall_at_5 / n,
        'chain_precision_at_1': chain_precision_at_1 / n,
        'alt_chain_coverage': alt_coverage / n_KU,
        # Phase 2.b
        'per_hop_verdict_accuracy': verdict_correct / verdict_total,
        'all_detected_per_Q': all_detected_per_Q / n_KU,
        'pool_median': np.median(pool_sizes),
        'llm_calls_per_query_mean': np.mean(llm_call_counts),
        # End-to-end
        'em_accuracy': em_correct / n,
    }

# validation/phase1_eval.py (W2 priority)
def evaluate_phase1_v2(hipporag, fc_mh_dataset):
    """W2: validate Phase 1 cache provides same recall + latency reduction."""
    gt_supersessions = load_gt_supersession_pairs(fc_mh_dataset)
    
    hipporag.index(fc_mh_dataset.passages, enable_phase1_v2=True, enable_phase1_cache=True)
    
    # Candidate Recall@K
    hits = 0
    for (p_old_gt, p_new_gt) in gt_supersessions:
        p_new_ours = find_matching_proposition(hipporag, p_new_gt)
        p_old_ours = find_matching_proposition(hipporag, p_old_gt)
        if p_old_ours and p_old_ours.id in (p_new_ours.candidate_supersedees or []):
            hits += 1
    candidate_recall = hits / len(gt_supersessions)
    
    pool_sizes = [
        len(p.candidate_supersedees or [])
        for p in hipporag.propositions.values()
    ]
    
    return {
        'candidate_recall_at_K': candidate_recall,
        'pool_median': np.median(pool_sizes),
        'pool_max': np.max(pool_sizes),
    }

# validation/phase3_ablation.py (W3 priority)
def phase3_ablation(hipporag, fc_mh_dataset):
    """W3: validate enriched output vs v1 scaffold, decompose evidence contribution."""
    configs = [
        ('vanilla', {'enable_phase3_v2_enriched': False, 'enable_phase3_v1_scaffold': False}),
        ('v1_scaffold', {'enable_phase3_v2_enriched': False, 'enable_phase3_v1_scaffold': True}),
        ('v2_passages_only', {'enable_phase3_v2_enriched': True, 'evidence_types': ['passages']}),
        ('v2_passages_hints', {'enable_phase3_v2_enriched': True, 'evidence_types': ['passages', 'hints']}),
        ('v2_passages_log', {'enable_phase3_v2_enriched': True, 'evidence_types': ['passages', 'log']}),
        ('v2_full', {'enable_phase3_v2_enriched': True, 'evidence_types': ['passages', 'hints', 'log']}),
    ]
    results = {}
    for name, cfg in configs:
        results[name] = run_end_to_end_em(hipporag, fc_mh_dataset, **cfg)
    return results
```

### B.6.3 Phase-level gates (cannot proceed without passing)

| Phase | Gate (v2.0.1) | If fail |
|---|---|---|
| Phase 2 standalone (W1) | Chain Recall@5 ≥ 80% AND Per-hop verdict ≥ 80% AND end-to-end MH ≥ 50% | Iterate path enum / pool construction / verdict prompt |
| Phase 1 cache (W2) | Candidate Recall ≥ 85% AND pool median ≤ 10 AND ≥ 30% latency reduction vs standalone | Tune τ_loose / K; if persistent fail, accept "Phase 1 not beneficial" and skip it (paper note) |
| Phase 3 (W3) | End-to-end FC-MH MH ≥ 55% AND non-KU 退步 < 2pp AND A3.2 non-inferior to v1 scaffold | Investigate which evidence type underperforms |

---

## §B.7 Implementation Order & Weekly Gates (v2.0.1: Phase 2 First)

| Week | Focus | Deliverable | Gate |
|---|---|---|---|
| **W1** | **Phase 2 standalone** (chain detection + verdict, on-the-fly candidate lookup, NO Phase 1 cache) | `phase2a/`, `phase2b/` modules + `validation/phase2_eval.py` + first FC-MH 6k full pipeline result | Chain Recall@5 ≥ 80% AND Per-hop verdict ≥ 80% AND end-to-end MH ≥ 50% |
| **W2** | **Phase 1 cache** (proposition extraction + candidate annotation) — purely as offline optimization | `phase1/` module + `validation/phase1_eval.py` + Phase 2 with cache enabled latency comparison | Candidate Recall ≥ 85% AND pool median ≤ 10 AND ≥ 30% latency reduction |
| **W3** | **Phase 3 enriched output** + Claim 2 ablation (A3.1-A3.5 assertions) | `phase3/` module + `validation/phase3_ablation.py` results | A3.1 hits +5pp, A3.2 non-inferior to v1 scaffold, A3.4 non-KU 退步 < 2pp |
| **W4** | 32k scaling + LongMemEval non-degradation check | 32k results + LongMemEval baseline measurement | 32k MH reasonable scaling; LongMemEval 不退 > 3pp |
| **W5** | Writing kickoff + 64k scaling | §C.6 / §C.7 draft + 64k results | 64k MH ≥ 25% |
| **W6** | Paper draft finalization + final ablations | Full paper draft (Ch.3 + Ch.4 + ablations) | — |
| **W7** | Buffer for re-runs / advisor review | Final submission | — |

**Contingency plans**:
- W1 Phase 2 standalone fail → 1 extra week iteration; if persistent, escalate (may need to revisit Q1 mechanism choice)
- W2 Phase 1 cache no benefit → **acceptable** — paper notes "Phase 1 offline precompute does not yield measurable improvement under our setup; on-the-fly query-time lookup suffices". Don't force Phase 1 if not beneficial.
- W3 enriched output fail → fallback to v1 scaffold + P2 v2 (still strong contribution; Claim 2 reframe abandoned with note)
- W4 32k scaling degrades severely → paper limits scope to 6k (with explicit disclosure)

---

## §B.8 PropRAG / Mem0 / Zep 角色重新定位

### B.8.1 PropRAG (EMNLP 2025)

| 層 | v2.0.1 定位 |
|---|---|
| Engineering | (參考 codebase pattern, 我們 reimplement in HippoRAG-v2) |
| Method concept | **Inspiration only** — proposition representation 啟發我們的 Phase 1 提粒度與 Phase 2.b context-rich pool; **beam search 沒採用** (我們用 bounded path enumeration + scoring, 更輕量) |
| Paper narrative | §C.2 cite 一次: "Inspired by recent work on proposition-level retrieval (PropRAG, etc.) for multi-hop QA, we adopt proposition as the internal memory representation for conflict detection while preserving HippoRAG-v2's raw-passage return paradigm." 不 framing 為 method baseline |

→ **Framing implication**: 我們 paper 仍 100% conversational agent memory community, PropRAG 是 method inspiration 之一, 不跑 baseline。

### B.8.2 Mem0 (ECAI 2025)

| 維度 | Mem0 限制 | v2.0.1 解法 |
|---|---|---|
| Detection locus | write-time only | v2 主 verdict 在 query-time, Phase 1 只 cache |
| Pool size | top-k=5 (small but write-time) | v2 small-pool 但 query-anchored (chain-restricted, K_pool=10) |
| Multi-hop coherence | 各 hop 獨立 judge, accumulation lossy | v2 chain context → 同 query 多 hops 在同 LLM context 下判 |

→ **Paper §C.4 Diagnostic**: 用 Mem0 41/100 數字, 對比 v2 target ≥ 60/100。

### B.8.3 Zep (arXiv 2024)

| 維度 | Zep 限制 | v2.0.1 解法 |
|---|---|---|
| Temporal annotation | 假設有 explicit temporal qualifier | v2 用 chunk turn_idx 作 implicit timestamp |
| Exclusion detection | 每 fact 獨立 judge | v2 chain-restricted, 同 chain 內 propositions 並列判斷 |
| FC degenerate to deterministic | 38% per-hop | v2 不依賴 explicit temporal markers, 仍能 leverage metadata in chain context |

→ **Paper §C.4 Diagnostic**: Zep timestamp 在 isolated fact judge 失效, 但在 chain context + LLM 一起判時有用。

### B.8.4 LightMem / EMG-RAG / KEDKG

(維持 v1.1 §C.2 描述) v2 與這些的差異: 都是 fact-level / write-time-only / rule-or-LLM-shortcut, v2 是 chain-aware / query-time critical detection。

---

## §B.9 Open Design Questions (deferred to implementation)

| Open Q | Default | When to revisit |
|---|---|---|
| `tau_loose` (Phase 1 candidate cosine threshold) | 0.7 | W2, after Candidate Recall measured |
| `region_topK` (Phase 2.a active region size) | 50 | W1, balance chain recall vs latency |
| `enum_beam_width` (Phase 2.a path enum beam) | 8 | W1, similar |
| Verdict prompt phrasing | Initial draft in B.3.2.2 | W1, iterate based on verdict accuracy |
| Phase 3 evidence weighting (passages vs hints vs log) | All included | W3, A3.3 ablation |
| Fallback when no chain found | Pure HippoRAG-v2 PPR retrieval | W1 stress test |
| Hedged language threshold for low-confidence verdicts | confidence='low' triggers hedge | W3 |
| Should `find_corresponding_propositions` use stricter heuristic (e.g., entity overlap ≥ 2)? | overlap ≥ 1 default | W1 if too many false pairs |
| Phase 1 cache value | TBD (W2 gate) | W2 — may abandon if no benefit |

---

## §B.10 Skeleton Summary Table (v2.0.1)

| Phase | Sub-phase | Role | Locked decision | Key file |
|---|---|---|---|---|
| 1 | proposition extraction | upgrade memory granularity | G2 | `phase1/proposition_extractor.py` |
| 1 | candidate annotation | OFFLINE CACHE for Phase 2 (optional) | Mechanism A+B union, K=20, **no LLM, no easy-case** | `phase1/candidate_annotator.py` |
| 2.a | active region | scope chain search | PPR top-50 + query-entity 1-hop | `phase2a/active_region.py` |
| 2.a | path enumeration | discover candidate chains | Bounded beam width 8, depth 3, score-based top-M | `phase2a/path_enumeration.py` |
| 2.b | chain-restricted verdict | THE critical detection (only LLM in Phase 2) | Small pool ≤ 10, chain context, opportunistic γ via pool | `phase2b/verdict.py` |
| 3 | enriched context | return rich evidence | passages + hints (A4) + log (B2), prompt unchanged, hedged for low-conf | `phase3/enriched_context_renderer.py` |

**v2.0.1 from v2.0**:
- ❌ Phase 1 easy-case detection (removed)
- ❌ Phase 2.a Step 4 LLM tail validate (removed)
- ❌ Phase 2.a γ chain-level pairing (removed; γ moved to Phase 2.b pool as opportunistic)
- ✅ Phase 2 first implementation order
- ➕ Hedged language for low-confidence cases
- ➕ Coverage limitations honesty (§B.12)

---

## §B.11 Quick-Start for Claude Code (v2.0.1)

> 給 Claude Code 開工的最小指引

1. **Read order**: §B.0 (architecture overview) → §B.1 (where hooks plug in) → **§B.3 (Phase 2 spec, 主戰場)** → §B.6 (validation) → §B.11 (this) → §B.7 (weekly gates) → §B.12 (limitations)
2. **Start with: W1 Phase 2 standalone implementation** (`phase2a/` + `phase2b/` + `validation/phase2_eval.py`)
3. **W1 explicit DON'T**:
   - DON'T implement easy-case detection / functional whitelist / cardinality classification
   - DON'T add LLM tail validate in Phase 2.a
   - DON'T require Phase 1 to be implemented — Phase 2 must work standalone
   - DON'T filter superseded propositions before Phase 2.b verdict
4. **W1 explicit DO**:
   - DO use on-the-fly candidate lookup in Phase 2.b pool construction
   - DO test on FC-MH 6k with full ground-truth chain comparison
   - DO log every verdict event with confidence and pool size for offline analysis
   - DO ensure Phase 2.a is supersession-AGNOSTIC (both old and new chains discoverable)
5. **Critical invariants throughout**:
   - Phase 1 NO LLM (W2 onward); NO easy-case detection (ever)
   - Phase 2.a supersession-AGNOSTIC; no LLM
   - Phase 2.b pool ≤ 10 strict
   - Phase 3 prompt template unchanged
6. **Feature flags**:
   ```
   enable_phase1_v2: bool = False           # W1; W2 onward True
   enable_phase1_cache: bool = False        # W1; W2 if gate passed
   enable_phase2_chain_detection: bool = True   # W1 onward
   enable_phase3_v2_enriched: bool = False  # W3 onward
   enable_phase3_v1_scaffold: bool = False  # only for A3.2 ablation
   ```
7. **W1 ablations to expose**:
   - Vanilla HippoRAG-v2 (all flags off)
   - Phase 2 standalone only (no Phase 3 enrich) — main W1 deliverable
   - Phase 2.a only (no Phase 2.b verdict; just chain-based passage rerank) — sanity baseline
8. **Data persistence**:
   - `proposition_index.json`: id → Proposition (W1 partial: extraction only; W2 full: with candidate_supersedees)
   - `graph.graphml`: KG (extended with proposition nodes)
   - **No `supersession_index.json` written at indexing time** — supersession edges are query-time artifacts
9. **Logging**: log every chain enumeration result, every verdict event with confidence + reason, every pool composition (Phase 1 contribution vs on-the-fly vs γ pair)

---

## §B.12 Coverage Limitations Honesty Box

> **這節必須寫進 paper §C.5.2 Limitations**, 也是 W1 onward Claude Code 看到 case D 行為時的 expected behavior reference。

v2.0.1 設計有 4 種 (p_old, p_new) coverage 情況, 我們明確 disclose 各自處理:

| Case | KG 狀態 | Phase 2.b 行為 | Paper 表達 |
|---|---|---|---|
| **A** | 只有 new (沒 old 進過 KG) | Pool 空或 no relevant candidate → verdict 'current' high-conf | ✅ 正確處理 |
| **B** | new + old 都在 KG, candidate lookup 成功 | γ via pool → verdict 可比較 | ✅ 主要 contribution case |
| **C** | new + old 都在 KG, candidate lookup 失敗 (Phase 1 漏 + on-the-fly cosine 也漏) | Pool 不完整 → verdict 可能誤判 'current' (medium/low confidence) | ⚠️ **partial mitigation**: hedged language in Phase 3 if confidence < high; admission in §C.5.2 |
| **D** | 只有 old 在 KG (new 從未被 extract 進 propositions) | 永遠無法偵測 | ❌ **honest limitation**: 寫進 §C.5.2 |

**Case D 的 root cause**:
- OpenIE / proposition extraction 在某些 chunk 沒抽到對應 proposition
- 這是 representation coverage 問題, 不是我們 detection mechanism 問題
- Quantification: Method v1 §13.2 顯示 30% missed 是 "OpenIE 完全沒抽到 chain_old triple"; 同類問題可能影響 proposition 抽取

**Paper §C.5.2 wording (suggestion)**:
> "Our method's detection coverage is upper-bounded by the proposition extraction quality. When a superseder fact fails to be extracted as a proposition during indexing (estimated ~XX% of cases based on FC-MH 6k diagnostic), no downstream mechanism can recover the supersession signal. This is a representation coverage limitation shared by all KG-based memory methods, and is orthogonal to our query-anchored detection contribution. Future work could address this via more robust proposition extraction prompts or cross-pass extraction."

---

## §B.13 Concrete Dependency Graph & Data Flow (v2.0.1)

```
Indexing (offline):
─────────────────────────────────────────────────────
Passages → I1 OpenIE → I2 Embed → I2.5 Propositions
                                       ↓
                              I3c proposition KG nodes
                                       ↓
                              I4 synonymy edges
                                       ↓
                       [OPTIONAL W2] I4.5 candidate annotation
                                       ↓
                              I5 save indexes


Query-time (per query):
─────────────────────────────────────────────────────
Query → O1 fact scoring → O3 seed weights → O4 PPR
                                                ↓
                                       O4.5 Active region 
                                                ↓
                                       O4.6 Path enumeration (Phase 2.a)
                                                ↓
                                            top-M chains
                                                ↓
                                       O4.7 Verdict (Phase 2.b)
                                            ├── pool ← Phase 1 cache (if W2+)
                                            ├── pool ← on-the-fly lookup (always)
                                            └── pool ← γ (other chains)
                                                ↓
                                            verdicts per proposition
                                                ↓
                                       Phase 2 → Phase 3 handoff
                                                ↓
                                       Filter passages by verdict
                                                ↓
                                       O5.5 render enriched context
                                          ├── filtered passages
                                          ├── reasoning hints (chain)
                                          └── change log (verdicts)
                                                ↓
                                       O6 rag_qa (prompt UNCHANGED)
                                                ↓
                                            Final answer
```

---

**End of Method Design v2.0.1 Specification**

Sign-off: This document supersedes v2.0. Source of truth for implementation. Updates to method design must be reflected here first before code change.

**Key learning from v2.0 → v2.0.1**: Repeated reviewer pushback against rule-based shortcuts (functional whitelist) was correct. The clean architecture has only ONE LLM call type in Phase 2 (verdict), avoids any a priori relation classification, and works standalone without Phase 1 dependency. This minimalism is both methodologically cleaner and easier to defend in writing.
