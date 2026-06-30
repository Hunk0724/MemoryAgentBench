"""
P1.5 — FC-MH same-pool single-hop baseline with ORIG prompt (vanilla HippoRAG-v2).

Validates the multiplicative baseline assumption that P_KU on FC-MH question pool
≈ FC-SH 77% (HippoRAG-v2 vanilla orig prompt).

Existing B ablation already cached per-hop retrieval results with MODIFIED prompt
(94.5% EM). We reuse `retrieved_docs` cache and only re-run inference with vanilla
ORIG prompt to align with FC-SH 77% baseline regime.

Setup:
- Reuse retrieved_docs from b_hop_ablation_results.json (HippoRAG-v2 retrieval per hop)
- Use vanilla HippoRAG-v2 ORIG prompt (no trailer, no Intermediate answers)
- Use FC_WRAPPER (seq rule wrapper, same as FC-SH 77% measurement)
- Each hop = standalone single-hop FC question over 6k corpus

Reads:
  analysis/results/diagnostic/b_hop_ablation_results.json (per-hop retrieved_docs)

Writes:
  analysis/results/diagnostic/p1_5_per_hop_origprompt_results.json

Reports:
  - Per-hop average EM
  - Per-question all-pass EM (all hops correct)
  - Stratified by num_hops (2/3/4)
  - Compared to FC-SH 77% baseline
"""

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from google import genai
from google.genai import types

BASE = Path("/home/yhchiang/MemoryAgentBench")
B_RESULTS = BASE / "analysis/results/diagnostic/b_hop_ablation_results.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
OUT = BASE / "analysis/results/diagnostic/p1_5_per_hop_origprompt_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# === FC task wrapper (same as FC-SH baseline measurement) ===
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

# === ORIG vanilla HippoRAG-v2 prompt (NO trailer) ===
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
    "and received its Royal Charter as a university in 1952, has over 22,000 students.\n"
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
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn: return False
    return pn == gn or gn in pn or pn in gn


def extract_final(s):
    if "Answer:" in s:
        return s.split("Answer:")[-1].strip()
    return s.strip()


def build_messages(retrieved_docs, wrapped_query):
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
    OUT.parent.mkdir(parents=True, exist_ok=True)

    b_data = json.load(open(B_RESULTS))
    print(f"[setup] {len(b_data)} per-hop entries from B ablation cache")

    existing = []; done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
        done = {(r["query_id"], r["hop_idx"]) for r in existing}
        print(f"[resume] {len(done)} done")

    todo = [r for r in b_data if (r["query_id"], r["hop_idx"]) not in done]
    print(f"[pending] {len(todo)}")
    if not todo:
        return

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, sub in enumerate(todo):
        retrieved_docs = sub.get("retrieved_docs", [])
        if not retrieved_docs:
            existing.append({**sub, "raw_output_orig": "NO_RETRIEVAL", "pred_answer_orig": "", "exact_match_gt_orig": False})
            continue
        wrapped_query = FC_WRAPPER.format(question=sub["hop_question"])
        messages = build_messages(retrieved_docs, wrapped_query)
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        final = extract_final(raw)
        em_gt = fuzzy_match(final, sub["gt_answer"])
        em_old = fuzzy_match(final, sub.get("old_answer", "")) if sub.get("old_answer") else False
        existing.append({
            "query_id": sub["query_id"], "hop_idx": sub["hop_idx"],
            "hop_question": sub["hop_question"],
            "gt_answer": sub["gt_answer"], "old_answer": sub.get("old_answer"),
            "conflict_type": sub.get("conflict_type"),
            "raw_output_orig": raw,
            "pred_answer_orig": final,
            "exact_match_gt_orig": em_gt,
            "exact_match_old_orig": em_old,
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 20 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r.get("exact_match_gt_orig"))
            print(f"  [{i+1}/{len(todo)}] qid={sub['query_id']} hop={sub['hop_idx']} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")

    print(f"\nDone. Total {len(existing)} results saved to {OUT}")

    # === Summary ===
    print("\n=== P1.5 Summary ===")
    print(f"Per-hop EM (orig prompt): ", end="")
    ok = sum(1 for r in existing if r.get("exact_match_gt_orig"))
    print(f"{ok}/{len(existing)} = {ok/len(existing)*100:.1f}%")
    print(f"Per-hop EM (modified prompt, B baseline): {sum(1 for r in b_data if r['exact_match_gt'])}/{len(b_data)} = {sum(1 for r in b_data if r['exact_match_gt'])/len(b_data)*100:.1f}%")
    print(f"FC-SH baseline (orig prompt, comparison): 77%")

    # Per-question all-pass
    mh_gt = json.load(open(MH_GT))
    qid_to_n_hops = {q['query_id']: q['num_hops'] for q in mh_gt}
    by_qid = defaultdict(list)
    for r in existing:
        by_qid[r['query_id']].append(r)

    all_pass = sum(1 for qid, rs in by_qid.items() if all(r.get('exact_match_gt_orig') for r in rs))
    print(f'Per-question all-pass: {all_pass}/{len(by_qid)} = {all_pass/len(by_qid)*100:.1f}%')

    # By num_hops
    print('\nBy num_hops:')
    nhops_groups = defaultdict(list)
    for qid, rs in by_qid.items():
        nh = qid_to_n_hops.get(qid, 0)
        nhops_groups[nh].append(rs)
    for nh in sorted(nhops_groups):
        groups = nhops_groups[nh]
        per_hop_ok = sum(1 for rs in groups for r in rs if r.get('exact_match_gt_orig'))
        per_hop_n = sum(len(rs) for rs in groups)
        all_pass_n = sum(1 for rs in groups if all(r.get('exact_match_gt_orig') for r in rs))
        print(f'  {nh}-hop ({len(groups)} questions): per-hop {per_hop_ok}/{per_hop_n} = {per_hop_ok/per_hop_n*100:.1f}%; all-pass {all_pass_n}/{len(groups)} = {all_pass_n/len(groups)*100:.1f}%')


if __name__ == "__main__":
    main()
