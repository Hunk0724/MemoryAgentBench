"""
Task B - Hop-by-hop ablation: run each MH hop as a standalone FC-SH question.

For each MH question, decompose into N single-hop sub-questions
(`hop_question` from MQuAKE per-hop GT). Run each sub-question through
vanilla HippoRAG-v2 retrieval + modified-prompt inference (matching A1).

Goal: separate two failure sources
  (a) "single-hop ceiling": if single-hops have high accuracy in isolation,
       MH failure is purely chain accumulation
  (b) "single-hop weakness": if single-hops also fail at similar rate, the
       chain isn't the new culprit — base reasoning is

Cross-references with A2 per-hop classes:
  - A2 "this hop in chain context, what did LLM predict?"
  - B  "this hop standalone with its own retrieval, can LLM solve it?"

Reads:
  analysis/results/mh_512_mquake_analysis.json  (per-hop GT, hop_question, gt_answer, old_answer)
  HippoRAG cached index: outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/

Writes:
  analysis/results/diagnostic/b_hop_ablation_results.json
  analysis/results/diagnostic/b_hop_ablation_summary.txt

Resume: re-run skips (qid, hop_idx) keys that already exist in output JSON.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
BASE = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(BASE))

MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
HIPPO_INDEX_DIR = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT_RESULTS = OUT_DIR / "b_hop_ablation_results.json"
OUT_SUMMARY = OUT_DIR / "b_hop_ablation_summary.txt"

OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048
TOP_K = 10

# Same FC question template as production (utils/templates.py:81 'rag_agent')
FC_WRAPPER = (
    "Pretend you are a knowledge management system. Each fact in the knowledge pool "
    "is provided with a serial number at the beginning, and the newer fact has larger "
    "serial number. \n You need to solve the conflicts of facts in the knowledge pool "
    "by finding the newest fact with larger serial number. You need to answer a "
    "question based on this rule. You should give a very concise answer without saying "
    "other words for the question **only** from the knowledge pool you have memorized "
    "rather than the real facts in real world. \n\nFor example:\n\n [Knowledge Pool] "
    "\n\n Question: Based on the provided Knowledge Pool, what is the name of the "
    "current president of Russia? \nAnswer: Donald Trump \n\n Now Answer the Question: "
    "Based on the provided Knowledge Pool, {question} \nAnswer:"
)

# Modified prompt (matches A1 — keep intermediate trailer for parsing consistency)
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

# One-shot demo (same as A1)
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


def build_inference_prompt(retrieved_docs, wrapped_query):
    """Build vanilla HippoRAG QA messages with modified system + one-shot."""
    prompt_user = ""
    for doc in retrieved_docs:
        prompt_user += f"Wikipedia Title: {doc}\n\n"
    prompt_user += f"Question: {wrapped_query}\nThought: "
    return [
        {"role": "system", "content": RAG_QA_SYSTEM},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user", "content": prompt_user},
    ]


def main():
    os.chdir("/home/yhchiang/MemoryAgentBench")

    # Build (qid, hop_idx, hop_question, gt_answer, old_answer, conflict_type) list
    mh_data = json.load(open(MH_GT))
    todo = []
    for q in mh_data:
        qid = q["query_id"]
        for k, h in enumerate(q.get("hops", [])):
            hop_q = h.get("hop_question")
            if not hop_q:
                continue
            todo.append({
                "query_id": qid,
                "hop_idx": k,
                "hop_question": hop_q,
                "gt_answer": h.get("gt_answer"),
                "old_answer": h.get("old_answer"),
                "conflict_type": h.get("conflict_type"),
            })

    print(f"Total single-hop subquestions: {len(todo)}")

    # Resume: load existing
    existing = []
    done_keys = set()
    if OUT_RESULTS.exists():
        existing = json.load(open(OUT_RESULTS))
        done_keys = {(r["query_id"], r["hop_idx"]) for r in existing}
        print(f"[resume] {len(done_keys)} already done")

    pending = [t for t in todo if (t["query_id"], t["hop_idx"]) not in done_keys]
    print(f"[pending] {len(pending)} subquestions remain")

    if not pending:
        print("Nothing to do. Run summary on existing results.")
        return existing

    # ── Initialize HippoRAG with cached index ──────────────────────────────────
    from methods.hipporag import HippoRAG
    print(f"[init] Loading HippoRAG with cached index from {HIPPO_INDEX_DIR}")
    hipporag = HippoRAG(
        save_dir=str(HIPPO_INDEX_DIR),
        llm_model_name=MODEL,
        embedding_model_name="nvidia/NV-Embed-v2",
    )
    # Re-index from cached chunks: OpenIE/embeddings are cached on disk; this only
    # rebuilds in-memory state (e.g. ent_node_to_num_chunk) needed by retrieve().
    cached_chunks = [
        v["content"] if isinstance(v, dict) else v
        for v in hipporag.chunk_embedding_store.get_text_for_all_rows().values()
    ]
    print(f"[init] Re-indexing {len(cached_chunks)} cached chunks (no re-embed/re-OpenIE)")
    hipporag.index(docs=cached_chunks)
    hipporag.prepare_retrieval_objects()
    print("[init] HippoRAG retrieval objects ready")

    # ── Initialize Gemini client (separate from HippoRAG's internal LLM) ──────
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError, ServerError
    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    def call_gemini(messages):
        system_instruction = None
        contents = []
        for m in messages:
            if m["role"] == "system":
                system_instruction = m["content"]
            elif m["role"] == "user":
                contents.append({"role": "user", "parts": [{"text": m["content"]}]})
            elif m["role"] == "assistant":
                contents.append({"role": "model", "parts": [{"text": m["content"]}]})
        gen_config = types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if system_instruction:
            gen_config.system_instruction = system_instruction
        for attempt in range(10):
            try:
                resp = client.models.generate_content(model=MODEL, contents=contents, config=gen_config)
                break
            except (ClientError, ServerError) as e:
                code = getattr(e, "code", None)
                if code not in (429, 503) or attempt == 9:
                    raise
                m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
                delay = float(m.group(1)) + 2 if m else min(2 ** attempt * 5, 60)
                time.sleep(delay)
        text = resp.text if resp.text is not None else ""
        um = resp.usage_metadata
        return text, getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)

    # ── Process subquestions one-at-a-time (so resume is fine-grained) ────────
    n = len(pending)
    for i, sub in enumerate(pending):
        wrapped_query = FC_WRAPPER.format(question=sub["hop_question"])

        # Retrieve
        try:
            retrieval_results, _ = hipporag.retrieve(queries=[wrapped_query], num_to_retrieve=TOP_K)
            retrieved_docs = retrieval_results[0].docs
        except Exception as e:
            print(f"  [retrieval err qid={sub['query_id']} hop={sub['hop_idx']}] {e}")
            existing.append({
                **sub,
                "retrieved_docs": [],
                "raw_output": f"RETRIEVAL_ERROR: {e}",
                "intermediate_answers": None,
                "pred_answer": "",
                "exact_match_gt": False,
                "exact_match_old": False,
            })
            with open(OUT_RESULTS, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            continue

        # Inference
        messages = build_inference_prompt(retrieved_docs, wrapped_query)
        try:
            raw, ptok, ctok = call_gemini(messages)
        except Exception as e:
            print(f"  [inference err qid={sub['query_id']} hop={sub['hop_idx']}] {e}")
            raw, ptok, ctok = f"INFERENCE_ERROR: {e}", 0, 0

        intermediates, final = extract_intermediate_and_final(raw)
        em_gt = fuzzy_match(final, sub["gt_answer"])
        em_old = fuzzy_match(final, sub["old_answer"]) if sub.get("old_answer") else False

        existing.append({
            **sub,
            "retrieved_docs": retrieved_docs,
            "raw_output": raw,
            "intermediate_answers": intermediates,
            "pred_answer": final,
            "exact_match_gt": em_gt,
            "exact_match_old": em_old,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        })

        with open(OUT_RESULTS, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == n - 1:
            done_n = len(existing)
            ok_n = sum(1 for r in existing if r["exact_match_gt"])
            print(f"  [{i+1}/{n}] qid={sub['query_id']} hop={sub['hop_idx']} "
                  f"acc={ok_n}/{done_n}={ok_n/done_n*100:.1f}%")

    print(f"\nDone. Total {len(existing)} results saved to {OUT_RESULTS}")
    return existing


if __name__ == "__main__":
    main()
