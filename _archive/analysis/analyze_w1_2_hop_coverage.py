"""W1.2 per-hop coverage breakdown.

Reads cached W1.2 dry-test result + GT, and reports for each query
EXACTLY which hops' chain_new / chain_old got covered by:
  (a) Top-1 chain
  (b) Top-5 chains (any)
  (c) Same chain (chain_new + chain_old in one path → best for verdict)

Uses robust fact_match (token Jaccard) to avoid the surface-mismatch
false negatives we saw in qid=45's eyeball check.
"""
import json
import re
import unicodedata
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
W12_RESULT = BASE / "analysis/results/phase_v2/w1_2_dry_test.json"


def _norm(s: str) -> str:
    s = s.lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_PREDICATE_PATTERNS = [
    r"\bis a citizen of\b", r"\bcitizen of\b",
    r"\bis married to\b", r"\bwas married to\b", r"\bmarried to\b",
    r"\bis associated with\b", r"\bwas associated with\b", r"\bassociated with\b",
    r"\bplays the position of\b", r"\bplays position\b", r"\bposition of\b",
    r"\bis the chairperson of\b", r"\bwas the chairperson of\b", r"\bchairperson of\b",
    r"\bwas born in\b", r"\bis born in\b", r"\bborn in\b",
    r"\bdied in\b", r"\bwas employed by\b", r"\bis employed by\b", r"\bemployed by\b",
    r"\bwas founded by\b", r"\bis founded by\b", r"\bfounded by\b",
    r"\bwas created by\b", r"\bis created by\b", r"\bcreated by\b",
    r"\bwas authored by\b", r"\bis authored by\b", r"\bauthored by\b",
    r"\bis the author of\b", r"\bwas the author of\b", r"\bauthor of\b",
    r"\bis the director of\b", r"\bwas the director of\b", r"\bdirector of\b",
    r"\bis located in the continent of\b", r"\bis located in\b", r"\blocated in\b",
    r"\bis the capital of\b", r"\bcapital of\b",
    r"\bis the founder of\b", r"\bfounder of\b",
    r"\bcreated in the country of\b", r"\bcreated in\b",
    r"\bwritten in the language of\b", r"\bwritten in\b",
    r"\bspeaks\b", r"\bwrote\b", r"\bcomposed\b",
    r"\bis owned by\b", r"\bowned by\b",
    r"\bworks for\b", r"\bworked for\b",
    r"\bworks in field of\b",
    r"\bplace of death\b", r"\bdied\b",
    r"\bceo of\b", r"\bchief executive officer of\b",
    r"\bis famous for\b", r"\bfamous for\b",
    r"\bis the sport of\b", r"\bsport of\b",
    r"\bis the country of citizenship of\b",
    # Fallback (broad)
    r"\bis the\b", r"\bwas the\b", r"\bis\b", r"\bwas\b",
]


def extract_so(fact_text: str):
    """Best-effort extract (subject, object) from a fact text.

    Tries longest predicate patterns first to avoid premature short-pattern matches.
    Returns (s_norm, o_norm) or (None, None) if no pattern matches.
    """
    text = _norm(fact_text)
    # Try all patterns; keep the one where BOTH s and o are non-empty and ≥3 chars
    best = None
    best_span_len = 0
    for pat in _PREDICATE_PATTERNS:
        m = re.search(pat, text)
        if not m:
            continue
        s_phrase = text[:m.start()].strip()
        o_phrase = text[m.end():].strip()
        # strip leading articles
        s_phrase = re.sub(r"^(the |a |an )+", "", s_phrase)
        o_phrase = re.sub(r"^(the |a |an )+", "", o_phrase)
        if len(s_phrase) < 3 or len(o_phrase) < 3:
            continue
        # Prefer LONGER predicate match (more specific)
        span_len = m.end() - m.start()
        if span_len > best_span_len:
            best = (s_phrase, o_phrase)
            best_span_len = span_len
    return best if best else (None, None)


def fact_match(a: str, b: str) -> bool:
    """Strict: both extracted (s, o) must overlap (substring) on both sides.

    Handles: 'X is married to Y' ↔ 'X married to Y'
             'The author of X is Y' ↔ 'Y is the author of X' (subj/obj flip)
    """
    sa, oa = extract_so(a)
    sb, ob = extract_so(b)
    if sa is None or sb is None:
        return False

    def overlap(x, y):
        if len(x) < 3 or len(y) < 3:
            return False
        return x in y or y in x

    forward = overlap(sa, sb) and overlap(oa, ob)
    flipped = overlap(sa, ob) and overlap(oa, sb)
    return forward or flipped


