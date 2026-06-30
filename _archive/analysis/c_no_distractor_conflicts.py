"""
Task C - MH without distractor conflicts.

For each FC-MH question, build context = full 6k context BUT remove all
"non-chain old facts" (old facts whose new versions are NOT on this question's
chain). Keep:
  - All NEWEST facts (whether on chain or not)
  - The chain's has_conflict OLD facts (so the question's own conflicts are
    preserved — Oracle A would have removed these too, this is the difference)
  - Remove non-chain OLD facts (i.e. old versions of facts not in this chain)

Goal: distinguish whether query-irrelevant conflicts are interfering noise or
harmless background. If accuracy >> baseline -> non-chain conflicts DO mislead
the LLM (it gets pulled toward arbitrary old answers it shouldn't care about).
If accuracy ≈ Oracle A -> only query-relevant conflict matters.

Method to identify "old" facts globally:
  A fact at seq=S is OLD if there exists another fact in the 455-context
  with the SAME (subject + predicate) but at seq>S. We approximate
  (subject + predicate) by stripping the trailing object phrase from each
  fact's text — but we don't have a clean parse, so instead we use the
  union of `old_seq` values across ALL 100 questions' has_pair hops as the
  global old-fact set. This is incomplete but covers all olds that any test
  question cares about — the only "non-chain olds" we miss are ones that no
  test question references, i.e. truly inert background.

Reads:
  analysis/results/mh_512_mquake_analysis.json     (per-question chain old_seq)
  analysis/contexts/factconsolidation_6k_context.txt   (455 numbered facts)

Writes:
  analysis/results/diagnostic/c_no_distractor_conflicts_results.json
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
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT = OUT_DIR / "c_no_distractor_conflicts_results.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# Same modified prompt
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
    facts = {}
    for line in open(CONTEXT_FILE):
        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip()
    return facts


def build_global_old_seqs(mh_gt, sh_gt):
    """Union of old_seq across SH+MH per-hop has_pair entries."""
    olds = set()
    for q in mh_gt:
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
                olds.add(h["old_seq"])
    for q in sh_gt:
        if q.get("conflict_type") == "has_pair" and q.get("old_seq") is not None:
            olds.add(q["old_seq"])
    return olds


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


def main():
    facts = load_facts()
    mh_gt = json.load(open(MH_GT))
    sh_gt = json.load(open(SH_GT)) if SH_GT.exists() else []
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    global_olds = build_global_old_seqs(mh_gt, sh_gt)
    print(f"Total facts: {len(facts)}")
    print(f"Globally identified old seqs: {len(global_olds)}")

    # Resume
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
        # Identify chain old_seqs (these we KEEP — they're the question's own conflicts)
        chain_old_seqs = {
            h.get("old_seq")
            for h in q.get("hops", [])
            if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None
        }
        # Non-chain olds = global olds minus chain olds
        non_chain_olds_to_remove = global_olds - chain_old_seqs

        kept_seqs = sorted(s for s in facts.keys() if s not in non_chain_olds_to_remove)
        body = "\n".join(f"{s}. {facts[s]}" for s in kept_seqs)
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
            "num_hops": q.get("num_hops"),
            "n_conflict": sum(1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair"),
            "n_facts_kept": len(kept_seqs),
            "n_olds_removed": len(non_chain_olds_to_remove),
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
