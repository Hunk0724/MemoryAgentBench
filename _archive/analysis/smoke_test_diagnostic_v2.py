"""
Smoke test v2: surgically integrate diagnostic into the FC `rag_agent`
template's middle section, while preserving 100% of the original
HippoRAG-v2 / Zep inference prompt structure.

ISOLATION GUARANTEE: this script does NOT modify any file under
methods/ utils/ or run_zep_*.py. All original templates are reproduced
LOCALLY and modified only in this script's memory.

Sources reproduced (verbatim where applicable):
  • methods/hipporag/prompts/templates/rag_qa_musique.py
      → RAG_QA_SYSTEM, ONE_SHOT_DOCS, ONE_SHOT_INPUT, ONE_SHOT_OUTPUT
  • methods/hipporag/HippoRAG.py:456-471 (qa() prompt assembly)
      → Wikipedia Title format + Question + Thought: trailer
  • methods/zep.py:10-30 (TEMPLATE), :114-129 (llm_response)
      → FACTS/ENTITIES/EPISODES sections + briefly-answer wrapper
  • utils/templates.py:81 (FC rag_agent query template)
      → with the middle section (output-constraint + one-shot example)
        SURGICALLY REPLACED by diagnostic spec; rest preserved verbatim

Output:
  analysis/results/zep/smoke_test_diagnostic_v2_traces.json
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

# ─── DIAGNOSTIC SPEC (replaces FC template's middle section) ────────────────
# Replaces from "You should give a very concise answer..." through the
# "For example: ... Answer: Donald Trump" block, but BEFORE the
# "Now Answer the Question:" line.
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

# ─── FC `rag_agent` template — LOCAL COPY with surgical replacement ─────────
# Original from utils/templates.py:81. KEEP the conflict-resolution rule
# at the top and the question-wrapping at the bottom; REPLACE the middle
# (output-constraint + one-shot example) with DIAGNOSTIC_SPEC.
# Per user feedback: pull "rather than the real facts in real world" into
# the final question line so the world-knowledge-aversion constraint is
# preserved even after dropping the original output-constraint sentence.
FC_TEMPLATE_V2 = (
    "Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. \n"
    "You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. "
    + DIAGNOSTIC_SPEC
    + "\nNow Answer the Question: Based on the provided Knowledge Pool you have memorized rather than the real facts in real world, {question} \nAnswer:"
)

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
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human Factors and Ergonomics at the University of Southampton. ... He has also helped organisations design new human-machine interfaces, such as the Adaptive Cruise Control system for Jaguar Cars.\n"
    "Wikipedia Title: Finding Nemo\nFinding Nemo Theatrical release poster Directed by Andrew Stanton ... Box office $$940.3 million"
)
HIPPO_ONE_SHOT_INPUT = (
    HIPPO_ONE_SHOT_DOCS
    + "\n\nQuestion: When was Neville A. Stanton's employer founded?"
    + "\nThought: "
)
HIPPO_ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862. "
    "\nAnswer: 1862."
)

# ─── Zep originals (verbatim from methods/zep.py) ───────────────────────────
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
def build_hippo_messages(passages_text, fc_v2_query):
    """Reproduce HippoRAG.qa() prompt with v2 FC template substituted in
    place of the original FC rag_agent template.

    passages_text: raw saved retrieval string ("Passage 1:\n...Passage 2:\n...")
    fc_v2_query: full v2 FC template wrapped query string
    """
    # parse "Passage k:" segments to extract individual passage texts
    import re
    parts = re.split(r'Passage \d+:\n', passages_text)
    passages = [p.strip() for p in parts if p.strip()]
    prompt_user = ''
    for passage in passages:
        prompt_user += f'Wikipedia Title: {passage}\n\n'
    prompt_user += 'Question: ' + fc_v2_query + '\nThought: '
    return [
        {"role": "system", "content": HIPPO_RAG_QA_SYSTEM},
        {"role": "user", "content": HIPPO_ONE_SHOT_INPUT},
        {"role": "assistant", "content": HIPPO_ONE_SHOT_OUTPUT},
        {"role": "user", "content": prompt_user},
    ]


def build_zep_context(zep_record):
    """Reproduce compose_search_context output."""
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
    return ZEP_TEMPLATE.format(
        facts='\n'.join(facts),
        entities='\n'.join(entities),
        episodes='\n'.join(eps),
    )


def build_zep_messages(zep_record, fc_v2_query):
    context = build_zep_context(zep_record)
    user_prompt = ZEP_USER_WRAP.format(context=context, question=fc_v2_query)
    return [
        {"role": "system", "content": ZEP_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]


def fc_v2_wrap(real_question):
    """Wrap a real factconsolidation question with the v2 FC template."""
    return FC_TEMPLATE_V2.format(question=real_question)


def extract_real_question(fc_query_full):
    """The hippo['data'][i]['query'] field is already the full FC template
    wrapped query. Extract just the real question portion (after 'Now Answer
    the Question: Based on the provided Knowledge Pool, ' and before the
    final '\\nAnswer:')."""
    marker = 'Now Answer the Question: Based on the provided Knowledge Pool, '
    idx = fc_query_full.rfind(marker)
    if idx == -1:
        return fc_query_full  # fallback
    tail = fc_query_full[idx + len(marker):]
    if tail.endswith('\nAnswer:'):
        tail = tail[:-len('\nAnswer:')]
    return tail.strip()


# ─── LLM call ───────────────────────────────────────────────────────────────
def call_llm(client, messages, label):
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=messages,
            )
            return resp.choices[0].message.content
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"  [{label}] error attempt {attempt+1}: {e} — sleep {wait}s")
            time.sleep(wait)
    return f"ERROR after retries"


def main():
    targets = json.load(open(BASE / 'analysis/results/zep/smoke_test_targets.json'))

    zep_full = {r['query_id']: r for r in
                json.load(open(BASE / 'outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json'))}
    hippo_data = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    fc_query_map = {e['query_id']: e['query'] for e in hippo_data['data']}
    hippo_dir = BASE / 'outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512'

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    out = []
    for t in targets:
        qid = t['qid']
        # Get real question from the saved FC query
        fc_full = fc_query_map[qid]
        real_q = extract_real_question(fc_full)
        # Wrap with v2 FC template
        fc_v2_query = fc_v2_wrap(real_q)

        # HippoRAG
        passages_text = json.load(open(hippo_dir / f'query_{qid}_context_0.json'))
        hippo_msgs = build_hippo_messages(passages_text, fc_v2_query)
        hippo_resp = call_llm(client, hippo_msgs, f"q{qid} Hippo")

        # Zep
        zep_msgs = build_zep_messages(zep_full[qid], fc_v2_query)
        zep_resp = call_llm(client, zep_msgs, f"q{qid} Zep")

        out.append({
            **t,
            'real_question': real_q,
            'fc_v2_template_used': fc_v2_query,
            'hippo_diagnostic': hippo_resp,
            'zep_diagnostic': zep_resp,
        })
        print(f"  q{qid} done")

    out_path = BASE / 'analysis/results/zep/smoke_test_diagnostic_v2_traces.json'
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
    print(f"\nSaved → {out_path}")

    # Print the v2 prompt structure once for verification
    print("\n" + "=" * 70)
    print("V2 FC TEMPLATE (ready for review)")
    print("=" * 70)
    sample = fc_v2_wrap("<example real question here>")
    print(sample)
    print("=" * 70)


if __name__ == '__main__':
    main()
