"""Phase 2.b data structures (v2.0.2 §B.3.2 + §B.2.4).

`Verdict` represents a per-proposition supersession judgment, produced by
the small-pool LLM judge in chain_restricted_verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal, Optional


@dataclass
class Verdict:
    """Supersession verdict on a single proposition.

    Per spec §B.3.2:
      - status: 'current' / 'superseded' / 'uncertain'
      - confidence: 'high' / 'medium' / 'low'
      - superseder_id: prop_id that supersedes (if status='superseded'),
                       else None
      - older_contradicting_pool_pids: pool pids that LLM identified as
                       contradicting AND timestamp-wise STRICTLY EARLIER
                       than focus. These are "older twins" of focus when
                       focus is the newer one (status='current'). Enables
                       BIDIRECTIONAL chain_old_pids aggregation — fix for
                       coverage gap where focus is newer but pool contains
                       older twin (previously dropped on the floor).
                       See docs/C_v2_chunk_rebuild_design.md.
      - reason: one-sentence explanation from LLM (≤ ~20 words)
      - pool_size: # candidates in pool at verdict time (diagnostic)
      - pool_sources: which sources contributed pool (cache/dynamic/gamma)
                      diagnostic-only, helps tune Phase 1 cache value
    """
    status: Literal["current", "superseded", "uncertain"]
    confidence: Literal["high", "medium", "low"]
    superseder_id: Optional[str] = None
    older_contradicting_pool_pids: list = None  # List[str] — older twins of focus
    reason: str = ""
    pool_size: int = 0
    pool_sources: list = None  # ['dynamic_before', 'dynamic_after', 'gamma']

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("pool_sources") is None:
            d["pool_sources"] = []
        if d.get("older_contradicting_pool_pids") is None:
            d["older_contradicting_pool_pids"] = []
        return d
