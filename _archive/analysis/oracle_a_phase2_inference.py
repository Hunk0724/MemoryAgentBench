"""
Oracle A Phase 2: Run LLM inference with filtered passages (old facts removed).

Reproduces the exact same prompt format as HippoRAG v2 QA:
  System: "As an advanced reading comprehension assistant..."
  User (one-shot): [Wikipedia Title docs + question]
  Assistant (one-shot): [example answer]
  User: "Wikipedia Title: {passage}\\n\\n...\\nQuestion: {query}\\nThought: "

LLM params: gpt-4o-mini, temperature=0, max_completion_tokens=2048, seed=0
"""

import json
import re
import os
import time
from pathlib import Path
from collections import defaultdict
from openai import OpenAI

# === Config ===
MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_TOKENS = 2048
SEED = 0

# === Paths ===
BASE = Path("/home/yhchiang/MemoryAgentBench")
SH_RESULTS = BASE / "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
MH_RESULTS = BASE / "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
SH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
CORRECTED_RANKS = BASE / "analysis/results/oracle_a_corrected_ranks.json"
OUT_DIR = BASE / "analysis/results/oracle_a"

os.makedirs(OUT_DIR, exist_ok=True)

# === HippoRAG v2 QA prompt template (from rag_qa_musique.py) ===
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

ONE_SHOT_INPUT = (
    ONE_SHOT_DOCS
    + "\n\nQuestion: When was Neville A. Stanton's employer founded?"
    + "\nThought: "
)

ONE_SHOT_OUTPUT = (
    "The employer of Neville A. Stanton is University of Southampton. "
    "The University of Southampton was founded in 1862. "
    "\nAnswer: 1862."
)


def parse_passages(context_str):
    """Parse retrieved context into dict {rank(int): text(str)}."""
    passages = {}
    parts = re.split(r'(Passage \d+:\n)', context_str)
    i = 0
    while i < len(parts):
        m = re.match(r'Passage (\d+):', parts[i])
        if m and i + 1 < len(parts):
            rank = int(m.group(1))
            passages[rank] = parts[i + 1].strip()
            i += 2
        else:
            if parts[i].strip():
                m2 = re.match(r'Passage (\d+):\n(.*)', parts[i], re.DOTALL)
                if m2:
                    passages[int(m2.group(1))] = m2.group(2).strip()
            i += 1
    return passages


def build_prompt(passages_dict, ranks_to_keep, query_text):
    """
    Build HippoRAG v2 QA prompt messages.

    passages_dict: {rank: text}
    ranks_to_keep: sorted list of passage ranks to include (original numbering)
    query_text: full factconsolidation query string
    """
    # Build prompt_user with Wikipedia Title format (same as HippoRAG qa())
    prompt_user = ""
    for rank in ranks_to_keep:
        prompt_user += f"Wikipedia Title: {passages_dict[rank]}\n\n"
    prompt_user += f"Question: {query_text}\nThought: "

    messages = [
        {"role": "system", "content": RAG_QA_SYSTEM},
        {"role": "user", "content": ONE_SHOT_INPUT},
        {"role": "assistant", "content": ONE_SHOT_OUTPUT},
        {"role": "user", "content": prompt_user},
    ]
    return messages


def extract_answer(response_text):
    """Extract answer from LLM response (after 'Answer:')."""
    if "Answer:" in response_text:
        return response_text.split("Answer:")[-1].strip()
    return response_text.strip()


def normalize(s):
    """Normalize for exact match comparison."""
    return s.strip().rstrip(".,;:!?\"'").strip().lower()


def exact_match(pred, gold):
    """Check exact match (normalized)."""
    return normalize(pred) == normalize(gold)


