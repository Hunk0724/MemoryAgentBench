"""Phase 2.a Step 2-3 — Bounded path enumeration + chain scoring (O4.6).

Spec §B.3.1.1 step 2-3.

Path = ordered sequence of propositions sharing entities.
Beam search over the active-region subgraph.

Critical invariant: SUPERSESSION-AGNOSTIC. Path enumeration does NOT
filter by supersession status. Both old-chain and new-chain variants
must be discoverable.

Connection rule (Q6 default per spec §B.3.1.2):
  - Two propositions are "connected" if they share ≥ 1 entity (substring,
    case-insensitive, both directions). Synonyms via synonymy edges are
    handled implicitly when caller provides a synonym-expanded entity set.
  - depth = #propositions in chain (not entity-hops)

Score = relevance + 0.3*coherence + 0.2*ppr_coverage + length_penalty
  - relevance = sum of cosine(p.emb, query.emb)
  - coherence = avg # of entities shared between consecutive props (normalized)
  - length_penalty = -0.1 * len(chain)
  - ppr_coverage = sum of prop_ppr_mass over chain
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from ..phase1.data_structures import Proposition
from ..utils.misc_utils import compute_mdhash_id
from .data_structures import Chain


# ────────────────────────────────────────────────────────────────────────────
# Entity matching helpers
# ────────────────────────────────────────────────────────────────────────────

def _norm_entity(e: str) -> str:
    return re.sub(r"\s+", " ", (e or "").strip().lower())


def _entity_overlap(p_a: Proposition, p_b: Proposition) -> Set[str]:
    """Return set of entity surface forms shared between two propositions.

    Lenient match: case-insensitive substring (both directions), min len 3.
    """
    a_ents = {_norm_entity(e): e for e in p_a.entities if len(e) >= 3}
    b_ents = {_norm_entity(e): e for e in p_b.entities if len(e) >= 3}
    shared = set()
    for ka, oa in a_ents.items():
        for kb, ob in b_ents.items():
            if ka == kb or ka in kb or kb in ka:
                # Prefer the longer surface form for display
                shared.add(oa if len(oa) >= len(ob) else ob)
    return shared


# ────────────────────────────────────────────────────────────────────────────
# Score function
# ────────────────────────────────────────────────────────────────────────────

def score_chain(
    prop_ids: List[str],
    propositions: Dict[str, Proposition],
    query_embedding: np.ndarray,
    prop_ppr_mass: Dict[str, float],
    shared_entity_path: List[Set[str]],
) -> Tuple[float, dict]:
    """Compute chain score + breakdown.

    Returns (score, breakdown_dict).
    """
    if not prop_ids:
        return 0.0, {"relevance": 0, "coherence": 0, "length_penalty": 0, "ppr_coverage": 0}

    q = np.asarray(query_embedding, dtype="float32").flatten()

    # relevance: sum of prop-query cosine
    relevance = 0.0
    for pid in prop_ids:
        p = propositions[pid]
        if p.embedding:
            relevance += float(np.dot(np.asarray(p.embedding, dtype="float32"), q))

    # coherence: normalized average # entities shared between consecutive props
    if len(prop_ids) <= 1:
        coherence = 0.0
    else:
        total_shared = sum(len(s) for s in shared_entity_path)
        coherence = total_shared / len(shared_entity_path)

    # length penalty (favor compact chains, but not too short for multi-hop queries)
    length_penalty = -0.1 * len(prop_ids)

    # ppr coverage: sum of prop_ppr_mass
    ppr_coverage = sum(prop_ppr_mass.get(pid, 0.0) for pid in prop_ids)

    total = relevance + 0.3 * coherence + 0.2 * ppr_coverage + length_penalty
    breakdown = {
        "relevance": relevance,
        "coherence": coherence,
        "length_penalty": length_penalty,
        "ppr_coverage": ppr_coverage,
    }
    return total, breakdown


# ────────────────────────────────────────────────────────────────────────────
# Beam search
# ────────────────────────────────────────────────────────────────────────────

def enumerate_candidate_chains(
    query_embedding: np.ndarray,
    active_propositions: Dict[str, Proposition],
    prop_ppr_mass: Dict[str, float],
    M: int = 5,
    L: int = 3,
    beam_width: int = 8,
    n_seed: int = 20,
    query_entities: Optional[Set[str]] = None,
    scoring_variant: str = "adhoc",
    embedding_model: object = None,
) -> List[Chain]:
    """Bounded beam-search path enumeration over active region.

    Args:
        query_embedding: NV-Embed-v2 query embedding (normalized, 4096-d)
        active_propositions: dict prop_id → Proposition (active region only)
        prop_ppr_mass: dict prop_id → mass (proxy or real PPR)
        M: max chains to return (top-M by score)
        L: max chain depth (= max # propositions)
        beam_width: beam search width per depth
        n_seed: number of seed propositions to start beams from (top by mass)
        query_entities: optional, used to PREFER chains starting near query
        scoring_variant: {"adhoc"(default), "pure_relevance", "proprag_strict"}
            See scoring_variants.py.
        embedding_model: required for "proprag_strict", ignored otherwise.

    Returns:
        List[Chain] sorted by score descending, length ≤ M.
    """
    if not active_propositions or M <= 0:
        return []

    # Lazy import to avoid circular dep
    from .scoring_variants import score_chains_batch

    # ─── Step 2a: seed beam with top-n_seed propositions by mass ───
    seed_pids = sorted(active_propositions.keys(),
                        key=lambda pid: -prop_ppr_mass.get(pid, 0.0))[:n_seed]

    # Each beam entry: dict with prop_ids (ordered), entities_path (list of sets)
    initial_beam = []
    for pid in seed_pids[:beam_width]:
        initial_beam.append({
            "prop_ids": [pid],
            "entities_path": [],  # empty for depth=1
            "entities_seen": {_norm_entity(e) for e in active_propositions[pid].entities},
        })

    # All chains collected across depths (depth-1 results are valid too)
    all_chains: List[dict] = [dict(b) for b in initial_beam]

    # ─── Step 2b: extend beams depth by depth ───
    beam = initial_beam
    for depth in range(2, L + 1):
        new_candidates = []
        for path in beam:
            last_pid = path["prop_ids"][-1]
            last_p = active_propositions[last_pid]
            # Find connected props in active region
            for next_pid, next_p in active_propositions.items():
                if next_pid in path["prop_ids"]:
                    continue  # avoid cycles
                shared = _entity_overlap(last_p, next_p)
                if not shared:
                    continue
                new_path = {
                    "prop_ids": path["prop_ids"] + [next_pid],
                    "entities_path": path["entities_path"] + [shared],
                    "entities_seen": path["entities_seen"] | {_norm_entity(e) for e in next_p.entities},
                }
                new_candidates.append(new_path)
        if not new_candidates:
            break
        # Score candidates (batched — esp. important for proprag_strict)
        # and keep top-beam_width.
        scored = score_chains_batch(
            new_candidates, active_propositions, query_embedding, prop_ppr_mass,
            variant=scoring_variant, embedding_model=embedding_model,
        )
        scored_candidates = list(zip([s for s, _ in scored], new_candidates))
        scored_candidates.sort(key=lambda x: -x[0])
        beam = [c for _, c in scored_candidates[:beam_width]]
        all_chains.extend([dict(c) for c in beam])

    # ─── Step 3: score all collected chains, dedup, return top-M ───
    seen_keys = set()
    deduped: List[dict] = []
    for cand in all_chains:
        key = tuple(sorted(cand["prop_ids"]))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(cand)

    # Batched final scoring
    scored_final = score_chains_batch(
        deduped, active_propositions, query_embedding, prop_ppr_mass,
        variant=scoring_variant, embedding_model=embedding_model,
    )
    final = []
    for cand, (score, breakdown) in zip(deduped, scored_final):
        chain_id = compute_mdhash_id(
            content="|".join(cand["prop_ids"]),
            prefix="chain-",
        )
        final.append(Chain(
            id=chain_id,
            proposition_ids=cand["prop_ids"],
            shared_entity_path=cand["entities_path"],
            score=score,
            score_breakdown=breakdown,
        ))

    final.sort(key=lambda c: -c.score)
    return final[:M]
