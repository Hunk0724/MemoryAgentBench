"""Plain HippoRAG-v2 inference on gemini-3.1-flash-lite-preview, full 100 MH queries.
Condition C only (original FC `rag_agent` template, no diagnostic).

Goal: backbone-swap baseline. Compare to:
  - HippoRAG gpt-4o-mini full 100: 11/100
  - RPT gemini full 100: 68/100
  - RPT-min gemini full 100: 60/100
"""
import os, json, time, sys, re
from pathlib import Path

sys.path.insert(0, '/home/yhchiang/MemoryAgentBench/analysis')
from smoke_test_diagnostic_all import (
    FC_ORIG, parse_passages_text, hippo_messages,
    extract_real_question, parse_final_answer,
)

with open('/home/yhchiang/MemoryAgentBench/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'fc-mh-494213')
os.environ.setdefault('GOOGLE_CLOUD_LOCATION', 'global')

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

BASE = Path('/home/yhchiang/MemoryAgentBench')
MODEL = "gemini-3.1-flash-lite-preview"


def call_gemini(client, messages, label, retries=8):
    sys_inst, contents = None, []
    for m in messages:
        if m["role"] == "system":
            sys_inst = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
    cfg = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=2048,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if sys_inst:
        cfg.system_instruction = sys_inst
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            return resp.text or ''
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == retries - 1:
                return f"ERROR: {e}"
            mtch = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            wait = float(mtch.group(1)) + 2 if mtch else min(2 ** attempt * 5, 60)
            time.sleep(wait)
        except Exception as e:
            return f"ERROR: {e}"
    return "ERROR: retries exhausted"


def main():
    hippo_data = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    fc_full_map = {e['query_id']: e['query'] for e in hippo_data['data']}
    gt_map = {e['query_id']: (e['answer'][0] if isinstance(e['answer'], list) else e['answer']) for e in hippo_data['data']}
    hippo_dir = BASE / 'outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512'

    client = genai.Client(
        vertexai=True,
        project=os.environ['GOOGLE_CLOUD_PROJECT'],
        location=os.environ['GOOGLE_CLOUD_LOCATION'],
    )

    out = []
    correct = 0
    t0 = time.time()
    for i, qid in enumerate(sorted(fc_full_map.keys())):
        fc_full = fc_full_map[qid]
        real_q = extract_real_question(fc_full)
        passages_text = json.load(open(hippo_dir / f'query_{qid}_context_0.json'))
        passages_list = parse_passages_text(passages_text)
        fc_orig_query = FC_ORIG.format(question=real_q)

        msgs = hippo_messages(passages_list, fc_orig_query)
        resp = call_gemini(client, msgs, f"q{qid}")
        ans = parse_final_answer(resp)
        gt = gt_map[qid]

        em = ans.lower().strip().rstrip('.,;:!?') == gt.lower().strip().rstrip('.,;:!?')
        if em:
            correct += 1
        out.append({
            'query_id': qid,
            'gt': gt,
            'pred': ans,
            'exact_match': em,
            'response': resp,
        })
        if (i + 1) % 10 == 0 or i == len(fc_full_map) - 1:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(fc_full_map)}] EM={correct}/{i+1}={correct/(i+1)*100:.1f}%, elapsed {elapsed:.0f}s", flush=True)

    out_path = BASE / 'analysis/results/zep/plain_hippo_gemini_full100.json'
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\nSaved → {out_path}")
    print(f"=== FINAL plain HippoRAG-v2 + gemini-3.1-flash-lite full 100 MH: {correct}/100 = {correct}% ===")


if __name__ == '__main__':
    main()
