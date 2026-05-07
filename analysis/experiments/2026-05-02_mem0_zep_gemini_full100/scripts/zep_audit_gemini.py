"""
Zep × Gemini detection audit — re-pull edges from the new gemini_full100
Zep graphs and classify invalidations vs FC GT (matches existing
analysis/results/oracle_a/zep_*_invalidation_audit_v2.json shape).

For each Zep edge with invalid_at != None:
  - Find the OLD fact (whichever side was invalidated)
  - Find the counterpart NEW fact
  - Classify against GT: correct / wrong / false_positive

Run after the Zep × Gemini full run finished (graphs exist on Zep cloud).
"""

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/home/yhchiang/MemoryAgentBench/.env")
except ImportError:
    pass

from zep_cloud import Zep

BASE = Path("/home/yhchiang/MemoryAgentBench")
RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"

SESSION_PREFIX = "gemini_full100"


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


def collect_pairs(task):
    gt_path = SH_GT if task == "SH" else MH_GT
    gt = json.load(open(gt_path))
    pairs = []
    if task == "SH":
        for q in gt:
            if q.get("conflict_type") == "has_pair":
                pairs.append({
                    "qid": q["query_id"],
                    "old_seq": q.get("old_seq"), "old": q.get("old_fact_text", ""),
                    "new_seq": q.get("gt_seq"), "new": q.get("gt_fact_text", ""),
                })
    else:
        for q in gt:
            for h in q.get("hops", []):
                if h.get("conflict_type") == "has_pair":
                    pairs.append({
                        "qid": q["query_id"], "hop_idx": h.get("hop_idx"),
                        "old_seq": h.get("old_seq"), "old": h.get("old_fact_text", ""),
                        "new_seq": h.get("gt_seq"), "new": h.get("gt_fact_text", ""),
                    })
    return pairs


def fetch_edges_with_invalid(zep, graph_id, task):
    """Search edges using FC entity names as queries → cover more of graph."""
    # Generic boostraps
    base_queries = ["supersedes", "invalid", "moved", "is", "born", "associated",
                    "located", "spouse", "author", "country", "language", "headquarters",
                    "sport", "city", "founded", "currency"]
    # Entity-name queries from GT
    entity_queries = set()
    pairs = collect_pairs(task)
    for p in pairs:
        # First word(s) of GT fact often contain the subject entity
        for fact in (p["old"], p["new"]):
            if fact:
                # Take up to 3 words as the entity prefix
                words = fact.split()
                for k in (3, 2, 1):
                    if len(words) >= k:
                        entity_queries.add(" ".join(words[:k]))
    queries = base_queries + list(entity_queries)
    print(f"  using {len(queries)} queries to fetch edges")

    seen = {}
    for q in queries:
        try:
            resp = zep.graph.search(graph_id=graph_id, query=q[:399], scope="edges", limit=50)
            edges = resp.edges if resp and getattr(resp, "edges", None) else []
            for e in edges:
                uid = getattr(e, "uuid_", None) or id(e)
                if uid in seen:
                    continue
                seen[uid] = {
                    "fact": getattr(e, "fact", ""),
                    "name": getattr(e, "name", ""),
                    "valid_at": str(getattr(e, "valid_at", "")) if getattr(e, "valid_at", None) else None,
                    "invalid_at": str(getattr(e, "invalid_at", "")) if getattr(e, "invalid_at", None) else None,
                    "uuid": str(uid),
                }
        except Exception as ex:
            pass
    return list(seen.values())


def audit_task(task, zep, label):
    suffix = f"factconsolidation_{task.lower()}_6k"
    graph_id = f"graph_{SESSION_PREFIX}_{suffix}"
    print(f"\n=== {label} ({graph_id}) ===")

    edges = fetch_edges_with_invalid(zep, graph_id, task)
    print(f"  total edges sampled: {len(edges)}")

    invalidated = [e for e in edges if e["invalid_at"]]
    print(f"  edges with invalid_at != None: {len(invalidated)}")

    pairs = collect_pairs(task)

    correct_items, wrong_items, fp_items = [], [], []
    correct_pair_idx = set()

    for e in invalidated:
        fact = e["fact"]
        # Match: this fact is the OLD that should be invalidated → correct
        for pi, p in enumerate(pairs):
            if text_contains(fact, p["old"]):
                correct_items.append({
                    "edge_fact": fact, "edge_invalid_at": e["invalid_at"],
                    "matched_pair_qid": p["qid"],
                    "gt_old": p["old"], "gt_new": p["new"],
                })
                correct_pair_idx.add(pi)
                break
        else:
            # Wrong direction: this fact is the NEW (which should NOT be invalidated)
            wrong = False
            for pi, p in enumerate(pairs):
                if text_contains(fact, p["new"]):
                    wrong_items.append({
                        "edge_fact": fact, "edge_invalid_at": e["invalid_at"],
                        "matched_pair_qid": p["qid"],
                        "gt_old": p["old"], "gt_new": p["new"],
                        "note": "Zep invalidated NEW (counterfactual bias)",
                    })
                    wrong = True
                    break
            if not wrong:
                fp_items.append({"edge_fact": fact, "edge_invalid_at": e["invalid_at"]})

    n_total = len(invalidated)
    n_correct = len(correct_items)
    n_wrong = len(wrong_items)
    n_fp = len(fp_items)
    n_pairs = len(pairs)

    p_event = n_correct / n_total if n_total else 0
    r_pair = len(correct_pair_idx) / n_pairs if n_pairs else 0
    f1 = 2 * p_event * r_pair / (p_event + r_pair) if (p_event + r_pair) else 0

    audit = {
        "label": label,
        "total_invalidations_made_by_zep": n_total,
        "correct": n_correct,
        "wrong": n_wrong,
        "false_positive": n_fp,
        "unknown": 0,
        "has_pair_in_dataset": n_pairs,
        "uniquely_correct_pairs": len(correct_pair_idx),
        "precision_event_level": round(p_event, 4),
        "recall_pair_level": round(r_pair, 4),
        "f1": round(f1, 4),
        "correct_items": correct_items[:20],
        "wrong_items": wrong_items[:20],
        "false_positive_items": fp_items[:20],
    }
    print(f"  total_invalidations: {n_total}")
    print(f"  correct: {n_correct}  wrong: {n_wrong}  false_positive: {n_fp}")
    print(f"  uniquely_correct_pairs: {len(correct_pair_idx)} / {n_pairs}")
    print(f"  precision: {p_event*100:.1f}%  recall: {r_pair*100:.1f}%  F1: {f1*100:.1f}%")
    return audit


def main():
    api_key = os.environ.get("ZEP_API_KEY")
    if not api_key:
        raise RuntimeError("ZEP_API_KEY not set")
    zep = Zep(api_key=api_key)

    sh_audit = audit_task("SH", zep, "Zep × Gemini — FC-SH")
    mh_audit = audit_task("MH", zep, "Zep × Gemini — FC-MH (hop-level)")

    sh_path = RESULTS / "zep_gemini_sh_invalidation_audit.json"
    mh_path = RESULTS / "zep_gemini_mh_invalidation_audit.json"
    sh_path.write_text(json.dumps(sh_audit, indent=2, ensure_ascii=False))
    mh_path.write_text(json.dumps(mh_audit, indent=2, ensure_ascii=False))
    print(f"\nWritten: {sh_path}")
    print(f"Written: {mh_path}")


if __name__ == "__main__":
    main()
