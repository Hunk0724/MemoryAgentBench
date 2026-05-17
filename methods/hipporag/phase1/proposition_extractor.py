"""Phase 1 proposition extractor (v2.0.2 W1.1).

Implements I2.5 of v2.0.2 spec:
  - PropRAG-style proposition extraction via LLM
  - Fed HippoRAG-v2 triple-derived entities (chunk_triple_entities) — Q3=ii locked
  - Three sentinel monitors (yield, entity compliance, truncation)
  - Batch fallback when sentinels trigger

Spec sections:
  §B.2.2.1 — PropRAG prompt port
  §B.2.2.2 — Batch strategy + sentinel monitoring
  §B.2.2.3 — Proposition node addition (handled in I3c, not here)
  §B.2.4 — Data structures
  §B.2.5 — Validation metrics (proposition yield ≥ 0.85, entity compliance ≥ 0.95)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..utils.misc_utils import compute_mdhash_id
from .data_structures import Proposition, PropositionExtractionSentinels
from .prompts.proposition_extraction_prompt import build_messages

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Robust JSON parser for PropRAG output
# ────────────────────────────────────────────────────────────────────────────

def parse_proprag_output(raw: str) -> List[dict]:
    """Extract `propositions` list from raw LLM response.

    PropRAG expected format:
        {"propositions": [{"text": "...", "entities": [...]}, ...]}

    Handles:
      - Plain JSON
      - Markdown code fences (```json ... ```)
      - Trailing prose
    Returns [] on parse failure.
    """
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the outermost JSON object
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    if not isinstance(parsed, dict):
        return []
    props_raw = parsed.get("propositions", [])
    if not isinstance(props_raw, list):
        return []

    out = []
    for p in props_raw:
        if not isinstance(p, dict):
            continue
        text = str(p.get("text", "")).strip()
        ents = p.get("entities", [])
        if not text or not isinstance(ents, list):
            continue
        out.append({"text": text, "entities": [str(e).strip() for e in ents]})
    return out


# ────────────────────────────────────────────────────────────────────────────
# Helpers — FC numbered-list counting + chunk splitting
# ────────────────────────────────────────────────────────────────────────────

_NUMBERED_MARKER_RE = re.compile(r"(\d+)\.\s+")


def count_numbered_facts(passage: str) -> int:
    """Count `N. ` markers in passage. For FC-MH this = numbered facts count."""
    return len(list(_NUMBERED_MARKER_RE.finditer(passage)))


def split_passage_by_numbered_facts(passage: str, n_batches: int) -> List[str]:
    """Split passage into n_batches sub-passages, each containing ~1/n_batches
    of the numbered facts. Preserves the "Here is a list of facts:" preamble
    if present (prepended to every batch).

    Returns list of n_batches sub-passage strings. If passage has < n_batches
    facts, returns [passage] (no split).
    """
    markers = list(_NUMBERED_MARKER_RE.finditer(passage))
    if len(markers) < n_batches or n_batches < 2:
        return [passage]

    # Detect preamble (text before first numbered marker)
    preamble = passage[:markers[0].start()].strip()

    # Split markers into n_batches groups
    n_per_batch = len(markers) // n_batches
    leftover = len(markers) % n_batches
    batch_starts = []
    idx = 0
    for b in range(n_batches):
        batch_size = n_per_batch + (1 if b < leftover else 0)
        batch_starts.append((idx, idx + batch_size))
        idx += batch_size

    sub_passages = []
    for start_idx, end_idx in batch_starts:
        start_char = markers[start_idx].start()
        end_char = markers[end_idx].start() if end_idx < len(markers) else len(passage)
        body = passage[start_char:end_char].strip()
        if preamble:
            sub_passages.append(f"{preamble}\n{body}")
        else:
            sub_passages.append(body)
    return sub_passages


def derive_chunk_triple_entities(extracted_triples: List[List[str]]) -> Set[str]:
    """Union of (subject, object) across triples in a chunk.

    Mirrors `extract_entity_nodes()` in utils/misc_utils.py — Q3=ii lock.
    """
    out: Set[str] = set()
    for t in extracted_triples:
        if isinstance(t, (list, tuple)) and len(t) == 3:
            s, _, o = [str(x).strip() for x in t]
            if s:
                out.add(s)
            if o:
                out.add(o)
    return out


# ────────────────────────────────────────────────────────────────────────────
# Sentinel evaluation
# ────────────────────────────────────────────────────────────────────────────

def _norm_entity(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def evaluate_sentinels(
    propositions: List[dict],
    chunk_passage: str,
    triple_entities: Set[str],
    raw_response: str,
    finish_reason: str,
    cache_hit: bool,
) -> PropositionExtractionSentinels:
    """Compute the three sentinel monitors per §B.2.2.2."""
    expected = count_numbered_facts(chunk_passage)

    # Entities-not-in-input: case-insensitive substring-style check vs triple_entities
    triple_ents_norm = {_norm_entity(e) for e in triple_entities}
    out_of_list_count = 0
    for p in propositions:
        for e in p.get("entities", []):
            e_n = _norm_entity(e)
            # Pass if entity matches any triple entity (substring either direction)
            ok = any(
                e_n == te or e_n in te or te in e_n
                for te in triple_ents_norm
                if len(te) >= 3 and len(e_n) >= 3
            )
            if not ok:
                out_of_list_count += 1

    return PropositionExtractionSentinels(
        proposition_count_per_chunk=len(propositions),
        expected_proposition_count=expected,
        entities_not_in_input=out_of_list_count,
        finish_reason_length=(str(finish_reason).lower().endswith("length")
                              or str(finish_reason).upper() == "MAX_TOKENS"),
        raw_response_char_count=len(raw_response or ""),
        cache_hit=cache_hit,
    )


# ────────────────────────────────────────────────────────────────────────────
# Main extraction (single-chunk; batch fallback wrapper below)
# ────────────────────────────────────────────────────────────────────────────

def _build_propositions(
    raw_props: List[dict],
    chunk_id: str,
    chunk_idx: int,
) -> List[Proposition]:
    """Wrap raw {text, entities} dicts into Proposition dataclasses with
    timestamp = (chunk_idx, in_chunk_position) and content-hash id.
    """
    out = []
    for in_chunk_pos, p in enumerate(raw_props):
        text = p["text"]
        ents = p["entities"]
        pid = compute_mdhash_id(
            content=f"{chunk_idx}-{in_chunk_pos}-{text}",
            prefix="prop-",
        )
        out.append(Proposition(
            id=pid, text=text, entities=ents,
            source_chunk_id=chunk_id,
            timestamp=(chunk_idx, in_chunk_pos),
        ))
    return out


def extract_propositions_for_chunk(
    chunk_id: str,
    chunk_idx: int,
    passage: str,
    triple_entities: Set[str],
    llm_model,
    max_new_tokens: int = 2048,
    sentinel_log_path: Optional[Path] = None,
) -> Tuple[List[Proposition], PropositionExtractionSentinels]:
    """Single-chunk PropRAG-style extraction (no batching, no fallback).

    Returns (propositions, sentinels). Caller decides whether to invoke
    `extract_with_batch_fallback` based on sentinel alarms.
    """
    entities_list = sorted(triple_entities)  # deterministic order for cache stability
    messages = build_messages(passage=passage,
                              named_entities_json=json.dumps(entities_list))

    raw_response, meta, cache_hit = llm_model.infer(
        messages, max_output_tokens=max_new_tokens, temperature=0.0,
    )
    finish_reason = meta.get("finish_reason", "stop")

    raw_props = parse_proprag_output(raw_response)
    sentinels = evaluate_sentinels(
        propositions=raw_props,
        chunk_passage=passage,
        triple_entities=triple_entities,
        raw_response=raw_response,
        finish_reason=finish_reason,
        cache_hit=cache_hit,
    )
    propositions = _build_propositions(raw_props, chunk_id, chunk_idx)

    if sentinel_log_path is not None:
        _append_sentinel_log(sentinel_log_path, {
            "chunk_id": chunk_id, "chunk_idx": chunk_idx,
            "mode": "whole",
            "sentinels": sentinels.to_dict(),
        })

    return propositions, sentinels


# ────────────────────────────────────────────────────────────────────────────
# Batch fallback wrapper
# ────────────────────────────────────────────────────────────────────────────

def _partition_entities_by_subchunk(
    triple_entities: Set[str],
    sub_passages: List[str],
) -> List[Set[str]]:
    """Assign each entity to sub_passages whose text contains it (substring,
    case-insensitive). An entity may appear in multiple sub-passages.

    Entities not found in any sub-passage are skipped (extremely rare; would
    indicate OpenIE produced an entity not present in original passage).
    """
    sub_ents: List[Set[str]] = [set() for _ in sub_passages]
    for e in triple_entities:
        e_lo = e.lower()
        if len(e_lo) < 3:
            continue
        for i, sp in enumerate(sub_passages):
            if e_lo in sp.lower():
                sub_ents[i].add(e)
    return sub_ents


def extract_with_batch_fallback(
    chunk_id: str,
    chunk_idx: int,
    passage: str,
    triple_entities: Set[str],
    llm_model,
    max_new_tokens: int = 2048,
    sentinel_log_path: Optional[Path] = None,
    max_n_batches: int = 4,
    yield_target: float = 0.7,
) -> Tuple[List[Proposition], List[PropositionExtractionSentinels]]:
    """Whole-chunk first; if sentinels trigger, escalate to batched extraction.

    Default escalation: 1 → 2 → 4 batches (capped at max_n_batches).
    Returns (merged_propositions, [sentinels_per_attempt]).

    The merged propositions get unique `(chunk_idx, in_chunk_position)`
    timestamps spanning across all batches in sub-passage order.
    """
    all_sentinels: List[PropositionExtractionSentinels] = []

    # Attempt 1: whole chunk
    props, sent = extract_propositions_for_chunk(
        chunk_id, chunk_idx, passage, triple_entities, llm_model,
        max_new_tokens=max_new_tokens, sentinel_log_path=sentinel_log_path,
    )
    all_sentinels.append(sent)
    triggered = sent.alarms()
    if not triggered:
        return props, all_sentinels

    # Decide whether to escalate: only LOW_PROPOSITION_YIELD or LLM_TRUNCATION
    # benefit from batching (entities-out-of-list won't be helped by batching).
    escalate = (
        "LOW_PROPOSITION_YIELD" in triggered or
        "LLM_TRUNCATION" in triggered
    )
    if not escalate:
        return props, all_sentinels

    # Attempt 2+: batched
    n_batches = 2
    while n_batches <= max_n_batches:
        logger.info(f"[batch fallback] chunk_idx={chunk_idx}: trying n_batches={n_batches} "
                    f"(prev yield={sent.proposition_yield_ratio:.2f})")
        sub_passages = split_passage_by_numbered_facts(passage, n_batches)
        if len(sub_passages) < n_batches:
            break  # not enough numbered markers to subdivide further
        sub_entities = _partition_entities_by_subchunk(triple_entities, sub_passages)

        merged_props: List[Proposition] = []
        merged_sent_yield = 0
        merged_sent_expected = 0
        merged_out_of_list = 0
        merged_finish_length = False
        merged_raw_chars = 0
        cache_hits = []
        in_chunk_pos_offset = 0

        for sub_idx, (sub_p, sub_e) in enumerate(zip(sub_passages, sub_entities)):
            entities_list = sorted(sub_e)
            messages = build_messages(passage=sub_p,
                                      named_entities_json=json.dumps(entities_list))
            raw_response, meta, cache_hit = llm_model.infer(
                messages, max_output_tokens=max_new_tokens, temperature=0.0,
            )
            finish_reason = meta.get("finish_reason", "stop")
            raw_props = parse_proprag_output(raw_response)

            sub_sent = evaluate_sentinels(
                propositions=raw_props,
                chunk_passage=sub_p,
                triple_entities=sub_e,
                raw_response=raw_response,
                finish_reason=finish_reason,
                cache_hit=cache_hit,
            )
            merged_sent_yield += sub_sent.proposition_count_per_chunk
            merged_sent_expected += sub_sent.expected_proposition_count
            merged_out_of_list += sub_sent.entities_not_in_input
            merged_finish_length = merged_finish_length or sub_sent.finish_reason_length
            merged_raw_chars += sub_sent.raw_response_char_count
            cache_hits.append(cache_hit)

            # Assign in_chunk_position with offset across batches
            for in_batch_pos, p in enumerate(raw_props):
                pid = compute_mdhash_id(
                    content=f"{chunk_idx}-{in_chunk_pos_offset + in_batch_pos}-{p['text']}",
                    prefix="prop-",
                )
                merged_props.append(Proposition(
                    id=pid, text=p["text"], entities=p["entities"],
                    source_chunk_id=chunk_id,
                    timestamp=(chunk_idx, in_chunk_pos_offset + in_batch_pos),
                ))
            in_chunk_pos_offset += len(raw_props)

        sent = PropositionExtractionSentinels(
            proposition_count_per_chunk=merged_sent_yield,
            expected_proposition_count=merged_sent_expected,
            entities_not_in_input=merged_out_of_list,
            finish_reason_length=merged_finish_length,
            raw_response_char_count=merged_raw_chars,
            cache_hit=all(cache_hits),
        )
        all_sentinels.append(sent)
        if sentinel_log_path is not None:
            _append_sentinel_log(sentinel_log_path, {
                "chunk_id": chunk_id, "chunk_idx": chunk_idx,
                "mode": f"batch_n{n_batches}",
                "sentinels": sent.to_dict(),
            })

        if sent.proposition_yield_ratio >= yield_target and not sent.finish_reason_length:
            return merged_props, all_sentinels

        # Keep latest props in case we exit loop without recovery
        props = merged_props
        n_batches *= 2

    return props, all_sentinels


# ────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────

def _append_sentinel_log(path: Path, entry: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        json.dump(entry, f)
        f.write("\n")
