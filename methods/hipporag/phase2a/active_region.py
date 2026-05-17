"""Phase 2.a Step 1 — Active region identification (O4.5).

Spec §B.3.1.1 step 1.

Input:
  - query (text)
  - propositions (dict prop_id → Proposition)
  - prop_ppr_mass (dict prop_id → float) — pre-computed proposition-level PPR
    mass. v2.0.2 Q5 lock: this comes from `mean(entity_ppr)` per spec
    (aggregator computed by caller; this module just consumes the dict).
  - query_entities (optional set of entity strings linked to KG) — augments
    active region with 1-hop propositions

Output:
  - Set of proposition IDs to consider for path enumeration

Invariants:
  - Supersession-AGNOSTIC (no filtering by supersession status)
  - No LLM call
"""
from __future__ import annotations

from typing import Dict, Optional, Set

from ..phase1.data_structures import Proposition


def identify_active_region(
    query: str,
    propositions: Dict[str, Proposition],
    prop_ppr_mass: Dict[str, float],
    query_entities: Optional[Set[str]] = None,
    region_topK: int = 50,
) -> Set[str]:
    """Identify the set of proposition IDs forming the "active region" for
    chain enumeration.

    Algorithm:
      1. Top-K propositions by prop_ppr_mass (descending)
      2. (Optional) Augment with all propositions that mention any
         `query_entities` (1-hop expansion)
      3. Return union of (1) + (2)

    Args:
        query: user query text (not used in this function directly; reserved
               for future query-aware scoring)
        propositions: all propositions in KG, keyed by prop_id
        prop_ppr_mass: pre-computed mass per proposition. If a prop is missing
                       from this dict, it gets mass=0.0
        query_entities: optional set of entity surface forms linked to query
                        (typically from NER or query embedding → entity)
        region_topK: number of top propositions to take by mass

    Returns:
        Set of proposition IDs in active region.
    """
    # Step 1: top-K by mass
    ranked = sorted(
        propositions.keys(),
        key=lambda pid: -prop_ppr_mass.get(pid, 0.0),
    )
    active: Set[str] = set(ranked[:region_topK])

    # Step 2: 1-hop expansion via query entities
    if query_entities:
        ents_norm = {e.lower() for e in query_entities if len(e) >= 3}
        for pid, p in propositions.items():
            if pid in active:
                continue
            p_ents_norm = {e.lower() for e in p.entities if len(e) >= 3}
            # Substring match either direction (handles case + spacing variance)
            if any(any(qe == pe or qe in pe or pe in qe for pe in p_ents_norm)
                   for qe in ents_norm):
                active.add(pid)

    return active


def compute_prop_ppr_mass_from_entity_ppr(
    propositions: Dict[str, Proposition],
    entity_ppr: Dict[str, float],
    aggregation: str = "mean",
) -> Dict[str, float]:
    """Aggregate entity-level PPR scores to proposition-level mass.

    Q5 locked: mean default, max as ablation variant.

    Args:
        propositions: all propositions, keyed by prop_id
        entity_ppr: dict entity_node_id (or entity surface form) → PPR score
        aggregation: 'mean' (default) or 'max'

    Returns:
        Dict prop_id → mass
    """
    import statistics
    out: Dict[str, float] = {}
    for pid, p in propositions.items():
        # Use entity_node_ids when populated (W1.2+ I3c); fallback to entity surface
        keys = p.entity_node_ids if p.entity_node_ids else p.entities
        scores = [entity_ppr.get(k, 0.0) for k in keys if k]
        if not scores:
            out[pid] = 0.0
            continue
        if aggregation == "max":
            out[pid] = max(scores)
        else:  # mean
            out[pid] = statistics.mean(scores)
    return out


def compute_prop_mass_proxy_from_query_cosine(
    propositions: Dict[str, Proposition],
    query_embedding,
) -> Dict[str, float]:
    """Dry-test / W1.2 proxy: use proposition-query cosine as mass surrogate.

    NOT the real PPR aggregation — this is a temporary substitute for the
    W1.2 dry-test where we don't have full HippoRAG.retrieve() flow running
    yet. Real PPR integration comes in W1.3 when wiring into retrieve().

    Args:
        propositions: all propositions (each must have .embedding populated)
        query_embedding: 1-d numpy array, normalized

    Returns:
        Dict prop_id → cosine (capped at 0 below, since cosine on normalized
        vectors ∈ [-1, 1] but PPR mass should be ≥ 0).
    """
    import numpy as np
    out: Dict[str, float] = {}
    q = np.asarray(query_embedding).astype("float32").flatten()
    for pid, p in propositions.items():
        if not p.embedding:
            out[pid] = 0.0
            continue
        emb = np.asarray(p.embedding, dtype="float32")
        out[pid] = max(0.0, float(np.dot(emb, q)))
    return out
