"""
Oracle A Phase 1: Validate passage removal before calling LLM API.

Matching strategy (two-step):
  1. Word-boundary seq number matching: r'(?:^|[\\s])SEQ\\.\\s'
  2. Fallback: exact text matching (for chunking edge cases where seq is cut off)

For each question:
  - Re-locate old facts and GT facts in passages
  - Determine which passages to remove
  - Classify each question's Oracle A eligibility
  - Report statistics per group
"""

import json
import re
import os
from collections import defaultdict
from pathlib import Path

# === Paths ===
BASE = Path("/home/yhchiang/MemoryAgentBench")
SH_ANALYSIS = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_ANALYSIS = BASE / "analysis/results/mh_512_mquake_analysis.json"
SH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"


def parse_passages(context_str):
    """Parse 'Passage 1:\\n...\\n\\nPassage 2:\\n...' into dict {rank(int): text(str)}."""
    passages = {}
    parts = re.split(r'(Passage \d+:\n)', context_str)
    i = 0
    while i < len(parts):
        m = re.match(r'Passage (\d+):', parts[i])
        if m and i + 1 < len(parts):
            rank = int(m.group(1))
            passages[rank] = parts[i + 1].strip()
            i += 2
        else:
            # First part might be empty or contain first passage without header split
            if parts[i].strip():
                m2 = re.match(r'Passage (\d+):\n(.*)', parts[i], re.DOTALL)
                if m2:
                    passages[int(m2.group(1))] = m2.group(2).strip()
            i += 1
    return passages


def find_in_passages(seq_no, fact_text, passages_dict):
    """
    Find which passage contains a fact. Two-step matching:
    1. Word-boundary seq number match
    2. Fallback: exact text match (handles chunking edge cases)

    Returns (rank, method) or (None, None).
    """
    # Step 1: Word-boundary seq number matching
    if seq_no is not None:
        pattern = r'(?:^|[\s])' + re.escape(str(seq_no)) + r'\.\s'
        for rank in sorted(passages_dict.keys()):
            if re.search(pattern, passages_dict[rank]):
                return rank, "seq"

    # Step 2: Exact text matching (for chunking edge cases)
    if fact_text:
        fact_lower = fact_text.lower().rstrip('.')
        for rank in sorted(passages_dict.keys()):
            if fact_lower in passages_dict[rank].lower():
                return rank, "text"

    return None, None


