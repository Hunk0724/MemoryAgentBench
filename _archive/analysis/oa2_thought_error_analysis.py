"""
Analyze remaining FC-MH errors in OA2 (original-prompt version) via Thought traces.

For each FC-MH question that OA2 still got wrong, parse the Thought block from
HippoRAG-v2's raw_output and classify the failure mode by inspecting:
  (a) what entity LLM mentioned at each chain step
  (b) what final answer LLM produced
  (c) whether LLM accessed the chain GT facts (gt_seq still present in context after fact-level filter)

Reads:
  analysis/results/diagnostic/oracle_a_fact_level_origprompt_mh_results.json
  analysis/results/mh_512_mquake_analysis.json
  analysis/contexts/factconsolidation_6k_context.txt   (455 numbered facts, for entity lookup)

Writes:
  analysis/results/diagnostic/oa2_remaining_errors_analysis.{json,txt}
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
OA2_MH = BASE / "analysis/results/diagnostic/oracle_a_fact_level_origprompt_mh_results.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
OUT_JSON = BASE / "analysis/results/diagnostic/oa2_remaining_errors_analysis.json"
OUT_TXT = BASE / "analysis/results/diagnostic/oa2_remaining_errors_analysis.txt"


def normalize(s):
    if s is None:
        return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(s, target):
    if not s or not target:
        return False
    s, t = normalize(s), normalize(target)
    return s == t or t in s or s in t


def parse_thought_and_answer(raw):
    """Pull Thought block + Answer from raw_output. raw may or may not include 'Thought:' prefix."""
    thought = ""
    if "Thought:" in raw:
        after_thought = raw.split("Thought:", 1)[1]
    else:
        after_thought = raw
    if "Answer:" in after_thought:
        thought_part, _ = after_thought.split("Answer:", 1)
        answer_part = after_thought.split("Answer:", 1)[1].strip()
    else:
        thought_part = after_thought
        answer_part = after_thought.strip()
    return thought_part.strip(), answer_part


def load_facts():
    facts = {}
    for line in open(CONTEXT_FILE):
        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip()
    return facts


def find_seq_mentions(thought_text):
    """Find all '<seq>.' or 'fact <seq>' or 'Fact <seq>' style mentions in Thought."""
    seqs = set()
    for pat in [r"\bFact\s+(\d+)\b", r"\bfact\s+(\d+)\b", r"\b(\d+)\.\s"]:
        for m in re.finditer(pat, thought_text):
            seqs.add(int(m.group(1)))
    return seqs


def classify_failure(record, gt_record, facts):
    """Return dict of classification info."""
    raw = record.get("raw_output", "")
    pred = record.get("pred_answer", "")
    thought, answer = parse_thought_and_answer(raw)

    hops = gt_record.get("hops", [])
    chain_gt_seqs = [h.get("gt_seq") for h in hops if h.get("gt_seq") is not None]
    chain_gt_answers = [h.get("gt_answer") for h in hops if h.get("gt_answer")]
    chain_old_seqs = [h.get("old_seq") for h in hops if h.get("old_seq") is not None]
    chain_old_answers = [h.get("old_answer") for h in hops if h.get("old_answer")]
    final_gt = chain_gt_answers[-1] if chain_gt_answers else None
    final_old = gt_record.get("old_final_answer")

    # 1. Check final answer category
    matched_old_final = bool(final_old) and fuzzy_match(pred, final_old)
    matched_intermediate_old = any(fuzzy_match(pred, oa) for oa in chain_old_answers if oa)
    matched_intermediate_gt = any(fuzzy_match(pred, ga) for ga in chain_gt_answers[:-1])

    # 2. Check Thought traces for which entities LLM saw
    # Find seqs the LLM cited; check if they include chain GTs vs old, etc.
    cited_seqs = find_seq_mentions(thought)
    cited_chain_gts = cited_seqs & set(chain_gt_seqs)
    cited_chain_olds = cited_seqs & set(chain_old_seqs)

    # Whether GT entities appear in Thought
    gt_in_thought = sum(1 for ga in chain_gt_answers if ga and ga.lower() in thought.lower())
    old_in_thought = sum(1 for oa in chain_old_answers if oa and oa.lower() in thought.lower())

    if matched_old_final:
        category = "older_fact_final"
    elif matched_intermediate_old:
        category = "older_intermediate"
    elif matched_intermediate_gt:
        category = "chain_break_at_GT"
    elif pred and any(pred.lower() in facts.get(s, "").lower() for s in facts.keys()):
        category = "entity_confusion"
    else:
        category = "hallucination_or_other"

    return {
        "query_id": record["query_id"],
        "num_hops": gt_record.get("num_hops"),
        "n_conflict": sum(1 for h in hops if h.get("conflict_type") == "has_pair"),
        "category": category,
        "pred": pred,
        "final_gt": final_gt,
        "final_old": final_old,
        "thought_len": len(thought),
        "thought_excerpt": thought[:400],
        "chain_gt_answers": chain_gt_answers,
        "chain_old_answers": chain_old_answers,
        "cited_chain_gt_seqs": sorted(cited_chain_gts),
        "cited_chain_old_seqs": sorted(cited_chain_olds),
        "gt_entities_seen_in_thought": gt_in_thought,
        "old_entities_seen_in_thought": old_in_thought,
    }


def main():
    facts = load_facts()
    oa2 = json.load(open(OA2_MH))
    gt_data = {r["query_id"]: r for r in json.load(open(MH_GT))}

    wrong = [r for r in oa2 if not r.get("exact_match")]
    print(f"OA2 origprompt MH: {sum(1 for r in oa2 if r.get('exact_match'))}/{len(oa2)} correct, {len(wrong)} wrong")

    analyses = []
    for r in wrong:
        gt_r = gt_data.get(r["query_id"])
        if gt_r is None:
            continue
        a = classify_failure(r, gt_r, facts)
        analyses.append(a)

    cat_count = Counter(a["category"] for a in analyses)
    by_group = defaultdict(lambda: Counter())
    for a in analyses:
        key = (a["num_hops"], a["n_conflict"])
        by_group[key][a["category"]] += 1

    lines = []
    P = lines.append
    P("=" * 78)
    P(f"OA2 (orig prompt) FC-MH remaining-errors analysis  (n={len(analyses)} wrong)")
    P("=" * 78)
    P("\n[1] Failure category distribution:")
    for cat, c in cat_count.most_common():
        P(f"  {cat:<30s}  {c:>3} ({c/len(analyses)*100:.0f}%)")

    P("\n[2] By (num_hops, n_conflict):")
    for key in sorted(by_group.keys()):
        nh, nc = key
        cc = by_group[key]
        items = ", ".join(f"{k}:{v}" for k, v in cc.most_common())
        P(f"  {nh}-hop, {nc}-conflict ({sum(cc.values())} wrong)  {items}")

    P("\n[3] Per-question detail:")
    for a in analyses:
        P(f"  qid {a['query_id']:>3} ({a['num_hops']}-hop, {a['n_conflict']}-c) "
          f"[{a['category']}] pred='{a['pred']}' "
          f"final_gt='{a['final_gt']}' final_old='{a['final_old']}'")
        P(f"    GT chain: {a['chain_gt_answers']}")
        P(f"    OLD chain: {a['chain_old_answers']}")
        P(f"    Thought ({a['thought_len']} chars): {a['thought_excerpt']!r}")
        P(f"    GT entities in thought: {a['gt_entities_seen_in_thought']}, OLD entities in thought: {a['old_entities_seen_in_thought']}")
        P("")

    P("=" * 78)

    txt = "\n".join(lines)
    OUT_TXT.write_text(txt)
    OUT_JSON.write_text(json.dumps(analyses, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_TXT}")
    print(txt[:5000])


if __name__ == "__main__":
    main()
