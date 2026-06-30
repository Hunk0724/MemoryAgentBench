"""
Perfect Annotation Test (PAT) for HippoRAG-v2 × Gemini 3.1 Flash-Lite.

Setup (per question):
  1. Keep all retrieved top-10 passages (no removal, unlike Oracle A).
  2. Use MQUAKE-CF ground truth to label fact lines:
       - Lines starting with "<gt_seq>." get prefixed with "[CURRENT FACT] "
       - Lines starting with "<old_seq>." get prefixed with "[OUTDATED FACT] "
       - Other lines unchanged.
  3. Prepend an explicit annotation-explanation paragraph to the user prompt
     (NOT the system prompt — keeps system+one-shot consistent with original HippoRAG).
  4. Run Gemini 3.1 Flash-Lite via Vertex global, same temperature/max_tokens
     as Oracle A so results are directly comparable.

Sample: same usable subset as Oracle A (SH=64, MH=66) so we can compare
        vanilla / Oracle A / PAT side by side.

Outputs:
  analysis/results/oracle_a_gemini/pat_sh_results.json
  analysis/results/oracle_a_gemini/pat_mh_results.json
"""
import json
import os
import re
import time
from pathlib import Path
from collections import defaultdict
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

# === Config ===
MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# === Paths ===
BASE = Path("/home/yhchiang/MemoryAgentBench")
SH_RESULTS  = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
MH_RESULTS  = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
SH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
SH_ANALYSIS = BASE / "analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json"
MH_ANALYSIS = BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"
CORRECTED_RANKS = BASE / "analysis/results/oracle_a_gemini/corrected_ranks.json"
OUT_DIR = BASE / "analysis/results/oracle_a_gemini"

os.makedirs(OUT_DIR, exist_ok=True)

# === HippoRAG v2 QA prompt (system + one-shot,不變) ===
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
ONE_SHOT_INPUT  = ONE_SHOT_DOCS + "\n\nQuestion: When was Neville A. Stanton's employer founded?\nThought: "
ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862. "
    "\nAnswer: 1862."
)

# === PAT-specific annotation explanation,放在 user prompt 開頭 ===
PAT_INSTRUCTION = (
    "Some facts in the context below have been pre-annotated:\n"
    "- [CURRENT FACT] marks information that is up-to-date.\n"
    "- [OUTDATED FACT] marks information that has been superseded by a later statement.\n\n"
    "When answering, use [CURRENT FACT] as the source of truth. "
    "You may reference [OUTDATED FACT] only if the question explicitly asks about historical states.\n\n"
)


# === Helpers ===
def parse_passages(s):
    """Parse 'Passage 1:\n...\nPassage 2:\n...' into {rank: text}."""
    out = {}
    parts = re.split(r'(Passage \d+:\n)', s)
    for i in range(len(parts) - 1):
        m = re.match(r'Passage (\d+):', parts[i])
        if m and i + 1 < len(parts):
            out[int(m.group(1))] = parts[i + 1].strip()
    return out


_FACT_NUMBER_RE = re.compile(r'(^|\s)(\d{1,4})\.\s')


def annotate_passage(text, current_seqs: set, outdated_seqs: set):
    """Prefix [CURRENT FACT] / [OUTDATED FACT] before fact serial numbers in `text`.

    Passage chunks are single-line strings where fact lines look like:
        "... 75. <fact A> 76. <fact B> 77. <fact C> ..."
    so we use a regex that matches `<ws_or_start><digits>. ` (digits up to 4),
    same boundary convention as Phase 1's `find_fact_in_passages_numbered`.
    """
    def repl(m):
        prefix_ws = m.group(1)  # may be '' (string start) or whitespace
        seq = int(m.group(2))
        if seq in current_seqs:
            return f"{prefix_ws}[CURRENT FACT] {seq}. "
        if seq in outdated_seqs:
            return f"{prefix_ws}[OUTDATED FACT] {seq}. "
        return m.group(0)
    return _FACT_NUMBER_RE.sub(repl, text)


def build_prompt(passages_dict, ranks_to_keep, query_text, current_seqs, outdated_seqs):
    """Build messages with PAT annotation."""
    prompt_user = PAT_INSTRUCTION  # ← 注入 annotation 說明
    for rank in ranks_to_keep:
        ann_passage = annotate_passage(passages_dict[rank], current_seqs, outdated_seqs)
        prompt_user += f"Wikipedia Title: {ann_passage}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "

    return [
        {"role": "system",    "content": RAG_QA_SYSTEM},
        {"role": "user",      "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user",      "content": prompt_user},
    ]


def call_gemini(client, messages, model=MODEL):
    """Issue a Gemini call (system_instruction + contents) with 429/503 retry."""
    sys_inst, contents = None, []
    for m in messages:
        if m["role"] == "system":
            sys_inst = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user",  "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
    cfg = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if sys_inst:
        cfg.system_instruction = sys_inst

    for attempt in range(10):
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=cfg)
            break
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == 9:
                raise
            mtch = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(mtch.group(1)) + 2 if mtch else min(2 ** attempt * 5, 60))
    text = resp.text if resp.text is not None else ""
    um = resp.usage_metadata
    return text, getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)


def extract_answer(text):
    return text.split("Answer:")[-1].strip() if "Answer:" in text else text.strip()


def normalize(s):
    return s.strip().rstrip(".,;:!?\"'").strip().lower()


def exact_match(pred, gold):
    return normalize(pred) == normalize(gold)


