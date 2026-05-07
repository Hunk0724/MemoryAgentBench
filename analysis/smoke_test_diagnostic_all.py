"""
Smoke test all-three-conditions: run (A) trace-first, (B) answer-then-explain,
(C) pure-original-thought on 6 MH targets × 2 methods (HippoRAG / Zep).

ISOLATION: all original templates reproduced LOCALLY; no edits to source files.

Conditions:
  (C) ORIGINAL: original FC `rag_agent` template, original method-specific
      outer prompt (HippoRAG: rag_qa_musique with Thought:/Answer:; Zep:
      llm_response wrapper with FACTS/ENTITIES/EPISODES). Look at LLM's
      spontaneous Thought-block reasoning.

  (A) TRACE_FIRST: same as v2 — replace FC template's middle section
      (output-constraint + Donald Trump example) with diagnostic spec
      forcing Evidence/Reasoning chain/Answer trace BEFORE answer.

  (B) ANSWER_FIRST: 2-pass.
        Pass-1 = (C) — get the answer with no diagnostic perturbation.
        Pass-2 = "you answered X. Now explain step-by-step what you
                  found and how you decided" — post-hoc rationalization.

Output: analysis/results/zep/smoke_test_all_traces.json
"""
import os, json, time, re
from pathlib import Path

