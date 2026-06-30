"""
Sim-OB grad v2 — clean variable isolation with ORIG HippoRAG-v2 prompt.

Three modes that progressively introduce variables:
  A. chain_only_olds : ctx = chain_new + chain_old only (no other distractors)
                       → tests pure conflict-pair effect, no noise
  B. grad_pure       : ctx = chain_new + k distractors, distractor pool excludes
                       BOTH chain_new AND chain_old of this question
                       k ∈ {10, 50, 100, 200, 447}, sources ∈ {random, ppr-nearby}
                       → tests pure noise tolerance with chain_old removed
  C. grad_injection  : ctx = chain_new + ALL non_chain_pure + n chain_olds
                       n ∈ {0, 1, ..., min(num_conflict_hops, 4)} cumulative in hop order
                       → measures dose response of chain_old conflict on saturated noise

All use ORIG prompt (long ONE_SHOT_DOCS, no Intermediate answers trailer) to
align with OA2 origprompt / NC origprompt regime.

Reads:
  analysis/results/mh_512_mquake_analysis.json
  analysis/contexts/factconsolidation_6k_context.txt
  outputs/rag_retrieved/.../query_{qid}_context_0.json   (PPR cache)

Writes:
  analysis/results/diagnostic/sim_ob_grad_v2_<mode>_results.json
"""

import argparse
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
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_DIR = BASE / "analysis/results/diagnostic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048
NOISE_LEVELS_PURE = [10, 50, 100, 200, 447]
SOURCES = ["random", "ppr-nearby"]
SEED = 42

# ---------- ORIG HippoRAG-v2 prompt (matches OA2 origprompt / sim_ob_chain_only_origprompt) ----------
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
    if "Answer:" in response_text:
        return response_text.split("Answer:")[-1].strip()
    return response_text.strip()


def load_facts():
    facts = {}
    for line in open(CONTEXT_FILE):
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
    seen = set(); out = []
    for s in seqs:
        if s not in seen:
            seen.add(s); out.append(s)
    return out


def get_chain_seqs(q):
    """Return (chain_new_seqs sorted, chain_old_seqs in hop order)."""
    chain_new = []
    chain_old = []
    for h in sorted(q.get("hops", []), key=lambda x: x.get("hop_idx", 0)):
        if h.get("gt_seq") is not None:
            chain_new.append(h["gt_seq"])
        if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
            chain_old.append(h["old_seq"])
    return chain_new, chain_old


def build_passage_body(seqs, facts):
    seqs_sorted = sorted(set(seqs))
    return "\n".join(f"{s}. {facts[s]}" for s in seqs_sorted if s in facts)


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
            if code not in (429, 503) or attempt == 9:
                raise
            mret = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(mret.group(1)) + 2 if mret else min(2 ** attempt * 5, 60))
    text = r.text if r.text is not None else ""
    um = r.usage_metadata
    return text, getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)


# ===== Mode runners =====

def run_chain_only_olds(client, mh_gt, qmap, amap, facts):
    out_path = OUT_DIR / "sim_ob_grad_v2_chain_only_olds_results.json"
    existing = []; done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume chain_only_olds] {len(done)} done")

    todo = [q for q in mh_gt if q["query_id"] not in done]
    print(f"[pending chain_only_olds] {len(todo)}")
    for i, q in enumerate(todo):
        qid = q["query_id"]
        chain_new, chain_old = get_chain_seqs(q)
        if not chain_new:
            continue
        all_seqs = list(chain_new) + list(chain_old)
        body = build_passage_body(all_seqs, facts)
        messages = build_messages(body, qmap.get(qid, ""))
        gt = amap.get(qid, "")
        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid,
            "num_hops": q.get("num_hops"),
            "n_conflict": len(chain_old),
            "n_chain_new": len(chain_new),
            "n_chain_old": len(chain_old),
            "raw_output": raw, "pred_answer": extract_final(raw),
            "gt_answer": gt, "exact_match": em,
            "prompt_tokens": ptok, "completion_tokens": ctok,
        })
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


