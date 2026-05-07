"""
Write-time evaluation — confusion matrix at GT-pair level.

For each FC supersession GT pair (old, new), classify what each system did:

Mem0 (6 classes from ~/.mem0/history.db events):
  W1 correct_UPDATE   — UPDATE event with old_memory ≈ old, new_memory ≈ new
  W2 wrong_direction  — UPDATE event with old/new flipped (counterfactual bias)
  W3 ADD_only         — both ADDed but no UPDATE bridges them (Mem0 sees no conflict)
  W4 missed           — neither old nor new appears in events (extraction failure)
  W5 mixed_other      — events present but unclear direction (e.g. partial UPDATE)
  W6 over_fire        — non-has_pair facts that got UPDATE/DELETE (system over-acted)

Zep (4 classes from full retrieved edges aggregated across queries):
  Z1 correct          — old edge has invalid_at, new edge present (no invalid_at)
  Z2 wrong_direction  — new edge has invalid_at, old edge present
  Z3 no_invalidation  — both edges present, neither invalid_at set
  Z4 extraction_miss  — old or new edge not present at all

Outputs:
  results/writetime_eval.json
  results/writetime_eval.md (human-readable tables)
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
HISTORY_DB = Path("/home/yhchiang/.mem0/history.db")
EXP_DIR = BASE / "analysis/experiments/2026-05-03_writetime_querytime_eval"
RESULTS = EXP_DIR / "results"
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"

SINCE = "2026-05-02T07:00:00"


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


def collect_gt_pairs(task):
    """has_pair pairs + non-conflict singletons."""
    gt_path = SH_GT if task == "SH" else MH_GT
    gt = json.load(open(gt_path))
    pairs = []
    singletons = []
    if task == "SH":
        for q in gt:
            old = q.get("old_fact_text", ""); new = q.get("gt_fact_text", "")
            if q.get("conflict_type") == "has_pair":
                pairs.append({
                    "qid": q["query_id"], "old_seq": q.get("old_seq"), "old": old,
                    "new_seq": q.get("gt_seq"), "new": new,
                })
            else:
                if new:
                    singletons.append({"qid": q["query_id"], "fact": new})
    else:
        for q in gt:
            for h in q.get("hops", []):
                old = h.get("old_fact_text", ""); new = h.get("gt_fact_text", "")
                if h.get("conflict_type") == "has_pair":
                    pairs.append({
                        "qid": q["query_id"], "hop_idx": h.get("hop_idx"),
                        "old_seq": h.get("old_seq"), "old": old,
                        "new_seq": h.get("gt_seq"), "new": new,
                    })
                else:
                    if new:
                        singletons.append({"qid": q["query_id"], "fact": new})
    return pairs, singletons


# ------------------------------- Mem0 -------------------------------

def load_mem0_events():
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT memory_id, old_memory, new_memory, event, created_at FROM history "
        "WHERE created_at >= ? ORDER BY created_at",
        (SINCE,)
    ).fetchall()
    return [{"mem_id": r[0], "old": r[1], "new": r[2], "event": r[3], "at": r[4]} for r in rows]


def classify_mem0_pair(events, gt_pair):
    """Classify Mem0's handling of one GT pair."""
    correct_updates = []
    wrong_updates = []
    add_old = []
    add_new = []

    for e in events:
        if e["event"] == "UPDATE":
            if text_contains(e["old"], gt_pair["old"]) and text_contains(e["new"], gt_pair["new"]):
                correct_updates.append(e)
            elif text_contains(e["old"], gt_pair["new"]) and text_contains(e["new"], gt_pair["old"]):
                wrong_updates.append(e)
        elif e["event"] == "ADD":
            if text_contains(e["new"], gt_pair["old"]):
                add_old.append(e)
            elif text_contains(e["new"], gt_pair["new"]):
                add_new.append(e)

    if correct_updates:
        return "W1_correct_UPDATE"
    if wrong_updates:
        return "W2_wrong_direction"
    if add_old and add_new:
        return "W3_ADD_only_both"  # both versions stored, no UPDATE bridge
    if add_new and not add_old:
        return "W3_ADD_new_only"   # only new ADDed
    if add_old and not add_new:
        return "W3_ADD_old_only"   # only old ADDed (new missed)
    return "W4_missed"


