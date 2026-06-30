"""
compute_claim_AB.py
====================
跨方法 Claim A (Detection) + Claim B (Multi-hop Retrieval) + chain_old leak + EM
per query × n_hops × ctx。

Definitions (per query):
  A_all_detected  = 該題所有 has_pair hop 的 chain_old 都被 method 正確識別
                    (method-specific signal:
                     - Mem0:           L2 UPDATE/DELETE event matched chain_old text
                     - Mem0g vector:   same as Mem0
                     - Mem0g graph:    G4 DELETE entity matched chain_old entity
                     - Mem0g union:    vector OR graph (寬鬆)
                     - Our method:     verdict list contains chain_old proposition
                    )
  B_all_retrieved = 該題所有 hop (含 no_pair) 的 GT fact 都在 retrieved memories
                    (用各方法的最終 LLM-facing retrieval 算)
  chain_old_leak  = 該題任一 has_pair hop 的 chain_old 在 retrieved memories
                    (低 = filter 對)
  EM              = 最終答對

Output:
  per method × ctx × n_hops 一行:
    n_q, A%, B%, leak%, EM%
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def compute_a_b_per_method(align_path: Path, detect_path: Path | None = None,
                            d_definition: str = "vector"):
    """
    Compute A (detection) + B (retrieval all-hops) + leak + EM per n_hops.

    d_definition options:
      'vector'   — count only vector-path UPDATE/DELETE events
      'graph'    — count only graph-path DELETE entity events (Mem0g only)
      'union'    — vector OR graph (Mem0g most permissive)
      'na'       — no detection available (LCA / HippoRAG vanilla)
    """
    align = json.load(open(align_path, encoding="utf-8"))
    entries = align["entries"]

    # Build detected map: query_id → set of (hop_idx that detection event matched)
    detected_per_query: dict[int, set] = defaultdict(set)
    if detect_path and detect_path.exists():
        detect = json.load(open(detect_path, encoding="utf-8"))
        for ev in detect.get("events", []):
            ev_type = ev.get("event", "")
            if ev_type not in ("UPDATE", "DELETE"):
                continue
            # matched_old_in_actedupon = [(query_id, hop_idx), ...]
            for (qid, hidx) in ev.get("matched_old_in_actedupon", []):
                detected_per_query[qid].add(hidx)

    rows_by_n_hops: dict[int, list[dict]] = defaultdict(list)
    for q in entries:
        n_hops = q.get("n_hops")
        if n_hops not in (2, 3, 4):
            continue
        qid = q.get("query_id")
        hops = q.get("hops") or []
        has_pair_hops = [h for h in hops if h.get("conflict_type") == "has_pair"]

        # B: all hops (including no_pair) GT fact retrieved
        all_gt_retrieved = all(bool(h.get("gt_in_memories")) for h in hops)

        # Detection: all has_pair hop's chain_old detected
        if has_pair_hops and d_definition != "na":
            detected_hop_ids = detected_per_query.get(qid, set())
            q_has_pair_hop_ids = {h.get("hop_idx") for h in has_pair_hops}
            a_all_detected = q_has_pair_hop_ids.issubset(detected_hop_ids)
        else:
            a_all_detected = None  # not applicable

        # Leak: any has_pair hop's chain_old in retrieved
        if has_pair_hops:
            any_chain_old_leak = any(bool(h.get("old_in_memories")) for h in has_pair_hops)
        else:
            any_chain_old_leak = None

        # chain_new (has_pair only) — narrower B for conflict-focused view
        if has_pair_hops:
            all_chain_new_hp = all(bool(h.get("gt_in_memories")) for h in has_pair_hops)
        else:
            all_chain_new_hp = None

        em = bool(q.get("exact_match", False))
        rows_by_n_hops[n_hops].append({
            "qid": qid,
            "A": a_all_detected,
            "B": all_gt_retrieved,
            "B_has_pair": all_chain_new_hp,
            "leak": any_chain_old_leak,
            "em": em,
        })
    return rows_by_n_hops


def summarize(rows_by_n_hops, label):
    print(f"\n=== {label} ===")
    header = (f"{'n_hops':>7} {'n':>4} {'A%':>7} {'B%(all)':>9} "
              f"{'B%(HP)':>8} {'leak%':>7} {'EM%':>7}")
    print(header)
    print("-" * len(header))
    all_rows = []
    for n_hops in (2, 3, 4):
        sub = rows_by_n_hops.get(n_hops, [])
        if not sub:
            continue
        n = len(sub)
        a_sub = [x for x in sub if x["A"] is not None]
        a_pct = (100 * sum(1 for x in a_sub if x["A"]) / len(a_sub)) if a_sub else None
        b_pct = 100 * sum(1 for x in sub if x["B"]) / n
        bhp_sub = [x for x in sub if x["B_has_pair"] is not None]
        bhp_pct = (100 * sum(1 for x in bhp_sub if x["B_has_pair"]) / len(bhp_sub)) if bhp_sub else None
        leak_sub = [x for x in sub if x["leak"] is not None]
        leak_pct = (100 * sum(1 for x in leak_sub if x["leak"]) / len(leak_sub)) if leak_sub else None
        em_pct = 100 * sum(1 for x in sub if x["em"]) / n
        print(f"{n_hops:>7} {n:>4} "
              f"{a_pct:>6.1f}% " if a_pct is not None else f"{n_hops:>7} {n:>4} {'  n/a':>7} ", end="")
        print(f"{b_pct:>8.1f}% {bhp_pct:>7.1f}% {leak_pct:>6.1f}% {em_pct:>6.1f}%")
        all_rows.extend(sub)
    if all_rows:
        n = len(all_rows)
        a_sub = [x for x in all_rows if x["A"] is not None]
        a_pct = (100 * sum(1 for x in a_sub if x["A"]) / len(a_sub)) if a_sub else None
        b_pct = 100 * sum(1 for x in all_rows if x["B"]) / n
        bhp_sub = [x for x in all_rows if x["B_has_pair"] is not None]
        bhp_pct = (100 * sum(1 for x in bhp_sub if x["B_has_pair"]) / len(bhp_sub)) if bhp_sub else None
        leak_sub = [x for x in all_rows if x["leak"] is not None]
        leak_pct = (100 * sum(1 for x in leak_sub if x["leak"]) / len(leak_sub)) if leak_sub else None
        em_pct = 100 * sum(1 for x in all_rows if x["em"]) / n
        a_str = f"{a_pct:>6.1f}%" if a_pct is not None else "  n/a "
        print(f"{'all':>7} {n:>4} {a_str} {b_pct:>8.1f}% {bhp_pct:>7.1f}% "
              f"{leak_pct:>6.1f}% {em_pct:>6.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--align", required=True, type=Path)
    ap.add_argument("--detect", type=Path, default=None,
                    help="detection-action json (compute_detection_action.py output). "
                         "Omit for methods without detection (LCA / HippoRAG vanilla).")
    ap.add_argument("--d-def", choices=["vector", "graph", "union", "na"],
                    default="vector",
                    help="Detection-event scope. 'vector' = L2 events only; "
                         "'graph' = G4 entity-delete only (Mem0g); 'union' = either; "
                         "'na' = no detection available.")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    label = args.label or f"{args.align.stem}  (D={args.d_def})"
    rows = compute_a_b_per_method(args.align, args.detect, args.d_def)
    summarize(rows, label)


if __name__ == "__main__":
    main()
