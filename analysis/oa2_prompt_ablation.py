"""
OA2 prompt ablation — isolate contribution of "trailer instruction" vs "trailer
demo (one-shot)" within the modified-prompt's +28pp gain on OA2.

Variants (all on OA2 fact-level filter context, FC-MH 100):
  V1 orig             system + orig one-shot    → already known: 55% (oracle_a_fact_level_origprompt)
  V2 modified system + orig one-shot            → instruction asks for trailer but example doesn't show it
  V3 orig system + modified one-shot            → instruction silent but example shows trailer
  V4 modified system + modified one-shot        → already known: 83% (oracle_a_fact_level)

If V2 ≈ 83 → instruction alone enough.
If V3 ≈ 83 → demo alone enough.
If both V2/V3 mid-range and V4 highest → both contribute.

Writes:
  analysis/results/diagnostic/oa2_ablation_v2_results.json   (modified instr + orig demo)
  analysis/results/diagnostic/oa2_ablation_v3_results.json   (orig instr + modified demo)
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
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# ---------- System prompts ----------
SYSTEM_ORIG = (
    "As an advanced reading comprehension assistant, your task is to analyze text passages "
    "and corresponding questions meticulously. Your response start after \"Thought: \", where "
    "you will methodically break down the reasoning process, illustrating how you arrive at "
    "conclusions. Conclude with \"Answer: \" to present a concise, definitive response, devoid "
    "of additional elaborations."
)

SYSTEM_MODIFIED = (
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

# ---------- One-shot ----------
ONE_SHOT_DOCS_LONG = (
    "Wikipedia Title: The Last Horse\nThe Last Horse (Spanish:El último caballo) is a 1950 "
    "Spanish comedy film directed by Edgar Neville starring Fernando Fernán Gómez.\n"
    "Wikipedia Title: Southampton\nThe University of Southampton, which was founded in 1862 "
    "and received its Royal Charter as a university in 1952, has over 22,000 students.\n"
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human "
    "Factors and Ergonomics at the University of Southampton."
)
ONE_SHOT_INPUT = ONE_SHOT_DOCS_LONG + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "
ONE_SHOT_OUTPUT_ORIG = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862. "
    "\nAnswer: 1862."
)
ONE_SHOT_OUTPUT_MODIFIED = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862."
    "\nIntermediate answers: [University of Southampton, 1862]"
    "\nAnswer: 1862."
)


# ---------- Excise old fact (same logic as oracle_a_fact_level.py) ----------
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


def extract_final(response_text):
    if "Answer:" in response_text:
        final = response_text.split("Answer:")[-1].strip()
    else:
        final = response_text.strip()
    return final


def parse_passages(context_str):
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
    n = 0
    pat = re.compile(rf"(?:(?<=^)|(?<=\s)){re.escape(str(old_seq))}\.\s")
    while True:
        m = pat.search(passage_text)
        if not m:
            break
        start = m.start()
        after = passage_text[m.end():]
        next_m = re.search(r"(?:(?<=\s)|(?<=^))\d+\.\s", after)
        end = m.end() + next_m.start() if next_m else len(passage_text)
        passage_text = passage_text[:start] + passage_text[end:]
        n += 1
    passage_text = re.sub(r"\s+", " ", passage_text).strip()
    return passage_text, n


def excise_facts_from_passages(passages, old_seqs):
    out = []
    for rank, text in passages:
        cur = text
        for s in old_seqs:
            cur, _ = excise_old_fact(cur, s)
        out.append((rank, cur))
    return out


def get_old_seqs(gt_record):
    return [
        h["old_seq"]
        for h in gt_record.get("hops", [])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None
    ]


def build_messages(passages_kept, query_text, system, one_shot_output):
    prompt_user = ""
    for _, doc in passages_kept:
        if doc.strip():
            prompt_user += f"Wikipedia Title: {doc}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": one_shot_output},
        {"role": "user", "content": prompt_user},
    ]


def call_gemini(client, messages):
    from google.genai.errors import ClientError, ServerError
    sysp = None
    contents = []
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
    if sysp:
        cfg.system_instruction = sysp
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
    return r.text if r.text is not None else ""


def run_variant(variant, system, one_shot_output, client, mh_gt, qmap, amap):
    """variant: 'v2' or 'v3'."""
    out_path = OUT_DIR / f"oa2_ablation_{variant}_results.json"
    existing = []
    done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume {variant}] {len(done)} done")

    todo = [q for q in mh_gt if q["query_id"] not in done]
    print(f"[pending {variant}] {len(todo)}")
    for i, q in enumerate(todo):
        qid = q["query_id"]
        old_seqs = get_old_seqs(q)
        ctx_path = RETRIEVED_DIR / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            continue
        ctx = json.load(open(ctx_path))
        passages = parse_passages(ctx)
        new_passages = excise_facts_from_passages(passages, old_seqs)
        query = qmap.get(qid, "")
        gt = amap.get(qid, "")
        messages = build_messages(new_passages, query, system, one_shot_output)
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid, "variant": variant,
            "raw_output": raw, "exact_match": em, "gt_answer": gt,
            "num_hops": q.get("num_hops"),
        })
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{variant} {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["v2", "v3", "both"], default="both")
    args = parser.parse_args()
    os.chdir("/home/yhchiang/MemoryAgentBench")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    if args.variant in ("v2", "both"):
        run_variant("v2", SYSTEM_MODIFIED, ONE_SHOT_OUTPUT_ORIG, client, mh_gt, qmap, amap)
    if args.variant in ("v3", "both"):
        run_variant("v3", SYSTEM_ORIG, ONE_SHOT_OUTPUT_MODIFIED, client, mh_gt, qmap, amap)


if __name__ == "__main__":
    main()
