"""Smoke test: ask gpt-4o-mini to expose its multi-hop reasoning trace
on Zep & HippoRAG-v2 contexts for 6 representative MH queries.

Goal: understand HOW the LLM actually processes FC-MH — does it decompose,
does it detect conflicts per hop, what signal does it use to resolve?

This is exploratory; output is intended for manual inspection.
"""
import os, json, time
from pathlib import Path

with open('/home/yhchiang/MemoryAgentBench/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

from openai import OpenAI

BASE = Path('/home/yhchiang/MemoryAgentBench')

# Diagnostic prompt — wraps the original task with reasoning-trace requirement.
DIAGNOSTIC_INSTRUCTIONS = """\
Before giving the final answer, expose your reasoning step-by-step in EXACTLY this format:

[STEP 1: Decomposition]
Break the question into ordered sub-questions (hops). For each hop, state the
(entity, relation) you need to look up.
Example:
  Hop 1: Who is the spouse of X?  -> need (X, spouse)
  Hop 2: Where did <Hop1 answer> die?  -> need (<Hop1 answer>, place_of_death)

[STEP 2: Per-hop resolution]
For each hop, output:
  ## Hop N: <sub-question>
  Candidate facts found in context:
    - <fact text> | source: [FACTS / ENTITIES / EPISODES / Passage k] | signal: <date range / serial / none>
    - ... (list ALL matching candidates, even if obviously wrong)
  Conflict detected: [yes / no]
  Selected answer: <the value you carry forward>
  Resolution criterion: <which signal you used and why>

[STEP 3: Final answer]
Final Answer: <one short answer, no extra text>
"""


def build_zep_prompt(zep_record, fc_query):
    """Recreate the same compose_search_context output as Zep at inference,
    then append diagnostic instructions and FC question."""
    edges = zep_record.get('edges', [])
    nodes = zep_record.get('nodes', [])
    episodes = zep_record.get('episodes', [])
    facts = []
    for e in edges:
        valid = e.get('valid_at') or 'date unknown'
        invalid = e.get('invalid_at') or 'present'
        facts.append(f"  - {e['fact']} ({valid} - {invalid})")
    entities = [f"  - {n['name']}: {n['summary']}" for n in nodes]
    eps = [f"  - Content: {ep['content']}" for ep in episodes]
    context = f"""FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
# format: FACT (Date range: from - to)

{chr(10).join(facts)}


# These are the most relevant entities
# ENTITY_NAME: entity summary

{chr(10).join(entities)}


# These are the most relevant episodes.
# format: EPISODE

{chr(10).join(eps)}
"""
    return context, fc_query


def build_hippo_prompt(passages_text, fc_query):
    """HippoRAG context = the passages_text (already concatenated)."""
    return passages_text, fc_query


SYSTEM = "You are a helpful expert assistant answering questions from users based on the provided context."

USER_TEMPLATE = """Your task is to answer a multi-hop question. You are given the following context from the previous conversation.

CONTEXT:
{context}

{diagnostic}

QUESTION:
{question}
"""


def run_one(client, context, fc_query, label):
    user = USER_TEMPLATE.format(context=context, diagnostic=DIAGNOSTIC_INSTRUCTIONS, question=fc_query)
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"  [{label}] error attempt {attempt+1}: {e} — sleep {wait}s")
            time.sleep(wait)
    return f"ERROR after retries"


def main():
    targets = json.load(open(BASE / 'analysis/results/zep/smoke_test_targets.json'))

    # Load retrieval data
    zep_full = {r['query_id']: r for r in
                json.load(open(BASE / 'outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json'))}
    hippo_data = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    fc_query_map = {e['query_id']: e['query'] for e in hippo_data['data']}
    hippo_dir = BASE / 'outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512'

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    out = []
    for t in targets:
        qid = t['qid']
        fc_query = fc_query_map[qid]
        # Zep
        zep_ctx, _ = build_zep_prompt(zep_full[qid], fc_query)
        zep_response = run_one(client, zep_ctx, fc_query, f"q{qid} Zep")
        # HippoRAG
        hippo_passages = json.load(open(hippo_dir / f'query_{qid}_context_0.json'))
        hippo_ctx, _ = build_hippo_prompt(hippo_passages, fc_query)
        hippo_response = run_one(client, hippo_ctx, fc_query, f"q{qid} Hippo")

        rec = {
            **t,
            'zep_diagnostic': zep_response,
            'hippo_diagnostic': hippo_response,
        }
        out.append(rec)
        print(f"  q{qid} done")

    out_path = BASE / 'analysis/results/zep/smoke_test_diagnostic_traces.json'
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\nSaved → {out_path}")


if __name__ == '__main__':
    main()
