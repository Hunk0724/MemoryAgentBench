"""
Non-counterfactual baseline (advisor 0422 建議).

Goal:
  Isolate "pure multi-hop reasoning over noisy 6k retrieval" from "conflict
  handling failure". Remove ALL old facts (chain + non-chain) from every
  question's top-10 retrieved passages, so the resulting 6k context is a
  consistent "post-edit world" with no conflicts. Run HippoRAG-v2 vanilla
  inference (modified prompt, matches A1 / B / Sim-OB / OA2).

  vs OA2 (oracle_a_fact_level.py):
    - OA2 removes ONLY this question's chain olds (other questions' olds remain).
    - This script removes the UNION of all olds across SH+MH GT.
  vs C (c_no_distractor_conflicts.py):
    - C removes non-chain olds, KEEPS this question's chain conflicts (42% on MH).
    - This script removes BOTH chain and non-chain olds.

Decomposition this enables:
    Sim-OB 98%   = no 6k noise + no conflict
    THIS exp ?   = with 6k noise + no conflict   ← decomposes noise vs conflict
    FC-MH 23%    = with 6k noise + with conflict

  → 6k retrieval noise loss = 98% - this_exp_em
  → conflict handling loss  = this_exp_em - 23%

Reads:
  analysis/results/{mh,sh}_512_mquake_analysis.json
  outputs/rag_retrieved/.../query_{qid}_context_0.json
  outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/.../{sh,mh}_6k_*_results.json

Writes:
  analysis/results/diagnostic/non_counterfactual_baseline_{sh,mh}_results.json

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

# Same modified prompt as A1 / B / Sim-OB / OA2 — fair comparison
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
    """Remove '{old_seq}. <fact text>' substring (until next numbered fact or EOF).

    Returns (new_text, n_removed). Same as OA2.
    """
    n = 0
    pat = re.compile(rf"(?:(?<=^)|(?<=\s)){re.escape(str(old_seq))}\.\s")
    while True:
        m = pat.search(passage_text)
        if not m:
            break
        start = m.start()
        after = passage_text[m.end():]
        next_m = re.search(r"(?:(?<=\s)|(?<=^))\d+\.\s", after)
        if next_m:
            end = m.end() + next_m.start()
        else:
            end = len(passage_text)
        passage_text = passage_text[:start] + passage_text[end:]
        n += 1
    passage_text = re.sub(r"\s+", " ", passage_text).strip()
    return passage_text, n


def excise_facts_from_passages(passages, old_seqs):
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


def collect_global_old_seqs():
    """Union of chain old_seqs across SH 100 + MH 100 questions.

    Empirically: MH alone has 165 unique olds, SH ⊂ MH (no SH-only olds),
    so this is effectively the full set of "outdated facts in the 6k context"
    as known from MQuAKE-CF GT. Removing them gives a no-conflict 6k.
    """
    mh = json.load(open(MH_GT))
    sh = json.load(open(SH_GT))
    olds = set()
    for q in mh:
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
                olds.add(h["old_seq"])
    for q in sh:
        if q.get("conflict_type") == "has_pair" and q.get("old_seq") is not None:
            olds.add(q["old_seq"])
    return sorted(olds)


def get_chain_old_seqs(task, gt_record):
    """Per-question chain olds (for sanity-check metadata)."""
    if task == "SH":
        if gt_record.get("conflict_type") == "has_pair" and gt_record.get("old_seq") is not None:
            return [gt_record["old_seq"]]
        return []
    return [
        h["old_seq"]
        for h in gt_record.get("hops", [])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None
    ]


def run_task(task, client, global_olds):
    if task == "SH":
        gt = json.load(open(SH_GT))
        results_data = json.load(open(SH_RESULTS))
        retrieved_dir = SH_RETRIEVED_DIR
        out_path = OUT_DIR / "non_counterfactual_baseline_sh_results.json"
    else:
        gt = json.load(open(MH_GT))
        results_data = json.load(open(MH_RESULTS))
        retrieved_dir = MH_RETRIEVED_DIR
        out_path = OUT_DIR / "non_counterfactual_baseline_mh_results.json"

    qmap = {e["query_id"]: e["query"] for e in results_data["data"]}
    amap = {e["query_id"]: e["answer"] for e in results_data["data"]}

    existing = []
    done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume {task}] {len(done)} done")

    todo = [r for r in gt if r["query_id"] not in done]
    print(f"[pending {task}] {len(todo)} (using {len(global_olds)} global old seqs)")
    if not todo:
        return existing

    for i, q in enumerate(todo):
        qid = q["query_id"]
        chain_olds = get_chain_old_seqs(task, q)
        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            print(f"  [skip qid={qid}] no retrieved cache")
            continue
        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        # Apply global olds (= chain + non-chain) to passages
        new_passages, log = excise_facts_from_passages(passages, global_olds)
        n_removed = sum(e["n_removed"] for e in log)

        # Sanity: of the chain olds that this question cares about,
        # how many were actually present in the top-10 passages?
        chain_olds_hit = sum(
            1 for s in chain_olds
            if any(e["old_seq"] == s for e in log)
        )

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
            "chain_old_seqs": chain_olds,
            "chain_olds_in_top10": chain_olds_hit,
            "n_total_old_facts_removed": n_removed,
            "n_global_olds_applied": len(global_olds),
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
    global_olds = collect_global_old_seqs()
    print(f"[setup] global old seqs (union of SH+MH chain olds): {len(global_olds)}")
    print(f"        seq range: [{min(global_olds)}, {max(global_olds)}]")

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    run_task("MH", client, global_olds)
    run_task("SH", client, global_olds)


if __name__ == "__main__":
    main()
