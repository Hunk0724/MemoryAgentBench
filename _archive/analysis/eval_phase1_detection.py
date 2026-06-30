"""Evaluate Phase 1 detection recall vs GT chain_old (FC-MH 6k).

Inputs:
  - supersession_index.json (output of HippoRAG Phase 1)
  - mh_512_mquake_analysis.json (GT with per-hop chain_old/new annotations)

Outputs:
  - analysis/results/phase_v1/phase1_detection_eval_<run_label>.json
  - Console summary table (compatible with motivation §4.3 format)

Detection recall = (# GT chain_old facts that match a superseded fact_key) / (# total GT has_pair hops)
Detection precision = (# superseded fact_keys that match a GT chain_old) / (# total superseded)

GT comparison: motivation §4.3.A per-hop:
  Mem0 SH 62%, MH 59%
  Zep  SH 35%, MH 38%
"""
import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict


def normalize_text(s):
    """Lowercase, strip articles, collapse whitespace, strip punctuation."""
    if not s:
        return ""
    s = s.lower().strip()
    # strip leading articles
    s = re.sub(r"^(the|a|an)\s+", "", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # strip end punctuation
    s = s.rstrip(".,;:!?\"'")
    return s


def fact_in_text(s: str, r: str, o: str, text: str) -> bool:
    """Heuristic: does (s, r, o) triple's subject+object appear in the GT fact text?
    Article-stripping + substring either direction. Skip trivially short strings.
    """
    s_n, o_n, t_n = normalize_text(s), normalize_text(o), normalize_text(text)
    if len(s_n) < 3 or len(o_n) < 3:
        return False
    # both subject and object must appear in the GT text
    return s_n in t_n and o_n in t_n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--supersession", type=Path,
                   default=Path("/home/yhchiang/MemoryAgentBench/outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/supersession_index.json"))
    p.add_argument("--gt", type=Path,
                   default=Path("/home/yhchiang/MemoryAgentBench/analysis/results/mh_512_mquake_analysis.json"))
    p.add_argument("--run-label", type=str, default="phase1_v0",
                   help="Label for output filename")
    p.add_argument("--out-dir", type=Path,
                   default=Path("/home/yhchiang/MemoryAgentBench/analysis/results/phase_v1"))
    args = p.parse_args()

    print(f"[eval] loading supersession from {args.supersession}")
    if not args.supersession.exists():
        print(f"ERROR: supersession_index.json not found at {args.supersession}", file=sys.stderr)
        print("  → enable Phase 1 + rebuild KG first: HIPPORAG_ENABLE_SUPERSESSION=1 bash run_hipporag_gemini.sh", file=sys.stderr)
        sys.exit(1)
    sup = json.load(open(args.supersession))
    superseded_facts = sup.get("superseded_facts", {})
    print(f"[eval]   superseded fact_keys: {len(superseded_facts)}")

    print(f"[eval] loading GT from {args.gt}")
    gt = json.load(open(args.gt))
    print(f"[eval]   GT questions: {len(gt)}")

    # ─────────────────────────────────────────────────────────────────
    # Collect all GT has_pair hops (each is a chain_old fact to detect)
    # Auto-detect MH (nested 'hops') vs SH (flat) structure.
    # ─────────────────────────────────────────────────────────────────
    gt_has_pair_hops = []  # list of dict with old_fact_text + s/o hints
    gt_by_q = defaultdict(list)  # qid -> [old_fact_text, ...]
    sample = gt[0] if gt else {}
    has_mh_structure = "hops" in sample and isinstance(sample.get("hops"), list)
    print(f"[eval]   GT structure: {'MH (nested hops)' if has_mh_structure else 'SH (flat)'}")

    for q in gt:
        qid = q.get("query_id")
        if has_mh_structure:
            for hop_idx, hop in enumerate(q.get("hops", [])):
                if hop.get("conflict_type") != "has_pair":
                    continue
                old_fact_text = hop.get("old_fact_text", "")
                if not old_fact_text:
                    continue
                entry = {
                    "qid": qid,
                    "hop_idx": hop_idx,
                    "old_fact_text": old_fact_text,
                    "old_answer": hop.get("old_answer", ""),
                    "hop_question": hop.get("hop_question", ""),
                }
                gt_has_pair_hops.append(entry)
                gt_by_q[qid].append(old_fact_text)
        else:
            # SH: flat structure with old_fact_text at top level
            old_fact_text = q.get("old_fact_text") or ""
            if not old_fact_text:
                continue
            entry = {
                "qid": qid,
                "hop_idx": q.get("hop_idx", 0),
                "old_fact_text": old_fact_text,
                "old_answer": q.get("old_answer", ""),
                "hop_question": q.get("question", ""),
            }
            gt_has_pair_hops.append(entry)
            gt_by_q[qid].append(old_fact_text)

    n_gt_hops = len(gt_has_pair_hops)
    print(f"[eval]   GT has_pair hops (chain_old facts): {n_gt_hops}")

    # ─────────────────────────────────────────────────────────────────
    # Per-hop recall: how many GT chain_old hops match a Phase 1 superseded fact?
    # ─────────────────────────────────────────────────────────────────
    detected_hops = 0
    hop_matches = []
    for hop in gt_has_pair_hops:
        matched = None
        for fk, info in superseded_facts.items():
            s, r, o_old = info.get("s", ""), info.get("r", ""), info.get("o_old", "")
            if fact_in_text(s, r, o_old, hop["old_fact_text"]):
                matched = {"fact_key": fk, "s": s, "r": r, "o_old": o_old,
                           "matched_old_fact_text": hop["old_fact_text"]}
                break
        if matched:
            detected_hops += 1
        hop_matches.append({**hop, "matched": matched is not None, "match_info": matched})

    recall_per_hop = detected_hops / n_gt_hops if n_gt_hops > 0 else 0.0

    # ─────────────────────────────────────────────────────────────────
    # Precision: how many Phase 1 superseded match SOME GT chain_old text?
    # ─────────────────────────────────────────────────────────────────
    tp = 0
    fp = 0
    fp_examples = []
    for fk, info in superseded_facts.items():
        s, r, o_old = info.get("s", ""), info.get("r", ""), info.get("o_old", "")
        is_tp = False
        for hop in gt_has_pair_hops:
            if fact_in_text(s, r, o_old, hop["old_fact_text"]):
                is_tp = True
                break
        if is_tp:
            tp += 1
        else:
            fp += 1
            if len(fp_examples) < 8:
                fp_examples.append({"s": s, "r": r, "o_old": o_old,
                                    "o_new": info.get("o_new", "")})
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    # ─────────────────────────────────────────────────────────────────
    # Per-question all_detected / partial_detected / no_detected
    # ─────────────────────────────────────────────────────────────────
    per_q = defaultdict(lambda: {"total_hops": 0, "detected": 0})
    for hop in hop_matches:
        per_q[hop["qid"]]["total_hops"] += 1
        if hop["matched"]:
            per_q[hop["qid"]]["detected"] += 1
    all_det = sum(1 for q in per_q.values() if q["detected"] == q["total_hops"])
    partial = sum(1 for q in per_q.values() if 0 < q["detected"] < q["total_hops"])
    no_det = sum(1 for q in per_q.values() if q["detected"] == 0)
    n_questions_with_has_pair = len(per_q)

    # Questions without any has_pair hop are "no_pair" - we count them separately
    # (motivation §4.3 reporting convention)
    n_total_q = len(gt)
    n_no_pair = n_total_q - n_questions_with_has_pair

    # ─────────────────────────────────────────────────────────────────
    # Print summary
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"Phase 1 Detection Eval — {args.run_label}")
    print("=" * 70)
    print(f"\nPer-hop recall (motivation §4.3.A format):")
    print(f"  Our Phase 1 MH: {detected_hops}/{n_gt_hops} = {recall_per_hop*100:.1f}%")
    print(f"  Baselines from motivation §4.3.A:")
    print(f"    Mem0 MH:  111/188 = 59%")
    print(f"    Zep  MH:   71/188 = 38%")
    print(f"  Assertion A1.2: recall ≥ 41% (Mem0 41% per old motivation reference)")
    a1_2_pass = recall_per_hop >= 0.41
    print(f"  A1.2 STATUS: {'✓ PASS' if a1_2_pass else '✗ FAIL'}")

    print(f"\nPrecision:")
    print(f"  TP={tp}, FP={fp}, precision={precision*100:.1f}%")
    if fp_examples:
        print(f"  Sample FP (Phase 1 detected but not in GT chain_old):")
        for e in fp_examples[:5]:
            print(f"    ({e['s']}, {e['r']}, {e['o_old']}) → new: {e['o_new']}")

    print(f"\nPer-question bucket (motivation §4.3.B format):")
    print(f"  Total questions: {n_total_q}")
    print(f"  Questions with ≥1 has_pair: {n_questions_with_has_pair}")
    print(f"  Questions with NO has_pair (no_pair bucket): {n_no_pair}")
    print(f"  Among has_pair questions:")
    print(f"    all_detected:     {all_det}")
    print(f"    partial_detected: {partial}")
    print(f"    no_detected:      {no_det}")

    # ─────────────────────────────────────────────────────────────────
    # Write JSON output
    # ─────────────────────────────────────────────────────────────────
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"phase1_detection_eval_{args.run_label}.json"
    summary = {
        "run_label": args.run_label,
        "supersession_index_path": str(args.supersession),
        "gt_path": str(args.gt),
        "n_superseded_total": len(superseded_facts),
        "n_gt_has_pair_hops": n_gt_hops,
        "n_total_questions": n_total_q,
        "per_hop": {
            "detected": detected_hops,
            "total": n_gt_hops,
            "recall": recall_per_hop,
            "baseline_mem0_mh": 111 / 188,
            "baseline_zep_mh": 71 / 188,
            "a1_2_target": 0.41,
            "a1_2_pass": a1_2_pass,
        },
        "precision": {
            "tp": tp, "fp": fp, "precision": precision,
            "fp_examples": fp_examples,
        },
        "per_question_bucket": {
            "all_detected": all_det,
            "partial_detected": partial,
            "no_detected": no_det,
            "no_pair_bucket": n_no_pair,
        },
        "per_q_detail": {str(k): v for k, v in per_q.items()},
    }
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[eval] wrote {out_path}")
    return summary


if __name__ == "__main__":
    main()
