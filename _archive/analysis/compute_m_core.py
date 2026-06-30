"""
compute_m_core.py
=================
Compute hop-level CLEAN / LEAK / MISS state for one method run,
per FC_metrics_spec.md §3 (M-core).

State classification per `has_pair` hop:
    new_present and not old_present   → CLEAN
    old_present                       → LEAK (regardless of new_present)
    not new_present and not old_present → MISS

For `no_conflict_pair` hop (pure retrieval):
    new_present  → RETRIEVED
    else         → MISS

Where `new_present` / `old_present` are computed by `check_fact_in_context`
against the `final_context_text` actually fed to the QA LLM.

Input:
    Per-query JSON dumps from agent.py / mem0 handler containing:
      - retrieved_memories[] OR final_context_text
    + alignment JSON from align_mem0_mquake.py

Output:
    Per-hop JSON entries with state + matched_via tier,
    aggregated CLEAN/LEAK/MISS rates per method × ctx.

Usage:
    python analysis/compute_m_core.py \\
        --alignment analysis/results/<run>_mh_<ctx>_mquake.json \\
        --retrieval-dir outputs/rag_retrieved/<agent>/k_<K>/<sub>/chunksize_<C>/ \\
        --out analysis/results/<run>_mh_<ctx>_mcore.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# fact-in-context matching (FC_metrics_spec.md §3.3)
# ─────────────────────────────────────────────────────────────────────────────

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s.]")


def normalize(s: str) -> str:
    """Lowercase, drop most punctuation, collapse whitespace. Keep '.' for fact boundaries."""
    if not s:
        return ""
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def extract_subject_entity_from_cloze(cloze: str) -> str:
    """Heuristic: subject = head NP of the cloze.

    Cloze format from MQuAKE:
      "The author of Our Mutual Friend is" -> "Our Mutual Friend" (the named entity)
      "Charles Darwin is married to" -> "Charles Darwin"
      "goaltender is associated with the sport of" -> "goaltender"

    Rule: take longest capitalized noun phrase, else the longest word sequence
    before the first 'is/was/are/were'.
    """
    if not cloze:
        return ""
    # Strip a trailing copula / "of"
    s = cloze.strip().rstrip(".").strip()

    # Find capitalized multi-word entity (most informative anchor)
    caps = re.findall(r"[A-Z][a-zA-Z0-9'\-]*(?:\s+[A-Z][a-zA-Z0-9'\-]*)+", cloze)
    if caps:
        return max(caps, key=len)

    # Fallback: span before first copula
    m = re.search(r"^(.*?)\b(?:is|was|are|were|has|have)\b", s)
    if m:
        return m.group(1).strip().rstrip(",").strip()

    # Last resort: first noun-ish word
    return s.split()[0] if s.split() else ""


def co_occur_in_same_unit(ctx_text: str, anchor: str, answer: str,
                          max_token_distance: int = 50) -> bool:
    """Check anchor and answer appear within max_token_distance tokens of each other.

    `ctx_text` is already normalized. We split on whitespace, then look for
    any pair (anchor_pos, answer_pos) with distance < max_token_distance.

    TBD per FC_metrics_spec.md §12: distance 50 may be too tight for paraphrased memories.
    """
    tokens = ctx_text.split()
    anchor_toks = anchor.split()
    answer_toks = answer.split()
    if not anchor_toks or not answer_toks:
        return False

    def find_positions(needle_toks):
        n = len(needle_toks)
        positions = []
        for i in range(len(tokens) - n + 1):
            if tokens[i:i + n] == needle_toks:
                positions.append(i)
        return positions

    anchor_pos = find_positions(anchor_toks)
    answer_pos = find_positions(answer_toks)
    if not anchor_pos or not answer_pos:
        return False
    for ap in anchor_pos:
        for op in answer_pos:
            if abs(ap - op) <= max_token_distance:
                return True
    return False


def check_fact_in_context(context_text: str, fact_text: str, answer: str,
                          cloze: str, max_distance: int = 50) -> tuple[bool, str]:
    """Three-tier match per §3.3.

    Returns (present, matched_via)
      matched_via ∈ {tier1_strict, tier2_anchor_answer, tier3_proximity, none}
    """
    if not context_text or not answer:
        return False, "none"

    ctx_norm = normalize(context_text)
    ans_norm = normalize(answer)

    # Tier 1: complete fact substring
    if fact_text:
        fact_norm = normalize(fact_text)
        if fact_norm and fact_norm in ctx_norm:
            return True, "tier1_strict"

    # Tier 2 / 3: anchor + answer
    anchor = extract_subject_entity_from_cloze(cloze)
    anchor_norm = normalize(anchor)
    if not anchor_norm or anchor_norm not in ctx_norm:
        return False, "none"
    if not ans_norm or ans_norm not in ctx_norm:
        return False, "none"

    # Tier 3: proximity (avoid false positive across unrelated facts)
    if co_occur_in_same_unit(ctx_norm, anchor_norm, ans_norm, max_distance):
        return True, "tier3_proximity"
    return False, "tier2_no_proximity"


# ─────────────────────────────────────────────────────────────────────────────
# Per-query final_context_text resolution
# ─────────────────────────────────────────────────────────────────────────────

def load_final_context(retrieval_file: Path) -> str:
    """Read one query_*_context_*.json and return the actual memory context string."""
    try:
        d = json.load(open(retrieval_file, encoding="utf-8"))
    except Exception:
        return ""
    # Mem0 / Mem0g: memories_str already concatenated
    if d.get("memories_str"):
        return d["memories_str"]
    # Fallback: build from retrieved_memories
    mems = d.get("retrieved_memories", [])
    if mems:
        return "\n".join(f"- {m.get('memory', m.get('text', ''))}" for m in mems if m)
    # Zep: edges
    if d.get("edges"):
        return "\n".join(f"- {e.get('fact', '')}" for e in d["edges"] if e)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Main classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_hop(hop: dict, ctx_text: str, max_distance: int) -> dict:
    """Compute new_present / old_present / state for one hop dict from alignment JSON."""
    new_present, new_via = check_fact_in_context(
        ctx_text, hop.get("gt_fact_text"), hop.get("gt_answer", ""),
        hop.get("cloze", ""), max_distance,
    )
    if hop.get("conflict_type") == "has_pair":
        old_present, old_via = check_fact_in_context(
            ctx_text, hop.get("old_fact_text"), hop.get("old_answer") or "",
            hop.get("cloze", ""), max_distance,
        )
    else:
        old_present, old_via = False, "no_old"

    if hop.get("conflict_type") == "has_pair":
        if new_present and not old_present:
            state = "CLEAN"
        elif old_present:
            state = "LEAK"
        else:
            state = "MISS"
    else:
        state = "RETRIEVED" if new_present else "MISS"

    return {
        "hop_idx": hop.get("hop_idx"),
        "conflict_type": hop.get("conflict_type"),
        "gt_seq": hop.get("gt_seq"),
        "old_seq": hop.get("old_seq"),
        "gt_answer": hop.get("gt_answer"),
        "old_answer": hop.get("old_answer"),
        "update_gap": hop.get("update_gap"),
        "new_present": new_present,
        "old_present": old_present,
        "new_matched_via": new_via,
        "old_matched_via": old_via,
        "state": state,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alignment", required=True, type=Path,
                    help="From align_mem0_mquake.py output")
    ap.add_argument("--retrieval-dir", required=True, type=Path,
                    help="Dir containing query_*_context_*.json")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--max-distance", type=int, default=50,
                    help="Token distance for tier-3 proximity (default 50)")
    args = ap.parse_args()

    align = json.load(open(args.alignment, encoding="utf-8"))
    out_entries = []
    state_counter = Counter()
    via_counter = Counter()
    has_pair_hops = 0
    no_conflict_hops = 0

    for q in align["entries"]:
        qid = q.get("query_id")
        # Find matching retrieval file
        cands = sorted(args.retrieval_dir.glob(f"query_{qid}_context_*.json")) if qid is not None else []
        ctx_text = load_final_context(cands[0]) if cands else ""

        classified_hops = []
        for hop in q["hops"]:
            c = classify_hop(hop, ctx_text, args.max_distance)
            classified_hops.append(c)
            state_counter[c["state"]] += 1
            via_counter[c["new_matched_via"]] += 1
            if hop.get("conflict_type") == "has_pair":
                has_pair_hops += 1
            else:
                no_conflict_hops += 1

        out_entries.append({
            "qa_pair_id": q.get("qa_pair_id"),
            "query_id": qid,
            "case_id": q.get("case_id"),
            "n_hops": len(classified_hops),
            "context_token_len_approx": len(ctx_text.split()) if ctx_text else 0,
            "hops": classified_hops,
        })

    total_hops = sum(state_counter.values())
    summary = {
        "alignment_file": str(args.alignment),
        "retrieval_dir": str(args.retrieval_dir),
        "n_queries": len(out_entries),
        "total_hops": total_hops,
        "has_pair_hops": has_pair_hops,
        "no_conflict_hops": no_conflict_hops,
        "state_counts": dict(state_counter),
        "matched_via_counts": dict(via_counter),
        # Rates per FC_metrics_spec §3.4
        "rates": {
            "CLEAN_rate_has_pair": (state_counter["CLEAN"] / has_pair_hops) if has_pair_hops else 0,
            "LEAK_rate_has_pair":  (state_counter["LEAK"]  / has_pair_hops) if has_pair_hops else 0,
            "MISS_rate_has_pair":  (state_counter["MISS"]  / has_pair_hops) if has_pair_hops else 0,
            "RETRIEVED_rate_no_conflict": (state_counter["RETRIEVED"] / no_conflict_hops) if no_conflict_hops else 0,
            "MISS_rate_no_conflict": ((state_counter["MISS"] - sum(
                1 for e in out_entries for h in e["hops"]
                if h["conflict_type"] == "has_pair" and h["state"] == "MISS"
            )) / no_conflict_hops) if no_conflict_hops else 0,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"summary": summary, "entries": out_entries},
              open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("=== M-core summary ===")
    print(f"  queries          : {summary['n_queries']}")
    print(f"  has_pair hops    : {has_pair_hops}")
    print(f"  no_conflict hops : {no_conflict_hops}")
    for k, v in state_counter.most_common():
        print(f"  {k:>10s} : {v:4d}")
    print()
    print("  CLEAN_rate(has_pair)     : {:.1f}%".format(summary["rates"]["CLEAN_rate_has_pair"] * 100))
    print("  LEAK_rate (has_pair)     : {:.1f}%".format(summary["rates"]["LEAK_rate_has_pair"] * 100))
    print("  MISS_rate (has_pair)     : {:.1f}%".format(summary["rates"]["MISS_rate_has_pair"] * 100))
    print("  RETRIEVED_rate (no_conflict): {:.1f}%".format(summary["rates"]["RETRIEVED_rate_no_conflict"] * 100))
    print(f"\n[write] {args.out}")


if __name__ == "__main__":
    main()
