"""
PAT + modified prompt (intermediate trailer) — fills the missing cell in the
2x2 table {filter, annotation} x {orig prompt, modified prompt}.

Same fact-level annotation as `pat_gemini.py`:
  - [CURRENT FACT] before chain GT fact's seq number
  - [OUTDATED FACT] before chain old fact's seq number
  - PAT_INSTRUCTION explaining the labels at top of user message
But uses the modified prompt (Intermediate answers trailer) so we can fairly
compare to OA2-modified (83% MH).

Reads:
  analysis/results/{mh,sh}_512_mquake_analysis.json
  outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_{sh,mh}_6k/chunksize_512/query_{qid}_context_0.json
  outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/.../{sh,mh}_6k_..._chunk512_results.json

Writes:
  analysis/results/diagnostic/pat_modified_{sh,mh}_results.json
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
SH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
SH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# --- Modified system prompt (same as A1 / OA2-modified) ---
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
ONE_SHOT_INPUT = ONE_SHOT_DOCS + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "
ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862."
    "\nIntermediate answers: [University of Southampton, 1862]"
    "\nAnswer: 1862."
)

PAT_INSTRUCTION = (
    "Some facts in the context below have been pre-annotated:\n"
    "- [CURRENT FACT] marks information that is up-to-date.\n"
    "- [OUTDATED FACT] marks information that has been superseded by a later statement.\n\n"
    "When answering, use [CURRENT FACT] as the source of truth. "
    "You may reference [OUTDATED FACT] only if the question explicitly asks about historical states.\n\n"
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


def parse_passages(s):
    out = {}
    parts = re.split(r"(Passage \d+:\n)", s)
    for i in range(len(parts) - 1):
        m = re.match(r"Passage (\d+):", parts[i])
        if m and i + 1 < len(parts):
            out[int(m.group(1))] = parts[i + 1].strip()
    return out


_FACT_NUMBER_RE = re.compile(r"(^|\s)(\d{1,4})\.\s")


def annotate_passage(text, current_seqs, outdated_seqs):
    def repl(m):
        prefix_ws = m.group(1)
        seq = int(m.group(2))
        if seq in current_seqs:
            return f"{prefix_ws}[CURRENT FACT] {seq}. "
        if seq in outdated_seqs:
            return f"{prefix_ws}[OUTDATED FACT] {seq}. "
        return m.group(0)

    return _FACT_NUMBER_RE.sub(repl, text)


def build_messages(passages_dict, current_seqs, outdated_seqs, query_text):
    prompt_user = PAT_INSTRUCTION
    for rank in sorted(passages_dict.keys()):
        annotated = annotate_passage(passages_dict[rank], current_seqs, outdated_seqs)
        prompt_user += f"Wikipedia Title: {annotated}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "
    return [
        {"role": "system", "content": RAG_QA_SYSTEM},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user", "content": prompt_user},
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
            mret = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(mret.group(1)) + 2 if mret else min(2 ** attempt * 5, 60))
    text = r.text if r.text is not None else ""
    um = r.usage_metadata
    return text, getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)


def get_chain_seqs(task, gt_record):
    if task == "SH":
        cur = {gt_record["gt_seq"]} if gt_record.get("gt_seq") is not None else set()
        old = {gt_record["old_seq"]} if (gt_record.get("conflict_type") == "has_pair" and gt_record.get("old_seq") is not None) else set()
        return cur, old
    cur = {h["gt_seq"] for h in gt_record.get("hops", []) if h.get("gt_seq") is not None}
    old = {h["old_seq"] for h in gt_record.get("hops", []) if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None}
    return cur, old


def run_task(task, client):
    if task == "SH":
        gt = json.load(open(SH_GT))
        results_data = json.load(open(SH_RESULTS))
        retrieved_dir = SH_RETRIEVED_DIR
        out_path = OUT_DIR / "pat_modified_sh_results.json"
    else:
        gt = json.load(open(MH_GT))
        results_data = json.load(open(MH_RESULTS))
        retrieved_dir = MH_RETRIEVED_DIR
        out_path = OUT_DIR / "pat_modified_mh_results.json"

    qmap = {e["query_id"]: e["query"] for e in results_data["data"]}
    amap = {e["query_id"]: e["answer"] for e in results_data["data"]}

    existing = []
    done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume {task}] {len(done)} done")

    todo = [r for r in gt if r["query_id"] not in done]
    print(f"[pending {task}] {len(todo)}")
    if not todo:
        return existing

    for i, q in enumerate(todo):
        qid = q["query_id"]
        cur_seqs, old_seqs = get_chain_seqs(task, q)
        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            print(f"  [skip qid={qid}]")
            continue
        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        query_text = qmap.get(qid, "")
        gt_ans = amap.get(qid, "")
        messages = build_messages(passages, cur_seqs, old_seqs, query_text)

        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0

        inter, final = extract_intermediate_and_final(raw)
        em = fuzzy_match(final, gt_ans)

        out_entry = {
            "query_id": qid,
            "current_seqs": sorted(cur_seqs),
            "outdated_seqs": sorted(old_seqs),
            "raw_output": raw,
            "intermediate_answers": inter,
            "pred_answer": final,
            "gt_answer": gt_ans,
            "exact_match": em,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        }
        if task == "MH":
            out_entry["num_hops"] = q.get("num_hops")
            out_entry["n_conflict"] = sum(
                1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair"
            )

        existing.append(out_entry)
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{task} {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")

    return existing


def main():
    os.chdir("/home/yhchiang/MemoryAgentBench")
    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    run_task("MH", client)
    run_task("SH", client)


if __name__ == "__main__":
    main()
