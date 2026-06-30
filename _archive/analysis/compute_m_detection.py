"""
compute_m_detection.py
======================
Query-level All-CLEAN / Any-LEAK / Any-MISS aggregation (FC_metrics_spec §4).

Reads the output of compute_m_core.py (per-hop state classification) and
aggregates to query-level:
    all_clean = all(hop.state == CLEAN for has_pair hops in query)
    any_leak  = any(hop.state == LEAK)
    any_miss  = any(hop.state == MISS)

Also breaks down by:
    - n_hops (2 / 3 / 4)
    - max_update_gap bucket

Usage:
    python analysis/compute_m_detection.py \\
        --mcore analysis/results/<run>_mh_<ctx>_mcore.json \\
        --align analysis/results/<run>_mh_<ctx>_align.json \\
        --out   analysis/results/<run>_mh_<ctx>_mdetection.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcore", required=True, type=Path)
    ap.add_argument("--align", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    mcore = json.load(open(args.mcore, encoding="utf-8"))
    align = json.load(open(args.align, encoding="utf-8"))

    # Build query_id → (has_pair hops with state + max_update_gap + n_hops)
    align_by_id = {e["query_id"]: e for e in align["entries"] if e.get("query_id") is not None}

    queries = []
    for q_entry in mcore["entries"]:
        qid = q_entry.get("query_id")
        if qid is None:
            continue
        align_q = align_by_id.get(qid)
        if not align_q:
            continue

        has_pair_hops = [h for h in q_entry["hops"] if h["conflict_type"] == "has_pair"]
        if not has_pair_hops:
            # query with no conflict pairs — skip from M-detection (per spec §4.2)
            continue

        states = [h["state"] for h in has_pair_hops]
        n_clean = sum(1 for s in states if s == "CLEAN")
        n_leak = sum(1 for s in states if s == "LEAK")
        n_miss = sum(1 for s in states if s == "MISS")
        all_clean = all(s == "CLEAN" for s in states)
        any_leak = any(s == "LEAK" for s in states)
        any_miss = any(s == "MISS" for s in states)

        gaps = [h.get("update_gap") for h in has_pair_hops if h.get("update_gap") is not None]
        max_gap = max(gaps) if gaps else None
        min_gap = min(gaps) if gaps else None

        queries.append({
            "qa_pair_id": q_entry.get("qa_pair_id"),
            "query_id": qid,
            "n_has_pair_hops": len(has_pair_hops),
            "n_total_hops": q_entry["n_hops"],
            "n_clean": n_clean, "n_leak": n_leak, "n_miss": n_miss,
            "all_clean": all_clean,
            "any_leak": any_leak,
            "any_miss": any_miss,
            "max_update_gap": max_gap,
            "min_update_gap": min_gap,
            "exact_match": align_q.get("exact_match", False),
            "error_type": align_q.get("error_type"),
        })

    total = len(queries)
    if total == 0:
        print("No queries with has_pair hops found")
        return

    n_all_clean = sum(1 for q in queries if q["all_clean"])
    n_any_leak = sum(1 for q in queries if q["any_leak"])
    n_any_miss = sum(1 for q in queries if q["any_miss"])

    summary = {
        "n_queries": total,
        "All_CLEAN_rate": n_all_clean / total,
        "Any_LEAK_rate": n_any_leak / total,
        "Any_MISS_rate": n_any_miss / total,
    }

    # Breakdown by n_total_hops
    by_n_hops = {}
    for n in sorted(set(q["n_total_hops"] for q in queries)):
        sub = [q for q in queries if q["n_total_hops"] == n]
        if sub:
            by_n_hops[n] = {
                "n": len(sub),
                "All_CLEAN_rate": sum(1 for q in sub if q["all_clean"]) / len(sub),
                "Any_LEAK_rate": sum(1 for q in sub if q["any_leak"]) / len(sub),
                "Any_MISS_rate": sum(1 for q in sub if q["any_miss"]) / len(sub),
                "EM_rate": sum(1 for q in sub if q["exact_match"]) / len(sub),
            }
    summary["by_n_hops"] = by_n_hops

    # Breakdown by max_update_gap bucket
    def bucket(g):
        if g is None:
            return "none"
        if g <= 50:
            return "close (≤50)"
        if g <= 200:
            return "mid (51-200)"
        return "far (>200)"

    by_gap = {}
    for q in queries:
        b = bucket(q["max_update_gap"])
        by_gap.setdefault(b, []).append(q)
    summary["by_max_update_gap"] = {
        b: {
            "n": len(sub),
            "All_CLEAN_rate": sum(1 for q in sub if q["all_clean"]) / len(sub),
            "Any_LEAK_rate": sum(1 for q in sub if q["any_leak"]) / len(sub),
            "EM_rate": sum(1 for q in sub if q["exact_match"]) / len(sub),
        }
        for b, sub in by_gap.items()
    }

    # Detection vs EM correlation matrix (4 cells)
    correlate = Counter()
    for q in queries:
        correlate[("clean" if q["all_clean"] else "not_clean",
                   "EM" if q["exact_match"] else "noEM")] += 1
    summary["detection_x_em"] = {
        "AllClean_EM": correlate[("clean", "EM")],
        "AllClean_noEM": correlate[("clean", "noEM")],
        "notClean_EM": correlate[("not_clean", "EM")],
        "notClean_noEM": correlate[("not_clean", "noEM")],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"summary": summary, "queries": queries},
              open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("=== M-detection summary ===")
    print(f"  queries (has_pair) : {total}")
    print(f"  All-CLEAN rate     : {summary['All_CLEAN_rate']*100:.1f}%")
    print(f"  Any-LEAK rate      : {summary['Any_LEAK_rate']*100:.1f}%")
    print(f"  Any-MISS rate      : {summary['Any_MISS_rate']*100:.1f}%")
    print()
    print("  By n_hops:")
    for n, v in by_n_hops.items():
        print(f"    {n}-hop: n={v['n']:>2}  AllCLEAN={v['All_CLEAN_rate']*100:>5.1f}%  "
              f"AnyLEAK={v['Any_LEAK_rate']*100:>5.1f}%  EM={v['EM_rate']*100:>5.1f}%")
    print()
    print("  By max_update_gap:")
    for b, v in summary["by_max_update_gap"].items():
        print(f"    {b:<16}: n={v['n']:>2}  AllCLEAN={v['All_CLEAN_rate']*100:>5.1f}%  "
              f"AnyLEAK={v['Any_LEAK_rate']*100:>5.1f}%  EM={v['EM_rate']*100:>5.1f}%")
    print()
    print("  Detection × EM:")
    for k, v in summary["detection_x_em"].items():
        print(f"    {k:<20s}: {v}")
    print(f"\n[write] {args.out}")


if __name__ == "__main__":
    main()
