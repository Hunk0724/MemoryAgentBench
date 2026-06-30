"""
extract_our_method_AB.py
=========================
從 our method (v2.0.2 Phase 2 bidir-on) 的 monitoring log + labels.json 提取:

  A_all_detected  per query = 所有 has_pair hop 的 chain_old prop 都被 verdict
                              標 status="superseded" (correct identification)
  B_all_retrieved per query = 所有 hop (含 no_pair) 的 GT fact prop 都在
                              active_pids (retrieval pool)
  chain_old_leak  per query = 任一 has_pair hop 的 chain_old prop 仍在
                              passages_kept (filter 後仍漏到 LLM context)
  EM              per query = result file 的 exact_match

Inputs:
  --run-dir   monitoring_logs/<run>/
              expects: phase2_w13_dump.jsonl + results.json + verdict_events.jsonl
  --labels    analysis/results/full100_eval/labels.json
  --out       analysis/results/plan_a/our_v2p2_mh_6k_<run>.json

Output:
  JSON with per-query rows + aggregate per n_hops
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    # Load labels (GT per query)
    labels = json.load(open(args.labels, encoding="utf-8"))
    labels_by_qid: dict[int, dict] = {l["query_id"]: l for l in labels}

    # Load results.json for EM
    results = json.load(open(args.run_dir / "results.json", encoding="utf-8"))
    em_by_qid: dict[int, bool] = {}
    for d in results["data"]:
        qid = d.get("query_id")
        if qid is None:
            continue
        em_by_qid[qid] = bool(d.get("exact_match", False))

    # Walk phase2_w13_dump per query
    rows_by_n_hops: dict[int, list[dict]] = defaultdict(list)
    qid_seen = set()
    dump_path = args.run_dir / "phase2_w13_dump.jsonl"
    with open(dump_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            d = json.loads(line)
            # query string in dump doesn't include query_id; use index as fallback
            # But labels.json keys are query_id (0..99) in order
            # We'll match by question text to be safe
            qs = d.get("query", "")
            # Find matching label entry by question substring (queries in
            # phase2_w13_dump are wrapped with "Based on the provided
            # Knowledge Pool, X" - need to match X to label["question"])
            matched_qid = None
            for qid, lab in labels_by_qid.items():
                if qid in qid_seen:
                    continue
                if lab["question"] in qs:
                    matched_qid = qid
                    break
            if matched_qid is None:
                # fallback: use line index as qid (queries usually in order)
                matched_qid = i
                if matched_qid not in labels_by_qid:
                    continue
            qid_seen.add(matched_qid)
            lab = labels_by_qid[matched_qid]
            n_hops = lab["num_hops"]
            if n_hops not in (2, 3, 4):
                continue

            # GT prop IDs per hop
            chain_new_pid_per_hop = []  # for has_pair hops, the chain_new prop_id
            chain_old_pid_per_hop = []  # for has_pair hops, the chain_old prop_id
            all_gt_pid_per_hop = []     # for ALL hops (including no_pair), the GT prop_id
            for h in lab.get("hops", []):
                # GT new prop matches list (could be multiple matching prop_ids per hop)
                cn_matches = h.get("chain_new_matches") or []
                co_matches = h.get("chain_old_matches") or []
                # Use the first match as canonical (paper-wise: at least one needs to be there)
                cn_pids = [m["prop_id"] for m in cn_matches]
                co_pids = [m["prop_id"] for m in co_matches]
                all_gt_pid_per_hop.append(cn_pids)  # treat chain_new as GT for all
                if h.get("conflict_type") == "has_pair":
                    chain_new_pid_per_hop.append(cn_pids)
                    chain_old_pid_per_hop.append(co_pids)

            # Retrieved active props (chain enumeration pool)
            active_pids = set(d.get("active_pids") or [])
            # Verdicts (per prop_id)
            verdicts = d.get("verdicts") or {}
            chain_old_pids_in_dump = set(d.get("chain_old_pids") or [])
            # Passages kept (chunk_ids)
            kept_chunks = set(d.get("passages_kept_chunk_ids") or [])

            # ─── A: all has_pair hop's chain_old prop is verdict.status="superseded" ───
            # A hop is "detected" if at least one of its chain_old prop_ids has a
            # verdict marking it as "superseded".
            if chain_old_pid_per_hop:
                hop_detected = []
                for pid_list in chain_old_pid_per_hop:
                    detected = any(
                        verdicts.get(pid, {}).get("status") == "superseded"
                        for pid in pid_list
                    )
                    hop_detected.append(detected)
                a_all_detected = all(hop_detected) if hop_detected else None
            else:
                a_all_detected = None

            # ─── B: all hop's GT (chain_new for has_pair, the single fact for no_pair)
            #         prop is in active_pids ───
            hop_retrieved = []
            for pid_list in all_gt_pid_per_hop:
                if not pid_list:
                    hop_retrieved.append(False)  # no prop matches in labels
                    continue
                hop_retrieved.append(any(pid in active_pids for pid in pid_list))
            b_all_retrieved = all(hop_retrieved) if hop_retrieved else False

            # ─── chain_old leak: any has_pair hop's chain_old prop survives in
            #     kept passages (i.e., its source_chunk_id is in kept_chunks) ───
            #     We need to know each chain_old prop's source_chunk_id.
            any_old_leak = False
            for h in lab.get("hops", []):
                if h.get("conflict_type") != "has_pair":
                    continue
                for m in h.get("chain_old_matches") or []:
                    source_chunk = m.get("source_chunk_id")
                    if source_chunk and source_chunk in kept_chunks:
                        any_old_leak = True
                        break
                if any_old_leak:
                    break

            em = em_by_qid.get(matched_qid, False)
            rows_by_n_hops[n_hops].append({
                "qid": matched_qid,
                "A": a_all_detected,
                "B": b_all_retrieved,
                "leak": any_old_leak if any(
                    h.get("conflict_type") == "has_pair" for h in lab.get("hops") or []
                ) else None,
                "em": em,
            })

    # Summarize
    def fmt_pct(sub, key):
        vals = [x for x in sub if x[key] is not None]
        if not vals:
            return "n/a"
        return f"{100*sum(1 for x in vals if x[key])/len(vals):>5.1f}%"

    summary = {}
    all_rows = []
    for n_hops in (2, 3, 4):
        sub = rows_by_n_hops.get(n_hops, [])
        if not sub:
            continue
        all_rows.extend(sub)
        summary[n_hops] = {
            "n": len(sub),
            "A_pct": fmt_pct(sub, "A"),
            "B_pct": fmt_pct(sub, "B"),
            "leak_pct": fmt_pct(sub, "leak"),
            "EM_pct": fmt_pct(sub, "em"),
        }
    summary["all"] = {
        "n": len(all_rows),
        "A_pct": fmt_pct(all_rows, "A"),
        "B_pct": fmt_pct(all_rows, "B"),
        "leak_pct": fmt_pct(all_rows, "leak"),
        "EM_pct": fmt_pct(all_rows, "em"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"summary": summary, "rows": rows_by_n_hops},
              open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2,
              default=lambda o: list(o) if hasattr(o, '__iter__') else str(o))

    print(f"\n=== Our method v2.0.2 (run={args.run_dir.name}) ===")
    header = f"{'n_hops':>7} {'n':>4} {'A%':>7} {'B%':>7} {'leak%':>7} {'EM%':>7}"
    print(header)
    print("-" * len(header))
    for n_hops in (2, 3, 4, "all"):
        if n_hops not in summary:
            continue
        s = summary[n_hops]
        print(f"{str(n_hops):>7} {s['n']:>4} {s['A_pct']:>7} {s['B_pct']:>7} "
              f"{s['leak_pct']:>7} {s['EM_pct']:>7}")


if __name__ == "__main__":
    main()
