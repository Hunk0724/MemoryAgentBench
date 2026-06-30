"""
check_mquake_coverage.py
========================
Validate MQuAKE alignment coverage for all 8 FC subsets
(SH/MH × 6k/32k/64k/262k) WITHOUT needing any model run.

Reads HF dataset arrow directly to get the 100 (question, answer) pairs per
subset, then for each question runs the same alignment logic as
analyze_lca_mquake.py / align_mem0_mquake.py and reports:

  per-subset:
    - matched / unmatched (能否在 MQuAKE 索引找到 case)
    - per-hop conflict_type distribution (has_pair / no_conflict_pair / answer_not_in_ctx)
    - n_hops distribution

Usage:
    python analysis/check_mquake_coverage.py
        [--output analysis/results/mquake_coverage_report.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pyarrow import ipc

sys.path.insert(0, str(Path(__file__).parent))
from analyze_lca_mquake import (  # type: ignore
    load_mquake_index,
    parse_context,
    find_hop_gt,
    find_hop_old,
)

ARROW = ("/home/yhchiang/MemoryAgentBench/.cache/huggingface/datasets/"
         "ai-hyz___memory_agent_bench/default/0.0.0/"
         "00d1946269e29b41eed74511997afa8171b91e08/"
         "memory_agent_bench-Conflict_Resolution.arrow")
CTX_DIR = Path("/home/yhchiang/MemoryAgentBench/analysis/contexts")

SUBSETS = [
    ("sh", "6k"), ("mh", "6k"),
    ("sh", "32k"), ("mh", "32k"),
    ("sh", "64k"), ("mh", "64k"),
    ("sh", "262k"), ("mh", "262k"),
]


def load_arrow_rows():
    with open(ARROW, "rb") as f:
        return ipc.open_stream(f).read_all().to_pylist()


def question_from_query(query: str) -> str:
    """Extract the user-asked question out of MABench's wrapped query template."""
    m = re.search(r"Now Answer the Question:\s*(.+?)(?:\nAnswer:|$)", query, re.DOTALL)
    if not m:
        return query.strip()
    return re.sub(r"Based on the provided Knowledge Pool,\s*", "",
                  m.group(1).strip(), flags=re.IGNORECASE).strip()


def align_one(mode, question, gt_answers, sh_idx, mh_idx, ctx_lines, ctx_by_lower):
    """Replicate analyze_lca_mquake.analyze_{sh,mh} for one query."""
    case, hop_idx = None, None
    if mode == "sh":
        for a in gt_answers:
            m = sh_idx.get((question.lower(), a.strip().lower()))
            if m:
                case, hop_idx = m
                break
    else:
        for a in gt_answers:
            case = mh_idx.get((question.lower(), a.strip().lower()))
            if case:
                break
    if not case:
        return {"matched": False}

    rws = case.get("requested_rewrite", [])
    hops_src = ([case["new_single_hops"][hop_idx]] if mode == "sh"
                else case.get("new_single_hops", []))
    hop_offset = hop_idx if mode == "sh" else 0
    hop_infos = []
    for local_i, hop in enumerate(hops_src):
        absolute_idx = hop_offset + local_i if mode == "sh" else local_i
        gt_seq, _ = find_hop_gt(hop, ctx_by_lower)
        old_seq, _, old_ans, old_src = find_hop_old(
            hop, rws, absolute_idx, ctx_lines, ctx_by_lower
        )
        if old_seq is not None:
            conflict_type = "has_pair"
        elif old_ans:
            conflict_type = "answer_not_in_ctx"   # MQuAKE 有舊答案但 context 找不到對應 fact
        else:
            conflict_type = "no_conflict_pair"
        hop_infos.append({
            "hop_idx": absolute_idx,
            "gt_seq": gt_seq,
            "old_seq": old_seq,
            "conflict_type": conflict_type,
            "old_source": old_src,  # 'direct'/'cloze'/'none'
            "gt_found_in_ctx": gt_seq is not None,
        })
    return {
        "matched": True,
        "case_id": case["case_id"],
        "n_hops": len(hop_infos),
        "hops": hop_infos,
    }


def report_subset(mode, length, rows, sh_idx, mh_idx):
    src = f"factconsolidation_{mode}_{length}"
    matched_rows = [r for r in rows if (r.get("metadata") or {}).get("source") == src]
    if not matched_rows:
        return {"source": src, "found": False}
    row = matched_rows[0]
    questions = row["questions"]
    answers_per_q = row["answers"]
    # ctx 從 cache
    ctx_file = CTX_DIR / f"factconsolidation_{length}_context.txt"
    ctx_text = ctx_file.read_text(encoding="utf-8")
    ctx_lines, ctx_by_lower = parse_context(ctx_text)

    per_query = []
    n_match = n_unmatch = 0
    hop_conflict_counter = Counter()
    n_hops_dist = Counter()
    gt_found_total = 0
    hop_total = 0
    for i, q in enumerate(questions):
        # 對 MABench 的 query 解 wrap;但 HF dataset 內 questions 可能已經是裸問句
        bare_q = question_from_query(q) if "Now Answer the Question" in q else q
        gt_a = answers_per_q[i] if isinstance(answers_per_q[i], list) else [answers_per_q[i]]
        result = align_one(mode, bare_q, gt_a, sh_idx, mh_idx, ctx_lines, ctx_by_lower)
        per_query.append({"q_idx": i, "result": result})
        if result["matched"]:
            n_match += 1
            n_hops_dist[result["n_hops"]] += 1
            for h in result["hops"]:
                hop_conflict_counter[h["conflict_type"]] += 1
                hop_total += 1
                if h["gt_found_in_ctx"]:
                    gt_found_total += 1
        else:
            n_unmatch += 1

    return {
        "source": src,
        "found": True,
        "n_questions": len(questions),
        "matched": n_match,
        "unmatched": n_unmatch,
        "n_hops_distribution": dict(n_hops_dist),
        "hop_conflict_distribution": dict(hop_conflict_counter),
        "total_hops": hop_total,
        "gt_found_in_ctx_total": gt_found_total,
        "ctx_facts": len(ctx_lines),
        "per_query": per_query,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=Path("analysis/results/mquake_coverage_report.json"))
    args = ap.parse_args()

    print("[load] MQuAKE-CF…", flush=True)
    _, sh_idx, mh_idx = load_mquake_index()
    print("[load] arrow…", flush=True)
    rows = load_arrow_rows()

    print(f"\n{'Subset':<35} {'Match':>8} {'Unmatch':>8} {'Hops':>6}  Hop conflict_type dist.")
    print("-" * 110)
    full_report = []
    for mode, length in SUBSETS:
        r = report_subset(mode, length, rows, sh_idx, mh_idx)
        full_report.append(r)
        if not r["found"]:
            print(f"  {r['source']:<33} NOT FOUND in arrow")
            continue
        ct = r["hop_conflict_distribution"]
        ct_str = " | ".join(f"{k}={v}" for k, v in sorted(ct.items()))
        print(f"  {r['source']:<33} "
              f"{r['matched']:>4}/{r['n_questions']:<3} "
              f"{r['unmatched']:>8} "
              f"{r['total_hops']:>6}  "
              f"{ct_str}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    json.dump(full_report, open(args.output, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n[write] {args.output}")


if __name__ == "__main__":
    main()
