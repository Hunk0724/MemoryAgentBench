"""Phase 2.b dynamic candidate lookup (v2.0.2 §B.3.2.1).

On-the-fly retrieval of candidate (potential predecessor / superseder)
propositions for a focal proposition. W1 uses this as PRIMARY pool source
(Phase 1 candidate cache is W2+ optional optimization).

Mechanisms (per spec §B.3.2.1, mirrors I4.5 candidate annotation algorithm):
  1. Entity overlap (with synonyms via shared entity tokens)
  2. Cosine similarity (τ_loose = 0.7)
  3. Time-filter by chunk_idx ordering (before/after focal proposition)

Note: synonymy support delegated to caller — we use string-level overlap
on Proposition.entities (post-W2/I3c, entity_node_ids would let us tap
HippoRAG synonymy edges).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from ..phase1.data_structures import Proposition


def _norm(e: str) -> str:
    return re.sub(r"\s+", " ", (e or "").strip().lower())


def _ts_le(ts_a, ts_b) -> bool:
    """Tuple lex compare: ts_a <= ts_b. Both (chunk_idx, in_chunk_pos)."""
    return tuple(ts_a) <= tuple(ts_b)


def _ts_lt(ts_a, ts_b) -> bool:
    return tuple(ts_a) < tuple(ts_b)


def dynamic_candidate_lookup(
    focus: Proposition,
    all_propositions: Dict[str, Proposition],
    direction: str = "any",           # "before" / "after" / "any"
    tau_loose: float = 0.7,
    K: int = 20,
) -> Set[str]:
    """Find candidate propositions related to `focus` via entity overlap and/or
    embedding cosine. Returns top-K by combined score.

    Mechanism A (entity-overlap):
      - Find all propositions sharing ≥ 1 entity with focus (substring match)
    Mechanism B (cosine similarity):
      - Find propositions with cosine(focus.emb, p.emb) ≥ tau_loose
    Union, then trim to top-K by combined score (entity_overlap + cosine).

    Time filter (v2.0.2 W1.3 default is "any"):
      - "before": only props with ts STRICTLY < focus.ts
      - "after":  only props with ts STRICTLY > focus.ts
      - "any":    NO time filter; returns timestamp-agnostic candidate set.
                  Use this when downstream code handles direction mechanically
                  from timestamps (Phase 2.b W1.3 redesign).

    Args:
        focus: the proposition we're looking up candidates for
        all_propositions: dict prop_id → Proposition (entire KG)
        direction: "before" / "after" / "any" (W1.3 default)
        tau_loose: cosine threshold for Mechanism B
        K: cap on returned candidates

    Returns:
        Set of prop_ids (excluding focus itself).
    """
    if not focus.embedding:
        return set()

    focus_emb = np.asarray(focus.embedding, dtype="float32")
    focus_ents = {_norm(e) for e in focus.entities if len(e) >= 3}

    # Time filter
    if direction == "before":
        time_filter = lambda p: _ts_lt(p.timestamp, focus.timestamp)
    elif direction == "after":
        time_filter = lambda p: _ts_lt(focus.timestamp, p.timestamp)
    else:  # "any" — no time filter
        time_filter = lambda p: True

    candidates_scored = []  # list of (pid, combined_score)
    for pid, p in all_propositions.items():
        if pid == focus.id:
            continue
        if not time_filter(p):
            continue

        # Mechanism A: entity overlap count
        p_ents = {_norm(e) for e in p.entities if len(e) >= 3}
        overlap_count = 0
        for fe in focus_ents:
            for pe in p_ents:
                if fe == pe or fe in pe or pe in fe:
                    overlap_count += 1
                    break  # don't double-count

        # Mechanism B: cosine
        cos_sim = 0.0
        if p.embedding:
            cos_sim = float(np.dot(focus_emb,
                                    np.asarray(p.embedding, dtype="float32")))

        # Only include if at least one mechanism fires
        include = (overlap_count > 0) or (cos_sim >= tau_loose)
        if not include:
            continue

        combined = overlap_count + cos_sim
        candidates_scored.append((pid, combined))

    # Trim to top-K by combined score
    candidates_scored.sort(key=lambda x: -x[1])
    return {pid for pid, _ in candidates_scored[:K]}
