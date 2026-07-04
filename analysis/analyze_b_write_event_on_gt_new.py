"""Attribute write-time LLM event fate of GT_new for (b) mem0+P1 FC-SH has_pair
at 6k / 32k / 64k.

Matching (v2): for each event.memory we compute normalized full-sentence
similarity against both GT_new and GT_old. An event is "relevant" only if it
matches one of them with ratio ≥ 0.85 (or by substring). This avoids the v1
false-positive where object-token alone hit unrelated facts (e.g. "Thomas Kyd"
in a birthplace fact wrongly attributed to "author of Figaro is Thomas Kyd").

Buckets:
  A. UPDATE_kept_new     — GT_new appears with event=UPDATE (LLM did correct
                           replace; if b still answered wrong, failure is
                           downstream: retrieval / answer LLM)
  B. ADD_both_coexist    — GT_new appears with event=ADD AND GT_old still in
                           store (LLM missed conflict → two versions coexist)
  B'. ADD_new_only       — GT_new with event=ADD but GT_old previously DELETE'd
  C1. DELETE_dropped_new — GT_new appears with event=DELETE (LLM destructively
                           dropped the NEW value itself at ingest)
  C2. DELETE_lost_new    — GT_new never appears; GT_old appears with event=DELETE
                           (destructive: old removed, new never entered store)
  D. NONE_silent_drop    — GT_new never appears, GT_old ADD only (no DELETE) or
                           neither found (silent drop / extraction miss)
  E. Ambiguous           — pattern doesn't fit above cleanly

Output: docs/handoff/mem0_dest_write_event_attribution.md
"""
from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # /Users/yhchiang/MemoryAgentBench

LENGTHS = [
    ("6k", "sh_512_mquake_analysis.json",
     "factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k100_chunk512_results.json"),
    ("32k", "sh_32k_mquake_analysis.json",
     "factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k100_chunk512_results.json"),
    ("64k", "sh_64k_mquake_analysis.json",
     "factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k100_chunk512_results.json"),
]

DEST_INGEST_ROOT = REPO / "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100"
DEST_RESULTS_ROOT = REPO / "outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution"
GT_ROOT = REPO / "analysis/results"
OUT_MD = REPO / "docs/handoff/mem0_dest_write_event_attribution.md"

BUCKETS_ORDER = [
    "A. UPDATE_kept_new",
    "B. ADD_both_coexist",
    "B'. ADD_new_only",
    "C1. DELETE_dropped_new",
    "C2. DELETE_lost_new",
    "D. NONE_silent_drop",
]

MATCH_RATIO = 0.85


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_fact(memory_norm: str, gt_norm: str) -> bool:
    """Full-sentence match: substring OR SequenceMatcher ratio >= MATCH_RATIO."""
    if not memory_norm or not gt_norm:
        return False
    if gt_norm in memory_norm:
        return True
    # Handle mem0 dropping the trailing period / shortening slightly
    if memory_norm in gt_norm and len(memory_norm) >= 0.7 * len(gt_norm):
        return True
    # Cheap length-gate before O(n^2) SequenceMatcher
    la, lb = len(memory_norm), len(gt_norm)
    if max(la, lb) == 0 or min(la, lb) / max(la, lb) < 0.5:
        return False
    return SequenceMatcher(None, memory_norm, gt_norm).ratio() >= MATCH_RATIO


def load_gt_table(path: Path) -> dict:
    d = json.load(open(path))
    return {e["query_id"]: {
        "gt_new_text": e.get("gt_fact_text") or "",
        "gt_old_text": e.get("old_fact_text") or "",
        "conflict_type": e.get("conflict_type"),
        "gt_answer": e.get("gt_answer"),
        "old_answer": e.get("old_answer"),
    } for e in d}


def load_b_results(path: Path) -> dict:
    d = json.load(open(path))
    return {e["query_id"]: bool(e.get("exact_match")) for e in d["data"]}


