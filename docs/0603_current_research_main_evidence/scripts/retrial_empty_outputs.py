"""
Re-trial the empty-output FC-SH queries (thinking-budget artifact).
Replays the EXACT stored inference prompt (system_prompt + '\n\n' + user_message
from the retrieval json) via the same Vertex Gemini call as agent._answer_with_client.
  setting A = SAME as run: max_output_tokens=10, temp=0, no thinking_config (High thinking)
  setting B = larger budget: max_output_tokens=2048 (decouples thinking from answer)
to reveal whether the underlying answer is correct (artifact suppressed it) or wrong.
"""
import os, json, sys
from google import genai
from google.genai import types
RR="outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware_l2_32k/k_100/factconsolidation_sh_32k/chunksize_512"
GT={q["query_id"]:q for q in json.load(open("analysis/results/sh_32k_RUN_gt.json"))}
client=genai.Client(vertexai=True, project=os.environ['GOOGLE_CLOUD_PROJECT'], location=os.environ['GOOGLE_CLOUD_LOCATION'])
def run(prompt, max_tok):
    r=client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=max_tok, temperature=0))
    fr=r.candidates[0].finish_reason if r.candidates else None
    ct=getattr(r.usage_metadata,'candidates_token_count',0) or 0
    tt=getattr(r.usage_metadata,'thoughts_token_count',0) or 0
    return (r.text or ''), fr, ct, tt
for qid in [7,33,51]:
    rj=json.load(open(f"{RR}/query_{qid}_context_0.json"))
    prompt=rj["system_prompt"]+"\n\n"+rj["user_message"]
    gtans=GT[qid]["gt_answer"]
    print("="*70); print(f"qid{qid}  gt_answer={gtans!r}  (orig output='')")
    print("  [A same-setting max_tok=10] x3:")
    for i in range(3):
        t,fr,ct,tt=run(prompt,10); print(f"    trial{i}: text={t!r} finish={fr} ans_tok={ct} thought_tok={tt}")
    print("  [B large-budget max_tok=2048] x1:")
    t,fr,ct,tt=run(prompt,2048); print(f"    text={t!r} finish={fr} ans_tok={ct} thought_tok={tt}")
