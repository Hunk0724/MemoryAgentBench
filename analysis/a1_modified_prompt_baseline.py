"""
Task A1 - Modified-prompt vanilla baseline for FC-MH (and FC-SH for completeness).

Re-runs the HippoRAG-v2 x Gemini 3.1 Flash-Lite x chunk_size=512 baseline using a
modified prompt that requires the LLM to emit an explicit per-hop trailer:

    Thought: <free-form reasoning>
    Intermediate answers: [hop_1_answer, hop_2_answer, ..., final_answer]
    Answer: <final answer>

Why a re-baseline is required: changing the prompt changes the LLM behavior
(answer distribution, hallucination rate, etc.), so we need a fresh fair-compare
control group rather than diff-ing against the original baseline directly.

Reads the same retrieved-passages cache as Oracle A so we re-use the existing
HippoRAG-v2 retrieval (no re-indexing). Saves the full raw_output for Task A2.

Resume: Re-running the script auto-skips query_ids that already exist in the
output JSON. Do NOT delete partial outputs.
"""

import json
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

# === Config ===
MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# === Paths ===
BASE = Path("/home/yhchiang/MemoryAgentBench")
SH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
SH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"

os.makedirs(OUT_DIR, exist_ok=True)

# === Modified prompts =========================================================
# Adds an explicit "Intermediate answers: [...]" trailer requirement to make
# per-hop reasoning machine-parseable.

RAG_QA_SYSTEM_MODIFIED = (
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
    "and received its Royal Charter as a university in 1952, has over 22,000 students. The "
    "university is ranked in the top 100 research universities in the world in the Academic "
    "Ranking of World Universities 2010. In 2010, the THES - QS World University Rankings "
    "positioned the University of Southampton in the top 80 universities in the world. The "
    "university considers itself one of the top 5 research universities in the UK. The "
    "university has a global reputation for research into engineering sciences, oceanography, "
    "chemistry, cancer sciences, sound and vibration research, computer science and electronics, "
    "optoelectronics and textile conservation at the Textile Conservation Centre (which is due "
    "to close in October 2009.) It is also home to the National Oceanography Centre, Southampton "
    "(NOCS), the focus of Natural Environment Research Council-funded marine research.\n"
    "Wikipedia Title: Stanton Township, Champaign County, Illinois\nStanton Township is a "
    "township in Champaign County, Illinois, USA. As of the 2010 census, its population was "
    "505 and it contained 202 housing units.\n"
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human "
    "Factors and Ergonomics at the University of Southampton. Prof Stanton is a Chartered "
    "Engineer (C.Eng), Chartered Psychologist (C.Psychol) and Chartered Ergonomist (C.ErgHF). "
    "He has written and edited over a forty books and over three hundered peer-reviewed journal "
    "papers on applications of the subject. Stanton is a Fellow of the British Psychological "
    "Society, a Fellow of The Institute of Ergonomics and Human Factors and a member of the "
    "Institution of Engineering and Technology. He has been published in academic journals "
    'including "Nature". He has also helped organisations design new human-machine interfaces, '
    "such as the Adaptive Cruise Control system for Jaguar Cars.\n"
    "Wikipedia Title: Finding Nemo\nFinding Nemo Theatrical release poster Directed by Andrew "
    "Stanton Produced by Graham Walters Screenplay by Andrew Stanton Bob Peterson David Reynolds "
    "Story by Andrew Stanton Starring Albert Brooks Ellen DeGeneres Alexander Gould Willem Dafoe "
    "Music by Thomas Newman Cinematography Sharon Calahan Jeremy Lasky Edited by David Ian "
    "Salter Production company Walt Disney Pictures Pixar Animation Studios Distributed by "
    "Buena Vista Pictures Distribution Release date May 30, 2003 (2003 - 05 - 30) Running time "
    "100 minutes Country United States Language English Budget $$94 million Box office $$940.3 "
    "million"
)

ONE_SHOT_INPUT = (
    ONE_SHOT_DOCS
    + "\n\nQuestion: When was Neville A. Stanton's employer founded?"
    + "\nThought: "
)

# Modified one-shot output: 2-hop demo (employer -> founding date) explicitly
# shows the new trailer format.
ONE_SHOT_OUTPUT_MODIFIED = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862."
    "\nIntermediate answers: [University of Southampton, 1862]"
    "\nAnswer: 1862."
)


def parse_passages(context_str):
    """Parse retrieved context string into dict {rank(int): text(str)}."""
    passages = {}
    parts = re.split(r'(Passage \d+:\n)', context_str)
    i = 0
    while i < len(parts):
        m = re.match(r'Passage (\d+):', parts[i])
        if m and i + 1 < len(parts):
            rank = int(m.group(1))
            passages[rank] = parts[i + 1].strip()
            i += 2
        else:
            if parts[i].strip():
                m2 = re.match(r'Passage (\d+):\n(.*)', parts[i], re.DOTALL)
                if m2:
                    passages[int(m2.group(1))] = m2.group(2).strip()
            i += 1
    return passages


