"""
Query-time retrieval evaluation — for each FC question, check whether the
top-K retrieved content covers the chain's GT new/old facts.

Mem0: top-100 retrieved memories (`memory.search` results).
Zep: top-10 edges (per question; nodes/episodes also recorded but edges most
informative for has_pair coverage).

Metrics per question:
  - new_recall@K    : fraction of chain has_pair hops whose new fact is in retrieved top-K
  - old_recall@K    : fraction of chain has_pair hops whose old fact is in retrieved top-K
                      (high = system is sending distractor/outdated to LLM; for Mem0 this means
                       UPDATE/DELETE failed to clean it up)
  - both_in_topK    : fraction of chain hops where both old AND new co-exist in top-K
                      (interesting for Zep where LLM sees both with timestamps)

Aggregate:
  Avg per-question new_recall ; old_recall ; both_in_topK across all has_pair questions.

Outputs:
  results/querytime_eval.json
  results/querytime_eval.md
"""

import json
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
EXP_DIR = BASE / "analysis/experiments/2026-05-03_writetime_querytime_eval"
RESULTS = EXP_DIR / "results"
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"


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


def get_chain_pairs(q, task):
    """Return list of {old, new} for each has_pair hop in this question."""
    pairs = []
    if task == "SH":
        if q.get("conflict_type") == "has_pair":
            pairs.append({"old": q.get("old_fact_text", ""), "new": q.get("gt_fact_text", "")})
    else:
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair":
                pairs.append({"old": h.get("old_fact_text", ""), "new": h.get("gt_fact_text", "")})
    return pairs


# -------------------- Mem0 --------------------

def eval_mem0(task):
    full_path = RESULTS / f"mem0_full_retrieval_{task.lower()}.json"
    if not full_path.exists():
        return None
    retrieval = json.load(open(full_path))
    gt = json.load(open(SH_GT if task == "SH" else MH_GT))
    gt_by_qid = {q["query_id"]: q for q in gt}

    per_q = []
    for r in retrieval:
        qid = r["query_id"]
        gt_q = gt_by_qid.get(qid)
        if not gt_q: continue
        chain = get_chain_pairs(gt_q, task)
        if not chain:
            continue  # only evaluate has_pair questions
        memories = [m.get("memory", "") for m in r.get("retrieved_full", [])]

        new_hits = sum(1 for p in chain if any(text_contains(m, p["new"]) for m in memories))
        old_hits = sum(1 for p in chain if any(text_contains(m, p["old"]) for m in memories))
        both = sum(1 for p in chain
                   if any(text_contains(m, p["new"]) for m in memories)
                   and any(text_contains(m, p["old"]) for m in memories))

        per_q.append({
            "qid": qid, "n_chain_pairs": len(chain),
            "new_in_topK": new_hits, "old_in_topK": old_hits, "both_in_topK": both,
            "new_recall": new_hits / len(chain), "old_recall": old_hits / len(chain),
            "both_rate": both / len(chain),
        })

    if not per_q:
        return None

    n_total = len(per_q)
    return {
        "system": "Mem0 customized × Gemini",
        "task": task,
        "n_has_pair_questions": n_total,
        "K": 100,
        "avg_new_recall": round(sum(q["new_recall"] for q in per_q) / n_total, 4),
        "avg_old_recall": round(sum(q["old_recall"] for q in per_q) / n_total, 4),
        "avg_both_rate": round(sum(q["both_rate"] for q in per_q) / n_total, 4),
        "per_q": per_q,
    }


# -------------------- Zep --------------------