with open('/home/yhchiang/MemoryAgentBench/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

from openai import OpenAI

BASE = Path('/home/yhchiang/MemoryAgentBench')

# ─── ORIGINAL FC `rag_agent` template (verbatim from utils/templates.py:81) ─
FC_ORIG = (
    "Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. \n"
    " You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. "
    "You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. \n\n"
    "For example:\n\n"
    " [Knowledge Pool] \n\n"
    " Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? \n"
    "Answer: Donald Trump \n\n"
    " Now Answer the Question: Based on the provided Knowledge Pool, {question} \n"
    "Answer:"
)

# ─── DIAGNOSTIC SPEC (replaces FC middle section in condition A) ────────────
DIAGNOSTIC_SPEC = """\
Before producing the final answer, you MUST output a structured trace so a
reviewer can audit (A) what you found in context, (B) how you resolved any
conflict per hop, (C) how you chained hops to the final answer.

The trace MUST follow this exact format:

Evidence:
  Hop 1 (entity, relation): <pair>
    Candidates found in context (list ALL matches, including conflicting
    versions; do NOT pre-filter):
      - <fact text> | source: <Passage k or FACTS/ENTITIES/EPISODES> | seq: <number-if-any> | date-range: <if-any>
      - <other matching fact>
    Conflict among candidates: yes/no
    Selected: <value>
    Signal used: <serial-number / date-range / none>
    Criterion: <e.g., "larger serial number" / "later valid_at" / "fallback">
  Hop 2 (entity, relation): <pair>
    ... (same format)
  ... (one block per hop)

Reasoning chain:
  Hop 1 selected: <X1>
  Hop 2 lookup: (X1, <relation>) -> <X2>
  ... (show how each hop feeds the next)
  Final: <answer>

After the trace, output a single line:
Answer: <one short answer, no extra text>
"""

FC_V2 = (
    "Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. \n"
    "You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. "
    + DIAGNOSTIC_SPEC
    + "\nNow Answer the Question: Based on the provided Knowledge Pool you have memorized rather than the real facts in real world, {question} \nAnswer:"
)

# ─── Pass-2 explain prompt (condition B) ────────────────────────────────────
EXPLAIN_PROMPT = """\
You previously answered "{prior_answer}" to the question:

  {real_question}

Using the SAME context above, retrospectively explain step by step:

(A) What candidate facts did you find for each hop? List ALL matching facts
    in the context, including any conflicting versions you saw. Cite source
    location.
(B) For each hop, did you see a conflict? Which signal did you use to
    resolve it (serial number / date range / none / world knowledge / other)?
(C) How did you chain the hops to arrive at "{prior_answer}"?

Format:
Evidence:
  Hop 1: <facts found>
  ...
Reasoning chain:
  Hop 1 -> ... -> Final
Justification: <why your answer is correct given the rules above>
"""

# ─── HippoRAG-v2 originals (verbatim from rag_qa_musique.py) ────────────────
HIPPO_RAG_QA_SYSTEM = (
    'As an advanced reading comprehension assistant, your task is to analyze text passages and corresponding questions meticulously. '
    'Your response start after "Thought: ", where you will methodically break down the reasoning process, illustrating how you arrive at conclusions. '
    'Conclude with "Answer: " to present a concise, definitive response, devoid of additional elaborations.'
)
HIPPO_ONE_SHOT_DOCS = (
    "Wikipedia Title: The Last Horse\nThe Last Horse (Spanish:El último caballo) is a 1950 Spanish comedy film directed by Edgar Neville starring Fernando Fernán Gómez.\n"
    "Wikipedia Title: Southampton\nThe University of Southampton, which was founded in 1862 and received its Royal Charter as a university in 1952, has over 22,000 students. The university is ranked in the top 100 research universities in the world in the Academic Ranking of World Universities 2010. In 2010, the THES - QS World University Rankings positioned the University of Southampton in the top 80 universities in the world. The university considers itself one of the top 5 research universities in the UK. The university has a global reputation for research into engineering sciences, oceanography, chemistry, cancer sciences, sound and vibration research, computer science and electronics, optoelectronics and textile conservation at the Textile Conservation Centre (which is due to close in October 2009.) It is also home to the National Oceanography Centre, Southampton (NOCS), the focus of Natural Environment Research Council-funded marine research.\n"
    "Wikipedia Title: Stanton Township, Champaign County, Illinois\nStanton Township is a township in Champaign County, Illinois, USA. As of the 2010 census, its population was 505 and it contained 202 housing units.\n"
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human Factors and Ergonomics at the University of Southampton.\n"
    "Wikipedia Title: Finding Nemo\nFinding Nemo Theatrical release poster Directed by Andrew Stanton ..."
)
HIPPO_ONE_SHOT_INPUT = HIPPO_ONE_SHOT_DOCS + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "
HIPPO_ONE_SHOT_OUTPUT = "The employer of Neville A. Stanton is University of Southampton. The University of Southampton was founded in 1862. \nAnswer: 1862."

# ─── Zep originals ──────────────────────────────────────────────────────────
ZEP_TEMPLATE = """
FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
# format: FACT (Date range: from - to)

{facts}


# These are the most relevant entities
# ENTITY_NAME: entity summary

{entities}


# These are the most relevant episodes.
# format: EPISODE

{episodes}

"""
ZEP_SYSTEM = "You are a helpful expert assistant answering questions from users based on the provided context."
ZEP_USER_WRAP = """
            Your task is to briefly answer the question. You are given the following context from the previous conversation. If you don't know how to answer the question, abstain from answering.

                {context}


                {question}


            Answer:
            """


# ─── Builders ───────────────────────────────────────────────────────────────
def parse_passages_text(text):
    parts = re.split(r'Passage \d+:\n', text)
    return [p.strip() for p in parts if p.strip()]


def build_zep_context(zep_record):
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
    return ZEP_TEMPLATE.format(facts='\n'.join(facts), entities='\n'.join(entities), episodes='\n'.join(eps))


def hippo_messages(passages_list, fc_query):
    prompt_user = ''
    for p in passages_list:
        prompt_user += f'Wikipedia Title: {p}\n\n'
    prompt_user += 'Question: ' + fc_query + '\nThought: '
    return [
        {"role": "system", "content": HIPPO_RAG_QA_SYSTEM},
        {"role": "user", "content": HIPPO_ONE_SHOT_INPUT},
        {"role": "assistant", "content": HIPPO_ONE_SHOT_OUTPUT},
        {"role": "user", "content": prompt_user},
    ]


def zep_messages(zep_record, fc_query):
    ctx = build_zep_context(zep_record)
    return [
        {"role": "system", "content": ZEP_SYSTEM},
        {"role": "user", "content": ZEP_USER_WRAP.format(context=ctx, question=fc_query)},
    ]


def hippo_messages_passB(passages_list, real_question, prior_answer):
    """Pass-2 of condition B for HippoRAG: same context, ask retrospective explanation."""
    prompt_user = ''
    for p in passages_list:
        prompt_user += f'Wikipedia Title: {p}\n\n'
    prompt_user += 'Original Question: ' + real_question + '\n\n'
    prompt_user += EXPLAIN_PROMPT.format(prior_answer=prior_answer, real_question=real_question)
    # No Thought: trailer because we want it to follow our format.
    return [
        {"role": "system", "content": HIPPO_RAG_QA_SYSTEM},
        {"role": "user", "content": prompt_user},
    ]


def zep_messages_passB(zep_record, real_question, prior_answer):
    ctx = build_zep_context(zep_record)
    user = (
        ctx
        + "\n\nOriginal Question: " + real_question + "\n\n"
        + EXPLAIN_PROMPT.format(prior_answer=prior_answer, real_question=real_question)
    )
    return [
        {"role": "system", "content": ZEP_SYSTEM},
        {"role": "user", "content": user},
    ]


def extract_real_question(fc_query_full):
    marker = 'Now Answer the Question: Based on the provided Knowledge Pool, '
    idx = fc_query_full.rfind(marker)
    if idx == -1:
        return fc_query_full
    tail = fc_query_full[idx + len(marker):]
    if tail.endswith('\nAnswer:'):
        tail = tail[:-len('\nAnswer:')]
    return tail.strip()


def parse_final_answer(text):
    """Extract the LLM's final answer for parsing EM."""
    if 'Answer:' in text:
        # Last "Answer:" wins (after Thought block etc.)
        return text.rsplit('Answer:', 1)[-1].strip().split('\n')[0].strip().rstrip('.')
    return text.strip().split('\n')[0].strip().rstrip('.')


def call_llm(client, messages, label, retries=5):
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=messages,
            )
            return resp.choices[0].message.content
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"  [{label}] error attempt {attempt+1}: {e}; sleep {wait}s")
            time.sleep(wait)
    return f"ERROR after retries"


