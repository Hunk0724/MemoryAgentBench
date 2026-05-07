"""
Task Sim-OB - Simplified Oracle B (chain-only context).

For each FC-MH question, build a context that contains ONLY the chain's current
(GT) facts — strip every other fact (455 -> N where N is chain length).

Runs inference directly with this minimal context. No HippoRAG retrieval is
needed because we already know the chain facts from MQuAKE GT.

Goal: measure the LLM's pure multi-hop chain-reasoning ceiling under
zero-noise / zero-conflict conditions. If accuracy is near 100%, multi-hop
reasoning itself is fine and the bottleneck is conflict/noise. If <90%,
the LLM's own chain reasoning is a separate bottleneck.

Reads:
  analysis/results/mh_512_mquake_analysis.json  (per-hop gt_fact_text + gt_seq)
  outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/.../mh_6k_..._chunk512_results.json  (query text)

Writes:
  analysis/results/diagnostic/sim_ob_chain_only_results.json
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
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT = OUT_DIR / "sim_ob_chain_only_results.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# Same modified prompt as A1 / B
RAG_QA_SYSTEM = (
    "As an advanced reading comprehension assistant, your task is to analyze text passages "
    "and corresponding questions meticulously. Your response start after \"Thought: \", where "
    "you will methodically break down the reasoning process, illustrating how you arrive at "
    "conclusions step-by-step. "
    "After \"Thought: \", output a single line in the exact format "
    "\"Intermediate answers: [a, b, c]\" where the bracketed list contains your predicted "
    "entity at each reasoning hop in order (the last item being the final answer). "
    "If the question is single-hop, the list has exactly one item. "
    "Conclude with \"Answer: \" to present a concise, definitive response, devoid "
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
ONE_SHOT_INPUT = (
    ONE_SHOT_DOCS
    + "\n\nQuestion: When was Neville A. Stanton's employer founded?"
    + "\nThought: "
)
ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862."
    "\nIntermediate answers: [University of Southampton, 1862]"
    "\nAnswer: 1862."
)


def normalize(s):
    if s is None:
        return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(pred, gold):
    if pred is None or gold is None:
        return False
    if isinstance(gold, list):
        return any(fuzzy_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn:
        return False
    return pn == gn or gn in pn or pn in gn


def extract_intermediate_and_final(response_text):
    intermediates = None
    m = re.search(r"Intermediate answers:\s*\[([^\]]*)\]", response_text)
    if m:
        items = [x.strip().rstrip(".,;:!?\"'").strip() for x in m.group(1).split(",")]
        intermediates = [x for x in items if x]
    if "Answer:" in response_text:
        final = response_text.split("Answer:")[-1].strip()
    else:
        final = response_text.strip()
    return intermediates, final


def build_chain_only_context(hops):
    """
    Build a single 'Wikipedia Title:' passage containing only the N chain GT facts
    in original seq-no order. Preserves the 'serial number' framing from the
    factconsolidation prompt wrapper.
    """
    items = []
    for h in hops:
        seq = h.get("gt_seq")
        text = h.get("gt_fact_text")
        if seq is None or not text:
            continue
        items.append((seq, text))
    items.sort(key=lambda x: x[0])
    body = "\n".join(f"{seq}. {text}" for seq, text in items)
    return f"Wikipedia Title: \n{body}"


def build_messages(chain_passage, query_text):
    user_msg = f"{chain_passage}\n\nQuestion: {query_text}\nThought: "
    return [
        {"role": "system", "content": RAG_QA_SYSTEM},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user", "content": user_msg},
    ]


def call_gemini(client, messages):
    from google.genai.errors import ClientError, ServerError
    system_instruction = None
    contents = []
    for m in messages:
        if m["role"] == "system":
            system_instruction = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
    cfg = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if system_instruction:
        cfg.system_instruction = system_instruction
    for attempt in range(10):
        try:
            r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            break
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == 9:
                raise
            m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(m.group(1)) + 2 if m else min(2 ** attempt * 5, 60))
    text = r.text if r.text is not None else ""
    um = r.usage_metadata
    return text, getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)


def main():
    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    existing = []
    done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
        done = {r["query_id"] for r in existing}
        print(f"[resume] {len(done)} done")

    todo = [q for q in mh_gt if q["query_id"] not in done]
    print(f"[pending] {len(todo)}")

    if not todo:
        return existing

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, q in enumerate(todo):
        qid = q["query_id"]
        chain_passage = build_chain_only_context(q.get("hops", []))
        query_text = qmap.get(qid, "")
        gt = amap.get(qid, "")
        messages = build_messages(chain_passage, query_text)
        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0

        inter, final = extract_intermediate_and_final(raw)
        em = fuzzy_match(final, gt)

        existing.append({
            "query_id": qid,
            "num_hops": q.get("num_hops"),
            "n_conflict": sum(1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair"),
            "chain_passage": chain_passage,
            "raw_output": raw,
            "intermediate_answers": inter,
            "pred_answer": final,
            "gt_answer": gt,
            "exact_match": em,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")

    return existing


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")
    main()