def eval_zep(task):
    full_path = RESULTS / f"zep_full_retrieval_{task.lower()}.json"
    if not full_path.exists():
        return None
    retrieval = json.load(open(full_path))
    gt = json.load(open(SH_GT if task == "SH" else MH_GT))
    gt_by_qid = {q["query_id"]: q for q in gt}

    per_q = []
    for r in retrieval:
        qid = r["query_id"]
        gt_q = gt_by_qid.get(qid)
        if not gt_q: continue
        chain = get_chain_pairs(gt_q, task)
        if not chain:
            continue

        edges = r.get("edges", [])
        edge_facts = [e.get("fact", "") for e in edges]
        # Also include episode content as Zep gives it to LLM
        episodes = r.get("episodes", [])
        episode_contents = [ep.get("content", "") for ep in episodes]
        all_strs = edge_facts + episode_contents

        new_hits = sum(1 for p in chain if any(text_contains(s, p["new"]) for s in all_strs))
        old_hits = sum(1 for p in chain if any(text_contains(s, p["old"]) for s in all_strs))
        both = sum(1 for p in chain
                   if any(text_contains(s, p["new"]) for s in all_strs)
                   and any(text_contains(s, p["old"]) for s in all_strs))

        # For each chain pair, also examine if Zep correctly invalidated old in retrieved edges
        invalid_old_correct = 0
        for p in chain:
            for e in edges:
                if text_contains(e.get("fact", ""), p["old"]) and e.get("invalid_at"):
                    invalid_old_correct += 1
                    break

        per_q.append({
            "qid": qid, "n_chain_pairs": len(chain),
            "new_in_topK": new_hits, "old_in_topK": old_hits,
            "both_in_topK": both, "old_correctly_invalidated_in_retrieved": invalid_old_correct,
            "new_recall": new_hits / len(chain), "old_recall": old_hits / len(chain),
            "both_rate": both / len(chain),
            "old_invalid_signal_rate": invalid_old_correct / len(chain),
        })

    if not per_q:
        return None
    n_total = len(per_q)
    return {
        "system": "Zep × Gemini-inference",
        "task": task,
        "n_has_pair_questions": n_total,
        "K_edges": 10, "K_episodes": 10,
        "avg_new_recall": round(sum(q["new_recall"] for q in per_q) / n_total, 4),
        "avg_old_recall": round(sum(q["old_recall"] for q in per_q) / n_total, 4),
        "avg_both_rate": round(sum(q["both_rate"] for q in per_q) / n_total, 4),
        "avg_old_invalid_signal_rate": round(sum(q["old_invalid_signal_rate"] for q in per_q) / n_total, 4),
        "per_q": per_q,
    }


# -------------------- Render --------------------

def main():
    out = {
        "mem0_sh": eval_mem0("SH"),
        "mem0_mh": eval_mem0("MH"),
        "zep_sh": eval_zep("SH"),
        "zep_mh": eval_zep("MH"),
    }

    md = ["# Query-time Retrieval Evaluation\n"]
    md.append("> For each FC has_pair question, check whether top-K retrieved content")
    md.append("> covers the GT chain new/old facts.\n")
    md.append("---\n")

    md.append("## Aggregate metrics\n")
    md.append("| System / Task | n questions | new_recall @K | old_recall @K | both_in_topK | old_invalid_signal (Zep only) |")
    md.append("|---|:---:|:---:|:---:|:---:|:---:|")
    for label, key in [("Mem0 SH", "mem0_sh"), ("Mem0 MH", "mem0_mh"), ("Zep SH", "zep_sh"), ("Zep MH", "zep_mh")]:
        d = out.get(key)
        if not d:
            md.append(f"| {label} | — | — | — | — | — |")
            continue
        K = d.get("K") or d.get("K_edges")
        oinv = d.get("avg_old_invalid_signal_rate")
        oinv_s = f"{oinv*100:.1f}%" if oinv is not None else "—"
        md.append(f"| {label} (K={K}) | {d['n_has_pair_questions']} | {d['avg_new_recall']*100:.1f}% | {d['avg_old_recall']*100:.1f}% | {d['avg_both_rate']*100:.1f}% | {oinv_s} |")
    md.append("")
    md.append("**Interpretation**:")
    md.append("- new_recall = fraction of GT new facts the LLM gets to see")
    md.append("- old_recall = fraction of GT old facts also leaked into prompt (distractor)")
    md.append("- both_in_topK = LLM sees both — needs metadata to disambiguate (Zep) or relies on store-cleanup (Mem0)")
    md.append("- old_invalid_signal_rate (Zep only) = fraction where Zep correctly tagged the old as invalid_at")
    md.append("")
    md.append("---")

    md_text = "\n".join(md)
    out_path = RESULTS / "querytime_eval.json"
    md_path = RESULTS / "querytime_eval.md"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    md_path.write_text(md_text)
    print(md_text)
    print(f"\nWritten: {out_path}")
    print(f"Written: {md_path}")


if __name__ == "__main__":
    main()
