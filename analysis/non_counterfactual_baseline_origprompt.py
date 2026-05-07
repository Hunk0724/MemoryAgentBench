"""
Non-counterfactual baseline + ORIGINAL HippoRAG-v2 prompt (advisor 0422 原意對齊版).

Companion to `non_counterfactual_baseline.py` but uses the *unmodified*
HippoRAG-v2 inference prompt (the one used by RPT / PAT / RPT-min / OA1 /
OA2 origprompt), so that this measurement is the true "vanilla HippoRAG-v2
multi-hop ceiling under no-conflict context".

Difference vs `non_counterfactual_baseline.py` (modified prompt):
  - System prompt: original HippoRAG-v2 wording (no "Intermediate answers"
    trailer requirement).
  - One-shot output: original (no [a, b, c] list).

Reads / Writes:
  Same retrieval / GT inputs.
  Output: analysis/results/diagnostic/non_counterfactual_baseline_origprompt_{sh,mh}_results.json

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

# ---------- ORIGINAL HippoRAG-v2 prompt (matches oracle_a_fact_level_origprompt.py) ----------
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
ONE_SHOT_INPUT = ONE_SHOT_DOCS + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "
ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862. "
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


def extract_final(response_text):
    """Original prompt has no 'Intermediate answers' field — only Answer."""
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
        out_path = OUT_DIR / "non_counterfactual_baseline_origprompt_sh_results.json"
    else:
        gt = json.load(open(MH_GT))
        results_data = json.load(open(MH_RESULTS))
        retrieved_dir = MH_RETRIEVED_DIR
        out_path = OUT_DIR / "non_counterfactual_baseline_origprompt_mh_results.json"

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

        new_passages, log = excise_facts_from_passages(passages, global_olds)
        n_removed = sum(e["n_removed"] for e in log)

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

        final = extract_final(raw)
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
    print(f"[setup] global old seqs: {len(global_olds)}")

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    run_task("MH", client, global_olds)
    run_task("SH", client, global_olds)


if __name__ == "__main__":
    main()