# === Build per-question (current_seqs, outdated_seqs) from MQUAKE analysis ===
def build_label_sets(task: str):
    """Return {query_id: (current_seqs:set, outdated_seqs:set)}."""
    if task == "SH":
        analysis = json.load(open(SH_ANALYSIS))
        out = {}
        for e in analysis:
            qid = e["query_id"]
            curr = {e["gt_seq"]} if e.get("gt_seq") is not None else set()
            old  = {e["old_seq"]} if e.get("old_seq") is not None else set()
            out[qid] = (curr, old)
        return out
    else:  # MH
        analysis = json.load(open(MH_ANALYSIS))
        out = {}
        for e in analysis:
            qid = e["query_id"]
            curr, old = set(), set()
            for h in e["hops"]:
                if h.get("gt_seq") is not None:
                    curr.add(h["gt_seq"])
                if h.get("old_seq") is not None:
                    old.add(h["old_seq"])
            out[qid] = (curr, old)
        return out


# === Run ===
def run_pat(client, task, corrected_entries, results_data, retrieved_dir, label_sets):
    """Run PAT inference on the same usable subset as Oracle A."""
    query_map = {entry["query_id"]: entry["query"] for entry in results_data["data"]}
    em_before_map = {entry["query_id"]: bool(entry.get("exact_match", False))
                     for entry in results_data["data"]}

    usable = [e for e in corrected_entries if e["status"] == "usable"]
    print(f"\n{'='*60}\nPAT Inference: {task} ({len(usable)} usable questions)\n{'='*60}")

    results = []
    correct = 0
    errors = []
    for i, entry in enumerate(usable):
        qid = entry["query_id"]
        gt_answer = entry["gt_answer"]
        query_text = query_map.get(qid, "")
        if not query_text:
            errors.append(f"query_{qid}: no query text"); continue

        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        passages = parse_passages(json.load(open(ctx_path)))
        # PAT 不移除 — keep all 10 ranks
        ranks_to_keep = sorted(passages.keys())
        curr_seqs, old_seqs = label_sets.get(qid, (set(), set()))

        messages = build_prompt(passages, ranks_to_keep, query_text, curr_seqs, old_seqs)

        try:
            raw_output, ptok, ctok = call_gemini(client, messages)
            pred_answer = extract_answer(raw_output)
        except Exception as e:
            errors.append(f"query_{qid}: API error: {e}")
            raw_output = f"ERROR: {e}"
            pred_answer = ""
            ptok = ctok = 0

        em = exact_match(pred_answer, gt_answer)
        if em:
            correct += 1

        result_entry = {
            "query_id": qid,
            "gt_answer": gt_answer,
            "pred_answer": pred_answer,
            "raw_output": raw_output,
            "exact_match": em,
            "exact_match_before": em_before_map.get(qid, False),
            "n_current_facts_marked": len(curr_seqs),
            "n_outdated_facts_marked": len(old_seqs),
            "n_passages": len(ranks_to_keep),
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        }
        if task == "MH":
            result_entry["num_hops"]  = entry["num_hops"]
            result_entry["n_conflict"] = entry["n_conflict"]
        results.append(result_entry)

        if (i + 1) % 10 == 0 or i == len(usable) - 1:
            total = i + 1
            print(f"  [{total}/{len(usable)}] Acc so far: {correct}/{total} = {correct/total*100:.1f}%")

    print(f"\n  Final: {correct}/{len(usable)} = {correct/len(usable)*100:.1f}%")
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"    {e}")
    return results


def print_summary(task, results):
    n = len(results)
    after  = sum(1 for r in results if r["exact_match"])
    before = sum(1 for r in results if r.get("exact_match_before", False))
    print(f"\n{'='*60}\nPAT Results Summary: {task}\n{'='*60}")
    print(f"Usable n: {n}")
    print(f"Baseline (vanilla on this subset): {before}/{n} = {before/n*100:.1f}%")
    print(f"PAT Acc:                           {after}/{n} = {after/n*100:.1f}%")
    print(f"Improvement (vs vanilla):          +{after-before} (+{(after-before)/n*100:.1f} pp)")

    if task == "MH":
        groups = defaultdict(list)
        for r in results:
            groups[(r["num_hops"], r["n_conflict"])].append(r)
        print(f"\n--- Per-group breakdown (MH) ---")
        print(f"{'Group':<22} {'N':>3} {'Before':>9} {'PAT':>9} {'Δ':>5}")
        for k in sorted(groups):
            g = groups[k]
            n_g = len(g)
            b = sum(1 for r in g if r.get("exact_match_before", False))
            a = sum(1 for r in g if r["exact_match"])
            label = f"{k[0]}-hop, {k[1]}-conflict"
            print(f"  {label:<20} {n_g:>3} {b:>3}/{n_g} ({b/n_g*100:4.0f}%) {a:>3}/{n_g} ({a/n_g*100:4.0f}%) {a-b:>+4}")


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    corrected = json.load(open(CORRECTED_RANKS))
    sh_results_data = json.load(open(SH_RESULTS))
    mh_results_data = json.load(open(MH_RESULTS))
    sh_labels = build_label_sets("SH")
    mh_labels = build_label_sets("MH")

    sh_pat = run_pat(client, "SH", corrected["sh"], sh_results_data, SH_RETRIEVED_DIR, sh_labels)
    mh_pat = run_pat(client, "MH", corrected["mh"], mh_results_data, MH_RETRIEVED_DIR, mh_labels)

    json.dump(sh_pat, open(OUT_DIR / "pat_sh_results.json", "w"), ensure_ascii=False, indent=2)
    json.dump(mh_pat, open(OUT_DIR / "pat_mh_results.json", "w"), ensure_ascii=False, indent=2)

    print_summary("SH", sh_pat)
    print_summary("MH", mh_pat)
    print(f"\nSaved to {OUT_DIR}/pat_{{sh,mh}}_results.json")
