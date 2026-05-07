"""
Oracle A v2 — fact-level surgical removal.

Original Oracle A removed entire passages containing chain old facts, which
forced subset filtering (new/old must be in DIFFERENT passages of top-10).
v2 surgically removes ONLY the old-fact lines, preserving the rest of each
passage. This lets us run all 100 MH + 100 SH questions (full denominator).

Method:
  For each question, for each chain old_seq:
    For each top-10 passage:
      Locate every instance of  '{seq}. <fact text>'  using word-boundary regex
      and excise the substring up to the start of the next numbered fact.
  Reassemble passages and run modified-prompt inference (matches A1 / B / Sim-OB).

Reads:
  analysis/results/{mh,sh}_512_mquake_analysis.json    (per-hop old_seq / SH old_seq)
  outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_{sh,mh}_6k/chunksize_512/query_{qid}_context_0.json
  outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/.../{sh,mh}_6k_..._chunk512_results.json   (query text, GT)

Writes:
  analysis/results/diagnostic/oracle_a_fact_level_{sh,mh}_results.json

Resume: skip query_ids already in output.
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

# Same modified prompt as A1 / B / Sim-OB
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


def parse_passages(context_str):
    """Parse `Passage X:\n...` into ordered list [(rank, text)]."""
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
    """
    Remove '{old_seq}. <fact text>' from passage_text using word-boundary
    regex. Excises from the start of the seq match up to (but not including)
    the next '<digit>+. ' marker, or end-of-passage if it's the last fact.

    Returns (new_text, n_removed) — n_removed counts how many occurrences
    were excised (should be 0 or 1 in normal cases).
    """
    n = 0
    pat = re.compile(rf"(?:(?<=^)|(?<=\s)){re.escape(str(old_seq))}\.\s")
    while True:
        m = pat.search(passage_text)
        if not m:
            break
        start = m.start()
        # Find the next numbered fact after this seq
        after = passage_text[m.end():]
        next_m = re.search(r"(?:(?<=\s)|(?<=^))\d+\.\s", after)
        if next_m:
            end = m.end() + next_m.start()
        else:
            end = len(passage_text)
        passage_text = passage_text[:start] + passage_text[end:]
        n += 1
    # Tidy up double whitespace caused by excision
    passage_text = re.sub(r"\s+", " ", passage_text).strip()
    return passage_text, n


def excise_facts_from_passages(passages, old_seqs):
    """
    Apply excise_old_fact for every old_seq across all passages.
    Returns (new_passages_list_keeping_rank, removal_log).
    Empty passages (after removal) are kept as empty strings to preserve rank
    semantics in downstream analysis; we filter empties at prompt assembly.
    """
    new_passages = []
    log = []
    for rank, text in passages:
        cur = text
        for s in old_seqs:
            cur, n = excise_old_fact(cur, s)
            if n:
                log.append({"rank": rank, "old_seq": s, "n_removed": n})
        new_passages.append((rank, cur))
    return new_passages, log


def build_messages(passages_kept, query_text):
    """Build vanilla HippoRAG QA messages with modified system + one-shot."""
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


def get_old_seqs(task, gt_record):
    """Return list of old_seqs for this question (chain has_pair olds)."""
    if task == "SH":
        if gt_record.get("conflict_type") == "has_pair" and gt_record.get("old_seq") is not None:
            return [gt_record["old_seq"]]
        return []
    # MH
    return [
        h["old_seq"]
        for h in gt_record.get("hops", [])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None
    ]


def run_task(task, client):
    if task == "SH":
        gt = json.load(open(SH_GT))
        results_data = json.load(open(SH_RESULTS))
        retrieved_dir = SH_RETRIEVED_DIR
        out_path = OUT_DIR / "oracle_a_fact_level_sh_results.json"
    else:
        gt = json.load(open(MH_GT))
        results_data = json.load(open(MH_RESULTS))
        retrieved_dir = MH_RETRIEVED_DIR
        out_path = OUT_DIR / "oracle_a_fact_level_mh_results.json"

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
        old_seqs = get_old_seqs(task, q)
        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            print(f"  [skip qid={qid}] no retrieved cache")
            continue
        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        new_passages, log = excise_facts_from_passages(passages, old_seqs)
        n_removed = sum(e["n_removed"] for e in log)

        query_text = qmap.get(qid, "")
        gt_ans = amap.get(qid, "")
        messages = build_messages(new_passages, query_text)

        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0

        inter, final = extract_intermediate_and_final(raw)
        em = fuzzy_match(final, gt_ans)

        out_entry = {
            "query_id": qid,
            "old_seqs": old_seqs,
            "n_old_facts_removed": n_removed,
            "removal_log": log,
            "n_passages_with_content": sum(1 for _, t in new_passages if t.strip()),
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