def build_prompt(passages_dict, query_text):
    """Build vanilla HippoRAG QA prompt with modified system+one-shot."""
    prompt_user = ""
    for rank in sorted(passages_dict.keys()):
        prompt_user += f"Wikipedia Title: {passages_dict[rank]}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "

    return [
        {"role": "system", "content": RAG_QA_SYSTEM_MODIFIED},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT_MODIFIED},
        {"role": "user", "content": prompt_user},
    ]


def extract_intermediate_and_final(response_text):
    """Pull `Intermediate answers: [...]` list and `Answer: ...` final from raw response."""
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


def normalize(s):
    return s.strip().rstrip(".,;:!?\"'").strip().lower()


def exact_match(pred, gold):
    """Substring match (matches HippoRAG eval)."""
    if isinstance(gold, list):
        return any(exact_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    return pn == gn or gn in pn


# ── Gemini helper ─────────────────────────────────────────────────────────────
def _messages_to_gemini(messages):
    system_instruction = None
    contents = []
    for m in messages:
        role, text = m.get("role"), m.get("content", "")
        if role == "system":
            system_instruction = text
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
    return system_instruction, contents


def call_gemini(client, messages, model=MODEL):
    import time
    from google.genai.errors import ClientError, ServerError

    system_instruction, contents = _messages_to_gemini(messages)
    gen_config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if system_instruction:
        gen_config.system_instruction = system_instruction

    for attempt in range(10):
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=gen_config)
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


def run_task(client, task, results_data, retrieved_dir, out_path):
    """Run modified-prompt vanilla baseline for SH or MH. Resumes from existing out_path."""
    # Build qid -> query text map
    query_map = {entry.get("query_id", 0): entry.get("query", "") for entry in results_data["data"]}
    answer_map = {entry.get("query_id", 0): entry.get("answer", "") for entry in results_data["data"]}

    # Resume: load existing results, skip done qids
    existing = []
    done_ids = set()
    if out_path.exists():
        with open(out_path) as f:
            existing = json.load(f)
        done_ids = {r["query_id"] for r in existing}
        print(f"[resume] {len(done_ids)} already done in {out_path.name}")

    todo = [qid for qid in sorted(query_map.keys()) if qid not in done_ids]
    print(f"\n{'='*60}\nTask A1 modified-prompt baseline: {task} ({len(todo)} new / {len(query_map)} total)\n{'='*60}")

    correct = sum(1 for r in existing if r.get("exact_match"))
    total = len(existing)

    for i, qid in enumerate(todo):
        query_text = query_map[qid]
        gt = answer_map[qid]

        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            print(f"  [skip qid={qid}] no retrieved cache")
            continue
        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        messages = build_prompt(passages, query_text)
        try:
            raw_output, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            print(f"  [error qid={qid}] {e}")
            raw_output, ptok, ctok = f"ERROR: {e}", 0, 0

        intermediates, final = extract_intermediate_and_final(raw_output)
        em = exact_match(final, gt)
        if em:
            correct += 1
        total += 1

        existing.append({
            "query_id": qid,
            "gt_answer": gt,
            "pred_answer": final,
            "intermediate_answers": intermediates,
            "raw_output": raw_output,
            "exact_match": em,
            "n_passages": len(passages),
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        })

        # Persist after every call (cheap enough; ensures resume safety)
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == len(todo) - 1:
            print(f"  [{i+1}/{len(todo)}] qid={qid} acc={correct}/{total}={correct/total*100:.1f}% "
                  f"intermediates={'OK' if intermediates else 'MISS'}")

    print(f"\n  Final: {correct}/{total} = {correct/total*100:.1f}%")
    return existing


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    with open(SH_RESULTS) as f:
        sh_results = json.load(f)
    with open(MH_RESULTS) as f:
        mh_results = json.load(f)

    # MH first (the main subject of the diagnostic)
    mh_out = OUT_DIR / "a1_modified_baseline_mh.json"
    run_task(client, "MH", mh_results, MH_RETRIEVED_DIR, mh_out)
    print(f"\n[MH] saved to {mh_out}")

    # SH for completeness (lets us also do per-hop comparison on single-hop)
    sh_out = OUT_DIR / "a1_modified_baseline_sh.json"
    run_task(client, "SH", sh_results, SH_RETRIEVED_DIR, sh_out)
    print(f"\n[SH] saved to {sh_out}")
