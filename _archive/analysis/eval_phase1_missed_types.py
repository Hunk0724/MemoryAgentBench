"""Classify Phase 1 missed chain_old hops into Type-1 / Type-2 / Type-3
per chat §B.7.2 "discoverability asymmetry" framework.

Type-1: same (S, R) different O — our Phase 1 rule SHOULD catch this
        (e.g., (Charles Darwin, married to, Amala) vs (Charles Darwin, married to, Emma))
Type-2: hop 2+ direct conflict where S differs between chain_new and chain_old
        (e.g., chain_new (Bernard, nationality, France) vs chain_old (Jack, citizen, US))
Type-3: satellite — chain_old fact is correct in isolation but on chain_old entity
        (e.g., (Jack, born_in, NYC) is true but Jack himself is chain_old)

Heuristic: parse subject from gt_fact_text vs old_fact_text:
  same subject → Type-1
  different subject → Type-2 (we treat Type-3 as a subset of Type-2 for now since
                              they both have "wrong subject" pattern; LLM judge can
                              separate them if needed)

Output: how many MISSED hops are Type-1 (recoverable by better Phase 1) vs Type-2
        (need new mechanism beyond (S, R, O) detection — e.g., chain anchor propagation).
"""
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
SUPERSESSION = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/supersession_index.json"
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"


# Heuristic subject extraction. Common FC predicates as boundary markers.
PREDICATE_PATTERNS = [
    r"\bis a citizen of\b", r"\bis married to\b", r"\bwas married to\b",
    r"\bis associated with\b", r"\bwas associated with\b",
    r"\bplays the position of\b", r"\bplays position\b",
    r"\bis the chairperson of\b", r"\bwas the chairperson of\b",
    r"\bwas born in\b", r"\bis born in\b",
    r"\bdied in\b", r"\bwas employed by\b", r"\bis employed by\b",
    r"\bwas founded by\b", r"\bis founded by\b",
    r"\bwas performed by\b", r"\bis performed by\b",
    r"\bwas developed by\b", r"\bis developed by\b",
    r"\bwas created by\b", r"\bis created by\b",
    r"\bwas authored by\b", r"\bis authored by\b",
    r"\bwas composed by\b", r"\bis composed by\b",
    r"\bwas directed by\b", r"\bis directed by\b",
    r"\bis located in\b", r"\bwas located in\b",
    r"\bis the capital of\b", r"\bwas the capital of\b",
    r"\bis the founder of\b", r"\bwas the founder of\b",
    r"\bspeaks\b", r"\bwrote\b", r"\bcomposed\b",
    r"\bis owned by\b", r"\bwas owned by\b",
    r"\bworks for\b", r"\bworked for\b",
    r"\bis the author of\b", r"\bwas the author of\b",
    r"\bis the director of\b", r"\bwas the director of\b",
    r"\bis the country of citizenship of\b",
    # Generic copula fallback
    r"\bis the\b", r"\bwas the\b", r"\bare\b", r"\bwere\b",
    r"\bhas\b", r"\bhad\b", r"\bis\b", r"\bwas\b",
]


def parse_subject(fact_text: str) -> str:
    """Heuristic: subject is everything before the first matched predicate pattern."""
    text = fact_text.rstrip(".").strip()
    for pat in PREDICATE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            subj = text[: m.start()].strip().lower()
            if subj:
                return subj
    # fallback: first 3 tokens
    return " ".join(text.split()[:3]).lower()


def fact_in_text(s: str, r: str, o: str, text: str) -> bool:
    """For matching superseded (s, r, o) against GT old_fact_text (heuristic)."""
    s_n = s.lower().strip()
    o_n = o.lower().strip()
    t_n = text.lower()
    if len(s_n) < 3 or len(o_n) < 3:
        return False
    return s_n in t_n and o_n in t_n


