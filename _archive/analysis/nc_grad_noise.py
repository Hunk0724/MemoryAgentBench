"""
NC-grad: Sim-OB-grad's clean cousin — distractor pool is NEW-FACTS-ONLY.

For each FC-MH question, build context = chain GT facts + k distractors,
where distractors are sampled from non_chain_NEW facts (excluding all old facts
across all SH+MH GT). This isolates "pure multi-hop noise" from "cross-question
conflict noise" that Sim-OB-grad mixes.

Compared with Sim-OB-grad:
  - Sim-OB-grad pool = full 455 (165 old + 290 new) — distractors mix
  - NC-grad pool = ~287 new-only (455 − 165 old − chain_seqs)

If NC-grad still cliffs at k=100 PPR-nearby like Sim-OB-grad, → noise from
new-fact entity-overlap is sufficient.  If NC-grad doesn't cliff → cliff was
driven by old-fact conflict noise in distractors.

Reads:
  analysis/results/{sh,mh}_512_mquake_analysis.json
  analysis/contexts/factconsolidation_6k_context.txt
  outputs/rag_retrieved/.../query_{qid}_context_0.json

Writes:
  analysis/results/diagnostic/nc_grad_results.json
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
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT = OUT_DIR / "nc_grad_results.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048
NOISE_LEVELS = [10, 50, 100, 200]  # restricted to <287 (new pool size)
SOURCES = ["ppr-nearby"]  # focus on the source that cliffed in Sim-OB-grad
SEED = 42

# Modified prompt (matches Sim-OB-grad for apples-to-apples)
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


def collect_all_old_seqs():
    """Union of has_pair old_seqs across SH+MH GT — these are excluded from new-only pool."""
    olds = set()
    sh = json.load(open(SH_GT))
    for q in sh:
        if q.get("conflict_type") == "has_pair" and q.get("old_seq") is not None:
            olds.add(q["old_seq"])
    mh = json.load(open(MH_GT))
    for q in mh:
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
                olds.add(h["old_seq"])
    return olds


def load_facts():
    facts = {}
    for line in CONTEXT_FILE.read_text().splitlines():
        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip()
    return facts


def parse_passages(context_str):
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
    return [int(m.group(1)) for m in re.finditer(r"(?:^|\s)(\d+)\.\s", passage_text)]


def get_ppr_ordered_seqs(qid):
    p = RETRIEVED_DIR / f"query_{qid}_context_0.json"
    if not p.exists():
        return []
    ctx = json.load(open(p))
    seqs = []
    for psg in parse_passages(ctx):
        seqs.extend(passage_to_seqs(psg))
    seen, out = set(), []
    for s in seqs:
        if s not in seen:
            seen.add(s); out.append(s)
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
        temperature=TEMPERATURE, max_output_tokens=MAX_TOKENS,
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
    return text


def build_passage_body(seqs, facts_dict):
    seqs_sorted = sorted(seqs)
    return "\n".join(f"{s}. {facts_dict[s]}" for s in seqs_sorted if s in facts_dict)


def main():
    random.seed(SEED)
    os.chdir("/home/yhchiang/MemoryAgentBench")
    facts = load_facts()
    all_old_seqs = collect_all_old_seqs()
    print(f"[setup] {len(facts)} total facts, {len(all_old_seqs)} olds (excluded), {len(facts) - len(all_old_seqs)} new pool")

    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    existing = []
    done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
        done = {(r["query_id"], r["source"], r["noise_level"]) for r in existing}
        print(f"[resume] {len(done)} done")

    todo = []
    for q in mh_gt:
        qid = q["query_id"]
        chain_seqs = []
        for h in q.get("hops", []):
            if h.get("gt_seq") is not None:
                chain_seqs.append(h["gt_seq"])
        # Build new-only non-chain pool
        non_chain_new = [s for s in facts if s not in chain_seqs and s not in all_old_seqs]
        ppr_seqs = get_ppr_ordered_seqs(qid)
        ppr_non_chain_new = [s for s in ppr_seqs if s not in chain_seqs and s not in all_old_seqs]
        # Append remaining new seqs at end
        for s in non_chain_new:
            if s not in ppr_non_chain_new:
                ppr_non_chain_new.append(s)

        for source in SOURCES:
            for k in NOISE_LEVELS:
                if (qid, source, k) in done:
                    continue
                eff_k = min(k, len(non_chain_new))
                rng = random.Random(SEED + qid * 1000 + k)
                if source == "random":
                    distractors = rng.sample(non_chain_new, eff_k)
                else:
                    distractors = ppr_non_chain_new[:eff_k]
                todo.append({
                    "query_id": qid, "source": source, "noise_level": k,
                    "actual_k": eff_k, "chain_seqs": chain_seqs,
                    "distractor_seqs": distractors,
                })

    print(f"[pending] {len(todo)} configs")
    if not todo:
        return existing

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, t in enumerate(todo):
        all_seqs = sorted(set(t["chain_seqs"]) | set(t["distractor_seqs"]))
        passage = build_passage_body(all_seqs, facts)
        query = qmap.get(t["query_id"], "")
        gt = amap.get(t["query_id"], "")
        messages = build_messages(passage, query)
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        inter, final = extract_intermediate_and_final(raw)
        em = fuzzy_match(final, gt)
        existing.append({
            "query_id": t["query_id"], "source": t["source"],
            "noise_level": t["noise_level"], "actual_k": t["actual_k"],
            "n_chain": len(t["chain_seqs"]),
            "raw_output": raw, "intermediate_answers": inter,
            "pred_answer": final, "gt_answer": gt, "exact_match": em,
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 20 == 0:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={t['query_id']} src={t['source']} k={t['noise_level']} acc={ok}/{len(existing)}")
    return existing


if __name__ == "__main__":
    main()