def load_ingest_events(path: Path) -> list:
    """Return list of (chunk_idx, event_dict) in ingest order."""
    all_events = []
    for i, line in enumerate(open(path)):
        obj = json.loads(line)
        results = obj.get("vector_results", {}).get("results", []) or []
        for ev in results:
            all_events.append((i, ev))
    return all_events


def find_relevant_events(events, gt_new: str, gt_old: str) -> list:
    """Return list of relevant events (dicts) touching this fact, in chunk order.
    An event is relevant iff its normalized memory matches GT_new or GT_old at
    the full-sentence level (substring or SequenceMatcher ratio >= 0.85)."""
    new_n = norm(gt_new)
    old_n = norm(gt_old)
    rel = []
    for chunk_idx, ev in events:
        m = norm(ev.get("memory") or "")
        if not m:
            continue
        has_new = match_fact(m, new_n)
        has_old = match_fact(m, old_n)
        if not (has_new or has_old):
            continue
        rel.append({
            "chunk": chunk_idx,
            "event": ev.get("event"),
            "memory": ev.get("memory") or "",
            "has_new": has_new,
            "has_old": has_old,
        })
    return rel


def classify(rel: list) -> str:
    if not rel:
        return "D. NONE_silent_drop"
    last_new = next((r for r in reversed(rel) if r["has_new"]), None)
    last_old = next((r for r in reversed(rel) if r["has_old"]), None)
    if last_new:
        ev = last_new["event"]
        if ev == "UPDATE":
            return "A. UPDATE_kept_new"
        if ev == "ADD":
            if last_old and last_old["event"] != "DELETE":
                return "B. ADD_both_coexist"
            return "B'. ADD_new_only"
        if ev == "DELETE":
            return "C1. DELETE_dropped_new"
        if ev == "NONE":
            return "D. NONE_silent_drop"
        return f"E. Ambiguous (new_event={ev})"
    if last_old:
        ev = last_old["event"]
        if ev == "DELETE":
            return "C2. DELETE_lost_new"
        if ev == "ADD":
            return "D. NONE_silent_drop"
        if ev == "UPDATE":
            return "E. Ambiguous (old_UPDATE, no new)"
        if ev == "NONE":
            return "D. NONE_silent_drop"
        return f"E. Ambiguous (old_event={ev})"
    return "D. NONE_silent_drop"


def make_bucket_order(observed: set) -> list:
    keep = [b for b in BUCKETS_ORDER if b in observed]
    extras = sorted(b for b in observed if b not in BUCKETS_ORDER)
    return keep + extras


def format_case(qid, info, rel, bucket):
    lines = []
    lines.append(f"- **{bucket}** qid={qid}")
    lines.append(f"  - GT_new: `{info['gt_new_text']}`")
    lines.append(f"  - GT_old: `{info['gt_old_text']}`")
    if not rel:
        lines.append("  - No relevant events matched this fact.")
        return lines
    for r in rel[-3:]:  # last 3 events touching this fact
        marker = ("N" if r["has_new"] else "") + ("O" if r["has_old"] else "")
        lines.append(f"  - chunk={r['chunk']} event={r['event']} [{marker}] memory=`{r['memory'][:90]}`")
    return lines


def run_one_length(tag, analysis_name, results_name):
    analysis_path = GT_ROOT / analysis_name
    results_path = DEST_RESULTS_ROOT / results_name
    ingest_path = DEST_INGEST_ROOT / f"factconsolidation_sh_{tag}/chunksize_512/ingestion_context_0.jsonl"

    gt = load_gt_table(analysis_path)
    em = load_b_results(results_path)
    events = load_ingest_events(ingest_path)

    hp_qids = [q for q, info in gt.items() if info["conflict_type"] == "has_pair"]
    wrong_set = {q for q in hp_qids if not em.get(q, True)}
    correct_set = {q for q in hp_qids if em.get(q, False)}

    wrong_buckets = Counter()
    correct_buckets = Counter()
    case_records = []
    for q in hp_qids:
        info = gt[q]
        rel = find_relevant_events(events, info["gt_new_text"], info["gt_old_text"])
        bucket = classify(rel)
        (wrong_buckets if q in wrong_set else correct_buckets)[bucket] += 1
        case_records.append({
            "qid": q,
            "em": em.get(q, False),
            "info": info,
            "rel": rel,
            "bucket": bucket,
        })

    return {
        "tag": tag,
        "n_has_pair": len(hp_qids),
        "n_wrong": len(wrong_set),
        "n_correct": len(correct_set),
        "wrong_buckets": wrong_buckets,
        "correct_buckets": correct_buckets,
        "cases": case_records,
        "n_ingest_events": len(events),
    }


