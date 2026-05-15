"""Smoke test — LLM judge as detection mechanism, given facts + timestamp metadata.

Step 1 of the Q-Det-3 plan:
  - Pick 5 MH queries
  - For each, gather chain_new + chain_old facts (from GT) + 5 distractors
  - Add serial-number timestamps (larger = newer)
  - Send to Gemini; ask to identify superseded fact pairs
  - Compare LLM output to GT old_seqs

Purpose: validate that LLM can correctly identify chain_old when given a small
fact pool with timestamps, before scaling up to PropRAG-style large pools.
"""
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from methods.hipporag.llm.gemini_llm import CacheGemini

BASE = Path("/home/yhchiang/MemoryAgentBench")
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
OPENIE = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
OUT = BASE / "analysis/results/phase_v1/smoke_llm_judge_detection.json"


def build_prompt(query: str, facts_with_seq: List[Tuple[int, str]]) -> List[dict]:
    """Build (system, user) message list for Gemini.

    Detection-only design: LLM groups facts that contradict each other
    (same subject + same attribute kind + INCOMPATIBLE values). LLM does
    NOT decide which fact is outdated. Direction is resolved deterministically
    by serial number (max seq = current) outside the LLM.

    This avoids LLM world-knowledge prior overriding the timestamp signal
    when the dataset uses counterfactual updates.
    """
    facts_str = "\n".join(f"  [seq={s}] {t}" for s, t in facts_with_seq)
    system = (
        "You are a knowledge conflict detector. Identify groups of facts that "
        "genuinely contradict each other.\n\n"
        "To decide if two facts (s, r, o1) and (s, r, o2) — same subject, "
        "same kind of relation, different objects — actually conflict, "
        "classify the RELATION r into one of four types:\n\n"
        "1. FUNCTIONAL: relation that maps each subject to exactly ONE value "
        "(1-to-1 cardinality). Different o1, o2 are MUTUALLY EXCLUSIVE.\n"
        "   → Same (s, r) with different o IS A CONFLICT.\n\n"
        "2. CUMULATIVE: relation that allows multiple simultaneous values "
        "(1-to-many, values accumulate without displacing each other).\n"
        "   → Same (s, r) with different o is NOT a conflict. Both can coexist.\n\n"
        "3. TEMPORAL-FUNCTIONAL: relation is functional at any single point "
        "in time, but the value can change across time. Without explicit "
        "time context, treat as FUNCTIONAL by default — the newer value "
        "replaces the older.\n"
        "   → Same (s, r) with different o IS A CONFLICT (default behavior).\n\n"
        "4. AGGREGATED: multi-valued attributes where individual values "
        "represent independent additive facts (similar to CUMULATIVE).\n"
        "   → Same (s, r) with different o is NOT a conflict.\n\n"
        "When uncertain, default to FUNCTIONAL (conservative — flag the "
        "potential conflict and let downstream decide).\n\n"
        "IMPORTANT:\n"
        "• You only group conflicting facts. You do NOT decide which is "
        "outdated.\n"
        "• IGNORE your real-world knowledge about which fact is 'correct'. "
        "Treat facts as opaque data.\n"
        "• Each group can have 2+ facts."
    )
    user = (
        f"Facts (each prefixed by its serial number; treat seq as opaque ID):\n"
        f"{facts_str}\n\n"
        f"Query context (do not answer it): {query}\n\n"
        f"Identify conflict groups. Respond with ONLY valid JSON:\n"
        f'{{"conflict_groups": [[<seq>, <seq>, ...], ...]}}\n'
        f"Each inner list is a set of seqs that mutually conflict. "
        f"Return an empty outer list if no conflicts exist.\n"
        f"No prose, no markdown — only JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_response(raw: str) -> dict:
    """Extract JSON from LLM response, handle minor markdown wrapping."""
    raw = raw.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON object in response
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {"_parse_error": True, "_raw": raw[:500]}


def main():
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

    print(f"[load] {GT}")
    gt = json.load(open(GT))

    # Sample queries — spread across qid range, must have ≥2 has_pair hops
    sample_qids = [0, 20, 45, 65, 85]

    # Build distractor pool: collect all unique gt_fact_texts across all queries,
    # exclude those used in the sampled queries
    distractor_pool = set()
    for q in gt:
        for h in q.get("hops", []):
            t = h.get("gt_fact_text", "")
            if t:
                distractor_pool.add(t)

    # Init LLM (uses Vertex AI same as v1 pipeline)
    llm = CacheGemini(
        cache_dir=str(BASE / "outputs/smoke_test_cache"),
        cache_filename="smoke_llm_judge.sqlite",
        llm_name="gemini-3.1-flash-lite-preview",
        temperature=0.0,
        max_new_tokens=600,
    )

    results = []
    rng = random.Random(42)
    for qid in sample_qids:
        q = next((x for x in gt if x["query_id"] == qid), None)
        if q is None:
            print(f"[skip] qid={qid} not in GT")
            continue

        # Collect conflict facts from this query's hops
        conflict_facts = []   # [(seq, text, role)] role: 'chain_new' or 'chain_old'
        gt_old_seqs = []
        for h in q.get("hops", []):
            if h.get("conflict_type") != "has_pair":
                continue
            conflict_facts.append((h["gt_seq"], h["gt_fact_text"], "chain_new"))
            conflict_facts.append((h["old_seq"], h["old_fact_text"], "chain_old"))
            gt_old_seqs.append(h["old_seq"])

        if not conflict_facts:
            print(f"[skip] qid={qid} has no has_pair hops")
            continue

        # Add 5 distractor facts (random other facts, assigned random seqs)
        used_texts = {t for _, t, _ in conflict_facts}
        cand_distractors = [t for t in distractor_pool if t not in used_texts]
        n_dist = 5
        distractors = rng.sample(cand_distractors, min(n_dist, len(cand_distractors)))
        # Assign random seqs in range [1, 1000] avoiding clashes
        used_seqs = {s for s, _, _ in conflict_facts}
        distractor_facts = []
        for t in distractors:
            while True:
                s = rng.randint(1, 1000)
                if s not in used_seqs:
                    used_seqs.add(s)
                    break
            distractor_facts.append((s, t, "distractor"))

        # Shuffle final fact list
        all_facts = conflict_facts + distractor_facts
        rng.shuffle(all_facts)
        facts_with_seq = [(s, t) for s, t, _ in all_facts]

        # Call LLM (cache lookup may force re-run if prompt changed)
        messages = build_prompt(q["question"], facts_with_seq)
        response, _meta, _cache_hit = llm.infer(messages)
        parsed = parse_response(response)

        # Mechanical direction: in each conflict_group, max seq = current,
        # all other seqs in the group = outdated.
        flagged_seqs = set()
        conflict_pairs_llm = []  # for pair-level scoring
        if "conflict_groups" in parsed:
            for group in parsed.get("conflict_groups", []):
                if not isinstance(group, list) or len(group) < 2:
                    continue
                try:
                    group_ints = [int(s) for s in group]
                except (ValueError, TypeError):
                    continue
                max_seq = max(group_ints)
                for s in group_ints:
                    if s != max_seq:
                        flagged_seqs.add(s)
                # record group for pair-level diagnostic
                conflict_pairs_llm.append(sorted(group_ints))

        gt_set = set(gt_old_seqs)
        tp = flagged_seqs & gt_set
        fp = flagged_seqs - gt_set
        fn = gt_set - flagged_seqs

        # Pair-level recall: does each GT conflict pair appear in some LLM group?
        # A GT pair is (old_seq, gt_seq); we have old_seq, infer gt_seq from hops.
        gt_pairs = []  # [(old_seq, gt_seq), ...]
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair":
                gt_pairs.append((h["old_seq"], h["gt_seq"]))
        pair_recall_hits = 0
        for old_s, new_s in gt_pairs:
            for grp in conflict_pairs_llm:
                if old_s in grp and new_s in grp:
                    pair_recall_hits += 1
                    break

        chain_new_seqs = {s for s, _, role in conflict_facts if role == "chain_new"}
        distractor_seqs = {s for s, _, _ in distractor_facts}
        false_chain_new = flagged_seqs & chain_new_seqs
        false_distractor = flagged_seqs & distractor_seqs

        print()
        print("=" * 75)
        print(f"  qid={qid}: n_facts={len(facts_with_seq)} ({len(conflict_facts)//2} conflict pairs + {len(distractor_facts)} distractors)")
        print("=" * 75)
        print(f"  Query: {q['question'][:120]}")
        print(f"  GT conflict pairs (old,new): {gt_pairs}")
        print(f"  LLM conflict groups:         {conflict_pairs_llm}")
        print(f"  Direction-level: GT old_seqs={sorted(gt_set)}, flagged={sorted(flagged_seqs)}")
        print(f"  Direction TP={sorted(tp)}, FP={sorted(fp)}, FN={sorted(fn)}")
        print(f"  Pair-level recall: {pair_recall_hits}/{len(gt_pairs)} = {pair_recall_hits*100/max(1,len(gt_pairs)):.0f}%")
        if false_chain_new:
            print(f"  ⚠️  Direction reversed (flagged chain_new): {sorted(false_chain_new)}")
        if false_distractor:
            print(f"  ⚠️  Flagged distractor: {sorted(false_distractor)}")
        if "_parse_error" in parsed:
            print(f"  ⚠️  parse error, raw output: {parsed['_raw']}")

        results.append({
            "qid": qid,
            "n_facts": len(facts_with_seq),
            "n_conflict_pairs_gt": len(gt_pairs),
            "n_distractors": len(distractor_facts),
            "gt_pairs": gt_pairs,
            "llm_groups": conflict_pairs_llm,
            "pair_recall_hits": pair_recall_hits,
            "gt_old_seqs": sorted(gt_set),
            "flagged_seqs": sorted(flagged_seqs),
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
            "false_chain_new": sorted(false_chain_new),
            "false_distractor": sorted(false_distractor),
            "raw_response": response[:1500],
            "parsed_response": parsed,
            "facts_sent": facts_with_seq,
        })

    # Aggregate
    print("\n" + "=" * 75)
    print("  AGGREGATE")
    print("=" * 75)
    tot_gt = sum(len(r["gt_old_seqs"]) for r in results)
    tot_flagged = sum(len(r["flagged_seqs"]) for r in results)
    tot_tp = sum(len(r["tp"]) for r in results)
    tot_fp = sum(len(r["fp"]) for r in results)
    tot_fn = sum(len(r["fn"]) for r in results)
    recall = tot_tp / max(1, tot_gt)
    precision = tot_tp / max(1, tot_flagged)
    tot_pair_gt = sum(r["n_conflict_pairs_gt"] for r in results)
    tot_pair_hits = sum(r["pair_recall_hits"] for r in results)
    tot_false_dist = sum(len(r["false_distractor"]) for r in results)
    print(f"  --- Direction-level (does mechanical seq pick the GT chain_old?) ---")
    print(f"    Total GT chain_old facts: {tot_gt}")
    print(f"    LLM flagged:              {tot_flagged}")
    print(f"    TP={tot_tp}, FP={tot_fp}, FN={tot_fn}")
    print(f"    Recall    = {recall:.1%}")
    print(f"    Precision = {precision:.1%}")
    print(f"  --- Pair-level (did LLM group the GT conflicting pair together?) ---")
    print(f"    Pair recall = {tot_pair_hits}/{tot_pair_gt} = {tot_pair_hits*100/max(1,tot_pair_gt):.1f}%")
    print(f"  --- Distractor noise ---")
    print(f"    Flagged distractors = {tot_false_dist} (should be 0 in clean detection)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_queries": len(results),
        "aggregate": {
            "tot_gt": tot_gt, "tot_flagged": tot_flagged,
            "tot_tp": tot_tp, "tot_fp": tot_fp, "tot_fn": tot_fn,
            "recall": recall, "precision": precision,
        },
        "per_query": results,
    }, open(OUT, "w"), indent=2)
    print(f"\n[wrote] {OUT}")


if __name__ == "__main__":
    main()
