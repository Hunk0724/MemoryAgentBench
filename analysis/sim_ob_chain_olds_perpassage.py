"""
Mode A control — re-render chain_only_olds with per-passage Wikipedia Title format.

Tests whether the 89% Mode A acc is sensitive to user-content format. Compares:
  - Sim-OB-grad-v2 chain_only_olds (89%): single `Wikipedia Title: \n<facts>` block
  - This script:                          per-fact `Wikipedia Title: <seq>. <text>` blocks

Per-fact format matches HippoRAG-v2's actual inference user content style
(where each retrieved passage gets its own Wikipedia Title prefix and the seq
numbers come embedded in the passage content from the FC corpus).

Reads same MH GT and 455-facts file; writes:
  analysis/results/diagnostic/sim_ob_chain_olds_perpassage_results.json
"""

import json
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

BASE = Path("/home/yhchiang/MemoryAgentBench")
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
OUT = BASE / "analysis/results/diagnostic/sim_ob_chain_olds_perpassage_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# ORIG HippoRAG-v2 prompt (verbatim from methods/hipporag/prompts/templates/rag_qa_musique.py)
RAG_QA_SYSTEM = (
    "As an advanced reading comprehension assistant, your task is to analyze text passages "
    "and corresponding questions meticulously. Your response start after \"Thought: \", where "
    "you will methodically break down the reasoning process, illustrating how you arrive at "
    "conclusions. Conclude with \"Answer: \" to present a concise, definitive response, devoid "
    "of additional elaborations."
)

ONE_SHOT_DOCS = (
    "Wikipedia Title: The Last Horse\nThe Last Horse (Spanish:El último caballo) is a 1950 "
    "Spanish comedy film directed by Edgar Neville starring Fernando Fernán Gómez.\n"
    "Wikipedia Title: Southampton\nThe University of Southampton, which was founded in 1862 "
    "and received its Royal Charter as a university in 1952, has over 22,000 students. The "
    "university is ranked in the top 100 research universities in the world in the Academic "
    "Ranking of World Universities 2010.\n"
    "Wikipedia Title: Stanton Township, Champaign County, Illinois\nStanton Township is a "
    "township in Champaign County, Illinois, USA.\n"
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human "
    "Factors and Ergonomics at the University of Southampton."
)
ONE_SHOT_INPUT = ONE_SHOT_DOCS + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "
ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862. "
    "\nAnswer: 1862."
)


def normalize(s):
    if s is None: return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(pred, gold):
    if pred is None or gold is None: return False
    if isinstance(gold, list):
        return any(fuzzy_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn: return False
    return pn == gn or gn in pn or pn in gn


def extract_final(s):
    if "Answer:" in s:
        return s.split("Answer:")[-1].strip()
    return s.strip()


def load_facts():
    facts = {}
    for line in open(CONTEXT_FILE):
        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip()
    return facts


def get_chain_seqs(q):
    chain_new = []; chain_old = []
    for h in sorted(q.get("hops", []), key=lambda x: x.get("hop_idx", 0)):
        if h.get("gt_seq") is not None:
            chain_new.append(h["gt_seq"])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
            chain_old.append(h["old_seq"])
    return chain_new, chain_old


def build_prompt_user(seqs_in_order, facts, query_text):
    """Each fact gets its own 'Wikipedia Title: <seq>. <text>' block.
    Matches HippoRAG-v2's per-passage format (HippoRAG.py:458-461)."""
    body = ""
    for s in seqs_in_order:
        if s in facts:
            body += f"Wikipedia Title: {s}. {facts[s]}\n\n"
    body += f"Question: {query_text}\nThought: "
    return body


def build_messages(prompt_user):
    return [
        {"role": "system", "content": RAG_QA_SYSTEM},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user", "content": prompt_user},
    ]


def call_gemini(client, messages):
    from google.genai.errors import ClientError, ServerError
    sysp = None; contents = []
    for m in messages:
        if m["role"] == "system":
            sysp = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
    cfg = types.GenerateContentConfig(
        temperature=TEMPERATURE, max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if sysp: cfg.system_instruction = sysp
    for attempt in range(10):
        try:
            r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            break
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == 9: raise
            mret = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(mret.group(1)) + 2 if mret else min(2 ** attempt * 5, 60))
    return r.text if r.text is not None else ""


def main():
    os.chdir("/home/yhchiang/MemoryAgentBench")
    facts = load_facts()
    print(f"Loaded {len(facts)} facts")
    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    existing = []; done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
        done = {r["query_id"] for r in existing}
        print(f"[resume] {len(done)} done")

    todo = [q for q in mh_gt if q["query_id"] not in done]
    print(f"[pending] {len(todo)}")

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, q in enumerate(todo):
        qid = q["query_id"]
        chain_new, chain_old = get_chain_seqs(q)
        if not chain_new:
            continue
        # Order: chain_new first (in hop order), then chain_old (in hop order)
        # Mimics what HippoRAG might surface — "primary" facts first, alts after
        seqs = list(chain_new) + list(chain_old)
        prompt_user = build_prompt_user(seqs, facts, qmap.get(qid, ""))
        messages = build_messages(prompt_user)
        gt = amap.get(qid, "")
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid,
            "num_hops": q.get("num_hops"),
            "n_conflict": len(chain_old),
            "raw_output": raw,
            "pred_answer": extract_final(raw),
            "gt_answer": gt,
            "exact_match": em,
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


if __name__ == "__main__":
    main()
