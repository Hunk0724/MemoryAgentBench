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
      - reason: one-sentence explanation from LLM (≤ ~20 words)
      - pool_size: # candidates in pool at verdict time (diagnostic)
      - pool_sources: which sources contributed pool (cache/dynamic/gamma)
                      diagnostic-only, helps tune Phase 1 cache value
    """
    status: Literal["current", "superseded", "uncertain"]
    confidence: Literal["high", "medium", "low"]
    superseder_id: Optional[str] = None
    reason: str = ""
    pool_size: int = 0
    pool_sources: list = None  # ['dynamic_before', 'dynamic_after', 'gamma']

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("pool_sources") is None:
            d["pool_sources"] = []
        return d