def main():
    targets = json.load(open(BASE / 'analysis/results/zep/smoke_test_targets.json'))
    zep_full = {r['query_id']: r for r in
                json.load(open(BASE / 'outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json'))}
    hippo_data = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    fc_full_map = {e['query_id']: e['query'] for e in hippo_data['data']}
    hippo_dir = BASE / 'outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512'

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    out = []
    for t in targets:
        qid = t['qid']
        fc_full = fc_full_map[qid]
        real_q = extract_real_question(fc_full)
        passages_text = json.load(open(hippo_dir / f'query_{qid}_context_0.json'))
        passages_list = parse_passages_text(passages_text)

        # Build FC queries for conditions C and A
        fc_orig_query = FC_ORIG.format(question=real_q)
        fc_v2_query = FC_V2.format(question=real_q)

        rec = {**t, 'real_question': real_q}

        # ─ HippoRAG ─
        # (C) Original
        msgs_C = hippo_messages(passages_list, fc_orig_query)
        resp_C = call_llm(client, msgs_C, f"q{qid} hippo C")
        ans_C = parse_final_answer(resp_C)
        # (A) Trace-first
        msgs_A = hippo_messages(passages_list, fc_v2_query)
        resp_A = call_llm(client, msgs_A, f"q{qid} hippo A")
        ans_A = parse_final_answer(resp_A)
        # (B) Pass-2 explain (using ans_C as prior)
        msgs_B = hippo_messages_passB(passages_list, real_q, ans_C)
        resp_B = call_llm(client, msgs_B, f"q{qid} hippo B")
        rec['hippo'] = {
            'C_original': {'response': resp_C, 'parsed_answer': ans_C},
            'A_trace_first': {'response': resp_A, 'parsed_answer': ans_A},
            'B_post_hoc': {'response': resp_B, 'prior_answer': ans_C},
        }

        # ─ Zep ─
        msgs_C = zep_messages(zep_full[qid], fc_orig_query)
        resp_C = call_llm(client, msgs_C, f"q{qid} zep C")
        ans_C = parse_final_answer(resp_C)
        msgs_A = zep_messages(zep_full[qid], fc_v2_query)
        resp_A = call_llm(client, msgs_A, f"q{qid} zep A")
        ans_A = parse_final_answer(resp_A)
        msgs_B = zep_messages_passB(zep_full[qid], real_q, ans_C)
        resp_B = call_llm(client, msgs_B, f"q{qid} zep B")
        rec['zep'] = {
            'C_original': {'response': resp_C, 'parsed_answer': ans_C},
            'A_trace_first': {'response': resp_A, 'parsed_answer': ans_A},
            'B_post_hoc': {'response': resp_B, 'prior_answer': ans_C},
        }

        out.append(rec)
        print(f"  q{qid} done")

    out_path = BASE / 'analysis/results/zep/smoke_test_all_traces.json'
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\nSaved → {out_path}")


if __name__ == '__main__':
    main()
