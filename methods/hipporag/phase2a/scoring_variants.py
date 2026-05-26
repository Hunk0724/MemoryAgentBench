"""Phase 2.a — Scoring variants for ablation (T1).

Three variants of path scoring, all returning (score, breakdown_dict) tuples:

  adhoc(default — backwards compat)
    = Σ cosine(p.emb, q) + 0.3·coherence + 0.2·ppr_coverage - 0.1·len
    Original v2.0.2 hand-designed formula (no literature cite).

  pure_relevance(strawman)
    = Σ cosine(p.emb, q)
    Same relevance term as adhoc but WITHOUT coherence/ppr/length adjustments.
    Tests if our ad-hoc structure terms add anything.

  proprag_strict(principled)
    = cosine(embedding_model.encode(" ".join(p.text for p in chain)), q)
    Whole-chain text concatenated, re-encoded, single cosine with query.
    Matches PropRAG (Liu et al., EMNLP 2025) `embedding_combination="concatenate"`.
    No structure terms.

All variants support BATCHED computation for efficiency, especially
proprag_strict which calls the embedding model (slow if not batched).

Selection via `global_config.phase2a_scoring_variant ∈ {adhoc, pure_relevance, proprag_strict}`.
See docs/T1_scoring_variants_design.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ..phase1.data_structures import Proposition


# ────────────────────────────────────────────────────────────────────────────
# Per-variant single-chain scorers
# ────────────────────────────────────────────────────────────────────────────


def _score_adhoc(
    prop_ids: List[str],
    propositions: Dict[str, Proposition],
    query_emb_flat: np.ndarray,
    prop_ppr_mass: Dict[str, float],
    shared_entity_path: List[Set[str]],
) -> Tuple[float, dict]:
    """Original v2.0.2 ad-hoc formula (backwards-compat default)."""
    if not prop_ids:
        return 0.0, {"relevance": 0.0, "coherence": 0.0,
                     "length_penalty": 0.0, "ppr_coverage": 0.0}

    relevance = 0.0
    for pid in prop_ids:
        p = propositions[pid]
        if p.embedding:
            relevance += float(np.dot(
                np.asarray(p.embedding, dtype="float32"), query_emb_flat
            ))

    if len(prop_ids) <= 1:
        coherence = 0.0
    else:
        total_shared = sum(len(s) for s in shared_entity_path)
        coherence = total_shared / max(len(shared_entity_path), 1)

    length_penalty = -0.1 * len(prop_ids)
    ppr_coverage = sum(prop_ppr_mass.get(pid, 0.0) for pid in prop_ids)

    total = relevance + 0.3 * coherence + 0.2 * ppr_coverage + length_penalty
    return total, {
        "relevance": relevance,
        "coherence": coherence,
        "length_penalty": length_penalty,
        "ppr_coverage": ppr_coverage,
        "variant": "adhoc",
    }


def _score_pure_relevance(
    prop_ids: List[str],
    propositions: Dict[str, Proposition],
    query_emb_flat: np.ndarray,
    prop_ppr_mass: Dict[str, float],
    shared_entity_path: List[Set[str]],
) -> Tuple[float, dict]:
    """Σ cosine(p.emb, q) only — strawman without ad-hoc structure terms."""
    if not prop_ids:
        return 0.0, {"relevance": 0.0, "variant": "pure_relevance"}
    relevance = 0.0
    for pid in prop_ids:
        p = propositions[pid]
        if p.embedding:
            relevance += float(np.dot(
                np.asarray(p.embedding, dtype="float32"), query_emb_flat
            ))
    return relevance, {"relevance": relevance, "variant": "pure_relevance"}


# Note: proprag_strict needs the embedding model + batched encoding.
# Single-chain interface still provided for callers that don't batch,
# but inefficient — production beam search should use score_chains_batch.

def _score_proprag_strict_single(
    prop_ids: List[str],
    propositions: Dict[str, Proposition],
    query_emb_flat: np.ndarray,
    prop_ppr_mass: Dict[str, float],
    shared_entity_path: List[Set[str]],
    embedding_model: Any = None,
) -> Tuple[float, dict]:
    """cosine(encode(concat_chain_text), query_emb).

    Pure PropRAG `concatenate` mode. No structure terms.
    Single-chain — inefficient (calls model.batch_encode for one chain);
    prefer score_chains_batch when scoring many chains at once.
    """
    if not prop_ids or embedding_model is None:
        return 0.0, {"relevance": 0.0, "variant": "proprag_strict",
                     "error": "no_embedding_model" if embedding_model is None else "empty_chain"}
    chain_text = " ".join(propositions[pid].text for pid in prop_ids if pid in propositions)
    if not chain_text:
        return 0.0, {"relevance": 0.0, "variant": "proprag_strict"}
    chain_emb = embedding_model.batch_encode(
        [chain_text], norm=True, disable_tqdm=True
    )[0]
    chain_emb = np.asarray(chain_emb, dtype="float32").flatten()
    score = float(np.dot(chain_emb, query_emb_flat))
    return score, {"relevance": score, "variant": "proprag_strict"}


# ────────────────────────────────────────────────────────────────────────────
# Batched API — preferred for production beam search
# ────────────────────────────────────────────────────────────────────────────

def score_chains_batch(
    chain_records: List[dict],
    propositions: Dict[str, Proposition],
    query_embedding: np.ndarray,
    prop_ppr_mass: Dict[str, float],
    variant: str = "adhoc",
    embedding_model: Any = None,
) -> List[Tuple[float, dict]]:
    """Score a batch of chains under given variant.

    chain_records: list of dicts, each with keys 'prop_ids' (List[str])
                   and 'entities_path' (List[Set[str]]).

    Returns: list of (score, breakdown) tuples, parallel to input.
    """
    q = np.asarray(query_embedding, dtype="float32").flatten()

    if variant in ("adhoc", "pure_relevance"):
        scorer = _score_adhoc if variant == "adhoc" else _score_pure_relevance
        return [
            scorer(c["prop_ids"], propositions, q, prop_ppr_mass, c["entities_path"])
            for c in chain_records
        ]

    if variant == "proprag_strict":
        if embedding_model is None:
            raise ValueError(
                "proprag_strict requires embedding_model; pass via "
                "score_chains_batch(..., embedding_model=...). "
                "Threading: pass self.embedding_model from HippoRAG._v2_phase2_pipeline."
            )
        # Batch encode all chain texts at once
        chain_texts = []
        for c in chain_records:
            text = " ".join(
                propositions[pid].text
                for pid in c["prop_ids"]
                if pid in propositions
            )
            chain_texts.append(text if text else "<EMPTY>")
        # NV-Embed batch_encode; PropRAG default batch_size=8
        chain_embs = embedding_model.batch_encode(
            chain_texts, norm=True, disable_tqdm=True, batch_size=8
        )
        chain_embs = np.asarray(chain_embs, dtype="float32")
        if chain_embs.ndim == 1:
            chain_embs = chain_embs.reshape(1, -1)
        scores = chain_embs @ q  # dot product with normalized query
        out = []
        for i, s in enumerate(scores):
            out.append((float(s), {
                "relevance": float(s),
                "variant": "proprag_strict",
                "chain_text_chars": len(chain_texts[i]),
            }))
        return out

    raise ValueError(f"Unknown scoring variant: {variant!r}")
