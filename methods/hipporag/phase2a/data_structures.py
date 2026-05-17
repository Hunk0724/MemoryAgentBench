"""Phase 2.a data structures (v2.0.2 §B.3.1).

`Chain` represents a candidate reasoning chain — an ordered sequence of
propositions sharing entities. Output of `enumerate_candidate_chains`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Set, Tuple


@dataclass
class Chain:
    """A candidate reasoning chain.

    Invariants:
      - len(propositions) ≥ 1 (single-prop "chain" allowed for hop-1 queries)
      - len(propositions) ≤ L (max_depth, default 3)
      - Adjacent propositions share at least 1 entity (substring match,
        synonyms allowed via shared_entity_path)
    """
    id: str
    proposition_ids: List[str]                 # ordered prop IDs along the chain
    shared_entity_path: List[Set[str]]         # length = len(prop_ids) - 1, entities linking each adjacent pair
    score: float                                # from score_chain()
    score_breakdown: dict = field(default_factory=dict)  # {relevance, coherence, length_penalty, ppr_coverage}

    @property
    def depth(self) -> int:
        return len(self.proposition_ids)

    def to_dict(self) -> dict:
        d = asdict(self)
        # set → list for JSON
        d["shared_entity_path"] = [sorted(s) for s in self.shared_entity_path]
        return d
