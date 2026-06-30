"""
RPT-min: minimum-modification variant of RPT.

Difference vs the original RPT (`restructured_pat_gemini.py`):
- Keeps the vanilla HippoRAG `prompt_user` skeleton intact:
    [Wikipedia Title: ...] × N  +  "Question: <full>\\nThought: "
- Adds only:
    (a) a leading INSTRUCTION paragraph (like PAT does)
    (b) an inline label `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]` BEFORE each
        `Wikipedia Title:` line — passage order is reordered to put Section A first,
        but the `Wikipedia Title:` syntax + Question/Thought trailer are unchanged.
    (c) fact-level [CURRENT FACT] / [OUTDATED FACT] annotation INSIDE passages (same as PAT).

This isolates the effect of "section partition + strong instructions" without
restructuring the entire user message into `== HEADER ==` blocks.

Same usable subset as Oracle A / PAT / RPT (SH=64, MH=66).
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from collections import defaultdict
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

sys.path.insert(0, str(Path(__file__).parent))
from pat_gemini import (
    parse_passages, annotate_passage, build_label_sets,
    RAG_QA_SYSTEM, ONE_SHOT_INPUT, ONE_SHOT_OUTPUT,
    extract_answer, normalize, exact_match,
    SH_RESULTS, MH_RESULTS, SH_RETRIEVED_DIR, MH_RETRIEVED_DIR,
    CORRECTED_RANKS, OUT_DIR,
)
from restructured_pat_gemini import classify_passage

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# Keep instruction language equivalent to RPT but expressed inline
RPT_MIN_INSTRUCTION = (
    "Some retrieved passages contain conflicting facts. "
    "They are pre-organized into two groups by recency:\n"
    "  - Passages prefixed with [SECTION A: ACTIVE] contain current factual statements "
    "(some facts highlighted with [CURRENT FACT]). USE these for your answer.\n"
    "  - Passages prefixed with [SECTION B: SUPERSEDED] contain outdated facts "
    "(specific outdated facts marked with [OUTDATED FACT]). DO NOT use any fact from "
    "Section B as your answer.\n"
    "Within Section A, ignore any facts marked [OUTDATED FACT]. "
    "Only reference Section B if the question explicitly asks about historical states.\n\n"
)


def build_prompt(passages_dict, ranks_to_keep, query_text, current_seqs, outdated_seqs):
    """RPT-min: vanilla skeleton + leading instruction + inline section labels."""
    section_a, section_b = [], []
    for rank in ranks_to_keep:
        text = passages_dict[rank]
        ann = annotate_passage(text, current_seqs, outdated_seqs)
        ptype = classify_passage(text, current_seqs, outdated_seqs)
        if ptype == "outdated":
            section_b.append(ann)
        else:
            section_a.append(ann)

    prompt_user = RPT_MIN_INSTRUCTION
    for ann in section_a:
        prompt_user += f"[SECTION A: ACTIVE] Wikipedia Title: {ann}\n\n"
    for ann in section_b:
        prompt_user += f"[SECTION B: SUPERSEDED] Wikipedia Title: {ann}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "

    return [
        {"role": "system",    "content": RAG_QA_SYSTEM},
        {"role": "user",      "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user",      "content": prompt_user},
    ], len(section_a), len(section_b)


def call_gemini(client, messages):
    sys_inst, contents = None, []
    for m in messages:
        if m["role"] == "system":
            sys_inst = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
    cfg = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if sys_inst:
        cfg.system_instruction = sys_inst
    for attempt in range(10):
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            break
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == 9:
                raise
            mtch = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(mtch.group(1)) + 2 if mtch else min(2 ** attempt * 5, 60))
    text = resp.text if resp.text is not None else ""
    um = resp.usage_metadata
    return text, getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)


def run_rpt_min(client, task, corrected_entries, results_data, retrieved_dir, label_sets):
    query_map = {e["query_id"]: e["query"] for e in results_data["data"]}
    em_before_map = {e["query_id"]: bool(e.get("exact_match", False)) for e in results_data["data"]}
    usable = [e for e in corrected_entries if e["status"] == "usable"]
    print(f"\n{'='*60}\nRPT-min Inference: {task} ({len(usable)} usable)\n{'='*60}")

    results = []
    correct = 0
    errors = []
    for i, entry in enumerate(usable):
        qid = entry["query_id"]
        gt_answer = entry["gt_answer"]
        query_text = query_map.get(qid, "")
        if not query_text:
            errors.append(f"query_{qid}: no query text"); continue

        passages = parse_passages(json.load(open(retrieved_dir / f"query_{qid}_context_0.json")))
        ranks_to_keep = sorted(passages.keys())
        curr_seqs, old_seqs = label_sets.get(qid, (set(), set()))

        messages, n_a, n_b = build_prompt(passages, ranks_to_keep, query_text, curr_seqs, old_seqs)

        try:
            raw, ptok, ctok = call_gemini(client, messages)
            pred = extract_answer(raw)
        except Exception as e:
            errors.append(f"query_{qid}: API error: {e}")
            raw = f"ERROR: {e}"; pred = ""; ptok = ctok = 0

        em = exact_match(pred, gt_answer)
        if em:
            correct += 1

        rec = {
            "query_id": qid,
            "gt_answer": gt_answer,
            "pred_answer": pred,
            "raw_output": raw,
            "exact_match": em,
            "exact_match_before": em_before_map.get(qid, False),
            "n_section_a": n_a,
            "n_section_b": n_b,
            "n_current_facts_marked": len(curr_seqs),
            "n_outdated_facts_marked": len(old_seqs),
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        }
        if task == "MH":
            rec["num_hops"] = entry["num_hops"]
            rec["n_conflict"] = entry["n_conflict"]
        results.append(rec)

        if (i + 1) % 10 == 0 or i == len(usable) - 1:
            print(f"  [{i+1}/{len(usable)}] Acc: {correct}/{i+1} = {correct/(i+1)*100:.1f}%")

    print(f"\n  Final: {correct}/{len(usable)} = {correct/len(usable)*100:.1f}%")
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"    {e}")
    return results


def print_summary(task, results, old_map):
    n = len(results)
    after = sum(1 for r in results if r["exact_match"])
    before = sum(1 for r in results if r.get("exact_match_before", False))
    print(f"\n{'='*60}\nRPT-min Results Summary: {task}\n{'='*60}")
    print(f"Usable n: {n}")
    print(f"Baseline (vanilla on this subset):    {before}/{n} = {before/n*100:.1f}%")
    print(f"RPT-min Acc:                          {after}/{n} = {after/n*100:.1f}%")
    print(f"Improvement vs vanilla:               +{after-before} (+{(after-before)/n*100:.1f} pp)")

    fails = [r for r in results if not r["exact_match"]]
    older = sum(1 for r in fails
                if old_map.get(r["query_id"]) and (
                    normalize(r["pred_answer"]) == old_map[r["query_id"]]
                    or old_map[r["query_id"]] in normalize(r["pred_answer"])
                    or normalize(r["pred_answer"]) in old_map[r["query_id"]]))
    print(f"\nFailure-mode breakdown (n={len(fails)} fails):")
    print(f"  older_fact (answer matches OUTDATED): {older}/{len(fails)}")
    print(f"  other (entity confusion / hallucination): {len(fails)-older}/{len(fails)}")

    if task == "MH":
        groups = defaultdict(list)
        for r in results:
            groups[(r["num_hops"], r["n_conflict"])].append(r)
        print(f"\n--- Per-group breakdown (MH) ---")
        print(f"{'Group':<22} {'N':>3} {'Before':>9} {'RPT-min':>9} {'Δ':>5}")
        for k in sorted(groups):
            g = groups[k]
            ng = len(g)
            b = sum(1 for r in g if r.get("exact_match_before", False))
            a = sum(1 for r in g if r["exact_match"])
            print(f"  {k[0]}-hop, {k[1]}-conflict   {ng:>3} {b:>3}/{ng} ({b/ng*100:4.0f}%) {a:>3}/{ng} ({a/ng*100:4.0f}%) {a-b:>+4}")


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")
    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    corrected = json.load(open(CORRECTED_RANKS))
    sh_results_data = json.load(open(SH_RESULTS))
    mh_results_data = json.load(open(MH_RESULTS))
    sh_labels = build_label_sets("SH")
    mh_labels = build_label_sets("MH")

    sh_an = json.load(open("/home/yhchiang/MemoryAgentBench/analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json"))
    mh_an = json.load(open("/home/yhchiang/MemoryAgentBench/analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"))
    sh_old = {e["query_id"]: (e.get("old_answer") or "").strip().lower() for e in sh_an}
    mh_old = {e["query_id"]: (e.get("old_final_answer") or "").strip().lower() for e in mh_an}

    sh_rpt_min = run_rpt_min(client, "SH", corrected["sh"], sh_results_data, SH_RETRIEVED_DIR, sh_labels)
    mh_rpt_min = run_rpt_min(client, "MH", corrected["mh"], mh_results_data, MH_RETRIEVED_DIR, mh_labels)

    json.dump(sh_rpt_min, open(OUT_DIR / "rpt_min_sh_results.json", "w"), ensure_ascii=False, indent=2)
    json.dump(mh_rpt_min, open(OUT_DIR / "rpt_min_mh_results.json", "w"), ensure_ascii=False, indent=2)

    print_summary("SH", sh_rpt_min, sh_old)
    print_summary("MH", mh_rpt_min, mh_old)
    print(f"\nSaved to {OUT_DIR}/rpt_min_{{sh,mh}}_results.json")
