"""Run conditions (C) original + (A) trace-first on 30 expanded targets
× 2 methods (HippoRAG, Zep) = 120 calls. Skip (B) since rationalization
already validated on small sample.

Reuses templates and builders from smoke_test_diagnostic_all.py.
"""
import os, json, time, sys
from pathlib import Path

sys.path.insert(0, '/home/yhchiang/MemoryAgentBench/analysis')
from smoke_test_diagnostic_all import (
    FC_ORIG, FC_V2,
    parse_passages_text, build_zep_context,
    hippo_messages, zep_messages,
    extract_real_question, parse_final_answer, call_llm,
)

with open('/home/yhchiang/MemoryAgentBench/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

from openai import OpenAI

BASE = Path('/home/yhchiang/MemoryAgentBench')


def main():
    targets = json.load(open(BASE / 'analysis/results/zep/smoke_test_targets_expanded.json'))
    zep_full = {r['query_id']: r for r in
                json.load(open(BASE / 'outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json'))}
    hippo_data = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    fc_full_map = {e['query_id']: e['query'] for e in hippo_data['data']}
    hippo_dir = BASE / 'outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512'

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    out = []
    t0 = time.time()
    for i, t in enumerate(targets):
        qid = t['qid']
        fc_full = fc_full_map[qid]
        real_q = extract_real_question(fc_full)
        passages_text = json.load(open(hippo_dir / f'query_{qid}_context_0.json'))
        passages_list = parse_passages_text(passages_text)
        fc_orig_query = FC_ORIG.format(question=real_q)
        fc_v2_query = FC_V2.format(question=real_q)

        rec = {**t, 'real_question': real_q}

        # HippoRAG C + A
        msgs_C = hippo_messages(passages_list, fc_orig_query)
        resp_C = call_llm(client, msgs_C, f"q{qid} hippo C")
        msgs_A = hippo_messages(passages_list, fc_v2_query)
        resp_A = call_llm(client, msgs_A, f"q{qid} hippo A")
        rec['hippo'] = {
            'C_original': {'response': resp_C, 'parsed_answer': parse_final_answer(resp_C)},
            'A_trace_first': {'response': resp_A, 'parsed_answer': parse_final_answer(resp_A)},
        }
        # Zep C + A
        msgs_C = zep_messages(zep_full[qid], fc_orig_query)
        resp_C = call_llm(client, msgs_C, f"q{qid} zep C")
        msgs_A = zep_messages(zep_full[qid], fc_v2_query)
        resp_A = call_llm(client, msgs_A, f"q{qid} zep A")
        rec['zep'] = {
            'C_original': {'response': resp_C, 'parsed_answer': parse_final_answer(resp_C)},
            'A_trace_first': {'response': resp_A, 'parsed_answer': parse_final_answer(resp_A)},
        }
        out.append(rec)
        elapsed = time.time() - t0
        if (i + 1) % 5 == 0 or i == len(targets) - 1:
            print(f"  [{i+1}/{len(targets)}] elapsed {elapsed:.0f}s", flush=True)

    out_path = BASE / 'analysis/results/zep/smoke_test_expanded_traces.json'
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\nSaved → {out_path}")


if __name__ == '__main__':
    main()