def run_grad_pure(client, mh_gt, qmap, amap, facts):
    out_path = OUT_DIR / "sim_ob_grad_v2_grad_pure_results.json"
    existing = []; done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {(r["query_id"], r["source"], r["noise_level"]) for r in existing}
        print(f"[resume grad_pure] {len(done)} configs done")

    todo = []
    for q in mh_gt:
        qid = q["query_id"]
        chain_new, chain_old = get_chain_seqs(q)
        if not chain_new:
            continue
        excluded = set(chain_new) | set(chain_old)
        non_chain_pure = [s for s in facts.keys() if s not in excluded]
        ppr_order = get_ppr_ordered_seqs(qid)
        ppr_pure = [s for s in ppr_order if s not in excluded]
        seen = set(ppr_pure)
        for s in non_chain_pure:
            if s not in seen:
                ppr_pure.append(s); seen.add(s)

        for source in SOURCES:
            for k in NOISE_LEVELS_PURE:
                if (qid, source, k) in done:
                    continue
                eff_k = min(k, len(non_chain_pure))
                if source == "random":
                    rng = random.Random(SEED + qid * 1000 + k)
                    distractors = rng.sample(non_chain_pure, eff_k)
                else:
                    distractors = ppr_pure[:eff_k]
                todo.append({
                    "query_id": qid, "source": source, "noise_level": k,
                    "actual_k": eff_k, "chain_new": chain_new, "chain_old": chain_old,
                    "distractors": distractors,
                })

    print(f"[pending grad_pure] {len(todo)} configs")
    for i, cfg in enumerate(todo):
        qid = cfg["query_id"]
        all_seqs = list(cfg["chain_new"]) + list(cfg["distractors"])
        body = build_passage_body(all_seqs, facts)
        messages = build_messages(body, qmap.get(qid, ""))
        gt = amap.get(qid, "")
        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid, "source": cfg["source"], "noise_level": cfg["noise_level"],
            "actual_k": cfg["actual_k"], "n_chain_new": len(cfg["chain_new"]),
            "n_chain_old_excluded": len(cfg["chain_old"]),
            "num_hops": next((q["num_hops"] for q in mh_gt if q["query_id"] == qid), None),
            "raw_output": raw, "pred_answer": extract_final(raw),
            "gt_answer": gt, "exact_match": em,
            "prompt_tokens": ptok, "completion_tokens": ctok,
        })
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 20 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} {cfg['source']} k={cfg['noise_level']} "
                  f"acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


def run_grad_injection(client, mh_gt, qmap, amap, facts):
    out_path = OUT_DIR / "sim_ob_grad_v2_grad_injection_results.json"
    existing = []; done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {(r["query_id"], r["n_old_injected"]) for r in existing}
        print(f"[resume grad_injection] {len(done)} configs done")

    todo = []
    for q in mh_gt:
        qid = q["query_id"]
        chain_new, chain_old = get_chain_seqs(q)
        if not chain_new:
            continue
        excluded = set(chain_new) | set(chain_old)
        non_chain_pure = [s for s in facts.keys() if s not in excluded]
        # Inject n = 0..len(chain_old) cumulatively in hop order
        for n in range(len(chain_old) + 1):
            if (qid, n) in done:
                continue
            injected_olds = list(chain_old[:n])
            todo.append({
                "query_id": qid, "n_old_injected": n,
                "chain_new": chain_new, "injected_olds": injected_olds,
                "non_chain_pure": non_chain_pure,
            })

    print(f"[pending grad_injection] {len(todo)} configs")
    for i, cfg in enumerate(todo):
        qid = cfg["query_id"]
        all_seqs = list(cfg["chain_new"]) + list(cfg["non_chain_pure"]) + list(cfg["injected_olds"])
        body = build_passage_body(all_seqs, facts)
        messages = build_messages(body, qmap.get(qid, ""))
        gt = amap.get(qid, "")
        try:
            raw, ptok, ctok = call_gemini(client, messages)
        except Exception as e:
            raw, ptok, ctok = f"ERROR: {e}", 0, 0
        em = fuzzy_match(extract_final(raw), gt)
        existing.append({
            "query_id": qid, "n_old_injected": cfg["n_old_injected"],
            "n_chain_new": len(cfg["chain_new"]),
            "n_chain_old_total": next(
                (sum(1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair")
                 for q in mh_gt if q["query_id"] == qid), 0),
            "n_non_chain_pure": len(cfg["non_chain_pure"]),
            "num_hops": next((q["num_hops"] for q in mh_gt if q["query_id"] == qid), None),
            "raw_output": raw, "pred_answer": extract_final(raw),
            "gt_answer": gt, "exact_match": em,
            "prompt_tokens": ptok, "completion_tokens": ctok,
        })
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{i+1}/{len(todo)}] qid={qid} n_inject={cfg['n_old_injected']} "
                  f"acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["chain_only_olds", "grad_pure", "grad_injection", "all"],
                        default="all")
    args = parser.parse_args()
    os.chdir("/home/yhchiang/MemoryAgentBench")

    facts = load_facts()
    print(f"Loaded {len(facts)} facts")
    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    if args.mode in ("chain_only_olds", "all"):
        run_chain_only_olds(client, mh_gt, qmap, amap, facts)
    if args.mode in ("grad_pure", "all"):
        run_grad_pure(client, mh_gt, qmap, amap, facts)
    if args.mode in ("grad_injection", "all"):
        run_grad_injection(client, mh_gt, qmap, amap, facts)


if __name__ == "__main__":
    main()
