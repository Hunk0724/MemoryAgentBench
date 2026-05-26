"""Phase 2.c — Chunk rebuild filter (B2 design, corpus-agnostic).

Given a chunk's original text + the set of candidate-old prop IDs in that
chunk, rebuild the chunk from its REMAINING (non-old) props, preserving
in-chunk ordering by timestamp[1].

This is the "drop_all_old + keep co-located non-old props in original
slot" design from docs/C_v2_chunk_rebuild_design.md.

Why this generalizes (unlike B3 inline-remove):
  - No regex parsing of fact boundaries
  - No assumption of "N. fact-text." numbering
  - Only uses proposition_index metadata (source_chunk_id, timestamp[1],
    .text), all built corpus-agnostically during indexing

Trade-off vs B3:
  - prop.text may be canonicalized by OpenIE (e.g. S/V/O reordering)
    rather than verbatim from chunk. But since chain_old is removed, the
    LLM no longer needs original phrasing or list numbers for recency cues.
"""
from __future__ import annotations

from typing import Any


def rebuild_chunk_minus_old(
    original_chunk_text: str,
    pids_in_chunk: list[str],
    chain_old_pid_set: set[str],
    prop_idx: dict[str, Any],
) -> str:
    """Rebuild the chunk text from non-old props.

    Args:
        original_chunk_text: the raw chunk content from chunk_embedding_store.
        pids_in_chunk: ALL prop IDs whose source_chunk_id == this chunk's id.
        chain_old_pid_set: prop IDs verdict-marked-old (any reason).
        prop_idx: dict prop_id → Proposition (with .text, .timestamp).

    Returns:
        - If no prop in chunk is in chain_old_pid_set → original_chunk_text
          (no change; passage stays verbatim).
        - If some props removed → space-joined `.text` of remaining props,
          ordered by in_chunk_position (timestamp[1]).
        - If ALL props are chain_old → empty string (caller may decide to
          replace with placeholder; we return empty for now).
    """
    olds_in_chunk = [p for p in pids_in_chunk if p in chain_old_pid_set]
    if not olds_in_chunk:
        return original_chunk_text  # no change; preserve verbatim

    remaining = [p for p in pids_in_chunk if p not in chain_old_pid_set]
    if not remaining:
        return ""  # all old → empty chunk

    # Order by in_chunk_position (timestamp[1]) to mirror original sequence
    def _pos(pid: str) -> int:
        p = prop_idx.get(pid)
        if p is None:
            return 10**9  # unknown → push to end
        ts = getattr(p, "timestamp", None)
        return int(ts[1]) if (ts is not None and len(ts) >= 2) else 10**9

    remaining.sort(key=_pos)

    # Join prop texts with space (preserves "sentence" structure but loses
    # FC-specific list numbering — fine since conflict is resolved).
    lines = [getattr(prop_idx[pid], "text", "") for pid in remaining if pid in prop_idx]
    return " ".join(t.rstrip() for t in lines if t)
