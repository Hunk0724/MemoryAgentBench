"""Phase 3 enriched context renderer (v2.0.2 §B.4.2/§B.4.3 LOCKED).

Output format (LOCKED in spec):

    === Retrieved Passages ===
    [Passage 1 (already in qa() prompt as 'Wikipedia Title: ...')]
    ...
    [Passage K]

    === Reasoning Hints ===
    {A4 hybrid hint, with hedged language if any chain proposition has low-conf verdict}

    === Recent Updates ===
    {B2 natural language change notes, only if confidence ≥ medium}

This module renders **only** the Reasoning Hints + Recent Updates sections;
the Retrieved Passages block is assembled in HippoRAG.qa() as before
(spec contract: prompt template unchanged, only the body between passages
and Question: is extended).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..phase1.data_structures import Proposition
from ..phase2a.data_structures import Chain
from ..phase2b.data_structures import Verdict


def render_reasoning_hint(
    active_chain: Optional[Chain],
    propositions: Dict[str, Proposition],
    verdicts: Dict[str, Verdict],
) -> str:
    """Render Reasoning Hints section (A4 hybrid, hedged if any chain prop has low-conf verdict).

    Per spec §B.4.3:
      - If any chain proposition has confidence='low' → prefix "One possible reasoning path:"
      - Else → prefix "Reasoning hints for this query:"
      - Each chain proposition rendered as "  - <text> (turn <chunk_idx>, position <pos>)"
    """
    if active_chain is None or not active_chain.proposition_ids:
        return ""

    chain_props: List[Proposition] = [
        propositions[pid] for pid in active_chain.proposition_ids
        if pid in propositions
    ]
    if not chain_props:
        return ""

    any_low_conf = any(
        verdicts.get(p.id) is not None and verdicts[p.id].confidence == "low"
        for p in chain_props
    )
    prefix = (
        "One possible reasoning path:" if any_low_conf
        else "Reasoning hints for this query:"
    )

    parts: List[str] = []
    for p in chain_props:
        chunk_idx, pos = (p.timestamp[0], p.timestamp[1]) if p.timestamp else (-1, -1)
        parts.append(f"  - {p.text} (turn {chunk_idx}, position {pos})")
    return f"=== Reasoning Hints ===\n{prefix}\n" + "\n".join(parts)


def render_change_log(
    supersession_events: List[Tuple[str, str]],
    propositions: Dict[str, Proposition],
    verdicts: Dict[str, Verdict],
) -> str:
    """Render Recent Updates section (B2 natural language change notes).

    Per spec §B.4.3:
      - Only include events where verdict confidence ∈ {high, medium}
      - For each (p_old_id, p_new_id), emit one-line natural change note
      - W1 simplification: render note as
          "<p_new.text> (updates earlier: <p_old.text>)"

    Empty string if no confident events.
    """
    confident_events = [
        (old_id, new_id) for (old_id, new_id) in supersession_events
        if verdicts.get(old_id) is not None
        and verdicts[old_id].confidence in ("high", "medium")
    ]
    if not confident_events:
        return ""

    notes: List[str] = []
    for old_id, new_id in confident_events:
        p_old = propositions.get(old_id)
        p_new = propositions.get(new_id) if new_id else None
        if p_old is None:
            continue
        if p_new is None:
            notes.append(f"  - The earlier fact \"{p_old.text}\" has been updated.")
        else:
            notes.append(
                f"  - {p_new.text} (updates earlier: \"{p_old.text}\")"
            )
    if not notes:
        return ""
    return ("=== Recent Updates ===\nRecent updates relevant to this query:\n"
            + "\n".join(notes))


def render_enriched_context(
    active_chain: Optional[Chain],
    supersession_events: List[Tuple[str, str]],
    propositions: Dict[str, Proposition],
    verdicts: Dict[str, Verdict],
    include_hints: bool = True,
    include_updates: bool = True,
) -> str:
    """Render Reasoning Hints + Recent Updates blocks (concatenated, double-newline separated).

    Args:
        active_chain: top-1 chain by score (None if no chain)
        supersession_events: list of (chain_old_pid, chain_new_pid) pairs
        propositions: prop_id → Proposition lookup
        verdicts: prop_id → Verdict lookup
        include_hints: render Reasoning Hints block (ablation flag, default True)
        include_updates: render Recent Updates block (ablation flag, default True)

    Returns:
        Combined enriched context string (may be empty if both blocks suppressed
        or empty). To be injected into HippoRAG.qa() prompt between passages
        block and "Question:" line.

    Note: Does NOT prepend "=== Retrieved Passages ===" — qa() owns that
    section (formatting unchanged from vanilla HippoRAG-v2).
    """
    blocks: List[str] = []
    if include_hints:
        rh = render_reasoning_hint(active_chain, propositions, verdicts)
        if rh:
            blocks.append(rh)
    if include_updates:
        cl = render_change_log(supersession_events, propositions, verdicts)
        if cl:
            blocks.append(cl)
    return "\n\n".join(blocks)
