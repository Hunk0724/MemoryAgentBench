"""
NC + keep-chain-old experiment (FC-MH, orig prompt).

The mirror of OA2:
  - OA2:  remove this question's chain_olds from top-10 passages, keep all other olds
          → 55% on FC-MH orig prompt
  - NC:   remove ALL chain_olds globally (165 olds across SH+MH)
          → 60% on FC-MH orig prompt
  - THIS: remove all NON-chain olds globally, KEEP this question's chain_olds
          → ?

Goal: isolate the "chain_old in HippoRAG retrieval" effect when no other olds exist
anywhere in corpus. Helps decouple "chain_old contribution" from "non-chain old noise".

Predictions:
  - If close to vanilla 22%: chain_old is sufficient to break LLM
  - If close to NC 60%: chain_old in retrieval has minor effect when surrounded by clean
  - Likely between: 27-40% (chain_old is dominant local conflict source)

Reads same MH GT + retrieval cache as NC origprompt baseline.
Writes: analysis/results/diagnostic/nc_keep_chain_old_origprompt_mh_results.json
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
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT_PATH = OUT_DIR / "nc_keep_chain_old_origprompt_mh_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# ORIG HippoRAG-v2 prompt (same as OA2 orig / NC orig / Sim-OB orig)
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
    "and received its Royal Charter as a university in 1952, has over 22,000 students. The "
    "university is ranked in the top 100 research universities in the world in the Academic "
    "Ranking of World Universities 2010.\n"
    "Wikipedia Title: Stanton Township, Champaign County, Illinois\nStanton Township is a "
    "township in Champaign County, Illinois, USA.\n"
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
        if not m: break
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
    log = []
    for rank, text in passages:
        cur = text
        for s in old_seqs:
            cur, n = excise_old_fact(cur, s)
            if n:
                log.append({"rank": rank, "old_seq": s, "n_removed": n})
        out.append((rank, cur))
    return out, log


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
    if sysp:
        cfg.system_instruction = sysp
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


def collect_global_old_seqs():
    olds = set()
    for q in json.load(open(MH_GT)):
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
                olds.add(h["old_seq"])
    for q in json.load(open(SH_GT)):
        if q.get("conflict_type") == "has_pair" and q.get("old_seq") is not None:
            olds.add(q["old_seq"])
    return sorted(olds)


def get_chain_old_seqs(q):
    return [
        h["old_seq"]
        for h in q.get("hops", [])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None
    ]


def main():
    os.chdir("/home/yhchiang/MemoryAgentBench")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    global_olds = set(collect_global_old_seqs())
    print(f"[setup] global old seqs: {len(global_olds)}")

    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    existing = []; done = set()
    if OUT_PATH.exists():
        existing = json.load(open(OUT_PATH))
        done = {r["query_id"] for r in existing}
        print(f"[resume] {len(done)} done")

    todo = [q for q in mh_gt if q["query_id"] not in done]
    print(f"[pending] {len(todo)}")
    if not todo: return

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    for i, q in enumerate(todo):
        qid = q["query_id"]
        chain_olds = set(get_chain_old_seqs(q))
        olds_to_remove = sorted(global_olds - chain_olds)  # KEY: invert NC logic

        ctx_path = MH_RETRIEVED_DIR / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            print(f"  [skip qid={qid}] no retrieved cache")
            continue
        with open(ctx_path) as f:
            ctx_str = json.load(f)
        passages = parse_passages(ctx_str)

        new_passages, log = excise_facts_from_passages(passages, olds_to_remove)
        n_removed = sum(e["n_removed"] for e in log)

        # Verify chain_old is still in retrieved passages (if any)
        chain_olds_in_top10 = 0
        for s in chain_olds:
            for _, txt in new_passages:
                if re.search(rf"(?:^|\s){s}\.\s", txt):
                    chain_olds_in_top10 += 1; break

        messages = build_messages(new_passages, qmap.get(qid, ""))
        gt_ans = amap.get(qid, "")
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"

        final = extract_final(raw)
        em = fuzzy_match(final, gt_ans)

        existing.append({
            "query_id": qid,
            "chain_old_seqs": sorted(chain_olds),
            "chain_olds_kept_in_top10": chain_olds_in_top10,
            "n_total_olds_excised": n_removed,
            "n_olds_to_remove": len(olds_to_remove),
            "raw_output": raw,
            "pred_answer": final,
            "gt_answer": gt_ans,
            "exact_match": em,
            "num_hops": q.get("num_hops"),
            "n_conflict": sum(1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair"),
        })
        with open(OUT_PATH, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


if __name__ == "__main__":
    main()
