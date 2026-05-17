"""Data structures for Phase 1 (v2.0.2 §B.2.4).

W1.1 scope: Proposition (without embedding / entity_node_ids / candidate_supersedees —
those are populated in W1.2 / I3c / W2 respectively).
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


@dataclass
class Proposition:
    """Internal memory unit for v2 (replaces triple as the conflict-detection unit).

    Per spec §B.2.4. W1.1 only populates fields produced by I2.5 extraction.
    """
    id: str
    text: str
    entities: List[str]                       # entity mentions in proposition text
    source_chunk_id: str
    timestamp: Tuple[int, int]                # (chunk_idx, in_chunk_position) — Q7 locked

    # Populated later — W1.2 (I3c) and W2 (I4.5):
    entity_node_ids: List[str] = field(default_factory=list)
    embedding: Optional[list] = None          # stored as list for JSON serialization
    candidate_supersedees: Optional[List[str]] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = list(self.timestamp)  # tuple → list for JSON
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Proposition":
        ts = d.get("timestamp", [0, 0])
        return cls(
            id=d["id"], text=d["text"], entities=d["entities"],
            source_chunk_id=d["source_chunk_id"],
            timestamp=tuple(ts),
            entity_node_ids=d.get("entity_node_ids", []),
            embedding=d.get("embedding"),
            candidate_supersedees=d.get("candidate_supersedees"),
        )


@dataclass
class PropositionExtractionSentinels:
    """Three sentinel monitors per spec §B.2.2.2."""
    proposition_count_per_chunk: int            # actual proposition count returned
    expected_proposition_count: int             # numbered_fact_count in chunk passage
    entities_not_in_input: int                  # propositions cite entities outside list
    finish_reason_length: bool                  # LLM hit max_tokens (truncation)
    raw_response_char_count: int                # approx token via chars
    cache_hit: bool

    # Yield ratio convenience
    @property
    def proposition_yield_ratio(self) -> float:
        if self.expected_proposition_count == 0:
            return 0.0
        return self.proposition_count_per_chunk / self.expected_proposition_count

    def alarms(self) -> List[str]:
        """Return list of alarm codes triggered (empty if all OK)."""
        a = []
        if self.proposition_yield_ratio < 0.7:
            a.append("LOW_PROPOSITION_YIELD")
        if self.entities_not_in_input > 0:
            a.append("ENTITIES_OUT_OF_LIST")
        if self.finish_reason_length:
            a.append("LLM_TRUNCATION")
        return a

    def to_dict(self) -> dict:
        d = asdict(self)
        d["proposition_yield_ratio"] = self.proposition_yield_ratio
        d["alarms"] = self.alarms()
        return d
