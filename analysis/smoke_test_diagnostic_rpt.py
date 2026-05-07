"""Apply diagnostic (A) condition to RPT-min and RPT prompts on the 30
expanded MH targets, gemini-3.1-flash-lite-preview backbone.

Goal: validate H1+H2 by checking whether RPT-min/RPT inline marker prompts
yield ~100% LLM-side candidate-recall and high EM, AND see if diagnostic
trace remains consistent with their explicit-marker design.

Each call:
  • Wraps RPT-min / RPT prompt builder around the 30 target queries
  • Replaces the FC query body with FC_V2 (containing diagnostic spec) so
    LLM is forced to expose its trace alongside RPT marker handling
  • temp=0
"""
import os, json, time, sys, re
from pathlib import Path

sys.path.insert(0, '/home/yhchiang/MemoryAgentBench/analysis')

from smoke_test_diagnostic_all import FC_V2, FC_ORIG, extract_real_question, parse_final_answer

with open('/home/yhchiang/MemoryAgentBench/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'fc-mh-494213')
os.environ.setdefault('GOOGLE_CLOUD_LOCATION', 'global')

from pat_gemini import (
    parse_passages, annotate_passage,
    RAG_QA_SYSTEM, ONE_SHOT_INPUT, ONE_SHOT_OUTPUT,
)
from restructured_pat_gemini import (
    classify_passage,
    build_prompt as rpt_build_prompt,
)
from restructured_pat_min_gemini import (
    build_prompt as rpt_min_build_prompt,
)
from run_full_100 import build_question_index, call_gemini

from google import genai

BASE = Path('/home/yhchiang/MemoryAgentBench')


def main():
    # Load 30 targets
    targets = json.load(open(BASE / 'analysis/results/zep/smoke_test_targets_expanded.json'))
    target_qids = [t['qid'] for t in targets]

    # Question index (current_seqs / outdated_seqs per qid)
    qindex = {q['query_id']: q for q in build_question_index('mh')}

    # Hippo MH retrieval
    hippo_data = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    fc_full_map = {e['query_id']: e['query'] for e in hippo_data['data']}
    hippo_dir = BASE / 'outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512'

    client = genai.Client(
        vertexai=True,
        project=os.environ['GOOGLE_CLOUD_PROJECT'],
        location=os.environ['GOOGLE_CLOUD_LOCATION'],
    )

    out = []
    t0 = time.time()
    for i, t in enumerate(targets):
        qid = t['qid']
        q = qindex[qid]
        ctx_path = hippo_dir / f"query_{qid}_context_0.json"
        passages = parse_passages(json.load(open(ctx_path)))
        ranks_to_keep = sorted(passages.keys())

        real_q = extract_real_question(fc_full_map[qid])
        # Use FC_V2 (with diagnostic spec) as the query text
        fc_v2_query = FC_V2.format(question=real_q)
        # Also baseline with FC_ORIG
        fc_orig_query = FC_ORIG.format(question=real_q)

        rec = {**t, 'real_question': real_q}

        # RPT-min plain (FC_ORIG) + RPT-min diagnostic (FC_V2)
        msgs_orig, _, _ = rpt_min_build_prompt(passages, ranks_to_keep, fc_orig_query, q['current_seqs'], q['outdated_seqs'])
        msgs_diag, _, _ = rpt_min_build_prompt(passages, ranks_to_keep, fc_v2_query, q['current_seqs'], q['outdated_seqs'])
        try:
            resp_orig, _, _ = call_gemini(client, msgs_orig)
            time.sleep(0.5)
            resp_diag, _, _ = call_gemini(client, msgs_diag)
            time.sleep(0.5)
        except Exception as e:
            resp_orig = f"ERROR: {e}"
            resp_diag = f"ERROR: {e}"
        rec['rpt_min'] = {
            'C_original': {'response': resp_orig, 'parsed_answer': parse_final_answer(resp_orig)},
            'A_trace_first': {'response': resp_diag, 'parsed_answer': parse_final_answer(resp_diag)},
        }

        # RPT plain + RPT diagnostic
        msgs_orig, _, _ = rpt_build_prompt(passages, ranks_to_keep, fc_orig_query, q['current_seqs'], q['outdated_seqs'])
        msgs_diag, _, _ = rpt_build_prompt(passages, ranks_to_keep, fc_v2_query, q['current_seqs'], q['outdated_seqs'])
        try:
            resp_orig, _, _ = call_gemini(client, msgs_orig)
            time.sleep(0.5)
            resp_diag, _, _ = call_gemini(client, msgs_diag)
            time.sleep(0.5)
        except Exception as e:
            resp_orig = f"ERROR: {e}"
            resp_diag = f"ERROR: {e}"
        rec['rpt'] = {
            'C_original': {'response': resp_orig, 'parsed_answer': parse_final_answer(resp_orig)},
            'A_trace_first': {'response': resp_diag, 'parsed_answer': parse_final_answer(resp_diag)},
        }

        out.append(rec)
        if (i + 1) % 5 == 0 or i == len(targets) - 1:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(targets)}] elapsed {elapsed:.0f}s", flush=True)

    out_path = BASE / 'analysis/results/zep/smoke_test_rpt_diagnostic_traces.json'
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\nSaved → {out_path}")


if __name__ == '__main__':
    main()
