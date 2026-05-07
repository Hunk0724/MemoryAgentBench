"""
Run PAT / RPT / RPT-min inference on the FULL 100 questions per task
(not just Oracle A's usable subset), tagged with `status` for grouped analysis.

Output:
  analysis/results/oracle_a_gemini/<method>_full_{sh,mh}_results.json
  e.g. pat_full_sh_results.json, rpt_full_mh_results.json, rpt_min_full_sh_results.json

Each entry carries the `status` field so we can group post-hoc:
  - different_passage   (was Oracle A "usable")
  - same_passage        (new/old facts in same chunk)
  - retrieval_missing   (GT or Old not in top-10)
  - no_conflict_pair    (SH only; no has_pair to begin with)

Usage:
    python analysis/run_full_100.py --method pat --task sh
    python analysis/run_full_100.py --method rpt --task mh
    python analysis/run_full_100.py --method rpt_min --task sh
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from collections import Counter
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

sys.path.insert(0, str(Path(__file__).parent))
from pat_gemini import (
    parse_passages, annotate_passage,
    RAG_QA_SYSTEM, ONE_SHOT_INPUT, ONE_SHOT_OUTPUT,
    PAT_INSTRUCTION,
    extract_answer, normalize, exact_match,
    SH_RESULTS, MH_RESULTS, SH_RETRIEVED_DIR, MH_RETRIEVED_DIR,
)
from restructured_pat_gemini import (
    classify_passage,
    build_prompt as rpt_build_prompt,
)
from restructured_pat_min_gemini import (
    build_prompt as rpt_min_build_prompt,
    RPT_MIN_INSTRUCTION,
)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

BASE = Path("/home/yhchiang/MemoryAgentBench")
CORRECTED_RANKS = BASE / "analysis/results/oracle_a_gemini/corrected_ranks.json"
SH_ANALYSIS = BASE / "analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json"
MH_ANALYSIS = BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"
OUT_DIR = BASE / "analysis/results/oracle_a_gemini"


# ── status normalization → 3 broad groups + no_conflict_pair (SH-only) ─────────
def map_status_to_group(raw_status: str) -> str:
    """Map phase-1 status string to one of:
       different_passage / same_passage / retrieval_missing.
    """
    s = (raw_status or "").lower()
    if s == "usable":
        return "different_passage"
    if "same_passage" in s:
        return "same_passage"
    # gt_not_retrieved / old_not_all_found / gt_not_safe / both_missing / etc.
    return "retrieval_missing"


# ── Build per-question (current_seqs, outdated_seqs, status, gt_answer) ────────
def build_question_index(task: str):
    """Return list of dicts:
       [{query_id, gt_answer, current_seqs, outdated_seqs, status, group, ...}]
       covering ALL 100 questions of the task.
    """
    if task == "sh":
        analysis = json.load(open(SH_ANALYSIS))
        corrected = json.load(open(CORRECTED_RANKS))['sh']
        corrected_by_q = {e['query_id']: e for e in corrected}

        out = []
        for e in analysis:
            qid = e['query_id']
            gt_answer = e.get('gt_answer', '')
            ct = e.get('conflict_type')

            # current and outdated seq sets
            curr = {e['gt_seq']} if e.get('gt_seq') is not None else set()
            old  = {e['old_seq']} if e.get('old_seq') is not None else set()

            corr = corrected_by_q.get(qid)
            if ct == 'no_conflict_pair':
                status = 'no_conflict_pair'
                group = 'no_conflict_pair'
            elif corr:
                status = corr['status']
                group = map_status_to_group(status)
            else:
                # has_pair but missing from corrected (shouldn't happen; defensive)
                status = 'unknown'
                group = 'retrieval_missing'

            out.append({
                'query_id': qid,
                'gt_answer': gt_answer,
                'current_seqs': curr,
                'outdated_seqs': old,
                'conflict_type': ct,
                'status': status,
                'group': group,
                'mquake_em_before': bool(e.get('exact_match', False)),
            })
        return out

    else:  # mh
        analysis = json.load(open(MH_ANALYSIS))
        corrected = json.load(open(CORRECTED_RANKS))['mh']
        corrected_by_q = {e['query_id']: e for e in corrected}

        out = []
        for e in analysis:
            qid = e['query_id']
            gt_answer = e.get('gt_answer', '')

            curr, old = set(), set()
            for h in e['hops']:
                if h.get('gt_seq') is not None:
                    curr.add(h['gt_seq'])
                if h.get('old_seq') is not None:
                    old.add(h['old_seq'])

            corr = corrected_by_q.get(qid)
            if corr:
                status = corr['status']
                group = map_status_to_group(status)
            else:
                status = 'unknown'
                group = 'retrieval_missing'

            out.append({
                'query_id': qid,
                'gt_answer': gt_answer,
                'current_seqs': curr,
                'outdated_seqs': old,
                'conflict_type': 'has_pair',  # all MH usable subset is has_pair
                'status': status,
                'group': group,
                'num_hops': e.get('num_hops'),
                # pull n_conflict from corrected if available
                'n_conflict': corr.get('n_conflict') if corr else None,
                'mquake_em_before': bool(e.get('exact_match', False)),
            })
        return out


# ── Prompt builders for each method ────────────────────────────────────────────
def pat_build_prompt(passages_dict, ranks_to_keep, query_text, current_seqs, outdated_seqs):
    """PAT: vanilla skeleton + leading PAT_INSTRUCTION + fact-level annotation."""
    prompt_user = PAT_INSTRUCTION
    for r in ranks_to_keep:
        ann = annotate_passage(passages_dict[r], current_seqs, outdated_seqs)
        prompt_user += f"Wikipedia Title: {ann}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "
    return [
        {"role": "system",    "content": RAG_QA_SYSTEM},
        {"role": "user",      "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user",      "content": prompt_user},
    ]


METHODS = {
    'pat': lambda P, R, Q, C, O: pat_build_prompt(P, R, Q, C, O),
    'rpt': lambda P, R, Q, C, O: rpt_build_prompt(P, R, Q, C, O)[0],
    'rpt_min': lambda P, R, Q, C, O: rpt_min_build_prompt(P, R, Q, C, O)[0],
}


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


def run(method: str, task: str):
    assert method in METHODS, f"unknown method: {method}"
    assert task in ('sh', 'mh'), f"unknown task: {task}"

    print(f"\n{'='*60}\n{method.upper()} × {task.upper()} — full 100 questions\n{'='*60}")

    # Load resources
    if task == 'sh':
        retrieved_dir = SH_RETRIEVED_DIR
        results_data = json.load(open(SH_RESULTS))
    else:
        retrieved_dir = MH_RETRIEVED_DIR
        results_data = json.load(open(MH_RESULTS))
    query_map = {e['query_id']: e['query'] for e in results_data['data']}
    em_before_map = {e['query_id']: bool(e.get('exact_match', False)) for e in results_data['data']}

    questions = build_question_index(task)
    print(f"  Loaded {len(questions)} questions")
    grp_count = Counter(q['group'] for q in questions)
    for g, n in grp_count.items():
        print(f"    group={g:<22} n={n}")

    # Init Gemini client
    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    builder = METHODS[method]

    # Run inference
    results = []
    correct_overall = 0
    for i, q in enumerate(questions):
        qid = q['query_id']
        gt = q['gt_answer']
        query_text = query_map.get(qid, "")
        if not query_text:
            print(f"  WARN q{qid}: no query text")
            continue

        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        passages = parse_passages(json.load(open(ctx_path)))
        ranks_to_keep = sorted(passages.keys())  # all 10

        messages = builder(passages, ranks_to_keep, query_text,
                           q['current_seqs'], q['outdated_seqs'])

        try:
            raw, ptok, ctok = call_gemini(client, messages)
            pred = extract_answer(raw)
        except Exception as e:
            print(f"  q{qid} API error: {e}")
            raw = f"ERROR: {e}"
            pred = ""
            ptok = ctok = 0

        em = exact_match(pred, gt)
        if em:
            correct_overall += 1

        rec = {
            'query_id': qid,
            'gt_answer': gt,
            'pred_answer': pred,
            'raw_output': raw,
            'exact_match': em,
            'exact_match_before': em_before_map.get(qid, False),
            'group': q['group'],
            'status': q['status'],
            'conflict_type': q['conflict_type'],
            'n_current_facts_marked': len(q['current_seqs']),
            'n_outdated_facts_marked': len(q['outdated_seqs']),
            'prompt_tokens': ptok,
            'completion_tokens': ctok,
        }
        if task == 'mh':
            rec['num_hops'] = q.get('num_hops')
            rec['n_conflict'] = q.get('n_conflict')
        results.append(rec)

        if (i + 1) % 20 == 0 or i == len(questions) - 1:
            n = i + 1
            print(f"    [{n}/{len(questions)}] Acc so far: {correct_overall}/{n} = {correct_overall/n*100:.1f}%")

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{method}_full_{task}_results.json"
    json.dump(results, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\n  Saved → {out_path}")

    # Per-group summary
    print(f"\n  --- per-group breakdown ---")
    print(f"  {'group':<22} {'n':>3} {'EM':>6}")
    for g in sorted(set(r['group'] for r in results)):
        rs = [r for r in results if r['group'] == g]
        em = sum(1 for r in rs if r['exact_match'])
        print(f"  {g:<22} {len(rs):>3} {em}/{len(rs)}={em/len(rs)*100:.1f}%")
    print(f"  {'OVERALL':<22} {len(results):>3} {correct_overall}/{len(results)}={correct_overall/len(results)*100:.1f}%")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--method', choices=['pat', 'rpt', 'rpt_min'], required=True)
    ap.add_argument('--task', choices=['sh', 'mh'], required=True)
    args = ap.parse_args()
    os.chdir("/home/yhchiang/MemoryAgentBench")
    run(args.method, args.task)
