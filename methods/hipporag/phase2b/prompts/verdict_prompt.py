"""Phase 2.b conflict identifier prompt — v2.0.2 → updated 2026-05-17.

Design pivot from spec §B.3.2.2 verdict prompt:
  - OLD (verdict): LLM decides status + superseded_by + confidence in one call
  - NEW (identifier): LLM ONLY identifies which pool statements CONTRADICT
    focus (no direction, no timestamps); mechanical direction in verdict.py

Rationale (W1.3 dry-run findings, 2026-05-17):
  - Original verdict prompt let LLM decide direction, which got reversed by
    parametric world-knowledge bias on MQuAKE counterfactual content
    (e.g., Darwin authored Our Mutual Friend got flagged as superseded
     because LLM "knows" Dickens is the real author)
  - Result: 60% over-flag rate, MH EM dropped from 19% to 11%
  - Fix: separate semantic (LLM strength) from temporal ordering (code task)

Spec divergence (tracked, may promote to v2.0.3 if results good):
  - §B.3.2.2 verdict prompt template replaced with this CONFLICT_IDENTIFY_PROMPT
  - Output schema: {contradicting_pool_indices: List[int], reason: str}
  - Confidence determination moved entirely to code (verdict.py)
"""
import json
import re
from typing import Dict, List, Tuple


VERDICT_SYSTEM = """You are a conflict identifier. Your job is to find pool statements that make CONTRADICTING claims with a focus statement — meaning both cannot simultaneously be true."""


CONFLICT_IDENTIFY_PROMPT = """QUERY (for context only, do not use to judge): {query}

FOCUS:
"{focus_text}"

POOL:
{pool_block}

A pool statement CONTRADICTS the focus when both statements describe the SAME underlying fact about an entity (e.g., the same role, the same location, the same relationship, the same attribute), but assert DIFFERENT values for that fact, such that both cannot simultaneously be true.

CRITICAL RULES:
- Treat all statements as opaque assertions. DO NOT use real-world knowledge to judge which is "correct" or "plausible". The dataset may contain counterfactual content on purpose.
- DO NOT consider timestamps. They are IRRELEVANT for THIS task and are handled by a separate mechanism.
- DO NOT decide which statement is current and which is outdated. Your ONLY job is to identify CONTRADICTING pairs.

CONTRADICTING examples (both cannot simultaneously be true):
  - "Acme's CEO is Alice" ↔ "Bob currently leads Acme as CEO"
  - "The capital of Wakanda is Birnin" ↔ "Wakanda's capital is Eastside"
  - "Our Mutual Friend was written by Dickens" ↔ "Charles Darwin authored Our Mutual Friend"
    (Note: counterfactual content is intentional. Do not judge factually; they make incompatible claims about the same fact.)

NOT-CONTRADICTING examples (both can simultaneously hold):
  - "User likes Apple" + "User likes Banana"
    (cumulative preference, different objects)
  - "John works at Google" + "John lives in Seattle"
    (different aspects: employment vs residence)
  - "Alice studied at MIT" + "Alice now works at Microsoft"
    (different life events, both can be in her history)
  - "X is married to A" + "X has child B"
    (different relationships, both can hold)

Output (JSON only, no markdown):
{{
  "contradicting_pool_indices": [<int>, ...],
  "reason": "<one sentence describing what fact is being contradicted>"
}}"""


def build_verdict_messages(
    query: str,
    focus_proposition,         # Proposition
    pool: List,                # List[Proposition], max K_pool=10
) -> Tuple[List[dict], Dict[int, str]]:
    """Build chat-message list for the conflict-identify LLM call.

    Per v2.0.2 W1.3 redesign:
      - Drop chain_block from prompt (LLM doesn't see chain context)
      - Drop timestamps from pool_block (LLM doesn't see timestamps either)
      - Pool entries numbered [1], [2], ... — LLM references by index

    Returns:
        messages: chat-style list
        pool_number_to_pid: dict mapping LLM's pool numbers → proposition IDs
    """
    pool_lines = []
    pool_number_to_pid: Dict[int, str] = {}
    for i, p in enumerate(pool, start=1):
        pool_lines.append(f'  [{i}] "{p.text}"')
        pool_number_to_pid[i] = p.id
    pool_block = "\n".join(pool_lines) if pool_lines else "  (empty pool)"

    user_text = CONFLICT_IDENTIFY_PROMPT.format(
        query=query,
        focus_text=focus_proposition.text,
        pool_block=pool_block,
    )
    messages = [
        {"role": "system", "content": VERDICT_SYSTEM},
        {"role": "user", "content": user_text},
    ]
    return messages, pool_number_to_pid


def parse_verdict_response(raw: str, pool_number_to_pid: Dict[int, str]) -> dict:
    """Extract contradicting pool indices from LLM response.

    Returns dict:
      - contradicting_pids: List[str] — proposition IDs identified as contradicting
      - reason: str
      - parse_failed: bool — True if JSON parsing failed entirely
    """
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                pass

    if not isinstance(parsed, dict):
        return {
            "contradicting_pids": [],
            "reason": "",
            "parse_failed": True,
        }

    indices = parsed.get("contradicting_pool_indices", [])
    if not isinstance(indices, list):
        indices = []
    contradicting_pids = []
    for ix in indices:
        try:
            n = int(ix)
            if n in pool_number_to_pid:
                contradicting_pids.append(pool_number_to_pid[n])
        except (ValueError, TypeError):
            continue

    return {
        "contradicting_pids": contradicting_pids,
        "reason": str(parsed.get("reason", "")).strip()[:300],
        "parse_failed": False,
    }
