"""
P1.4 — No-seq-rule ablation on Mode C n_inject=0 / n=1.

Tests whether the multiplicative baseline / emergent gap argument depends on the
FC seq-rule wrapper (which explicitly tells LLM "newer = larger seq").

Original Mode C (sim_ob_grad_v2.py) uses q["query"] = full FC wrapper with seq rule.
This script uses q["question"] = bare question (no wrapper, no seq rule), aligned
with how Mem0/Zep are tested.

Setup:
- Same context construction as Mode C: chain_new + saturated noise (+ n_inject chain_olds)
- Same orig HippoRAG prompt (no trailer)
- Difference: use bare q["question"] instead of q["query"]
- Test n_inject = 0 and n_inject = 1 only (the killer comparison)

Expected outcomes:
- If 58% (n=0) and 9% (n=1) hold within ~5pp: seq rule isn't load-bearing
  → emergent gap robust to prompt setup
- If 58% (n=0) drops to e.g. 20%: seq rule was carrying significant weight
  → framing needs strengthening

Reads:
- Same data sources as sim_ob_grad_v2.py
- analysis/results/mh_512_mquake_analysis.json
- analysis/contexts/factconsolidation_6k_context.txt
- outputs/rag_retrieved/.../query_X_context_0.json (PPR cache)

Writes:
- analysis/results/diagnostic/p1_4_no_seq_rule_mode_c_results.json
"""

import argparse
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
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT = BASE / "analysis/results/diagnostic/p1_4_no_seq_rule_mode_c_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# === ORIG HippoRAG-v2 prompt (no trailer) ===
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
    if isinstance(gold, list):
        return any(fuzzy_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn: return False
    return pn == gn or gn in pn or pn in gn


def extract_final(s):
    if "Answer:" in s:
        return s.split("Answer:")[-1].strip()
    return s.strip()


def load_facts():
    facts = {}
    for line in open(CONTEXT_FILE):
        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip()
    return facts


def get_chain_seqs(q):
    chain_new, chain_old = [], []
    for h in sorted(q.get("hops", []), key=lambda x: x.get("hop_idx", 0)):
        if h.get("gt_seq") is not None:
            chain_new.append(h["gt_seq"])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
            chain_old.append(h["old_seq"])
    return chain_new, chain_old


def build_passage_body(seqs, facts):
    seqs_sorted = sorted(set(seqs))
    return "\n".join(f"{s}. {facts[s]}" for s in seqs_sorted if s in facts)


def build_messages(passage_body, question_text):
    """Use BARE question (no FC wrapper, no seq rule)."""
    user_msg = f"Wikipedia Title: \n{passage_body}\n\nQuestion: {question_text}\nThought: "
    return [
        {"role": "system", "content": RAG_QA_SYSTEM},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user", "content": user_msg},
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

    facts = load_facts()
    print(f"Loaded {len(facts)} facts")
    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    # KEY DIFFERENCE: use q["question"] (bare) instead of q["query"] (with FC wrapper)
    qmap_bare = {q["query_id"]: q["question"] for q in mh_gt}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    existing = []; done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
        done = {(r["query_id"], r["n_old_injected"]) for r in existing}
        print(f"[resume] {len(done)} done")

    todo = []
    for q in mh_gt:
        qid = q["query_id"]
        chain_new, chain_old = get_chain_seqs(q)
        if not chain_new:
            continue
        excluded = set(chain_new) | set(chain_old)
        non_chain_pure = [s for s in facts.keys() if s not in excluded]
        # Test n_inject = 0 and 1
        for n_inject in [0, 1]:
            if (qid, n_inject) in done: continue
            if n_inject > len(chain_old): continue
            injected_olds = list(chain_old[:n_inject])
            todo.append({
                "qid": qid, "n_inject": n_inject,
                "chain_new": chain_new, "non_chain_pure": non_chain_pure,
                "injected_olds": injected_olds,
            })

    print(f"[pending] {len(todo)} configs")
    if not todo: return

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, cfg in enumerate(todo):
        qid = cfg["qid"]
        all_seqs = list(cfg["chain_new"]) + list(cfg["non_chain_pure"]) + list(cfg["injected_olds"])
        body = build_passage_body(all_seqs, facts)
        question_bare = qmap_bare.get(qid, "")
        messages = build_messages(body, question_bare)
        gt = amap.get(qid, "")
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid,
            "n_old_injected": cfg["n_inject"],
            "num_hops": next((q.get("num_hops") for q in mh_gt if q["query_id"] == qid), None),
            "n_chain_old_total": len(cfg["chain_new"]),  # placeholder
            "raw_output": raw, "pred_answer": extract_final(raw),
            "gt_answer": gt, "exact_match": em,
            "question_used": "bare (no FC wrapper, no seq rule)",
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 20 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} n={cfg['n_inject']} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")

    # Summary
    from collections import defaultdict
    print("\n=== P1.4 No-seq-rule Ablation Summary ===")
    g = defaultdict(list)
    for r in existing: g[r['n_old_injected']].append(r)
    for n in sorted(g):
        rs = g[n]
        ok = sum(1 for r in rs if r['exact_match'])
        print(f'  n_inject={n}: {ok}/{len(rs)} = {ok/len(rs)*100:.1f}%')

    # Rule-clean 96
    violated = set()
    for q in mh_gt:
        for h in q.get('hops', []):
            if h.get('conflict_type') == 'has_pair' and h['gt_seq'] < h['old_seq']:
                violated.add(q['query_id']); break
    print('\nRule-clean 96:')
    for n in sorted(g):
        rs = [r for r in g[n] if r['query_id'] not in violated]
        ok = sum(1 for r in rs if r['exact_match'])
        print(f'  n_inject={n}: {ok}/{len(rs)} = {ok/len(rs)*100:.1f}%')


if __name__ == "__main__":
    main()
