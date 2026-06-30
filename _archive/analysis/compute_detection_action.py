"""
compute_detection_action.py
============================
Operation-level precision/recall for mem0/mem0g's write-time conflict detection.

Complements existing M-detection (query-level retrieval outcome) and M-core
(hop-level state) by asking:

    "When mem0 *acts* (emits UPDATE/DELETE during ingestion), is that act
    actually triggered by a true GT conflict?"

This measures the detection FUNCTION's quality, independent of downstream
retrieval. It is the analysis the user requested in spec v1.4 §32.1:
    "所有觸發偵測的情況中 → 哪些確實是真衝突,且判斷新舊知識都正確"

Per ingestion event:
    event in {ADD, UPDATE, DELETE, NONE}
    UPDATE/DELETE = "method-side conflict signal" (= positive prediction)
    ADD/NONE      = "no conflict" (= negative prediction)

GT label per event:
    Resolved by entity-match between mem0 memory text and align.json hop's
    {gt_answer, old_answer}. If mem0 text mentions a GT old_answer for any
    query-hop → the event acts on a "GT old fact" (= positive ground truth).
    If mem0 text mentions a GT gt_answer → acts on "GT new fact" (operator
    should not be removing this).

Contingency:
    TP = method UPDATE/DELETE on a GT old fact (correct detection)
    FP_overdetect    = method UPDATE/DELETE on something that's NOT a GT old
                       fact (over-trigger; includes "deleting the new fact",
                       which is also FP_kill_new — broken out separately)
        FP_kill_new  = method UPDATE/DELETE on a GT new fact
                       (catastrophic — kills the right answer)
        FP_other     = method UPDATE/DELETE on a fact unrelated to any GT pair
    FN = no method UPDATE/DELETE event targeting an existing GT old fact
         (under-detect; old fact silently coexists with new → retrieval LEAK)
    TN = no UPDATE/DELETE on facts unrelated to GT pairs (uninteresting)

For UPDATE specifically:
    Additional check: when mem0 says "old_memory → new_text", does the
    new_text match the GT gt_answer? → UPDATE-content-correct rate.

Inputs:
    --ingest   outputs/rag_retrieved/<agent>/k_<K>/<sub>/chunksize_<C>/ingestion_context_*.jsonl
    --align    analysis/results/<run>_<task>_<ctx>_align.json
    --out      analysis/results/<run>_<task>_<ctx>_detection_action.json

Output:
    JSON with summary stats + per-event records.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def _norm(s: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _contains_entity(memory_text: str, entity: str) -> bool:
    """Substring match for entity in memory text (normalised)."""
    if not entity:
        return False
    mt = _norm(memory_text)
    et = _norm(entity)
    if not et:
        return False
    # Require entity bounded by word boundaries to avoid spurious sub-token hits
    pattern = r"\b" + re.escape(et) + r"\b"
    return bool(re.search(pattern, mt))


def _classify_event_vs_gt(event_memory_text: str, gt_pairs: list[dict]) -> dict:
    """
    For a given mem0 memory text, determine which GT side (if any) it matches.

    gt_pairs: list of {gt_answer, old_answer, gt_fact_text, old_fact_text,
                       query_id, hop_idx} from align.json (only has_pair hops).

    Returns:
        {
          'matched_old_pairs':  [(query_id, hop_idx), ...],
          'matched_new_pairs':  [(query_id, hop_idx), ...],
        }
    A single text may match multiple hops (rare). If matches both new and old
    of the SAME pair (unlikely — old_answer != gt_answer), recorded in both.
    """
    matched_old = []
    matched_new = []
    for p in gt_pairs:
        old_ans = p.get("old_answer")
        gt_ans = p.get("gt_answer")
        if old_ans and _contains_entity(event_memory_text, old_ans):
            matched_old.append((p["query_id"], p["hop_idx"]))
        if gt_ans and _contains_entity(event_memory_text, gt_ans):
            matched_new.append((p["query_id"], p["hop_idx"]))
    return {"matched_old_pairs": matched_old, "matched_new_pairs": matched_new}


def _extract_event_text(item: dict) -> str:
    """
    For a mem0 ADD/UPDATE/DELETE event item, return the memory text being
    operated on. For UPDATE the relevant 'old' text is item.previous_memory
    (the memory being replaced), and the 'new' text is item.memory (the
    replacement). For DELETE the text is item.memory.
    """
    return item.get("memory", "") or ""


def _extract_event_old_text(item: dict) -> str:
    """For UPDATE events, the previous memory text (= what mem0 thought was old)."""
    return item.get("previous_memory", "") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", required=True, type=Path,
                    help="ingestion_context_*.jsonl (one file, or pass --ingest-glob)")
    ap.add_argument("--align", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    align = json.load(open(args.align, encoding="utf-8"))

    # Build flat list of has_pair hops (the GT positive set)
    gt_pairs = []
    for q in align["entries"]:
        if q.get("query_id") is None:
            continue
        for h in q.get("hops") or []:
            if h.get("conflict_type") != "has_pair":
                continue
            gt_pairs.append({
                "query_id": q["query_id"],
                "qa_pair_id": q.get("qa_pair_id"),
                "hop_idx": h.get("hop_idx"),
                "gt_answer": h.get("gt_answer"),
                "old_answer": h.get("old_answer"),
                "gt_fact_text": h.get("gt_fact_text"),
                "old_fact_text": h.get("old_fact_text"),
            })

    if not gt_pairs:
        print("[warn] no has_pair hops in align — nothing to score")
        return

    print(f"[info] {len(gt_pairs)} GT has_pair hops")

    # Walk through every ingestion event
    event_records = []
    chunk_counter = 0
    with open(args.ingest, encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            try:
                d = json.loads(line)
            except Exception:
                continue
            vr = d.get("vector_results") or {}
            # Vector store events (relevant for both mem0 + mem0g)
            for item in (vr.get("results") or []):
                ev = (item.get("event") or "").upper()
                if ev not in ("ADD", "UPDATE", "DELETE", "NONE"):
                    continue
                new_text = _extract_event_text(item)
                old_text = _extract_event_old_text(item)  # only UPDATE has this
                cls_new = _classify_event_vs_gt(new_text, gt_pairs)
                cls_old = _classify_event_vs_gt(old_text, gt_pairs) if old_text else \
                          {"matched_old_pairs": [], "matched_new_pairs": []}
                event_records.append({
                    "chunk_idx": line_idx,
                    "event": ev,
                    "memory_text": new_text,
                    "previous_memory_text": old_text,
                    # for the "operated on" classification:
                    # - ADD/UPDATE: the new content arrives; UPDATE additionally replaces something
                    # - DELETE: deletes the memory_text
                    # We classify "what got acted upon" as:
                    #   DELETE: matched_against = cls_new (the deleted text)
                    #   UPDATE: matched_against = cls_old (the replaced text)
                    #   ADD   : matched_against = cls_new (the added text)
                    "matched_old_in_actedupon": (cls_old if ev == "UPDATE" else cls_new)["matched_old_pairs"],
                    "matched_new_in_actedupon": (cls_old if ev == "UPDATE" else cls_new)["matched_new_pairs"],
                    # for UPDATE: did the REPLACEMENT content match GT new?
                    "update_new_matches_gt": cls_new["matched_new_pairs"] if ev == "UPDATE" else [],
                })
            chunk_counter += 1

    print(f"[info] {chunk_counter} ingestion chunks, {len(event_records)} events")

    # ============== Compute confusion matrix ==============
    # Positive prediction = UPDATE or DELETE
    # GT positive          = event acts upon a fact that matches a GT old_fact
    # GT negative          = event acts upon something that is NOT a GT old_fact
    #                        (could match GT new, or unrelated)

    pred_pos_count = 0  # method emitted UPDATE/DELETE
    pred_neg_count = 0  # method emitted ADD/NONE

    tp = 0  # UPDATE/DELETE on a GT old fact
    fp_kill_new = 0  # UPDATE/DELETE on a GT new fact (catastrophic)
    fp_other = 0  # UPDATE/DELETE on something unrelated
    # FN computed at the GT side later
    update_correct_replacement = 0  # UPDATE where new content matches GT gt_answer
    update_with_old_match = 0  # denominator for above

    detected_pair_ids = set()  # (query_id, hop_idx) of GT pairs that got a TP event

    for er in event_records:
        ev = er["event"]
        is_pos_pred = ev in ("UPDATE", "DELETE")
        if is_pos_pred:
            pred_pos_count += 1
            matched_old = er["matched_old_in_actedupon"]
            matched_new = er["matched_new_in_actedupon"]
            if matched_old:
                tp += 1
                for pid in matched_old:
                    detected_pair_ids.add(pid)
            if matched_new and not matched_old:
                fp_kill_new += 1
            if not matched_old and not matched_new:
                fp_other += 1
            # For UPDATE, content-correctness check
            if ev == "UPDATE" and matched_old:
                update_with_old_match += 1
                if er["update_new_matches_gt"]:
                    update_correct_replacement += 1
        else:
            pred_neg_count += 1

    # FN at the GT-pair level
    fn_pair_ids = {(p["query_id"], p["hop_idx"]) for p in gt_pairs} - detected_pair_ids
    fn = len(fn_pair_ids)

    # ============== Aggregates ==============
    precision = tp / (tp + fp_kill_new + fp_other) if (tp + fp_kill_new + fp_other) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    update_correct_rate = (update_correct_replacement / update_with_old_match) \
                          if update_with_old_match else None

    summary = {
        "n_events_total": len(event_records),
        "n_pred_pos": pred_pos_count,
        "n_pred_neg": pred_neg_count,
        "n_gt_pairs": len(gt_pairs),
        "TP": tp,
        "FP_kill_new": fp_kill_new,
        "FP_other": fp_other,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "update_content_correct": update_correct_replacement,
        "update_with_old_match": update_with_old_match,
        "update_content_correct_rate": update_correct_rate,
        "by_event_type": dict(Counter(e["event"] for e in event_records)),
    }

    out_obj = {"summary": summary, "events": event_records,
               "fn_pair_ids": sorted(fn_pair_ids)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out_obj, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("=== Detection-as-action ===")
    print(f"  events total          : {summary['n_events_total']}  "
          f"({summary['by_event_type']})")
    print(f"  positive pred (UPD/DEL): {pred_pos_count}")
    print(f"  GT pairs              : {len(gt_pairs)}")
    print(f"  TP                    : {tp}")
    print(f"  FP_kill_new           : {fp_kill_new}  (UPDATE/DELETE on GT new — catastrophic)")
    print(f"  FP_other              : {fp_other}  (UPDATE/DELETE on unrelated)")
    print(f"  FN                    : {fn}  (GT pair with no detection event)")
    print(f"  precision             : {precision:.3f}")
    print(f"  recall                : {recall:.3f}")
    print(f"  F1                    : {f1:.3f}")
    if update_correct_rate is not None:
        print(f"  UPDATE-content-correct: {update_correct_replacement}/"
              f"{update_with_old_match} = {update_correct_rate:.3f}")
    print(f"[write] {args.out}")


if __name__ == "__main__":
    main()