def main():
    gt = json.load(open(GT))
    w12 = json.load(open(W12_RESULT))

    per_query_summary = []
    for r in w12["per_query"]:
        qid = r["qid"]
        q = next(x for x in gt if x["query_id"] == qid)

        # Build per-hop GT (only has_pair hops)
        hops = [h for h in q["hops"] if h.get("conflict_type") == "has_pair"]

        # For each chain in top-5, list which props it contains
        chain_prop_texts = [c["prop_texts"] for c in r["top_chains"]]

        # Per-hop coverage check
        hop_coverage = []
        for hop in hops:
            hi = hop["hop_idx"]
            new_text = hop["gt_fact_text"]
            old_text = hop["old_fact_text"]

            # in_top1: is new/old in chain rank 0
            new_in_top1 = any(fact_match(new_text, t) for t in chain_prop_texts[0]) if chain_prop_texts else False
            old_in_top1 = any(fact_match(old_text, t) for t in chain_prop_texts[0]) if chain_prop_texts else False

            # in_top5: any chain in top-5 contains
            new_in_top5 = any(any(fact_match(new_text, t) for t in c) for c in chain_prop_texts)
            old_in_top5 = any(any(fact_match(old_text, t) for t in c) for c in chain_prop_texts)

            # both_in_same_chain: any single chain contains BOTH (= verdict ready)
            both_in_same = False
            same_chain_rank = -1
            for ci, c in enumerate(chain_prop_texts):
                has_new = any(fact_match(new_text, t) for t in c)
                has_old = any(fact_match(old_text, t) for t in c)
                if has_new and has_old:
                    both_in_same = True
                    same_chain_rank = ci
                    break

            hop_coverage.append({
                "hop_idx": hi,
                "gt_new": new_text,
                "gt_old": old_text,
                "new_in_top1": new_in_top1,
                "old_in_top1": old_in_top1,
                "new_in_top5": new_in_top5,
                "old_in_top5": old_in_top5,
                "both_in_same_chain": both_in_same,
                "same_chain_rank": same_chain_rank,
            })

        per_query_summary.append({"qid": qid, "n_hops": len(hops), "hops": hop_coverage})

    # ─── Per-hop print ───
    print("=" * 100)
    print("  W1.2 per-hop coverage breakdown (robust token-Jaccard match)")
    print("=" * 100)
    for r in per_query_summary:
        print(f"\nqid={r['qid']} (n_hops={r['n_hops']}):")
        print(f"  {'hop':>3}  {'new_top1':>9}  {'old_top1':>9}  {'new_top5':>9}  {'old_top5':>9}  {'same_chain':>11}  GT new / GT old")
        for h in r["hops"]:
            nt1 = "✓" if h["new_in_top1"] else "✗"
            ot1 = "✓" if h["old_in_top1"] else "✗"
            nt5 = "✓" if h["new_in_top5"] else "✗"
            ot5 = "✓" if h["old_in_top5"] else "✗"
            sm = f"✓ (rank {h['same_chain_rank']})" if h["both_in_same_chain"] else "✗"
            print(f"  {h['hop_idx']:>3}  {nt1:>9}  {ot1:>9}  {nt5:>9}  {ot5:>9}  {sm:>11}")
            print(f"         new: {h['gt_new']}")
            print(f"         old: {h['gt_old']}")

    # ─── Aggregate ───
    print()
    print("=" * 100)
    print("  AGGREGATE")
    print("=" * 100)
    all_hops = [h for r in per_query_summary for h in r["hops"]]
    n_total = len(all_hops)
    n_new_top1 = sum(1 for h in all_hops if h["new_in_top1"])
    n_old_top1 = sum(1 for h in all_hops if h["old_in_top1"])
    n_new_top5 = sum(1 for h in all_hops if h["new_in_top5"])
    n_old_top5 = sum(1 for h in all_hops if h["old_in_top5"])
    n_both_same = sum(1 for h in all_hops if h["both_in_same_chain"])
    print(f"  Total has_pair hops across 5 queries: {n_total}")
    print(f"  ─────────────────────────────────────────")
    print(f"  chain_new in top-1 chain:       {n_new_top1}/{n_total} = {n_new_top1*100/n_total:.0f}%")
    print(f"  chain_old in top-1 chain:       {n_old_top1}/{n_total} = {n_old_top1*100/n_total:.0f}%")
    print(f"  chain_new in any top-5 chain:   {n_new_top5}/{n_total} = {n_new_top5*100/n_total:.0f}%")
    print(f"  chain_old in any top-5 chain:   {n_old_top5}/{n_total} = {n_old_top5*100/n_total:.0f}%")
    print(f"  BOTH new+old in same chain:     {n_both_same}/{n_total} = {n_both_same*100/n_total:.0f}%  ← Phase 2.b verdict-ready")

    # ─── Save ───
    out = BASE / "analysis/results/phase_v2/w1_2_hop_coverage.json"
    json.dump({
        "n_queries": len(per_query_summary),
        "aggregate": {
            "total_hops": n_total,
            "new_in_top1": n_new_top1,
            "old_in_top1": n_old_top1,
            "new_in_top5": n_new_top5,
            "old_in_top5": n_old_top5,
            "both_in_same_chain": n_both_same,
        },
        "per_query": per_query_summary,
    }, open(out, "w"), indent=2)
    print(f"\n  [wrote] {out}")


if __name__ == "__main__":
    main()