def validate_sh():
    """Validate SH Oracle A passage removal."""
    print("=" * 70)
    print("FC-SH Oracle A Validation")
    print("=" * 70)

    with open(SH_ANALYSIS) as f:
        sh_data = json.load(f)

    has_pair = [q for q in sh_data if q["conflict_type"] == "has_pair"]
    print(f"Total has_pair questions: {len(has_pair)}")

    corrected_data = []
    issues = []
    counters = defaultdict(int)

    for q in has_pair:
        qid = q["query_id"]
        ctx_path = SH_RETRIEVED_DIR / f"query_{qid}_context_0.json"

        if not ctx_path.exists():
            issues.append(f"  [MISSING] query_{qid}: context file not found")
            continue

        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        old_rank, old_method = find_in_passages(q["old_seq"], q["old_fact_text"], passages)
        gt_rank, gt_method = find_in_passages(q["gt_seq"], q["gt_fact_text"], passages)

        same_passage = (old_rank is not None and gt_rank is not None and old_rank == gt_rank)
        remaining_ranks = set(passages.keys()) - ({old_rank} if old_rank is not None else set())
        gt_safe = gt_rank is not None and gt_rank in remaining_ranks

        # Classify
        if old_rank is None:
            status = "old_not_retrieved"
        elif same_passage:
            status = "same_passage"
        elif not gt_safe:
            status = "gt_not_retrieved"
        else:
            status = "usable"
        counters[status] += 1

        if old_method == "text":
            counters["old_matched_by_text_fallback"] += 1
        if gt_method == "text":
            counters["gt_matched_by_text_fallback"] += 1

        orig_old_rank = q["old_passage_rank"]
        if old_rank is not None and old_rank != orig_old_rank:
            counters["rank_corrected"] += 1
            issues.append(f"  [RANK_FIX] query_{qid}: old_rank {orig_old_rank} -> {old_rank} (seq={q['old_seq']}, method={old_method})")

        if same_passage:
            issues.append(f"  [SAME_PASSAGE] query_{qid}: both in passage {old_rank} (old_seq={q['old_seq']}, gt_seq={q['gt_seq']})")
        if old_rank is None:
            issues.append(f"  [OLD_NOT_FOUND] query_{qid}: old_seq={q['old_seq']}, old_fact={q['old_fact_text']}")
        if gt_rank is None:
            issues.append(f"  [GT_NOT_FOUND] query_{qid}: gt_seq={q['gt_seq']}, gt_fact={q['gt_fact_text']}")

        corrected_data.append({
            "query_id": qid,
            "question": q["question"],
            "gt_answer": q["gt_answer"],
            "old_seq": q["old_seq"],
            "gt_seq": q["gt_seq"],
            "old_fact_text": q["old_fact_text"],
            "gt_fact_text": q["gt_fact_text"],
            "corrected_old_rank": old_rank,
            "old_match_method": old_method,
            "corrected_gt_rank": gt_rank,
            "gt_match_method": gt_method,
            "same_passage": same_passage,
            "status": status,
            "n_passages_after": 10 - (1 if old_rank is not None else 0),
            "exact_match_before": q["exact_match"],
        })

    t = len(has_pair)
    print(f"\nStatus breakdown:")
    for status in ["usable", "same_passage", "gt_not_retrieved", "old_not_retrieved"]:
        print(f"  {status:<22}: {counters[status]:>3}/{t}")
    print(f"\nMatching details:")
    print(f"  Old matched by text fallback: {counters['old_matched_by_text_fallback']}")
    print(f"  GT matched by text fallback:  {counters['gt_matched_by_text_fallback']}")
    print(f"  Original rank corrected:      {counters['rank_corrected']}")

    if issues:
        print(f"\n--- Issues ---")
        for line in issues:
            print(line)

    return corrected_data


