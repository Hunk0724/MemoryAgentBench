"""
V3 decompose-first variant on OA2 fact-level filter (FC-MH).

Forces LLM to first list each reasoning hop as a sub-question before answering.

Vanilla → V3 diff:
  - SYSTEM adds 1 sentence: "Before answering, first list each reasoning hop
    as a sub-question."
  - ONE-SHOT OUTPUT adds "Sub-questions:" preamble.

Writes:
  analysis/results/diagnostic/oa2_v3_decompose_mh_results.json
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
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT = BASE / "analysis/results/diagnostic/oa2_v3_decompose_mh_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# === V3 decompose SYSTEM (vanilla + 1 sentence) ===
RAG_QA_SYSTEM = (
    "As an advanced reading comprehension assistant, your task is to analyze text passages "
    "and corresponding questions meticulously. "
    "Before answering, first list each reasoning hop of the question as a numbered sub-question. "
    "Your response start after \"Thought: \", where "
    "you will methodically break down the reasoning process, illustrating how you arrive at "
    "conclusions. Conclude with \"Answer: \" to present a concise, definitive response, devoid "
    "of additional elaborations."
)

ONE_SHOT_DOCS = (
    "Wikipedia Title: The Last Horse\nThe Last Horse (Spanish:El último caballo) is a 1950 "
    "Spanish comedy film directed by Edgar Neville starring Fernando Fernán Gómez.\n"
    "Wikipedia Title: Southampton\nThe University of Southampton, which was founded in 1862 "
    "and received its Royal Charter as a university in 1952, has over 22,000 students.\n"
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human "
    "Factors and Ergonomics at the University of Southampton."
)
ONE_SHOT_INPUT = ONE_SHOT_DOCS + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "

# === V3 ONE-SHOT OUTPUT (vanilla + Sub-questions preamble) ===
ONE_SHOT_OUTPUT = (
    "Sub-questions:\n"
    "1. Who is Neville A. Stanton's employer?\n"
    "2. When was that employer founded?\n\n"
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


def parse_passages(context_str):
    out = []
    parts = re.split(r"(Passage \d+:\n)", context_str)
    i = 0
    while i < len(parts):
        m = re.match(r"Passage (\d+):", parts[i])
        if m and i + 1 < len(parts):
            out.append((int(m.group(1)), parts[i + 1].rstrip()))
            i += 2
        else:
            i += 1
    return out


def excise_old_fact(passage_text, old_seq):
    pat = re.compile(rf"(?:(?<=^)|(?<=\s)){re.escape(str(old_seq))}\.\s")
    while True:
        m = pat.search(passage_text)
        if not m: break
        start = m.start()
        after = passage_text[m.end():]
        next_m = re.search(r"(?:(?<=\s)|(?<=^))\d+\.\s", after)
        end = m.end() + next_m.start() if next_m else len(passage_text)
        passage_text = passage_text[:start] + passage_text[end:]
    return re.sub(r"\s+", " ", passage_text).strip()


def build_messages(passages_kept, query_text):
    prompt_user = ""
    for _, doc in passages_kept:
        if doc.strip():
            prompt_user += f"Wikipedia Title: {doc}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "
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


def get_chain_olds(q):
    return [h["old_seq"] for h in q.get("hops", []) if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None]


def main():
    os.chdir("/home/yhchiang/MemoryAgentBench")
    OUT.parent.mkdir(parents=True, exist_ok=True)
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
    if not todo: return

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, q in enumerate(todo):
        qid = q["query_id"]
        chain_olds = get_chain_olds(q)
        ctx_path = RETRIEVED_DIR / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            continue
        ctx = json.load(open(ctx_path))
        passages = parse_passages(ctx)
        new_passages = []
        for rank, text in passages:
            cur = text
            for s in chain_olds:
                cur = excise_old_fact(cur, s)
            new_passages.append((rank, cur))

        messages = build_messages(new_passages, qmap.get(qid, ""))
        gt = amap.get(qid, "")
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid, "num_hops": q.get("num_hops"),
            "n_conflict": sum(1 for h in q['hops'] if h.get('conflict_type') == 'has_pair'),
            "raw_output": raw, "pred_answer": extract_final(raw),
            "gt_answer": gt, "exact_match": em,
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [V3 {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


if __name__ == "__main__":
    main()