def main():
    sup = json.load(open(SUPERSESSION))
    superseded_facts = sup.get("superseded_facts", {})
    gt = json.load(open(GT))

    detected_count = 0
    missed_count = 0
    missed_type1 = []
    missed_type2 = []
    detected_examples = []
    type_distribution_all_hops = {"Type-1": 0, "Type-2": 0}

    for q in gt:
        qid = q.get("query_id")
        for hop_idx, hop in enumerate(q.get("hops", [])):
            if hop.get("conflict_type") != "has_pair":
                continue

            gt_text = hop.get("gt_fact_text", "")
            old_text = hop.get("old_fact_text", "")
            if not gt_text or not old_text:
                continue

            # Type classify based on whether subject matches
            s_gt = parse_subject(gt_text)
            s_old = parse_subject(old_text)
            same_subject = (s_gt == s_old) and s_gt != ""
            type_label = "Type-1" if same_subject else "Type-2"
            type_distribution_all_hops[type_label] += 1

            # Did Phase 1 detect this chain_old?
            detected = False
            for fk, info in superseded_facts.items():
                if fact_in_text(info["s"], info["r"], info["o_old"], old_text):
                    detected = True
                    break

            if detected:
                detected_count += 1
                detected_examples.append({
                    "qid": qid, "hop_idx": hop_idx,
                    "type": type_label,
                    "s_gt": s_gt, "s_old": s_old,
                    "old_fact": old_text, "gt_fact": gt_text,
                })
            else:
                missed_count += 1
                bucket = missed_type1 if type_label == "Type-1" else missed_type2
                bucket.append({
                    "qid": qid, "hop_idx": hop_idx,
                    "type": type_label,
                    "s_gt": s_gt, "s_old": s_old,
                    "old_fact": old_text, "gt_fact": gt_text,
                })

    total = detected_count + missed_count

    # ===== Report =====
    print("=" * 72)
    print("Phase 1 Detection: Type-1/2 classification of GT chain_old hops")
    print("=" * 72)
    print(f"\nTotal GT has_pair hops: {total}")
    print(f"Phase 1 detected:       {detected_count} ({detected_count*100/total:.1f}%)")
    print(f"Phase 1 missed:         {missed_count} ({missed_count*100/total:.1f}%)")

    print(f"\n--- Type distribution across ALL GT has_pair hops ---")
    for t, c in type_distribution_all_hops.items():
        print(f"  {t}: {c}/{total} ({c*100/total:.1f}%)")

    print(f"\n--- Of {missed_count} MISSED hops ---")
    n_missed_type1 = len(missed_type1)
    n_missed_type2 = len(missed_type2)
    print(f"  Type-1 missed (same S, OpenIE surface mismatch): {n_missed_type1} ({n_missed_type1*100/missed_count:.1f}% of missed)")
    print(f"    → recoverable by Phase 1 v0.1 alias normalization")
    print(f"  Type-2 missed (different S, hop 2+ structural): {n_missed_type2} ({n_missed_type2*100/missed_count:.1f}% of missed)")
    print(f"    → needs new mechanism (chain_old anchor propagation, subgraph injection)")

    # Detection rate by type
    detected_t1 = sum(1 for e in detected_examples if e["type"] == "Type-1")
    detected_t2 = sum(1 for e in detected_examples if e["type"] == "Type-2")
    total_t1 = detected_t1 + n_missed_type1
    total_t2 = detected_t2 + n_missed_type2
    print(f"\n--- Detection rate by Type ---")
    if total_t1 > 0:
        print(f"  Type-1: {detected_t1}/{total_t1} = {detected_t1*100/total_t1:.1f}% detected")
    if total_t2 > 0:
        print(f"  Type-2: {detected_t2}/{total_t2} = {detected_t2*100/total_t2:.1f}% detected (expect low)")
    else:
        print(f"  Type-2: 0 GT cases (FC-MH 6k GT is entirely Type-1 by construction)")

    print(f"\n--- Sample Type-1 MISSED (Phase 1 should catch with better surface matching) ---")
    for e in missed_type1[:5]:
        print(f"  qid={e['qid']} hop={e['hop_idx']}  s={e['s_gt']!r}")
        print(f"    GT new:  {e['gt_fact']!r}")
        print(f"    GT old:  {e['old_fact']!r}")

    print(f"\n--- Sample Type-2 MISSED (different S, structural — needs v2 mechanism) ---")
    for e in missed_type2[:5]:
        print(f"  qid={e['qid']} hop={e['hop_idx']}  s_gt={e['s_gt']!r} s_old={e['s_old']!r}")
        print(f"    GT new:  {e['gt_fact']!r}")
        print(f"    GT old:  {e['old_fact']!r}")

    # Save
    out = BASE / "analysis/results/phase_v1/phase1_missed_types.json"
    json.dump({
        "n_total_has_pair_hops": total,
        "n_detected": detected_count,
        "n_missed": missed_count,
        "type_distribution_all": type_distribution_all_hops,
        "detection_rate_by_type": {
            "Type-1": {"detected": detected_t1, "total": total_t1, "rate": detected_t1/total_t1 if total_t1 else 0},
            "Type-2": {"detected": detected_t2, "total": total_t2, "rate": detected_t2/total_t2 if total_t2 else 0},
        },
        "missed_type1_examples": missed_type1[:20],
        "missed_type2_examples": missed_type2[:20],
    }, open(out, "w"), indent=2)
    print(f"\n[wrote] {out}")


if __name__ == "__main__":
    main()
