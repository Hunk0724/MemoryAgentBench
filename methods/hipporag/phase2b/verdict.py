"""Phase 2.b chain-restricted supersession verdict (v2.0.2 W1.3 redesigned 2026-05-17).

DESIGN PIVOT from v2.0.2 §B.3.2 verdict prompt:
  - OLD: LLM does grouping + direction in one call → counterfactual content
    triggers world-knowledge bias, reverses direction, double-flags both
    chain_NEW + chain_OLD (W1.3 first dry-run: MH dropped to 11%)
  - NEW: LLM ONLY identifies contradicting pairs (no timestamps in prompt);
    direction decided MECHANICALLY in this module from proposition timestamps

Algorithm:
  For each unique proposition on candidate chains:
    1. Build timestamp-agnostic pool (≤ K_pool=10):
       - Phase 1 cache (W2+ optional)
       - dynamic_candidate_lookup(direction="any") — entity overlap + cosine
       - γ opportunistic — props from other candidate chains sharing entities
    2. LLM call: identify contradicting pool indices (no direction, no timestamps)
    3. Mechanical direction from timestamps:
       - Among contradicting pids, find those with strictly LATER timestamp
       - If found: status=superseded, confidence=high, superseder=latest
       - If contradicting found but all earlier/equal: status=current, confidence=low
       - If no contradicting: status=current, confidence=high
       - If LLM parse fail: status=uncertain, confidence=low
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from ..phase1.data_structures import Proposition
from ..phase2a.data_structures import Chain
from .data_structures import Verdict
from .dynamic_lookup import dynamic_candidate_lookup
from .prompts.verdict_prompt import build_verdict_messages, parse_verdict_response

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# γ opportunistic pairing (across chains)
# ────────────────────────────────────────────────────────────────────────────

def find_corresponding_propositions(
    focus: Proposition,
    own_chain: Chain,
    other_chain: Chain,
    propositions: Dict[str, Proposition],
    min_entity_overlap: int = 1,
) -> Set[str]:
    """Find propositions in other_chain that may be 'alternative versions' of focus.

    Heuristic: high entity overlap (≥ min_entity_overlap shared entities)
    AND not identical to focus.
    """
    def _norm_set(p):
        return {re.sub(r"\s+", " ", e.strip().lower()) for e in p.entities if len(e) >= 3}

    focus_ents = _norm_set(focus)
    out = set()
    for other_pid in other_chain.proposition_ids:
        if other_pid == focus.id:
            continue
        if other_pid not in propositions:
            continue
        other_p = propositions[other_pid]
        other_ents = _norm_set(other_p)
        # Substring-aware overlap
        overlap = 0
        for fe in focus_ents:
            for oe in other_ents:
                if fe == oe or fe in oe or oe in fe:
                    overlap += 1
                    break
        if overlap >= min_entity_overlap:
            out.add(other_pid)
    return out


# ────────────────────────────────────────────────────────────────────────────
# Top-K by relevance to focus
# ────────────────────────────────────────────────────────────────────────────

def _top_k_by_relevance(
    pool_pids: Set[str],
    focus: Proposition,
    propositions: Dict[str, Proposition],
    K: int = 10,
) -> List[str]:
    """Trim pool to top-K most relevant to focus by combined
    entity-overlap-count + embedding cosine.
    """
    if not focus.embedding:
        # Fall back to entity-overlap-only ordering
        focus_emb = None
    else:
        focus_emb = np.asarray(focus.embedding, dtype="float32")

    def _norm(e):
        return re.sub(r"\s+", " ", e.strip().lower())
    focus_ents = {_norm(e) for e in focus.entities if len(e) >= 3}

    scored = []
    for pid in pool_pids:
        if pid == focus.id:
            continue
        if pid not in propositions:
            continue
        p = propositions[pid]
        p_ents = {_norm(e) for e in p.entities if len(e) >= 3}
        overlap = sum(1 for fe in focus_ents
                      if any(fe == pe or fe in pe or pe in fe for pe in p_ents))
        cos = 0.0
        if focus_emb is not None and p.embedding:
            cos = float(np.dot(focus_emb, np.asarray(p.embedding, dtype="float32")))
        scored.append((pid, overlap + cos))
    scored.sort(key=lambda x: -x[1])
    return [pid for pid, _ in scored[:K]]


# ────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ────────────────────────────────────────────────────────────────────────────

def chain_restricted_verdict(
    candidate_chains: List[Chain],
    query: str,
    propositions: Dict[str, Proposition],
    llm_model,
    K_pool: int = 10,
    enable_phase1_cache: bool = False,        # W1 always False
    tau_loose: float = 0.7,
    lookup_K: int = 20,
    verdict_log_path: Optional[Path] = None,
) -> Dict[str, Verdict]:
    """For each proposition on each chain, run small-pool LLM judge.

    Returns dict prop_id → Verdict (one verdict per unique prop_id;
    if a prop appears in multiple chains, the LATEST (chronologically last
    processed) verdict overwrites earlier ones — should be deterministic
    because chain order is deterministic from Phase 2.a).

    Args:
        candidate_chains: top-M chains from Phase 2.a
        query: user query text
        propositions: all KG propositions (needed for on-the-fly lookup)
        llm_model: object with .infer(messages) → (raw, meta, cache_hit)
        K_pool: max pool size for LLM call (spec lock = 10)
        enable_phase1_cache: W1 False; W2+ True
        tau_loose: cosine threshold for dynamic_candidate_lookup
        lookup_K: K for each direction of dynamic_candidate_lookup
        verdict_log_path: optional JSONL log path (per spec §B.11.7)

    Returns:
        Dict[prop_id, Verdict] — verdicts only for propositions appearing
        on candidate_chains.
    """
    verdicts: Dict[str, Verdict] = {}

    if not candidate_chains:
        return verdicts

    # Pre-compute unique chain-prop pairs to avoid re-verdicting the same
    # proposition (e.g., if multi chains contain it).
    seen_pids: Set[str] = set()

    for chain in candidate_chains:
        chain_props = [propositions[pid] for pid in chain.proposition_ids
                       if pid in propositions]
        for focus_pid in chain.proposition_ids:
            if focus_pid in seen_pids:
                continue
            seen_pids.add(focus_pid)
            if focus_pid not in propositions:
                continue
            focus = propositions[focus_pid]

            # ─── Pool construction ───
            pool: Set[str] = set()
            sources: List[str] = []

            # Source 1: Phase 1 cache (W2+)
            if enable_phase1_cache and focus.candidate_supersedees:
                pool |= set(focus.candidate_supersedees)
                sources.append("phase1_cache")

            # Source 2: on-the-fly lookup (always, timestamp-agnostic — W1.3)
            agnostic = dynamic_candidate_lookup(
                focus, propositions, direction="any",
                tau_loose=tau_loose, K=lookup_K,
            )
            if agnostic:
                pool |= agnostic
                sources.append("dynamic_any")

            # Source 3: γ opportunistic (other chains)
            gamma_added = False
            for other_chain in candidate_chains:
                if other_chain.id == chain.id:
                    continue
                paired = find_corresponding_propositions(
                    focus, chain, other_chain, propositions,
                    min_entity_overlap=1,
                )
                if paired:
                    pool |= paired
                    gamma_added = True
            if gamma_added:
                sources.append("gamma")

            # Drop focus from pool (defensive)
            pool.discard(focus_pid)

            # ─── Trim to top-K_pool by relevance to focus ───
            pool_list = _top_k_by_relevance(pool, focus, propositions, K=K_pool)

            # ─── Empty pool → 'current' high-conf (Case A/D per §B.3.1.3) ───
            if not pool_list:
                v = Verdict(
                    status="current",
                    confidence="low",  # spec §B.3.2.1: low conf when no candidates
                    superseder_id=None,
                    reason="no candidates found in pool",
                    pool_size=0,
                    pool_sources=sources,
                )
                verdicts[focus_pid] = v
                _log_verdict_event(verdict_log_path, {
                    "query": query, "chain_id": chain.id,
                    "focus_pid": focus_pid, "focus_text": focus.text,
                    "pool_pids": [], "pool_size": 0,
                    "sources": sources, "verdict": v.to_dict(),
                    "raw_response": None,
                })
                continue

            # ─── LLM identify contradicting pairs (no chain, no timestamps) ───
            pool_props = [propositions[pid] for pid in pool_list if pid in propositions]
            messages, num_to_pid = build_verdict_messages(
                query=query, focus_proposition=focus, pool=pool_props,
            )
            try:
                raw, meta, _hit = llm_model.infer(
                    messages, max_output_tokens=400, temperature=0.0,
                )
            except Exception as e:
                logger.warning(f"[verdict LLM] failed for prop {focus_pid}: {e}")
                raw = ""
                meta = {}
            parsed = parse_verdict_response(raw, num_to_pid)

            # ─── Mechanical direction from timestamps ───
            v = _decide_verdict_mechanically(
                focus=focus,
                contradicting_pids=parsed["contradicting_pids"],
                parse_failed=parsed["parse_failed"],
                propositions=propositions,
                pool_size=len(pool_list),
                sources=sources,
                llm_reason=parsed["reason"],
            )
            verdicts[focus_pid] = v
            _log_verdict_event(verdict_log_path, {
                "query": query, "chain_id": chain.id,
                "focus_pid": focus_pid, "focus_text": focus.text,
                "pool_pids": pool_list, "pool_size": len(pool_list),
                "sources": sources, "verdict": v.to_dict(),
                "llm_contradicting_pids": parsed["contradicting_pids"],
                "raw_response": (raw or "")[:1000],
            })

    return verdicts


def _decide_verdict_mechanically(
    focus,
    contradicting_pids: List[str],
    parse_failed: bool,
    propositions: Dict[str, "Proposition"],
    pool_size: int,
    sources: List[str],
    llm_reason: str,
) -> Verdict:
    """Decide final Verdict from LLM contradicting list + timestamps.

    Decision table (W1.3 redesign):
      parse_failed                                  → uncertain, low
      contradicting empty                            → current,    high  (no conflict found)
      contradicting found, ALL ts ≤ focus.ts         → current,    low   (defensive)
      contradicting found, ANY ts > focus.ts (strict) → superseded, high, superseder=latest
    """
    if parse_failed:
        return Verdict(
            status="uncertain", confidence="low",
            superseder_id=None,
            older_contradicting_pool_pids=[],
            reason="LLM parse failed; no verdict",
            pool_size=pool_size, pool_sources=sources,
        )

    if not contradicting_pids:
        return Verdict(
            status="current", confidence="high",
            superseder_id=None,
            older_contradicting_pool_pids=[],
            reason=f"no contradicting pool member ({llm_reason[:80]})",
            pool_size=pool_size, pool_sources=sources,
        )

    focus_ts = tuple(focus.timestamp)
    later: list = []
    earlier: list = []  # NEW: pool pids strictly EARLIER than focus (older twins)
    for pid in contradicting_pids:
        if pid not in propositions:
            continue
        pid_ts = tuple(propositions[pid].timestamp)
        if pid_ts > focus_ts:
            later.append(pid)
        elif pid_ts < focus_ts:
            earlier.append(pid)
        # pid_ts == focus_ts: skip (ambiguous; rare)

    if later:
        latest_pid = max(later, key=lambda p: tuple(propositions[p].timestamp))
        return Verdict(
            status="superseded", confidence="high",
            superseder_id=latest_pid,
            older_contradicting_pool_pids=earlier,
            reason=f"superseded by later contradicting prop ({llm_reason[:80]})",
            pool_size=pool_size, pool_sources=sources,
        )
    else:
        return Verdict(
            status="current", confidence="low",
            superseder_id=None,
            older_contradicting_pool_pids=earlier,
            reason=f"contradicting found but no strictly later timestamp ({llm_reason[:80]})",
            pool_size=pool_size, pool_sources=sources,
        )


# ────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────

def _log_verdict_event(path: Optional[Path], entry: dict):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        json.dump(entry, f)
        f.write("\n")