def validate_mh():
    """Validate MH Oracle A passage removal."""
    print("\n" + "=" * 70)
    print("FC-MH Oracle A Validation")
    print("=" * 70)

    with open(MH_ANALYSIS) as f:
        mh_data = json.load(f)

    print(f"Total MH questions: {len(mh_data)}")

    corrected_data = []
    all_issues = []

    for q in mh_data:
        qid = q["query_id"]
        n_hops = q["num_hops"]
        n_conflict = sum(1 for h in q["hops"] if h["conflict_type"] == "has_pair")

        ctx_path = MH_RETRIEVED_DIR / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            corrected_data.append({
                "query_id": qid, "num_hops": n_hops, "n_conflict": n_conflict,
                "status": "context_missing", "valid": False
            })
            continue

        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        old_ranks = []
        gt_ranks = []
        hop_details = []
        rank_fixes = []
        all_old_found = True
        any_same_passage = False

        for hop in q["hops"]:
            if hop["conflict_type"] != "has_pair":
                continue

            old_rank, old_method = find_in_passages(hop["old_seq"], hop["old_fact_text"], passages)
            gt_rank, gt_method = find_in_passages(hop["gt_seq"], hop["gt_fact_text"], passages)

            orig_old_rank = hop.get("old_rank")
            orig_gt_rank = hop.get("gt_rank")

            if old_rank != orig_old_rank:
                rank_fixes.append(f"hop_{hop['hop_idx']}: old {orig_old_rank}->{old_rank} (seq={hop['old_seq']}, {old_method})")
            if gt_rank != orig_gt_rank:
                rank_fixes.append(f"hop_{hop['hop_idx']}: gt {orig_gt_rank}->{gt_rank} (seq={hop['gt_seq']}, {gt_method})")

            if old_rank is not None:
                old_ranks.append(old_rank)
            else:
                all_old_found = False
                all_issues.append(f"  [OLD_NOT_FOUND] query_{qid} hop_{hop['hop_idx']}: seq={hop['old_seq']}, fact={hop['old_fact_text']}")

            if gt_rank is not None:
                gt_ranks.append(gt_rank)

            if old_rank is not None and gt_rank is not None and old_rank == gt_rank:
                any_same_passage = True
                all_issues.append(f"  [SAME_PASSAGE] query_{qid} hop_{hop['hop_idx']}: both in passage {old_rank}")

            hop_details.append({
                "hop_idx": hop["hop_idx"],
                "old_seq": hop["old_seq"],
                "gt_seq": hop["gt_seq"],
                "old_rank": old_rank,
                "old_method": old_method,
                "gt_rank": gt_rank,
                "gt_method": gt_method,
                "same_passage": old_rank == gt_rank if (old_rank and gt_rank) else False,
            })

        for fix in rank_fixes:
            all_issues.append(f"  [RANK_FIX] query_{qid} {fix}")

        ranks_to_remove = sorted(set(old_ranks))
        remaining_ranks = set(passages.keys()) - set(ranks_to_remove)
        gt_safe = all(r in remaining_ranks for r in gt_ranks) and len(gt_ranks) == n_conflict

        # Determine status
        if not all_old_found and any_same_passage:
            status = "old_missing+same_passage"
        elif not all_old_found:
            status = "old_not_all_found"
        elif any_same_passage:
            # Check if ONLY same-passage hops cause gt_safe to fail
            status = "same_passage"
        elif not gt_safe:
            status = "gt_not_safe"
        else:
            status = "usable"

        corrected_data.append({
            "query_id": qid,
            "num_hops": n_hops,
            "n_conflict": n_conflict,
            "gt_answer": q["gt_answer"],
            "corrected_old_ranks": ranks_to_remove,
            "corrected_gt_ranks": gt_ranks,
            "hop_details": hop_details,
            "status": status,
            "n_passages_after": 10 - len(ranks_to_remove),
            "valid": True,
            "exact_match_before": q["exact_match"],
        })

    # Report per group
    groups = defaultdict(list)
    for e in corrected_data:
        if not e.get("valid", False):
            continue
        groups[(e["num_hops"], e["n_conflict"])].append(e)

    overall_usable = 0
    overall_total = 0

    for key in sorted(groups.keys()):
        n_hops, n_conflict = key
        entries = groups[key]
        n = len(entries)
        overall_total += n

        status_counts = defaultdict(int)
        for e in entries:
            status_counts[e["status"]] += 1

        usable = status_counts["usable"]
        overall_usable += usable

        print(f"\n--- {n_hops}-hop, {n_conflict} conflict ({n} questions) ---")
        print(f"  usable:              {usable}/{n}")
        for s in ["same_passage", "old_not_all_found", "gt_not_safe", "old_missing+same_passage"]:
            if status_counts[s] > 0:
                print(f"  {s:<22}: {status_counts[s]}/{n}")
        print(f"  passages after:      {10 - n_conflict}")

    print(f"\n--- MH Overall ---")
    print(f"Total: {overall_total}, Usable: {overall_usable}")

    if all_issues:
        print(f"\n--- Issues ({len(all_issues)} lines) ---")
        for line in all_issues[:80]:
            print(line)
        if len(all_issues) > 80:
            print(f"  ... and {len(all_issues) - 80} more")

    return corrected_data


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")

    sh_corrected = validate_sh()
    mh_corrected = validate_mh()

    # Save corrected data for Phase 2
    output = {"sh": sh_corrected, "mh": mh_corrected}
    out_path = BASE / "analysis/results/oracle_a_corrected_ranks.json"
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nCorrected ranks saved to {out_path}")