def run_oracle_a(client, task, corrected_entries, results_data, retrieved_dir):
    """Run Oracle A inference for SH or MH."""
    # Build query_id -> original query mapping from results
    query_map = {}
    for entry in results_data["data"]:
        qid = entry.get("query_id", 0)
        query_map[qid] = entry.get("query", "")

    usable = [e for e in corrected_entries if e["status"] == "usable"]
    print(f"\n{'='*60}")
    print(f"Oracle A Inference: {task} ({len(usable)} usable questions)")
    print(f"{'='*60}")

    results = []
    correct = 0
    total = 0
    errors = []

    for i, entry in enumerate(usable):
        qid = entry["query_id"]
        gt_answer = entry["gt_answer"]
        query_text = query_map.get(qid, "")

        if not query_text:
            errors.append(f"query_{qid}: no query text found")
            continue

        # Load passages
        ctx_path = retrieved_dir / f"query_{qid}_context_0.json"
        with open(ctx_path) as f:
            context_str = json.load(f)
        passages = parse_passages(context_str)

        # Determine ranks to remove and keep
        if task == "SH":
            ranks_to_remove = {entry["corrected_old_rank"]}
        else:  # MH
            ranks_to_remove = set(entry["corrected_old_ranks"])

        ranks_to_keep = sorted(r for r in passages.keys() if r not in ranks_to_remove)

        # Build prompt
        messages = build_prompt(passages, ranks_to_keep, query_text)

        # Call API
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                max_completion_tokens=MAX_TOKENS,
                seed=SEED,
            )
            raw_output = response.choices[0].message.content
            pred_answer = extract_answer(raw_output)
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        except Exception as e:
            errors.append(f"query_{qid}: API error: {e}")
            raw_output = f"ERROR: {e}"
            pred_answer = ""
            prompt_tokens = 0
            completion_tokens = 0

        em = exact_match(pred_answer, gt_answer)
        if em:
            correct += 1
        total += 1

        result_entry = {
            "query_id": qid,
            "gt_answer": gt_answer,
            "pred_answer": pred_answer,
            "raw_output": raw_output,
            "exact_match": em,
            "exact_match_before": entry.get("exact_match_before", None),
            "passages_removed": sorted(ranks_to_remove),
            "passages_kept": ranks_to_keep,
            "n_passages": len(ranks_to_keep),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

        if task == "MH":
            result_entry["num_hops"] = entry["num_hops"]
            result_entry["n_conflict"] = entry["n_conflict"]

        results.append(result_entry)

        # Progress
        status_char = "✓" if em else "✗"
        if (i + 1) % 10 == 0 or i == len(usable) - 1:
            print(f"  [{i+1}/{len(usable)}] Acc so far: {correct}/{total} = {correct/total*100:.1f}%")

    print(f"\n  Final: {correct}/{total} = {correct/total*100:.1f}%")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors:
            print(f"    {e}")

    return results


def print_summary(task, results, corrected_entries):
    """Print detailed summary with group breakdown."""
    usable = [e for e in corrected_entries if e["status"] == "usable"]
    non_usable = [e for e in corrected_entries if e["status"] != "usable"]

    print(f"\n{'='*60}")
    print(f"Oracle A Results Summary: {task}")
    print(f"{'='*60}")

    # Overall
    total = len(results)
    correct_after = sum(1 for r in results if r["exact_match"])
    correct_before = sum(1 for r in results if r.get("exact_match_before", False))

    print(f"\nUsable questions: {total}")
    print(f"Baseline Acc (before): {correct_before}/{total} = {correct_before/total*100:.1f}%")
    print(f"Oracle A Acc (after):  {correct_after}/{total} = {correct_after/total*100:.1f}%")
    print(f"Improvement:           +{correct_after - correct_before} questions (+{(correct_after-correct_before)/total*100:.1f}pp)")

    if task == "MH":
        # Group breakdown
        groups = defaultdict(list)
        for r in results:
            key = (r["num_hops"], r["n_conflict"])
            groups[key].append(r)

        print(f"\n--- Per-group breakdown ---")
        print(f"{'Group':<22} {'N':>3} {'Before':>8} {'After':>8} {'Δ':>6}")
        print("-" * 50)
        for key in sorted(groups.keys()):
            n_hops, n_conflict = key
            g = groups[key]
            n = len(g)
            before = sum(1 for r in g if r.get("exact_match_before", False))
            after = sum(1 for r in g if r["exact_match"])
            delta = after - before
            label = f"{n_hops}-hop, {n_conflict}-conflict"
            print(f"  {label:<20} {n:>3} {before:>3}/{n} ({before/n*100:4.0f}%) {after:>3}/{n} ({after/n*100:4.0f}%) {delta:>+4}")

    # Non-usable summary
    print(f"\nExcluded questions: {len(non_usable)}")
    status_counts = defaultdict(int)
    for e in non_usable:
        status_counts[e["status"]] += 1
    for s, c in sorted(status_counts.items()):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    os.chdir("/home/yhchiang/MemoryAgentBench")

    # Load API key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        # Try .env
        env_path = Path("/home/yhchiang/MemoryAgentBench/.env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found")

    client = OpenAI(api_key=api_key)

    # Load corrected ranks
    with open(CORRECTED_RANKS) as f:
        corrected = json.load(f)

    # Load original results (for query text)
    with open(SH_RESULTS) as f:
        sh_results = json.load(f)
    with open(MH_RESULTS) as f:
        mh_results = json.load(f)

    # === Run SH ===
    sh_oracle_results = run_oracle_a(
        client, "SH", corrected["sh"], sh_results, SH_RETRIEVED_DIR
    )

    # Save SH results
    sh_out = OUT_DIR / "oracle_a_sh_results.json"
    with open(sh_out, "w") as f:
        json.dump(sh_oracle_results, f, ensure_ascii=False, indent=2)
    print(f"\nSH results saved to {sh_out}")

    print_summary("SH", sh_oracle_results, corrected["sh"])

    # === Run MH ===
    mh_oracle_results = run_oracle_a(
        client, "MH", corrected["mh"], mh_results, MH_RETRIEVED_DIR
    )

    # Save MH results
    mh_out = OUT_DIR / "oracle_a_mh_results.json"
    with open(mh_out, "w") as f:
        json.dump(mh_oracle_results, f, ensure_ascii=False, indent=2)
    print(f"\nMH results saved to {mh_out}")

    print_summary("MH", mh_oracle_results, corrected["mh"])
