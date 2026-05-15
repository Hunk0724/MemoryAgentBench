"""v2 LLM-judge detector — query-time conflict detection on top-N passage facts.

Design rationale (see analysis/results/phase_v1/smoke_llm_judge_detection.json):
  - LLM does SEMANTIC GROUPING only ("which facts contradict each other?")
  - Direction (which is outdated) resolved MECHANICALLY by chunk_idx serial number
  - This decouples LLM's world-knowledge prior from temporal ordering
  - Prompt teaches Wikidata-style cardinality taxonomy (functional / cumulative /
    temporal-functional / aggregated) instead of dataset-specific examples

Smoke test on 5 FC-MH queries (n_facts=7-11 each): 90% pair recall, 100% precision,
0 distractor FP.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a knowledge conflict detector. Identify groups of facts that "
    "genuinely contradict each other.\n\n"
    "To decide if two facts (s, r, o1) and (s, r, o2) — same subject, same kind "
    "of relation, different objects — actually conflict, classify the RELATION r "
    "into one of four types:\n\n"
    "1. FUNCTIONAL: relation that maps each subject to exactly ONE value "
    "(1-to-1 cardinality). Different o1, o2 are MUTUALLY EXCLUSIVE.\n"
    "   → Same (s, r) with different o IS A CONFLICT.\n\n"
    "2. CUMULATIVE: relation that allows multiple simultaneous values "
    "(1-to-many, values accumulate without displacing each other).\n"
    "   → Same (s, r) with different o is NOT a conflict. Both can coexist.\n\n"
    "3. TEMPORAL-FUNCTIONAL: relation is functional at any single point in time, "
    "but the value can change across time. Without explicit time context, "
    "treat as FUNCTIONAL by default — the newer value replaces the older.\n"
    "   → Same (s, r) with different o IS A CONFLICT (default behavior).\n\n"
    "4. AGGREGATED: multi-valued attributes where individual values represent "
    "independent additive facts (similar to CUMULATIVE).\n"
    "   → Same (s, r) with different o is NOT a conflict.\n\n"
    "When uncertain, default to FUNCTIONAL (conservative — flag the potential "
    "conflict and let downstream decide).\n\n"
    "IMPORTANT:\n"
    "• You only group conflicting facts. You do NOT decide which is outdated.\n"
    "• IGNORE your real-world knowledge about which fact is 'correct'. Treat "
    "facts as opaque data.\n"
    "• Each group can have 2+ facts."
)


def build_detection_prompt(query: str, facts_with_seq: List[Tuple[int, str]]) -> List[Dict]:
    """Build (system, user) message list for the LLM judge."""
    facts_str = "\n".join(f"  [seq={s}] {t}" for s, t in facts_with_seq)
    user = (
        f"Facts (each prefixed by its serial number; treat seq as opaque ID):\n"
        f"{facts_str}\n\n"
        f"Query context (do not answer it): {query}\n\n"
        f"Identify conflict groups. Respond with ONLY valid JSON:\n"
        f'{{"conflict_groups": [[<seq>, <seq>, ...], ...]}}\n'
        f"Each inner list is a set of seqs that mutually conflict. "
        f"Return an empty outer list if no conflicts exist.\n"
        f"No prose, no markdown — only JSON."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_detection_response(raw: str) -> List[List[int]]:
    """Extract conflict_groups list from LLM response. Returns [] on parse failure."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        try:
            d = json.loads(m.group(0))
        except Exception:
            return []
    groups_raw = d.get("conflict_groups", []) if isinstance(d, dict) else []
    out = []
    for g in groups_raw:
        if not isinstance(g, list) or len(g) < 2:
            continue
        try:
            out.append([int(s) for s in g])
        except (ValueError, TypeError):
            continue
    return out