def classify_mem0_singleton(events, fact):
    """For non-has_pair fact, expect ADD only."""
    has_add = any(e["event"] == "ADD" and text_contains(e["new"], fact) for e in events)
    has_update = any(
        (e["event"] == "UPDATE") and (text_contains(e["old"], fact) or text_contains(e["new"], fact))
        for e in events
    )
    has_delete = any(e["event"] == "DELETE" and text_contains(e["old"], fact) for e in events)
    if has_update or has_delete:
        return "S6_over_fire"
    if has_add:
        return "S5_correct_ADD"
    return "S7_extraction_miss"


def mem0_writetime_eval(task, events):
    pairs, singletons = collect_gt_pairs(task)
    pair_classes = defaultdict(list)
    for p in pairs:
        c = classify_mem0_pair(events, p)
        pair_classes[c].append(p)

    sing_classes = defaultdict(list)
    for s in singletons:
        c = classify_mem0_singleton(events, s["fact"])
        sing_classes[c].append(s)

    # Over-fire = UPDATE events not corresponding to any GT pair (in either direction)
    n_overfire = 0
    update_events = [e for e in events if e["event"] == "UPDATE"]
    for e in update_events:
        match = False
        for p in pairs:
            if (text_contains(e["old"], p["old"]) and text_contains(e["new"], p["new"])) or \
               (text_contains(e["old"], p["new"]) and text_contains(e["new"], p["old"])):
                match = True; break
        if not match:
            n_overfire += 1

    return {
        "task": task,
        "total_pairs": len(pairs),
        "total_singletons": len(singletons),
        "pair_class_counts": {k: len(v) for k, v in pair_classes.items()},
        "singleton_class_counts": {k: len(v) for k, v in sing_classes.items()},
        "n_update_events_total": len(update_events),
        "n_update_events_overfire_no_GT_match": n_overfire,
    }


# ------------------------------- Zep -------------------------------

def aggregate_zep_edges_from_retrieval(task):
    """Use the rerun's per-question full retrieval to aggregate unique edges."""
    p = RESULTS / f"zep_full_retrieval_{task.lower()}.json"
    if not p.exists():
        print(f"[zep_writetime warn] {p} not found — run rerun_full_retrieval.py first")
        return {}
    data = json.load(open(p))
    seen = {}
    for q in data:
        for e in q.get("edges", []):
            uid = e.get("uuid")
            if uid and uid not in seen:
                seen[uid] = e
    return seen


def classify_zep_pair(edges_by_uuid, gt_pair):
    """Classify Zep's handling of one GT pair."""
    # Find edges matching old_fact and new_fact
    old_edges = [e for e in edges_by_uuid.values() if text_contains(e.get("fact", ""), gt_pair["old"])]
    new_edges = [e for e in edges_by_uuid.values() if text_contains(e.get("fact", ""), gt_pair["new"])]

    old_invalid = any(e.get("invalid_at") for e in old_edges)
    new_invalid = any(e.get("invalid_at") for e in new_edges)

    if not old_edges and not new_edges:
        return "Z4_extraction_miss"
    if old_invalid and not new_invalid:
        return "Z1_correct"
    if new_invalid and not old_invalid:
        return "Z2_wrong_direction"
    if old_edges and new_edges and not old_invalid and not new_invalid:
        return "Z3_no_invalidation"
    if old_edges and not new_edges:
        return "Z4_new_extraction_miss"
    if new_edges and not old_edges:
        return "Z4_old_extraction_miss"
    return "Z5_both_invalid_ambig"


def zep_writetime_eval(task):
    pairs, singletons = collect_gt_pairs(task)
    edges = aggregate_zep_edges_from_retrieval(task)
    if not edges:
        return None

    pair_classes = defaultdict(list)
    for p in pairs:
        c = classify_zep_pair(edges, p)
        pair_classes[c].append(p)

    return {
        "task": task,
        "total_pairs": len(pairs),
        "total_zep_edges_aggregated": len(edges),
        "n_edges_with_invalid_at": sum(1 for e in edges.values() if e.get("invalid_at")),
        "pair_class_counts": {k: len(v) for k, v in pair_classes.items()},
    }


