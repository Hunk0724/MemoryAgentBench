"""
Compute Mem0 detection precision/recall/F1 vs FC ground truth supersession pairs.

Method:
  1. Read ~/.mem0/history.db UPDATE events filtered by run start time
  2. For each UPDATE event, normalize (old_memory, new_memory) text
  3. Match against FC GT supersession pairs:
       - SH: 74 has_pair questions, each with (old_fact_text, gt_fact_text)
       - MH: hop-level, 188 has_pair hops
  4. Compute TP / FP / FN / P / R / F1

Match logic:
  Fuzzy substring match — old_memory contains old_fact's key phrase AND
  new_memory contains new_fact's key phrase (and direction is correct).

Run:
  python mem0_detection_f1.py --since 2026-05-02T07:00:00
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
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
    """Loose substring match after normalization, ignoring articles/punctuation."""
    h = normalize(haystack)
    n = normalize(needle)
    if not h or not n:
        return False
    # Strip leading articles
    for art in ("the ", "a ", "an "):
        if n.startswith(art):
            n = n[len(art):]
        if h.startswith(art):
            h = h[len(art):]
    return n in h or h in n


def load_update_events(since):
    """Returns list of (old_memory, new_memory, created_at)."""
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT old_memory, new_memory, created_at FROM history "
        "WHERE event='UPDATE' AND created_at >= ?",
        (since,)
    ).fetchall()
    return rows


def collect_supersession_pairs():
    """Build the GT set of (old_fact_text, new_fact_text) pairs."""
    sh = json.load(open(SH_GT))
    mh = json.load(open(MH_GT))

    sh_pairs = []
    for q in sh:
        if q.get("conflict_type") == "has_pair":
            old_text = q.get("old_fact_text") or q.get("old_fact") or ""
            new_text = q.get("gt_fact_text") or ""
            if old_text and new_text:
                sh_pairs.append({
                    "task": "SH",
                    "qid": q["query_id"],
                    "old": old_text,
                    "new": new_text,
                    "old_seq": q.get("old_seq"),
                    "gt_seq": q.get("gt_seq"),
                })

    mh_pairs = []
    for q in mh:
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair":
                old_text = h.get("old_fact_text") or h.get("old_fact") or ""
                new_text = h.get("gt_fact_text") or ""
                if old_text and new_text:
                    mh_pairs.append({
                        "task": "MH",
                        "qid": q["query_id"],
                        "hop": h.get("hop_idx"),
                        "old": old_text,
                        "new": new_text,
                        "old_seq": h.get("old_seq"),
                        "gt_seq": h.get("gt_seq"),
                    })
    return sh_pairs, mh_pairs


def match_event_to_pair(old_mem, new_mem, pair):
    """Check if a Mem0 UPDATE event matches a GT supersession pair (correct direction)."""
    return text_contains(old_mem, pair["old"]) and text_contains(new_mem, pair["new"])


def match_event_reverse(old_mem, new_mem, pair):
    """Wrong-direction match: Mem0 mistakenly invalidates the NEW (counterfactual bias)."""
    return text_contains(old_mem, pair["new"]) and text_contains(new_mem, pair["old"])


def compute_metrics(events, pairs, label):
    """For a set of UPDATE events vs GT pairs, compute P/R/F1.

    A pair is detected (TP) if there exists at least one event matching it
    in the correct direction. Wrong-direction events are FP. Events that
    don't match any pair (in either direction) are also FP.
    """
    tp_pairs = set()
    wrong_direction_pairs = set()
    matched_event_indices = set()

    for ei, (old_mem, new_mem, _) in enumerate(events):
        for pi, pair in enumerate(pairs):
            if match_event_to_pair(old_mem, new_mem, pair):
                tp_pairs.add(pi)
                matched_event_indices.add(ei)
            elif match_event_reverse(old_mem, new_mem, pair):
                wrong_direction_pairs.add(pi)
                matched_event_indices.add(ei)

    tp = len(tp_pairs)
    wrong = len(wrong_direction_pairs - tp_pairs)  # only count wrong if not also TP
    fp_unmatched = len(events) - len(matched_event_indices)
    fp = wrong + fp_unmatched
    fn = len(pairs) - tp  # GT pairs not detected correctly

    p = tp / (tp + fp) if (tp + fp) else 0
    r = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * p * r / (p + r) if (p + r) else 0

    print(f"\n=== {label} ===")
    print(f"  Total UPDATE events: {len(events)}")
    print(f"  Total GT supersession pairs: {len(pairs)}")
    print(f"  TP (correct direction match): {tp}")
    print(f"  FP wrong-direction (counterfactual bias): {wrong}")
    print(f"  FP unmatched (event matches no GT pair): {fp_unmatched}")
    print(f"  FN (GT pair not detected): {fn}")
    print(f"  Precision: {p:.4f}")
    print(f"  Recall: {r:.4f}")
    print(f"  F1: {f1:.4f}")

    return {
        "label": label,
        "total_update_events": len(events),
        "total_gt_pairs": len(pairs),
        "TP": tp,
        "FP_wrong_direction": wrong,
        "FP_unmatched": fp_unmatched,
        "FN": fn,
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True,
                        help="ISO timestamp lower bound (e.g., '2026-05-02T07:00:00') for filtering history.db UPDATE events")
    args = parser.parse_args()

    events = load_update_events(args.since)
    print(f"[load] {len(events)} UPDATE events since {args.since}")

    sh_pairs, mh_pairs = collect_supersession_pairs()
    print(f"[GT] SH has_pair pairs: {len(sh_pairs)}")
    print(f"[GT] MH has_pair pairs (hop-level): {len(mh_pairs)}")

    sh_metrics = compute_metrics(events, sh_pairs, "Mem0 customized × Gemini — FC-SH")
    mh_metrics = compute_metrics(events, mh_pairs, "Mem0 customized × Gemini — FC-MH (hop-level)")

    out = {
        "since": args.since,
        "total_update_events_in_window": len(events),
        "fc_sh": sh_metrics,
        "fc_mh": mh_metrics,
        "notes": [
            "Mem0 history.db is shared across runs; use --since to filter window.",
            "Match logic: old_memory contains GT old_fact text AND new_memory contains GT new_fact text (after normalization, articles stripped).",
            "Wrong-direction events (counterfactual world-knowledge bias) counted as FP.",
            "Unmatched events (Mem0 fired UPDATE on something not in FC GT) also FP.",
        ],
    }
    out_path = RESULTS / "mem0_detection_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWritten to: {out_path}")


if __name__ == "__main__":
    main()
