"""G.11 — Phase 2 filter event P/Q/R-P1/R-P2/S quadrant analysis.

Reads the per-query candidate dump produced by HippoRAG._phase2_filter_chain_old
(env-gated via HIPPORAG_PHASE2_DUMP_PATH) and cross-references with:
  - GT mh_512_mquake_analysis.json (chain_new/chain_old fact text per hop)
  - vdb_chunk.parquet (passage content for substring matching)
  - HippoRAG result JSON (exact_match per query, for EM correlation)

Output: per-passage quadrant classification + aggregate counts + EM correlation.

Quadrant definitions (per filter event OR per candidate-with-chain_old):
  P     filtered & contains chain_old              (correct filter)
  Q     filtered & contains chain_new only         (false-positive filter)
  S     filtered & neither chain_old nor chain_new (silent — no effect)
  R-P1  NOT filtered & contains chain_old & P1 didn't detect any superseded
        fact matching this hop (Phase 1 detection gap)
  R-P2  NOT filtered & contains chain_old & P1 detected a matching superseded
        fact, but Phase 2 didn't trigger filter (Phase 2 chain-anchor gap)

Usage:
  python analysis/eval_phase2_filter_quadrants.py \\
    --dump-sh monitoring_logs/<ts>_g11_phase2_dump/sh_phase2_dump.jsonl \\
    --dump-mh monitoring_logs/<ts>_g11_phase2_dump/mh_phase2_dump.jsonl \\
    --em-sh ... --em-mh ... \\
    --gt-mh analysis/results/mh_512_mquake_analysis.json \\
    --out analysis/results/phase_v1/g11_filter_quadrants.json
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

BASE = Path("/home/yhchiang/MemoryAgentBench")


def norm(s: str) -> str:
    """Aggressive normalize for substring match: lower, collapse ws, strip trailing punct."""
    s = re.sub(r"\s+", " ", (s or "").lower().strip())
    return s.rstrip(".,;:!?\"'")


def fact_in_passage(fact_text: str, passage_text: str) -> bool:
    """Check if fact_text appears in passage (substring on normalized form)."""
    f = norm(fact_text)
    p = norm(passage_text)
    if len(f) < 5:
        return False
    return f in p


def load_chunk_content_map(parquet_path: Path) -> Dict[str, str]:
    """hash_id -> content."""
    df = pd.read_parquet(parquet_path)
    return dict(zip(df["hash_id"], df["content"]))


def load_em_map(result_path: Path) -> Dict[int, dict]:
    """query_id -> {exact_match, output, answer, query}."""
    d = json.load(open(result_path))
    out = {}
    for rec in d["data"]:
        qid = rec["query_id"]
        out[qid] = {
            "exact_match": rec.get("exact_match", False),
            "substring_em": rec.get("substring_exact_match", False),
            "output": rec.get("output", ""),
            "answer": rec.get("answer", []),
        }
    return out


def load_dump(dump_path: Path) -> List[dict]:
    """Phase 2 per-query dump JSONL."""
    out = []
    with open(dump_path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def hop_matches_superseded(hop: dict, sf: dict) -> bool:
    """Check whether a P1-detected superseded fact (sf with s/r/o_old) corresponds to this hop.

    Loose match: fact's o_old appears in hop's old_fact_text, and fact's s appears too.
    """
    s, o_old = norm(sf["s"]), norm(sf["o_old"])
    old_text = norm(hop.get("old_fact_text", ""))
    if not s or not o_old or not old_text:
        return False
    return s in old_text and o_old in old_text and len(s) >= 3 and len(o_old) >= 3


def classify_passage_for_hop(cand: dict,
                              hop: dict,
                              passage_text: str) -> Optional[str]:
    """Return P/Q/S/R-P1/R-P2 or None (not relevant to this hop).

    A passage is "relevant to this hop" if it contains chain_old or chain_new
    text from the hop. If it contains neither, return None (skip).
    Special case: if filter_triggered=True AND passage contains neither, it
    means filter operated on a different hop's conflict → return 'S' (silent
    for THIS hop, but may be P/Q for another hop).
    """
    gt_text = hop.get("gt_fact_text", "")
    old_text = hop.get("old_fact_text", "")
    if not gt_text or not old_text:
        return None

    contains_old = fact_in_passage(old_text, passage_text)
    contains_new = fact_in_passage(gt_text, passage_text)

    filter_triggered = cand.get("filter_triggered", False)

    # Whether P1 has a superseded label matching this hop in this passage
    p1_detected_for_this_hop = any(
        hop_matches_superseded(hop, sf)
        for sf in cand.get("superseded_fact_details", [])
    )

    if filter_triggered:
        if contains_old and not contains_new:
            return "P"
        if contains_new and not contains_old:
            return "Q"
        if contains_old and contains_new:
            return "P_same_passage"  # filter removes chunk that has BOTH (tricky)
        return "S"  # filter triggered but passage doesn't contain this hop's facts
    else:
        # Not filtered
        if contains_old and not contains_new:
            return "R-P2" if p1_detected_for_this_hop else "R-P1"
        if contains_old and contains_new:
            # Same passage holds both; not "missed" since chain_new is also here
            return "R_same_passage"
        return None  # passage doesn't have chain_old → not a miss


def analyze_hop_aligned(split_name: str,
                         dump: List[dict],
                         em_map: Dict[int, dict],
                         gt: List[dict],
                         chunk_content: Dict[str, str]) -> dict:
    """Hop-aligned analysis (188 denominator).

    For each has_pair hop in GT, classify as exactly one of:
      A. chain_old not in top-N  (upstream retrieval miss)
      B. P-filtered              (chain_old in top-N, P2 filtered ≥1)
      C. R-P2                    (in top-N, P1 labeled, P2 didn't filter)
      D. R-P1                    (in top-N, P1 didn't label)
    Independent metric: E. Q-damaged (chain_new wrongly filtered, can co-occur)
    """
    gt_by_qid = {q["query_id"]: q for q in gt}
    status_counts = Counter()
    em_by_status = defaultdict(lambda: {"em_correct": 0, "em_wrong": 0})
    q_damaged_count = 0
    chain_new_in_topN_count = 0
    per_hop_records = []

    for rec in dump:
        qid = rec["q_idx"]
        gt_query = gt_by_qid.get(qid)
        em_rec = em_map.get(qid)
        if gt_query is None or em_rec is None:
            continue
        em = bool(em_rec["exact_match"]) or bool(em_rec.get("substring_em", False))

        hops_has_pair = [h for h in gt_query.get("hops", []) if h.get("conflict_type") == "has_pair"]
        candidates = rec["candidates"]

        for hop in hops_has_pair:
            gt_text = hop.get("gt_fact_text", "")
            old_text = hop.get("old_fact_text", "")
            if not gt_text or not old_text:
                continue

            # Pass over all candidates: find which contain chain_old / chain_new
            chain_old_passages = []
            chain_new_passages = []
            for cand in candidates:
                passage_text = chunk_content.get(cand["chunk_key"], "")
                if not passage_text:
                    continue
                if fact_in_passage(old_text, passage_text):
                    chain_old_passages.append(cand)
                if fact_in_passage(gt_text, passage_text):
                    chain_new_passages.append(cand)

            # Determine single hop status
            if not chain_old_passages:
                status = "A_not_in_topN"
            else:
                any_filtered = any(c["filter_triggered"] for c in chain_old_passages)
                any_p1_labeled = any(
                    hop_matches_superseded(hop, sf)
                    for c in chain_old_passages
                    for sf in c.get("superseded_fact_details", [])
                )
                if any_filtered:
                    status = "B_P_filtered"
                elif any_p1_labeled:
                    status = "C_R-P2"
                else:
                    status = "D_R-P1"

            status_counts[status] += 1
            em_by_status[status]["em_correct" if em else "em_wrong"] += 1

            # Independent: E. damage (chain_new wrongly filtered)
            chain_new_filtered_count = sum(1 for c in chain_new_passages if c["filter_triggered"])
            if chain_new_passages:
                chain_new_in_topN_count += 1
                if chain_new_filtered_count > 0:
                    q_damaged_count += 1

            per_hop_records.append({
                "qid": qid, "hop_idx": hop["hop_idx"], "status": status,
                "n_chain_old_passages": len(chain_old_passages),
                "n_chain_new_passages": len(chain_new_passages),
                "chain_new_filtered": chain_new_filtered_count > 0,
                "em": em,
            })

    total_hops = sum(status_counts.values())
    chain_old_in_topN = total_hops - status_counts["A_not_in_topN"]

    print(f"\n--- Hop-aligned status (n_hops={total_hops}) ---")
    for st in ("A_not_in_topN", "B_P_filtered", "C_R-P2", "D_R-P1"):
        c = status_counts[st]
        denom_pct = c * 100 / total_hops if total_hops else 0
        inscope_pct = (c * 100 / chain_old_in_topN if chain_old_in_topN and st != "A_not_in_topN" else None)
        line = f"  {st:18s}  {c:3d}  ({denom_pct:5.1f}% of all)"
        if inscope_pct is not None:
            line += f"   ({inscope_pct:5.1f}% of chain_old-in-topN)"
        print(line)

    print(f"\n--- Phase 2 derived metrics (denominator = chain_old in top-N = {chain_old_in_topN}) ---")
    if chain_old_in_topN > 0:
        p = status_counts["B_P_filtered"]
        rp2 = status_counts["C_R-P2"]
        rp1 = status_counts["D_R-P1"]
        filter_recall = p / chain_old_in_topN
        print(f"  Filter recall  (B / B+C+D):  {p}/{chain_old_in_topN} = {filter_recall:.1%}")
        # Filter precision: of all hops where filter triggered on a chain_old passage,
        # how many actually contained chain_old? = P / (P + filter_triggered_on_non_chain_old)
        # → derive from filter_events
        n_filter_events = sum(rec["n_filtered"] for rec in dump)
        # In hop-aligned view, B counts hops where filter helped on chain_old.
        # Hard to give precision purely from hop-status; use per-passage from earlier.
        print(f"  P1 detection (this hop's chain_old in P1 label):")
        print(f"    (B+C) / (B+C+D) = {p+rp2}/{chain_old_in_topN} = {(p+rp2)*100/chain_old_in_topN:.1f}%")

    print(f"\n--- Damage check ---")
    print(f"  chain_new in top-N:           {chain_new_in_topN_count}/{total_hops}")
    print(f"  chain_new wrongly filtered:   {q_damaged_count} ({q_damaged_count*100/max(1,chain_new_in_topN_count):.1f}% of chain_new-in-topN)")

    print(f"\n--- EM-by-status (correlation, not causation) ---")
    print(f"  {'status':<18s}  {'EM ok':>5s}  {'EM ng':>5s}  {'rate':>6s}")
    for st in ("A_not_in_topN", "B_P_filtered", "C_R-P2", "D_R-P1"):
        ok = em_by_status[st]["em_correct"]
        ng = em_by_status[st]["em_wrong"]
        if ok + ng == 0:
            continue
        print(f"  {st:<18s}  {ok:>5d}  {ng:>5d}  {ok/(ok+ng):>6.1%}")

    return {
        "split": split_name,
        "n_hops": total_hops,
        "status_counts": dict(status_counts),
        "chain_old_in_topN": chain_old_in_topN,
        "chain_new_in_topN": chain_new_in_topN_count,
        "q_damaged": q_damaged_count,
        "em_by_status": {st: dict(v) for st, v in em_by_status.items()},
        "per_hop_records": per_hop_records,
    }


def analyze_split(split_name: str,
                  dump: List[dict],
                  em_map: Dict[int, dict],
                  gt: Optional[List[dict]],
                  chunk_content: Dict[str, str]) -> dict:
    """Analyze one split (sh or mh). For SH, gt is None (only MH has chain analysis JSON)."""
    print(f"\n{'=' * 75}")
    print(f"  Split: {split_name}  (n_queries_dump={len(dump)}, n_queries_em={len(em_map)})")
    print(f"{'=' * 75}")

    if gt is None:
        # SH split — only report filter behavior + EM correlation (no chain-level analysis)
        return analyze_sh_split(split_name, dump, em_map, chunk_content)

    gt_by_qid = {q["query_id"]: q for q in gt}
    n_filters_total = 0
    n_filters_with_chain_old_pass = 0
    quadrant_counts = Counter()
    per_query_summary = []

    # EM correlation: when filter triggered on chain_old, does EM improve?
    # We don't have a counterfactual EM-without-filter here (would need separate run);
    # instead we report EM correctness conditional on quadrant.
    em_by_quadrant = defaultdict(lambda: {"em_correct": 0, "em_wrong": 0})

    for rec in dump:
        qid = rec["q_idx"]
        gt_query = gt_by_qid.get(qid)
        em_rec = em_map.get(qid)
        if gt_query is None or em_rec is None:
            continue
        em = bool(em_rec["exact_match"]) or bool(em_rec.get("substring_em", False))

        hops_has_pair = [h for h in gt_query.get("hops", []) if h.get("conflict_type") == "has_pair"]
        query_quadrants = []
        for cand in rec["candidates"]:
            passage_text = chunk_content.get(cand["chunk_key"], "")
            if not passage_text:
                continue
            if cand["filter_triggered"]:
                n_filters_total += 1
            for hop in hops_has_pair:
                q = classify_passage_for_hop(cand, hop, passage_text)
                if q is None:
                    continue
                quadrant_counts[q] += 1
                em_by_quadrant[q]["em_correct" if em else "em_wrong"] += 1
                query_quadrants.append({
                    "rank": cand["rank"], "hop_idx": hop["hop_idx"], "quadrant": q,
                })
                if q in ("P", "P_same_passage") and cand["filter_triggered"]:
                    n_filters_with_chain_old_pass += 1

        per_query_summary.append({
            "qid": qid, "em": em, "events": query_quadrants,
        })

    print(f"\nQuadrant distribution ({split_name}):")
    total = sum(quadrant_counts.values())
    if total > 0:
        for q, c in quadrant_counts.most_common():
            print(f"  {q:18s}  {c:5d}  ({c*100/total:5.1f}%)")
    print(f"  TOTAL              {total}")

    print(f"\nEM-conditional-on-quadrant ({split_name}):")
    print(f"  {'quadrant':<18s}  {'EM ok':>6s}  {'EM ng':>6s}  {'rate':>6s}")
    for q in ("P", "P_same_passage", "Q", "S", "R-P1", "R-P2", "R_same_passage"):
        ok = em_by_quadrant[q]["em_correct"]
        ng = em_by_quadrant[q]["em_wrong"]
        if ok + ng == 0:
            continue
        rate = ok / (ok + ng) if (ok + ng) > 0 else 0
        print(f"  {q:<18s}  {ok:>6d}  {ng:>6d}  {rate:>6.1%}")

    print(f"\nFilter precision proxy:")
    print(f"  filtered events total:           {n_filters_total}")
    print(f"  filtered passages with chain_old: {n_filters_with_chain_old_pass}  "
          f"({n_filters_with_chain_old_pass*100/max(1,n_filters_total):.1f}%)")

    return {
        "split": split_name,
        "n_queries": len(per_query_summary),
        "n_filters_total": n_filters_total,
        "quadrant_counts": dict(quadrant_counts),
        "em_by_quadrant": {q: dict(v) for q, v in em_by_quadrant.items()},
        "per_query_summary": per_query_summary,
    }


def analyze_sh_split(split_name: str,
                     dump: List[dict],
                     em_map: Dict[int, dict],
                     chunk_content: Dict[str, str]) -> dict:
    """SH split: report only filter behavior + EM correlation (no chain-level ground truth)."""
    n_queries = len(dump)
    n_filtered_events = sum(c["filter_triggered"]
                            for r in dump for c in r["candidates"])
    queries_with_any_filter = sum(
        1 for r in dump if any(c["filter_triggered"] for c in r["candidates"])
    )
    em_with_filter = sum(
        1 for r in dump
        if any(c["filter_triggered"] for c in r["candidates"])
        and em_map.get(r["q_idx"], {}).get("exact_match", False)
    )
    em_without_filter = sum(
        1 for r in dump
        if not any(c["filter_triggered"] for c in r["candidates"])
        and em_map.get(r["q_idx"], {}).get("exact_match", False)
    )

    n_no_filter = n_queries - queries_with_any_filter
    print(f"  Total filter events:      {n_filtered_events}")
    print(f"  Queries with ≥1 filter:   {queries_with_any_filter}/{n_queries}")
    if queries_with_any_filter > 0:
        print(f"    EM correct rate:        {em_with_filter}/{queries_with_any_filter} = "
              f"{em_with_filter*100/queries_with_any_filter:.1f}%")
    if n_no_filter > 0:
        print(f"  Queries with 0 filter:    {n_no_filter}")
        print(f"    EM correct rate:        {em_without_filter}/{n_no_filter} = "
              f"{em_without_filter*100/n_no_filter:.1f}%")

    return {
        "split": split_name,
        "n_queries": n_queries,
        "n_filter_events": n_filtered_events,
        "queries_with_filter": queries_with_any_filter,
        "em_with_filter": em_with_filter,
        "em_without_filter": em_without_filter,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-sh", type=Path, required=True)
    ap.add_argument("--dump-mh", type=Path, required=True)
    ap.add_argument("--em-sh", type=Path, required=True)
    ap.add_argument("--em-mh", type=Path, required=True)
    ap.add_argument("--gt-mh", type=Path,
                    default=BASE / "analysis/results/mh_512_mquake_analysis.json")
    ap.add_argument("--chunk-parquet-mh", type=Path,
                    default=BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/chunk_embeddings/vdb_chunk.parquet")
    ap.add_argument("--chunk-parquet-sh", type=Path,
                    default=BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_sh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/chunk_embeddings/vdb_chunk.parquet")
    ap.add_argument("--out", type=Path,
                    default=BASE / "analysis/results/phase_v1/g11_filter_quadrants.json")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[load] SH dump:  {args.dump_sh}")
    dump_sh = load_dump(args.dump_sh)
    print(f"  → {len(dump_sh)} query records")
    print(f"[load] MH dump:  {args.dump_mh}")
    dump_mh = load_dump(args.dump_mh)
    print(f"  → {len(dump_mh)} query records")

    print(f"[load] SH EM:    {args.em_sh}")
    em_sh = load_em_map(args.em_sh)
    print(f"[load] MH EM:    {args.em_mh}")
    em_mh = load_em_map(args.em_mh)

    print(f"[load] MH GT:    {args.gt_mh}")
    gt_mh = json.load(open(args.gt_mh))

    print(f"[load] MH chunks: {args.chunk_parquet_mh}")
    chunks_mh = load_chunk_content_map(args.chunk_parquet_mh)
    print(f"[load] SH chunks: {args.chunk_parquet_sh}")
    chunks_sh = load_chunk_content_map(args.chunk_parquet_sh) if args.chunk_parquet_sh.exists() else {}

    # === Headline: hop-aligned (188 denominator) ===
    print("\n" + "=" * 75)
    print("  HOP-ALIGNED METRICS (single-status per hop, 188 denominator)")
    print("=" * 75)
    result_mh_hop = analyze_hop_aligned("MH", dump_mh, em_mh, gt_mh, chunks_mh)

    # === Detail: per-(passage, hop) (252-style classification) ===
    print("\n" + "=" * 75)
    print("  PER-(PASSAGE, HOP) DETAIL (cross-tab, for QA cross-hop S analysis)")
    print("=" * 75)
    result_mh = analyze_split("MH", dump_mh, em_mh, gt_mh, chunks_mh)
    result_sh = analyze_split("SH", dump_sh, em_sh, None, chunks_sh)

    out = {"mh_hop_aligned": result_mh_hop, "mh_per_passage": result_mh, "sh": result_sh}
    json.dump(out, open(args.out, "w"), indent=2)
    print(f"\n[wrote] {args.out}")


if __name__ == "__main__":
    main()
