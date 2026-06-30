"""
Task Sim-OB-grad - Noise gradient sweep on Simplified Oracle B.

For each FC-MH question, build context = chain GT facts + k distractors, where
k iterates over multiple noise levels and distractors come from one of two
sources:

  (a) random   : uniformly sampled non-chain facts from the 455-fact pool
                  (length-only baseline; no semantic similarity to chain)
  (b) ppr-nearby : non-chain facts ordered by their position in the cached
                   HippoRAG retrieval (top-ranked = PPR-most-relevant);
                   simulates the realistic RAG noise distribution

Goal: find the noise tolerance threshold and separate "pure length confound"
from "semantic distractor" effects.

Reads:
  analysis/results/mh_512_mquake_analysis.json
  analysis/contexts/factconsolidation_6k_context.txt           (455 numbered facts)
  outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512/query_{qid}_context_0.json

Writes:
  analysis/results/diagnostic/sim_ob_grad_results.json   (one row per (qid, source, k))
"""

import json
import os
import random
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

BASE = Path("/home/yhchiang/MemoryAgentBench")
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT = OUT_DIR / "sim_ob_grad_results.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048
NOISE_LEVELS = [10, 50, 100, 200, 455]   # 455 means "all non-chain facts"
SOURCES = ["random", "ppr-nearby"]
SEED = 42

# Same modified prompt as Sim-OB
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


def load_facts():
    """Load 455 numbered facts: returns dict {seq: text}."""
    facts = {}
    for line in open(CONTEXT_FILE):
        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip()
    return facts


def parse_passages(context_str):
    """Parse `Passage X:\n...` into ordered list of passage texts."""
    passages = {}
    parts = re.split(r"(Passage \d+:\n)", context_str)
    i = 0
    while i < len(parts):
        m = re.match(r"Passage (\d+):", parts[i])
        if m and i + 1 < len(parts):
            passages[int(m.group(1))] = parts[i + 1].strip()
            i += 2
        else:
            i += 1
    return [passages[k] for k in sorted(passages.keys())]


def passage_to_seqs(passage_text):
    """Extract ordered list of seq numbers appearing in a passage."""
    return [int(m.group(1)) for m in re.finditer(r"(?:^|\s)(\d+)\.\s", passage_text)]


def get_ppr_ordered_seqs(qid):
    """Return seqs in PPR order (passage 1 facts first, then passage 2, etc.) from cache."""
    p = RETRIEVED_DIR / f"query_{qid}_context_0.json"
    if not p.exists():
        return []
    ctx = json.load(open(p))
    seqs = []
    for psg in parse_passages(ctx):
        seqs.extend(passage_to_seqs(psg))
    # Dedup keeping first-seen order
    seen = set()
    out = []
    for s in seqs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_messages(passage_body, query_text):
    user_msg = f"Wikipedia Title: \n{passage_body}\n\nQuestion: {query_text}\nThought: "
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


def build_passage_body(seqs_in_order, facts_dict):
    """Render selected seqs as numbered fact lines in seq-no ascending order."""
    seqs_sorted = sorted(seqs_in_order)
    return "\n".join(f"{s}. {facts_dict[s]}" for s in seqs_sorted if s in facts_dict)


def main():
    random.seed(SEED)
    facts = load_facts()
    print(f"Loaded {len(facts)} facts from 6k context")

    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    # Resume
    existing = []
    done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
        done = {(r["query_id"], r["source"], r["noise_level"]) for r in existing}
        print(f"[resume] {len(done)} configs done")

    todo = []
    for q in mh_gt:
        qid = q["query_id"]
        chain_seqs = sorted({h.get("gt_seq") for h in q.get("hops", []) if h.get("gt_seq") is not None})
        non_chain = [s for s in facts.keys() if s not in chain_seqs]
        ppr_order = get_ppr_ordered_seqs(qid)
        ppr_non_chain = [s for s in ppr_order if s not in chain_seqs]
        # Pad PPR list with the remaining non-chain seqs in arbitrary order so we can reach k=455
        seen = set(ppr_non_chain)
        for s in non_chain:
            if s not in seen:
                ppr_non_chain.append(s)
                seen.add(s)

        for source in SOURCES:
            for k in NOISE_LEVELS:
                if (qid, source, k) in done:
                    continue
                eff_k = min(k, len(non_chain))
                if source == "random":
                    rng = random.Random(SEED + qid * 1000 + k)
                    distractors = rng.sample(non_chain, eff_k)
                else:  # ppr-nearby
                    distractors = ppr_non_chain[:eff_k]
                todo.append({
                    "query_id": qid,
                    "source": source,
                    "noise_level": k,
                    "actual_k": eff_k,
                    "chain_seqs": chain_seqs,
                    "distractor_seqs": distractors,
                })

    print(f"[pending] {len(todo)} configs to run")
    if not todo:
        return existing

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, cfg in enumerate(todo):
        qid = cfg["query_id"]
        all_seqs = list(cfg["chain_seqs"]) + list(cfg["distractor_seqs"])
        body = build_passage_body(all_seqs, facts)
        query_text = qmap.get(qid, "")
        gt = amap.get(qid, "")

        messages = build_messages(body, query_text)
        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0

        inter, final = extract_intermediate_and_final(raw)
        em = fuzzy_match(final, gt)

        existing.append({
            "query_id": qid,
            "source": cfg["source"],
            "noise_level": cfg["noise_level"],
            "actual_k": cfg["actual_k"],
            "n_chain": len(cfg["chain_seqs"]),
            "n_total_facts": len(all_seqs),
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

        if (i + 1) % 20 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} {cfg['source']} k={cfg['noise_level']} "
                  f"running_acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")

    return existing


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")
    main()
