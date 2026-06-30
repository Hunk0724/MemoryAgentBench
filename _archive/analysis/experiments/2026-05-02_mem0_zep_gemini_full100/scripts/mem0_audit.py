"""
Mem0 detection audit (Zep-audit-format).

For each Mem0 UPDATE event in the run window, classify against FC GT pairs:
  - correct: event matches a GT pair in correct direction (old→new)
  - wrong: event matches a GT pair in REVERSE direction (new→old)
                (= counterfactual world-knowledge bias)
  - false_positive: event doesn't match any GT pair either direction
  - unknown: ambiguous (partial match)

Outputs the same JSON shape as analysis/results/oracle_a/zep_*_invalidation_audit_v2.json.
"""

import argparse
import json
import sqlite3
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
HISTORY_DB = Path("/home/yhchiang/.mem0/history.db")
RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"


def normalize(s):
    if s is None:
        return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def text_contains(haystack, needle):
    h = normalize(haystack); n = normalize(needle)
    if not h or not n:
        return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def load_update_events(since):
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT old_memory, new_memory, created_at FROM history "
        "WHERE event='UPDATE' AND created_at >= ? ORDER BY created_at",
        (since,)
    ).fetchall()
    return [{"old": r[0], "new": r[1], "at": r[2]} for r in rows]


def collect_pairs(task):
    if task == "SH":
        gt = json.load(open(SH_GT))
        pairs = []
        for q in gt:
            if q.get("conflict_type") == "has_pair":
                pairs.append({
                    "qid": q["query_id"],
                    "old_seq": q.get("old_seq"), "old": q.get("old_fact_text", ""),
                    "new_seq": q.get("gt_seq"), "new": q.get("gt_fact_text", ""),
                })
        return pairs
    else:
        gt = json.load(open(MH_GT))
        pairs = []
        for q in gt:
            for h in q.get("hops", []):
                if h.get("conflict_type") == "has_pair":
                    pairs.append({
                        "qid": q["query_id"],
                        "hop_idx": h.get("hop_idx"),
                        "old_seq": h.get("old_seq"), "old": h.get("old_fact_text", ""),
                        "new_seq": h.get("gt_seq"), "new": h.get("gt_fact_text", ""),
                    })
        return pairs


def classify(event, pairs):
    """Returns (status, matched_pair_idx). status in {correct, wrong, false_positive}"""
    for pi, p in enumerate(pairs):
        if text_contains(event["old"], p["old"]) and text_contains(event["new"], p["new"]):
            return "correct", pi
    for pi, p in enumerate(pairs):
        if text_contains(event["old"], p["new"]) and text_contains(event["new"], p["old"]):
            return "wrong", pi
    return "false_positive", None


def audit_task(task, events, label):
    pairs = collect_pairs(task)

    correct_items, wrong_items, fp_items = [], [], []
    correct_pairs_set, wrong_pairs_set = set(), set()

    for e in events:
        status, pi = classify(e, pairs)
        item = {"event_old": e["old"], "event_new": e["new"], "at": e["at"]}
        if status == "correct":
            item.update({
                "matched_pair_qid": pairs[pi]["qid"],
                "gt_old_seq": pairs[pi]["old_seq"], "gt_old": pairs[pi]["old"],
                "gt_new_seq": pairs[pi]["new_seq"], "gt_new": pairs[pi]["new"],
            })
            correct_items.append(item)
            correct_pairs_set.add(pi)
        elif status == "wrong":
            item.update({
                "matched_pair_qid": pairs[pi]["qid"],
                "gt_old_seq": pairs[pi]["old_seq"], "gt_old": pairs[pi]["old"],
                "gt_new_seq": pairs[pi]["new_seq"], "gt_new": pairs[pi]["new"],
                "note": "Mem0 UPDATE is REVERSE direction — invalidated NEW instead of OLD",
            })
            wrong_items.append(item)
            wrong_pairs_set.add(pi)
        else:
            fp_items.append(item)

    n_correct = len(correct_items)
    n_wrong = len(wrong_items)
    n_fp = len(fp_items)
    n_total = n_correct + n_wrong + n_fp
    n_pairs = len(pairs)

    # Audit-table style: per Zep audit
    audit = {
        "label": label,
        "total_invalidations_made_by_mem0": n_total,
        "correct": n_correct,
        "wrong": n_wrong,
        "false_positive": n_fp,
        "unknown": 0,
        "has_pair_in_dataset": n_pairs,
        "uniquely_correct_pairs": len(correct_pairs_set),
        "precision_event_level": round(n_correct / n_total, 4) if n_total else 0,
        "recall_pair_level": round(len(correct_pairs_set) / n_pairs, 4) if n_pairs else 0,
        "f1": 0,
        "correct_items": correct_items[:20],
        "wrong_items": wrong_items[:20],
        "false_positive_items": fp_items[:20],
    }
    if audit["precision_event_level"] + audit["recall_pair_level"] > 0:
        p, r = audit["precision_event_level"], audit["recall_pair_level"]
        audit["f1"] = round(2 * p * r / (p + r), 4)

    print(f"\n=== {label} ===")
    print(f"  total_invalidations: {n_total}")
    print(f"  correct: {n_correct}  wrong: {n_wrong}  false_positive: {n_fp}")
    print(f"  uniquely_correct_pairs: {len(correct_pairs_set)} / {n_pairs}")
    print(f"  precision (event-level): {audit['precision_event_level']*100:.1f}%")
    print(f"  recall (pair-level):     {audit['recall_pair_level']*100:.1f}%")
    print(f"  F1:                      {audit['f1']*100:.1f}%")
    return audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True)
    args = parser.parse_args()

    events = load_update_events(args.since)
    print(f"[load] {len(events)} UPDATE events since {args.since}")

    sh_audit = audit_task("SH", events, "Mem0 customized × Gemini — FC-SH")
    mh_audit = audit_task("MH", events, "Mem0 customized × Gemini — FC-MH (hop-level)")

    # Save per-task to mirror Zep audit file format
    sh_path = RESULTS / "mem0_sh_invalidation_audit.json"
    mh_path = RESULTS / "mem0_mh_invalidation_audit.json"
    sh_path.write_text(json.dumps(sh_audit, indent=2, ensure_ascii=False))
    mh_path.write_text(json.dumps(mh_audit, indent=2, ensure_ascii=False))
    print(f"\nWritten: {sh_path}")
    print(f"Written: {mh_path}")


if __name__ == "__main__":
    main()
