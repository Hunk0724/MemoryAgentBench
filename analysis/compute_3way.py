"""
compute_3way.py
================
3-way contingency table: Detection × Retrieval × Answer.

Per query (FC_metrics_spec.md v1.4 §32.3):

    D (detection): did the method emit any UPDATE/DELETE event targeting
                   ANY of this query's GT old facts? (per-query aggregation
                   of compute_detection_action.py output)
    R (retrieval): is retrieval CLEAN for this query?
                   = all has_pair hops have gt_in_memories=True AND
                     old_in_memories=False (i.e., GT new fact retrieved,
                     no stale GT old fact leaking)
    A (answer)   : exact_match flag from align.json

8 cells, every query falls into exactly one:

    (D, R, A): ✓✓✓  clean win
    (D, R, ✗): inference failure — right context, LLM still wrong
    (D, ✗, ✗): retrieval failure — write-time detection right but retrieval missed
    (D, ✗, ✓): noise win — wrong context, lucky
    (✗, R, ✓): retrieval-only win — detection miss but retrieval was clean anyway
    (✗, R, ✗): retrieval clean but LLM still wrong
    (✗, ✗, ✗): full failure
    (✗, ✗, ✓): pure noise win

Inputs:
    --align        analysis/results/<run>_<task>_<ctx>_align.json
    --detect-act   analysis/results/<run>_<task>_<ctx>_detection_action.json
    --out          analysis/results/<run>_<task>_<ctx>_3way.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--align", required=True, type=Path)
    ap.add_argument("--detect-act", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    align = json.load(open(args.align, encoding="utf-8"))
    da = json.load(open(args.detect_act, encoding="utf-8"))

    # Build per-query set of "detected pair_ids" (query_id, hop_idx)
    detected_pairs_by_query = {}
    for ev in da.get("events", []):
        if ev["event"] not in ("UPDATE", "DELETE"):
            continue
        for (qid, hidx) in ev.get("matched_old_in_actedupon", []):
            detected_pairs_by_query.setdefault(qid, set()).add(hidx)

    rows = []
    cell_counter = Counter()  # keys: ('D','R','A') in {0,1}

    for q in align["entries"]:
        qid = q.get("query_id")
        if qid is None:
            continue
        # Only score queries with at least one has_pair hop (consistent with M-detection §4.2)
        has_pair_hops = [h for h in (q.get("hops") or []) if h.get("conflict_type") == "has_pair"]
        if not has_pair_hops:
            continue

        # R: clean retrieval = every has_pair hop has gt retrieved + no old leaked
        R_clean = all(
            bool(h.get("gt_in_memories")) and not bool(h.get("old_in_memories"))
            for h in has_pair_hops
        )

        # D: detected = method emitted UPDATE/DELETE matching ANY of this query's
        # has_pair hops (we use ANY rather than ALL because even partial detection
        # signals the method recognises a conflict on this query)
        q_hop_ids = {h.get("hop_idx") for h in has_pair_hops}
        detected_for_q = detected_pairs_by_query.get(qid, set())
        D_detected = bool(q_hop_ids & detected_for_q)

        # A: exact_match
        A = bool(q.get("exact_match"))

        cell = (int(D_detected), int(R_clean), int(A))
        cell_counter[cell] += 1

        rows.append({
            "qa_pair_id": q.get("qa_pair_id"),
            "query_id": qid,
            "n_has_pair_hops": len(has_pair_hops),
            "D": int(D_detected),
            "R": int(R_clean),
            "A": int(A),
            "cell": "".join(map(str, cell)),
            "n_detected_hops": len(q_hop_ids & detected_for_q),
        })

    total = sum(cell_counter.values())
    if total == 0:
        print("[warn] no queries with has_pair hops")
        return

    cell_labels = {
        (1, 1, 1): "clean win (D✓R✓A✓)",
        (1, 1, 0): "inference fail (D✓R✓A✗)",
        (1, 0, 1): "noise win (D✓R✗A✓)",
        (1, 0, 0): "retrieval fail (D✓R✗A✗)",
        (0, 1, 1): "retrieval-only win (D✗R✓A✓)",
        (0, 1, 0): "retrieval-only fail (D✗R✓A✗)",
        (0, 0, 1): "noise win (D✗R✗A✓)",
        (0, 0, 0): "full fail (D✗R✗A✗)",
    }

    cell_summary = {}
    for cell, label in cell_labels.items():
        n = cell_counter.get(cell, 0)
        cell_summary[label] = {"n": n, "pct": (100 * n / total) if total else 0.0}

    # Marginal rates
    D_rate = sum(1 for r in rows if r["D"]) / total
    R_rate = sum(1 for r in rows if r["R"]) / total
    A_rate = sum(1 for r in rows if r["A"]) / total

    # Conditional rates (mechanism evidence)
    cond = {
        "A | D=1, R=1": _cond(rows, lambda r: r["D"] and r["R"], lambda r: r["A"]),
        "A | D=1, R=0": _cond(rows, lambda r: r["D"] and not r["R"], lambda r: r["A"]),
        "A | D=0, R=1": _cond(rows, lambda r: not r["D"] and r["R"], lambda r: r["A"]),
        "A | D=0, R=0": _cond(rows, lambda r: not r["D"] and not r["R"], lambda r: r["A"]),
        "R | D=1":      _cond(rows, lambda r: r["D"], lambda r: r["R"]),
        "R | D=0":      _cond(rows, lambda r: not r["D"], lambda r: r["R"]),
        "A | R=1":      _cond(rows, lambda r: r["R"], lambda r: r["A"]),
        "A | R=0":      _cond(rows, lambda r: not r["R"], lambda r: r["A"]),
    }

    summary = {
        "n_queries": total,
        "D_rate": D_rate, "R_rate": R_rate, "A_rate": A_rate,
        "cells": cell_summary,
        "conditional": cond,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"summary": summary, "rows": rows},
              open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("=== 3-way D × R × A ===")
    print(f"  n_queries (has_pair): {total}")
    print(f"  D rate: {D_rate*100:5.1f}%   R rate: {R_rate*100:5.1f}%   "
          f"A rate (EM): {A_rate*100:5.1f}%")
    print()
    print("  Cells:")
    for cell, label in cell_labels.items():
        v = cell_summary[label]
        print(f"    {label:<30s} {v['n']:>4d}  ({v['pct']:>5.1f}%)")
    print()
    print("  Conditional rates (mechanism evidence):")
    for k, v in cond.items():
        if v is not None:
            n, p = v
            print(f"    P({k}): {p*100:>5.1f}%  (n={n})")
        else:
            print(f"    P({k}): n/a (empty conditioning set)")
    print(f"\n[write] {args.out}")


def _cond(rows, cond_fn, target_fn):
    """Compute P(target | condition). Returns (n_cond, rate) or None."""
    sub = [r for r in rows if cond_fn(r)]
    if not sub:
        return None
    return (len(sub), sum(1 for r in sub if target_fn(r)) / len(sub))


if __name__ == "__main__":
    main()