# ------------------------------- Main -------------------------------

def render_md(out):
    md = ["# Write-time Evaluation\n"]
    md.append("> Confusion matrix at GT-pair level: how each system handled each FC supersession.\n")
    md.append("---\n")

    # Mem0 table
    md.append("## Mem0 customized × Gemini (chunk=512)\n")
    md.append("| Class | SH | MH (hops) |")
    md.append("|---|:---:|:---:|")
    classes = sorted(set(out["mem0_sh"]["pair_class_counts"]) | set(out["mem0_mh"]["pair_class_counts"]))
    for c in classes:
        sh = out["mem0_sh"]["pair_class_counts"].get(c, 0)
        mh = out["mem0_mh"]["pair_class_counts"].get(c, 0)
        md.append(f"| {c} | {sh} | {mh} |")
    md.append(f"| **total has_pair** | **{out['mem0_sh']['total_pairs']}** | **{out['mem0_mh']['total_pairs']}** |")
    md.append("")
    md.append(f"Singleton (non-conflict) facts:")
    md.append("| Class | SH | MH |")
    md.append("|---|:---:|:---:|")
    sclasses = sorted(set(out["mem0_sh"]["singleton_class_counts"]) | set(out["mem0_mh"]["singleton_class_counts"]))
    for c in sclasses:
        md.append(f"| {c} | {out['mem0_sh']['singleton_class_counts'].get(c, 0)} | {out['mem0_mh']['singleton_class_counts'].get(c, 0)} |")
    md.append(f"| **total singletons** | **{out['mem0_sh']['total_singletons']}** | **{out['mem0_mh']['total_singletons']}** |")
    md.append("")
    md.append(f"Over-fire (UPDATE events not matching any GT pair):  SH {out['mem0_sh']['n_update_events_overfire_no_GT_match']} / {out['mem0_sh']['n_update_events_total']} total UPDATEs.  MH {out['mem0_mh']['n_update_events_overfire_no_GT_match']} / {out['mem0_mh']['n_update_events_total']} total UPDATEs.\n")

    # Zep table
    md.append("---\n## Zep × Gemini-inference (chunk=512, edges aggregated from per-question retrievals)\n")
    if out.get("zep_sh") and out.get("zep_mh"):
        md.append("| Class | SH | MH (hops) |")
        md.append("|---|:---:|:---:|")
        classes = sorted(set(out["zep_sh"]["pair_class_counts"]) | set(out["zep_mh"]["pair_class_counts"]))
        for c in classes:
            sh = out["zep_sh"]["pair_class_counts"].get(c, 0)
            mh = out["zep_mh"]["pair_class_counts"].get(c, 0)
            md.append(f"| {c} | {sh} | {mh} |")
        md.append(f"| **total has_pair** | **{out['zep_sh']['total_pairs']}** | **{out['zep_mh']['total_pairs']}** |")
        md.append("")
        md.append(f"Aggregated unique edges: SH {out['zep_sh']['total_zep_edges_aggregated']} ({out['zep_sh']['n_edges_with_invalid_at']} with invalid_at);  MH {out['zep_mh']['total_zep_edges_aggregated']} ({out['zep_mh']['n_edges_with_invalid_at']} with invalid_at)\n")
    else:
        md.append("(zep retrieval data not yet available — run rerun_full_retrieval.py first)\n")

    return "\n".join(md)


def main():
    events = load_mem0_events()
    print(f"[load] {len(events)} Mem0 events since {SINCE}")

    out = {
        "mem0_sh": mem0_writetime_eval("SH", events),
        "mem0_mh": mem0_writetime_eval("MH", events),
        "zep_sh": zep_writetime_eval("SH"),
        "zep_mh": zep_writetime_eval("MH"),
    }
    out_path = RESULTS / "writetime_eval.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    md = render_md(out)
    md_path = RESULTS / "writetime_eval.md"
    md_path.write_text(md)
    print(md)
    print(f"\nWritten: {out_path}")
    print(f"Written: {md_path}")


if __name__ == "__main__":
    main()
