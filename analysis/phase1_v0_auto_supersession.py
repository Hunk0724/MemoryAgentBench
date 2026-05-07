"""
Phase 1 V0 prototype: HippoRAG-v2 + auto-detected supersession (orig prompt).

Mechanism (deterministic, no LLM judge):
  1. Read OpenIE-extracted triples per chunk (already cached)
  2. Aggregate (subject, relation) → list of [(chunk_idx, object)]
  3. For each (S, R) with multiple distinct O across chunks, mark all O from
     earlier chunks as "superseded" (later chunk wins, ingestion order = newer)
  4. At query time: retrieve top-10 passages (existing cache)
  5. For each numbered fact in passage, check if it contains any superseded
     (subject, object) pair → if yes, excise that fact line
  6. Feed cleaned passages to LLM with orig prompt (matches OA2 / NC condition)

Auto-detection coverage: ~41% of GT chain_olds (vs OA2 oracle 100%)
False positive rate: ~1% (1/73 auto-detected don't match any GT old)

Expected EM gain: vanilla 22% → 25-35% (gains scale with auto-detection recall)

Reads:
  outputs/rag_retrieved/NV-Embed-v2/.../openie_results_ner_gemini-3.1-flash-lite-preview.json
  outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/.../query_X_context_0.json
  outputs/.../factconsolidation_mh_6k_*_results.json (for query text)
  analysis/results/mh_512_mquake_analysis.json

Writes:
  analysis/results/diagnostic/phase1_v0_auto_supersession_mh_results.json
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
OPENIE = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
MH_RESULTS = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
MH_RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT = BASE / "analysis/results/diagnostic/phase1_v0_auto_supersession_mh_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048

# === ORIG HippoRAG-v2 prompt (matches OA2 / NC orig regime) ===
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


def build_supersession_set():
    """Auto-detect superseded triples from OpenIE cache.

    Returns: list of {subject, relation, object} dicts that should be excised.
    """
    oie = json.load(open(OPENIE))
    sr_to_objs = defaultdict(list)
    for chunk_idx, doc in enumerate(oie['docs']):
        for t in doc.get('extracted_triples', []):
            if isinstance(t, list) and len(t) == 3:
                s, r, o = [str(x).strip() for x in t]
                sr_to_objs[(s.lower(), r.lower())].append((chunk_idx, o))

    superseded = []
    for sr, objs in sr_to_objs.items():
        # Find conflict candidates: (S, R) with >1 distinct O
        distinct_o = set(o for _, o in objs)
        if len(distinct_o) <= 1:
            continue
        # Latest chunk's O is "current"; earlier chunks' O are "superseded"
        latest_chunk = max(c for c, _ in objs)
        for c, o in objs:
            if c < latest_chunk:
                superseded.append({
                    'subject': sr[0], 'relation': sr[1], 'object': o,
                    'chunk': c, 'latest_chunk': latest_chunk,
                })
    return superseded


def excise_superseded_facts(passage_text, superseded_set):
    """Excise numbered facts from passage that match any superseded (subject, object) pair.

    Each numbered fact is "<seq>. <text>". Check if text contains both subject AND object
    of any superseded triple → if yes, excise the fact line.
    """
    # Find all numbered fact spans
    fact_pattern = re.compile(r"(?:^|(?<=\s))(\d+)\.\s")
    spans = []
    for m in fact_pattern.finditer(passage_text):
        spans.append((m.start(), m.end(), int(m.group(1))))

    if not spans:
        return passage_text, []

    # Build fact text per seq
    facts = []
    for i, (start, end_prefix, seq) in enumerate(spans):
        next_start = spans[i + 1][0] if i + 1 < len(spans) else len(passage_text)
        fact_text = passage_text[start:next_start]
        facts.append((seq, fact_text, start, next_start))

    # Identify which to excise
    to_excise = []
    for seq, fact_text, start, end in facts:
        ft_lower = fact_text.lower()
        for s in superseded_set:
            subj = s['subject']
            obj = s['object'].lower().strip()
            # Both subject and object must appear in fact text
            if subj in ft_lower and obj in ft_lower:
                # Verify length: subject ≥ 4 chars and object ≥ 3 chars to avoid trivial matches
                if len(subj) >= 4 and len(obj) >= 3:
                    to_excise.append((seq, start, end, s))
                    break

    # Excise (build new passage by skipping excised spans)
    if not to_excise:
        return passage_text, []

    excise_spans = sorted([(s[1], s[2]) for s in to_excise])
    # Merge overlaps
    merged = [excise_spans[0]]
    for st, en in excise_spans[1:]:
        if st <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], en))
        else:
            merged.append((st, en))

    # Build new text
    new_parts = []
    cursor = 0
    for st, en in merged:
        new_parts.append(passage_text[cursor:st])
        cursor = en
    new_parts.append(passage_text[cursor:])
    new_text = re.sub(r"\s+", " ", "".join(new_parts)).strip()

    excised_seqs = [s[0] for s in to_excise]
    return new_text, excised_seqs


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

    superseded_set = build_supersession_set()
    print(f"[setup] auto-detected superseded triples: {len(superseded_set)}")

    mh_gt = json.load(open(MH_GT))
    mh_results = json.load(open(MH_RESULTS))
    qmap = {e["query_id"]: e["query"] for e in mh_results["data"]}
    amap = {e["query_id"]: e["answer"] for e in mh_results["data"]}

    existing = []; done = set()
    if OUT.exists():
        existing = json.load(open(OUT))
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
        ctx_path = MH_RETRIEVED_DIR / f"query_{qid}_context_0.json"
        if not ctx_path.exists():
            continue
        ctx = json.load(open(ctx_path))
        passages = parse_passages(ctx)

        new_passages = []
        excised_log = []
        for rank, text in passages:
            new_text, excised = excise_superseded_facts(text, superseded_set)
            new_passages.append((rank, new_text))
            if excised:
                excised_log.append({'rank': rank, 'excised_seqs': excised})

        messages = build_messages(new_passages, qmap.get(qid, ""))
        gt_ans = amap.get(qid, "")
        try:
            raw = call_gemini(client, messages)
        except Exception as e:
            raw = f"ERROR: {e}"
        em = fuzzy_match(extract_final(raw), gt_ans)

        existing.append({
            "query_id": qid, "num_hops": q.get("num_hops"),
            "n_conflict": sum(1 for h in q['hops'] if h.get('conflict_type') == 'has_pair'),
            "excised_log": excised_log,
            "n_total_excised_seqs": sum(len(e['excised_seqs']) for e in excised_log),
            "raw_output": raw, "pred_answer": extract_final(raw),
            "gt_answer": gt_ans, "exact_match": em,
        })
        with open(OUT, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 10 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            avg_excised = sum(r['n_total_excised_seqs'] for r in existing) / len(existing)
            print(f"  [V0 {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}% avg_excised={avg_excised:.1f}")


if __name__ == "__main__":
    main()