class LLMJudgeDetector:
    """Query-time LLM-judge conflict detector for HippoRAG-v2 candidate facts.

    Usage:
        det = LLMJudgeDetector(llm_model, chunk_to_fact_keys, fact_content_map,
                                chunk_key_to_idx)
        result = det.detect(query, top_n_chunk_keys)
        # result = {
        #     "chain_old_fact_keys": Set[str],         # fact_keys marked superseded
        #     "chain_old_chunk_keys": Set[str],        # passages containing any chain_old fact
        #     "conflict_groups": List[List[Tuple[int, str]]],  # raw groups (seq, fact_key)
        #     "annotation_text": str,                  # natural-language note for QA prompt
        #     "n_facts_sent": int,
        # }
    """

    def __init__(self,
                 llm_model,
                 chunk_to_fact_keys: Dict[str, List[str]],
                 fact_content_map: Dict[str, str],
                 chunk_key_to_idx: Dict[str, int]):
        """
        Args:
            llm_model: object with .infer(messages) -> (response_str, meta, cache_hit)
                       (CacheGemini or compatible interface).
            chunk_to_fact_keys: chunk_key -> list of fact_keys (always-populated map).
            fact_content_map: fact_key -> "(s, r, o)" content string.
            chunk_key_to_idx: chunk_key -> chunk_idx (serial number, larger = newer).
        """
        self.llm = llm_model
        self.chunk_to_fact_keys = chunk_to_fact_keys
        self.fact_content_map = fact_content_map
        self.chunk_key_to_idx = chunk_key_to_idx

    def _build_fact_pool(self, top_n_chunk_keys: List[str]) -> List[Tuple[int, str, str]]:
        """Return list of (seq, fact_text_natural, fact_key) tuples, dedup'd by fact_key.

        seq = the smallest chunk_idx among chunks containing this fact (the chunk
        that first introduced it). If a fact appears only once, this is just its
        host chunk's idx.

        fact_text_natural: if fact_content_map value parses as a 3-tuple, format
        as "s r o"; otherwise use the value as-is (allows callers to supply
        pre-built natural sentences via the same fact_content_map).
        """
        fact_first_seq: Dict[str, int] = {}
        for ck in top_n_chunk_keys:
            seq = self.chunk_key_to_idx.get(ck)
            if seq is None:
                continue
            for fk in self.chunk_to_fact_keys.get(ck, []):
                if fk not in self.fact_content_map:
                    continue
                if fk not in fact_first_seq or seq < fact_first_seq[fk]:
                    fact_first_seq[fk] = seq

        pool = []
        for fk, seq in fact_first_seq.items():
            content_str = self.fact_content_map[fk]
            # If content looks like a tuple-string, eval it. Otherwise treat as
            # already-natural text.
            nat = content_str
            if isinstance(content_str, str) and content_str.startswith("("):
                try:
                    triple = eval(content_str)
                    if isinstance(triple, tuple) and len(triple) == 3:
                        # Skip empty fields cleanly to avoid leading/trailing spaces
                        parts = [str(x).strip() for x in triple if str(x).strip()]
                        if parts:
                            nat = " ".join(parts)
                except Exception:
                    pass
            pool.append((int(seq), nat, fk))
        # Sort by seq for stable prompt order
        pool.sort(key=lambda x: x[0])
        return pool

    def detect(self, query: str, top_n_chunk_keys: List[str],
               fact_key_to_query_score: Optional[Dict[str, float]] = None,
               top_k_facts: Optional[int] = None) -> Dict:
        """Run LLM judge on facts from top_n_chunk_keys; return chain_old result.

        Args:
            query: the user query text.
            top_n_chunk_keys: list of chunk_keys (passage hash_ids), PPR-ranked.
            fact_key_to_query_score: optional fact_key -> cosine(query, fact_emb).
                When provided AND top_k_facts is set, pool is pruned to top-K most
                query-relevant facts before LLM call.
            top_k_facts: optional cap on number of facts sent to LLM. When set,
                requires fact_key_to_query_score to also be provided. Lower values
                = smaller LLM context, better attention on query-relevant facts,
                but lower recall on conflicts NOT directly mentioned in query.

        Returns:
            dict with keys:
              - chain_old_fact_keys: Set[str]
              - chain_old_chunk_keys: Set[str]
              - conflict_groups: List[List[Tuple[seq, fact_key]]] — raw groups
              - annotation_text: str — natural-language note for QA prompt
              - n_facts_sent: int
              - n_pool_pre_filter: int (size before top-K filter, for diagnostics)
        """
        # 1. Build fact pool with seqs
        pool = self._build_fact_pool(top_n_chunk_keys)
        n_pre_filter = len(pool)
        if len(pool) < 2:
            return {"chain_old_fact_keys": set(), "chain_old_chunk_keys": set(),
                    "conflict_groups": [], "annotation_text": "",
                    "n_facts_sent": len(pool), "n_pool_pre_filter": n_pre_filter}

        # 1b. Optional cosine pre-filter (scope reduction for production-scale pools)
        if top_k_facts is not None and fact_key_to_query_score is not None and len(pool) > top_k_facts:
            pool_with_scores = [
                (seq, txt, fk, fact_key_to_query_score.get(fk, 0.0))
                for seq, txt, fk in pool
            ]
            pool_with_scores.sort(key=lambda x: -x[3])
            pool_with_scores = pool_with_scores[:top_k_facts]
            # Restore seq-order for stable LLM prompt
            pool = [(seq, txt, fk) for seq, txt, fk, _ in pool_with_scores]
            pool.sort(key=lambda x: x[0])
            logger.info(f"[v2] cosine pre-filter: pool {n_pre_filter} → {len(pool)}")

        seq_to_fact_key = {seq: fk for seq, _, fk in pool}
        facts_with_seq = [(seq, txt) for seq, txt, _ in pool]

        # 2. Call LLM judge
        messages = build_detection_prompt(query, facts_with_seq)
        try:
            response, _meta, _cache_hit = self.llm.infer(messages)
        except Exception as e:
            logger.warning(f"[v2] LLM judge inference failed: {e}")
            return {"chain_old_fact_keys": set(), "chain_old_chunk_keys": set(),
                    "conflict_groups": [], "annotation_text": "",
                    "n_facts_sent": len(pool)}

        groups_seq = parse_detection_response(response)

        # 3. Mechanical direction: in each group, max seq = current, others = chain_old
        chain_old_fact_keys = set()
        groups_with_fk = []  # [[(seq, fact_key), ...], ...]
        annotation_lines = []
        for grp in groups_seq:
            valid_seqs = [s for s in grp if s in seq_to_fact_key]
            if len(valid_seqs) < 2:
                continue
            max_seq = max(valid_seqs)
            group_full = [(s, seq_to_fact_key[s]) for s in valid_seqs]
            groups_with_fk.append(group_full)
            current_fk = seq_to_fact_key[max_seq]
            current_text = next(t for s, t, fk in pool if fk == current_fk)
            for s in valid_seqs:
                if s == max_seq:
                    continue
                fk = seq_to_fact_key[s]
                chain_old_fact_keys.add(fk)
                old_text = next(t for ss, t, ffk in pool if ffk == fk)
                annotation_lines.append(
                    f"  - The fact \"{old_text}\" has been superseded by "
                    f"\"{current_text}\"; rely on the newer fact."
                )

        # 4. Derive chain_old_chunk_keys (passages containing any chain_old fact)
        chain_old_chunk_keys = set()
        for ck in top_n_chunk_keys:
            for fk in self.chunk_to_fact_keys.get(ck, []):
                if fk in chain_old_fact_keys:
                    chain_old_chunk_keys.add(ck)
                    break

        # 5. Build annotation block for QA prompt
        if annotation_lines:
            annotation_text = (
                "Note — the following facts in the passages have been updated by "
                "newer information:\n" + "\n".join(annotation_lines)
            )
        else:
            annotation_text = ""

        return {
            "chain_old_fact_keys": chain_old_fact_keys,
            "chain_old_chunk_keys": chain_old_chunk_keys,
            "conflict_groups": groups_with_fk,
            "annotation_text": annotation_text,
            "n_facts_sent": len(pool),
            "n_pool_pre_filter": n_pre_filter,
        }
