"""Phase 2.c — Chunk rebuild filter (corpus-agnostic).

When a chunk contains any candidate-old prop, rebuild the chunk from its
remaining (non-old) props instead of dropping it. Preserves chunk position
in top-K; only the old fact-line texts are replaced.

Does NOT depend on FC-specific numbered-fact format. Uses proposition_index
mapping (source_chunk_id + timestamp) which is built corpus-agnostically.

See docs/C_v2_chunk_rebuild_design.md.
"""
from .chunk_rebuild import rebuild_chunk_minus_old

__all__ = ["rebuild_chunk_minus_old"]