def write_markdown(all_results):
    lines = []
    lines.append("# `b` (mem0+P1) has_pair wrong-qid write-event attribution")
    lines.append("")
    lines.append("- Method: `(b) mem0+P1` = MABench mem0 with our L2/unified extractor prompt (P1).")
    lines.append("- Backbone: gpt-4o-mini @ temp 0, chunk 512.")
    lines.append("- For each has_pair query we located the LATEST ingest-time event(s) whose")
    lines.append("  extracted-memory text matches this fact's shared stem AND at least one of the")
    lines.append("  new/old object tokens, then classified by event type + presence.")
    lines.append("")
    # Summary table
    lines.append("## Summary — bucket counts across lengths (wrong-qid only)")
    lines.append("")
    all_observed = set()
    for r in all_results:
        all_observed.update(r["wrong_buckets"].keys())
        all_observed.update(r["correct_buckets"].keys())
    order = make_bucket_order(all_observed)
    lines.append("| Bucket | 6k wrong | 32k wrong | 64k wrong |")
    lines.append("| :--- | ---: | ---: | ---: |")
    for b in order:
        row = [f"| {b} |"]
        for r in all_results:
            row.append(f" {r['wrong_buckets'].get(b, 0)} |")
        lines.append("".join(row))
    lines.append("")
    tot_row = ["| **Total wrong** |"]
    for r in all_results:
        tot_row.append(f" **{r['n_wrong']}** |")
    lines.append("".join(tot_row))
    lines.append("")
    lines.append("## Summary — bucket counts (correct-qid, control)")
    lines.append("")
    lines.append("| Bucket | 6k correct | 32k correct | 64k correct |")
    lines.append("| :--- | ---: | ---: | ---: |")
    for b in order:
        row = [f"| {b} |"]
        for r in all_results:
            row.append(f" {r['correct_buckets'].get(b, 0)} |")
        lines.append("".join(row))
    tot_row = ["| **Total correct** |"]
    for r in all_results:
        tot_row.append(f" **{r['n_correct']}** |")
    lines.append("".join(tot_row))
    lines.append("")
    # Per-length detail + samples
    for r in all_results:
        lines.append(f"## {r['tag']} — has_pair n={r['n_has_pair']}, wrong={r['n_wrong']}, correct={r['n_correct']}, ingest_events={r['n_ingest_events']}")
        lines.append("")
        lines.append("### Sample wrong-qid cases (up to 3 per bucket)")
        lines.append("")
        by_bucket = {}
        for c in r["cases"]:
            if not c["em"]:
                by_bucket.setdefault(c["bucket"], []).append(c)
        for b in make_bucket_order(set(by_bucket.keys())):
            for c in by_bucket[b][:3]:
                lines.extend(format_case(c["qid"], c["info"], c["rel"], c["bucket"]))
                lines.append("")
        lines.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))
    print(f"[write] {OUT_MD}")


def main():
    all_results = []
    for tag, analysis_name, results_name in LENGTHS:
        print(f"[run] {tag} ...")
        r = run_one_length(tag, analysis_name, results_name)
        print(f"   has_pair={r['n_has_pair']}  wrong={r['n_wrong']}  correct={r['n_correct']}  events={r['n_ingest_events']}")
        print(f"   wrong buckets: {dict(r['wrong_buckets'])}")
        print(f"   correct buckets: {dict(r['correct_buckets'])}")
        all_results.append(r)
    write_markdown(all_results)


if __name__ == "__main__":
    main()
