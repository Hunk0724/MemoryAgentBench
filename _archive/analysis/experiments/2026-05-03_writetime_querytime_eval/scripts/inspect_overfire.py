"""
Sample over-fire UPDATE events from Mem0 history.db.

"Over-fire" = Mem0 fired UPDATE during ingestion but the (old_memory, new_memory)
pair does NOT match any FC GT supersession pair (in either direction).

This helps disambiguate: are over-fire events
  (a) spurious (Mem0 wrongly merged unrelated facts), OR
  (b) legitimate supersessions that just happen to be outside our 100-question GT?

Outputs:
  results/overfire_samples.md — 20 sampled over-fire events with classification hints
"""

import json
import random
import sqlite3
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
HISTORY_DB = Path("/home/yhchiang/.mem0/history.db")
RESULTS = BASE / "analysis/experiments/2026-05-03_writetime_querytime_eval/results"
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"

SINCE = "2026-05-02T09:00:00"  # PT timezone-suffix; matches today's re-ingestion in CST


def normalize(s):
    if s is None: return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def text_contains(haystack, needle):
    h = normalize(haystack); n = normalize(needle)
    if not h or not n: return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def collect_all_gt_pairs():
    """Build the full GT pair set (SH + MH hops, both 'old' and 'new' direction)."""
    pairs = []
    sh = json.load(open(SH_GT))
    for q in sh:
        if q.get("conflict_type") == "has_pair":
            pairs.append({
                "src": "SH", "qid": q["query_id"],
                "old": q.get("old_fact_text", ""), "new": q.get("gt_fact_text", ""),
            })
    mh = json.load(open(MH_GT))
    for q in mh:
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair":
                pairs.append({
                    "src": f"MH q{q['query_id']} hop{h.get('hop_idx')}",
                    "old": h.get("old_fact_text", ""), "new": h.get("gt_fact_text", ""),
                })
    return pairs


def load_update_events(since):
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT old_memory, new_memory, created_at FROM history WHERE event='UPDATE' AND created_at >= ?",
        (since,)
    ).fetchall()
    return [{"old": r[0], "new": r[1], "at": r[2]} for r in rows]


def classify_event(event, pairs):
    """Return (status, matched_pair) — same as audit script."""
    for p in pairs:
        if text_contains(event["old"], p["old"]) and text_contains(event["new"], p["new"]):
            return "match_correct", p
    for p in pairs:
        if text_contains(event["old"], p["new"]) and text_contains(event["new"], p["old"]):
            return "match_reverse", p
    return "no_match", None


def find_partial_overlap(event, pairs):
    """For over-fire events, see if event's old/new shares an entity with any GT pair."""
    matches = []
    for p in pairs:
        # Check if any of event's facts share substring (>= 5 chars meaningful) with GT pair's facts
        ev_words = set(normalize(event["old"]).split()) | set(normalize(event["new"]).split())
        ev_words = {w for w in ev_words if len(w) >= 5}  # filter short words
        gt_words = set(normalize(p["old"]).split()) | set(normalize(p["new"]).split())
        gt_words = {w for w in gt_words if len(w) >= 5}
        common = ev_words & gt_words
        if len(common) >= 2:
            matches.append({"p": p, "common_words": list(common)})
            if len(matches) >= 3:
                break
    return matches


def main():
    pairs = collect_all_gt_pairs()
    print(f"[GT] {len(pairs)} total has_pair pairs (SH + MH hops)")

    events = load_update_events(SINCE)
    print(f"[events] {len(events)} UPDATE events since {SINCE}")

    overfire = []
    correct = []
    reverse = []
    for e in events:
        status, p = classify_event(e, pairs)
        if status == "match_correct":
            correct.append(e)
        elif status == "match_reverse":
            reverse.append(e)
        else:
            overfire.append(e)

    print(f"\n=== Classification ===")
    print(f"  Correct UPDATE (match GT correct direction):  {len(correct)}")
    print(f"  Reverse UPDATE (counterfactual bias):          {len(reverse)}")
    print(f"  Over-fire (no GT match either direction):      {len(overfire)}")

    md = ["# Over-fire Sample Inspection\n"]
    md.append(f"> {len(overfire)} of {len(events)} UPDATE events ({len(overfire)/len(events)*100:.1f}%) don't match any GT pair.")
    md.append(f"> Sampling 20 random ones to see if they're (a) spurious or (b) legit supersessions outside our GT.\n")
    md.append("---\n")

    random.seed(42)
    samples = random.sample(overfire, min(20, len(overfire)))
    for i, e in enumerate(samples):
        md.append(f"### Over-fire #{i+1}\n")
        md.append(f"- **old_memory**: `{e['old']}`")
        md.append(f"- **new_memory**: `{e['new']}`")
        md.append(f"- created_at: {e['at']}")
        # Find partial overlap with any GT pair
        overlaps = find_partial_overlap(e, pairs)
        if overlaps:
            md.append(f"- partial entity overlap with GT pairs:")
            for o in overlaps:
                md.append(f"  - GT pair from {o['p']['src']}: `{o['p']['old'][:60]}` → `{o['p']['new'][:60]}`")
                md.append(f"    common words: {o['common_words']}")
        else:
            md.append(f"- ❌ no GT pair shares any entity word with this event")
        md.append("")

    md.append("---\n")
    md.append("## How to interpret\n")
    md.append("- **No GT overlap** + plausible facts: 大概是「FC 6k context 中有但不在 100 題覆蓋的真實 supersession」 → 不算 spurious")
    md.append("- **No GT overlap** + nonsense pairing: 真 spurious — Mem0 LLM Update Memory 步驟錯把無關的 fact 當衝突")
    md.append("- **Has overlap + reverse direction confusion**: 同一 entity 兩 GT pair（e.g., MH chain 中 hop0+hop1）被 Mem0 串到一起當 supersession，FC chain 結構觸發的特殊 case")

    out_path = RESULTS / "overfire_samples.md"
    out_path.write_text("\n".join(md))
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
