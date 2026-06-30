"""
align_mem0_mquake.py
====================
Generic MQuAKE alignment for mem0 / mem0g (or any memory-based agent) outputs on
Fact-Consolidation SH/MH at any context length (6k/32k/64k/262k).

What it produces per query:
    qa_pair_id, case_id, n_hops,
    hops: [{hop_idx, cloze, gt_answer, old_answer,
            gt_seq, old_seq, gt_fact_text, old_fact_text,
            conflict_type, update_gap,
            gt_in_memories, old_in_memories,
            gt_memory_rank, old_memory_rank}],
    conflict_type_any, conflict_type_all, error_type, exact_match

Reuses helpers from analyze_lca_mquake.py to keep alignment logic identical to
prior LCA analyses (find_hop_gt / find_hop_old / classify_error / extract_question).

Usage (FC-MH 6k, no retrieval — pure GT alignment, LCA-style):
    python analysis/align_mem0_mquake.py \\
        --results outputs/<model>/Conflict_Resolution/factconsolidation_mh_6k_*_results.json \\
        --context analysis/contexts/factconsolidation_6k_context.txt \\
        --mode mh \\
        --out analysis/results/<model>_mem0_mh_6k_mquake.json

Usage (with mem0 retrieved memories):
    python analysis/align_mem0_mquake.py \\
        --results outputs/<model>/Conflict_Resolution/factconsolidation_mh_6k_*_results.json \\
        --context analysis/contexts/factconsolidation_6k_context.txt \\
        --mode mh \\
        --retrieval-dir outputs/rag_retrieved/<agent_name>/k_100/factconsolidation_mh_6k/ \\
        --out analysis/results/<model>_mem0_mh_6k_mquake.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from collections import Counter

# Re-use proven helpers (identical signatures)
sys.path.insert(0, str(Path(__file__).parent))
from analyze_lca_mquake import (  # type: ignore
    load_mquake_index,
    parse_context,
    extract_question,
    find_hop_gt,
    find_hop_old,
    classify_error,
)


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval lookup (mem0-style "memories" list of strings)
# ─────────────────────────────────────────────────────────────────────────────

def load_retrieval_for_query(retrieval_dir: Path | None, query_id: int) -> list[str]:
    """Return list of retrieved memory texts for one query, or []."""
    if retrieval_dir is None:
        return []
    # Convention used by mem0 / zep wrappers in agent.py: query_{i}_context_{j}.json
    # Take the first matching file (context_0 by default).
    candidates = sorted(retrieval_dir.glob(f"query_{query_id}_context_*.json"))
    if not candidates:
        return []
    try:
        d = json.load(open(candidates[0], encoding="utf-8"))
    except Exception:
        return []
    # Heuristic: mem0 stores under 'retrieved_memories' or 'memories_str';
    # zep stores under 'edges' with 'fact'. Normalize to list[str].
    mems: list[str] = []
    if isinstance(d.get("retrieved_memories"), list):
        for m in d["retrieved_memories"]:
            if isinstance(m, dict):
                mems.append(m.get("memory") or m.get("text") or "")
            elif isinstance(m, str):
                mems.append(m)
    elif isinstance(d.get("memories_str"), str):
        # split by lines starting with "- "
        mems = [ln.strip("- ").strip() for ln in d["memories_str"].split("\n") if ln.strip()]
    elif isinstance(d.get("edges"), list):
        # zep / graphiti style
        for e in d["edges"]:
            if isinstance(e, dict) and e.get("fact"):
                mems.append(e["fact"])
    return [m for m in mems if m]


def find_fact_in_memories(seq: int | None, fact_text: str | None, memories: list[str]) -> tuple[bool, int]:
    """Return (hit, rank) where rank is 1-indexed; (False, -1) if not found.

    Two-pass match:
      1. seq token like '146.' appears anywhere in a memory → strong hit
      2. fact_text substring (case-insensitive, full sentence body) appears → secondary hit
    Note: pass 1 only works if mem0 happened to keep '146.' prefix; usually it doesn't
    because mem0 extracts facts via LLM and discards numeric prefixes.
    """
    if not memories or fact_text is None:
        return False, -1
    body = re.sub(r"\.$", "", fact_text.strip()).lower()
    seq_token = f"{seq}." if seq is not None else None
    for rank, mem in enumerate(memories, 1):
        m_lower = mem.lower()
        if seq_token and seq_token in m_lower:
            return True, rank
        if body and body in m_lower:
            return True, rank
    return False, -1


# ─────────────────────────────────────────────────────────────────────────────
# SH / MH analysis
# ─────────────────────────────────────────────────────────────────────────────

def analyze(results, ctx_lines, ctx_by_lower, sh_hop_index, mh_q_index, mode,
            retrieval_dir: Path | None):
    """Return list of per-query dicts with full hop-level GT + retrieval status."""
    entries, no_match = [], 0
    for row in results["data"]:
        qa_id = row.get("qa_pair_id")
        query_id = row.get("query_id")
        qtext = extract_question(row.get("query", ""))
        gt_answers = row.get("answer", []) or [""]

        # Match case
        case, hop_idx = None, None
        if mode == "sh":
            for a in gt_answers:
                m = sh_hop_index.get((qtext.lower(), a.strip().lower()))
                if m:
                    case, hop_idx = m
                    break
        else:  # mh
            for a in gt_answers:
                case = mh_q_index.get((qtext.lower(), a.strip().lower()))
                if case:
                    break

        if not case:
            no_match += 1
            continue

        rws = case.get("requested_rewrite", [])
        hops_src = (
            [case["new_single_hops"][hop_idx]] if mode == "sh"
            else case.get("new_single_hops", [])
        )
        hop_offset = hop_idx if mode == "sh" else 0  # SH only has one hop in output but uses original idx

        # Load retrieved memories (if any)
        memories = load_retrieval_for_query(retrieval_dir, query_id) if query_id is not None else []

        hop_infos = []
        for local_i, hop in enumerate(hops_src):
            absolute_idx = hop_offset + local_i if mode == "sh" else local_i
            gt_seq, gt_fact = find_hop_gt(hop, ctx_by_lower)
            old_seq, old_fact, old_ans, old_src = find_hop_old(
                hop, rws, absolute_idx, ctx_lines, ctx_by_lower
            )

            gt_in_mem, gt_rank = find_fact_in_memories(gt_seq, gt_fact, memories)
            old_in_mem, old_rank = find_fact_in_memories(old_seq, old_fact, memories)

            hop_infos.append({
                "hop_idx": absolute_idx,
                "cloze": hop["cloze"],
                "gt_answer": hop["answer"],
                "old_answer": old_ans or None,
                "old_resolution": old_src,           # 'direct'(從 requested_rewrite) / 'cloze'(從 ctx 反推) / 'none'
                "gt_seq": gt_seq,
                "old_seq": old_seq,
                "gt_fact_text": gt_fact,
                "old_fact_text": old_fact,
                "conflict_type": "has_pair" if old_seq is not None else "no_conflict_pair",
                "update_gap": (gt_seq - old_seq) if (gt_seq is not None and old_seq is not None) else None,
                "gt_in_memories": gt_in_mem,
                "old_in_memories": old_in_mem,
                "gt_memory_rank": gt_rank if gt_rank > 0 else None,
                "old_memory_rank": old_rank if old_rank > 0 else None,
            })

        conflict_any = any(h["conflict_type"] == "has_pair" for h in hop_infos)
        conflict_all = all(h["conflict_type"] == "has_pair" for h in hop_infos) if hop_infos else False

        # Error classification (top-level for both modes)
        if mode == "sh":
            top_new = hop_infos[0]["gt_answer"]
            top_old = hop_infos[0]["old_answer"] or ""
        else:
            top_new = case.get("new_answer", "")
            top_old = case.get("answer", "")

        err = classify_error(row.get("parsed_output", ""), top_new, top_old, ctx_lines)

        entries.append({
            "qa_pair_id": qa_id,
            "query_id": query_id,
            "case_id": case["case_id"],
            "n_hops": len(hop_infos),
            "mode": mode,
            "conflict_type_any": "has_pair" if conflict_any else "no_conflict_pair",
            "conflict_type_all": ("has_pair" if conflict_all
                                   else ("partial" if conflict_any else "no_conflict_pair")),
            "hops": hop_infos,
            "error_type": err,
            "parsed_output": row.get("parsed_output"),
            "gt_answer": top_new,
            "old_answer": top_old,
            "exact_match": bool(row.get("exact_match")),
            "n_memories_retrieved": len(memories),
        })

    return entries, no_match


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

def summarize(entries, mode, results_meta):
    model = results_meta.get("agent_config", {}).get("model", "?")
    sub = results_meta.get("dataset_config", {}).get("sub_dataset", "?")
    n = len(entries)
    n_em = sum(1 for e in entries if e["exact_match"])

    print(f"\n=== Alignment summary ===")
    print(f"  model        : {model}")
    print(f"  sub_dataset  : {sub}")
    print(f"  mode         : {mode}")
    print(f"  aligned      : {n} queries")
    print(f"  exact_match  : {n_em}/{n} ({n_em/n*100:.1f}%)" if n else "  exact_match  : -/-")

    if n == 0:
        return

    # Conflict distribution
    print("\n  Conflict type (per query):")
    for ct, c in Counter(e["conflict_type_all"] for e in entries).most_common():
        print(f"    {ct:25s} {c:4d} ({c/n*100:.1f}%)")

    # Error types
    print("\n  Error type distribution:")
    for et, c in Counter(e["error_type"] for e in entries).most_common():
        print(f"    {et:25s} {c:4d} ({c/n*100:.1f}%)")

    # Per-hop conflict + retrieval
    total_hops = sum(e["n_hops"] for e in entries)
    has_pair_hops = sum(1 for e in entries for h in e["hops"] if h["conflict_type"] == "has_pair")
    gt_hit_hops = sum(1 for e in entries for h in e["hops"] if h["gt_in_memories"])
    old_hit_hops = sum(1 for e in entries for h in e["hops"] if h["old_in_memories"])

    print("\n  Hop-level stats:")
    print(f"    total hops              : {total_hops}")
    print(f"    has_pair hops           : {has_pair_hops} ({has_pair_hops/total_hops*100:.1f}%)")
    print(f"    gt fact in memories     : {gt_hit_hops} ({gt_hit_hops/total_hops*100:.1f}%)")
    print(f"    old fact in memories    : {old_hit_hops} ({old_hit_hops/total_hops*100:.1f}%)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, type=Path,
                    help="Path to MABench results JSON (e.g. outputs/<m>/Conflict_Resolution/factconsolidation_..._results.json)")
    ap.add_argument("--context", required=True, type=Path,
                    help="FC context txt (analysis/contexts/factconsolidation_{6k,32k,64k,262k}_context.txt)")
    ap.add_argument("--mode", required=True, choices=["sh", "mh"])
    ap.add_argument("--retrieval-dir", type=Path, default=None,
                    help="Optional: outputs/rag_retrieved/<agent>/k_X/<sub_dataset>/chunksize_Y/ "
                         "containing query_{i}_context_{j}.json. Skip if doing pure GT alignment.")
    ap.add_argument("--out", required=True, type=Path,
                    help="Output JSON path")
    args = ap.parse_args()

    print(f"[load] MQuAKE-CF…", flush=True)
    _, sh_idx, mh_idx = load_mquake_index()
    print(f"[load] context: {args.context}", flush=True)
    ctx_text = args.context.read_text(encoding="utf-8")
    ctx_lines, ctx_by_lower = parse_context(ctx_text)
    print(f"  → {len(ctx_lines)} numbered facts")
    print(f"[load] results: {args.results}", flush=True)
    results = json.load(open(args.results, encoding="utf-8"))

    if args.retrieval_dir:
        print(f"[load] retrieval_dir: {args.retrieval_dir}")

    entries, no_match = analyze(
        results, ctx_lines, ctx_by_lower, sh_idx, mh_idx,
        args.mode, args.retrieval_dir,
    )
    print(f"[align] {len(entries)} aligned, {no_match} unmatched")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "model": results.get("agent_config", {}).get("model"),
        "sub_dataset": results.get("dataset_config", {}).get("sub_dataset"),
        "mode": args.mode,
        "context_file": str(args.context),
        "retrieval_dir": str(args.retrieval_dir) if args.retrieval_dir else None,
        "n_aligned": len(entries),
        "n_unmatched": no_match,
        "entries": entries,
    }, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[write] {args.out}")

    summarize(entries, args.mode, results)


if __name__ == "__main__":
    main()
