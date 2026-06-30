"""Option 0 smoke: reconstruct source sentence per fact (FC numbered-list
structure), feed SENTENCES to LLM judge instead of stringified triples.

Hypothesis: LLM judge fails at production scale because OpenIE produces
inconsistent relation surface forms in (s, r, o) triples (e.g., "author"
vs "was authored by"). If we feed the original natural sentence instead,
surface is consistent and LLM should group conflicts correctly.

Validation:
  - 5 MH queries × top-K=30 facts (cosine pre-filter), but each fact
    represented as its SOURCE SENTENCE from the FC numbered-list passage
  - Compare recall vs triple-form smoke (was 20% at K=30)
  - If sentence form recall ≥ 70%, surface variation IS the root cause
    and architectural fix (PropRAG-style or relation alias) is justified.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from methods.hipporag.llm.gemini_llm import CacheGemini
from methods.hipporag.utils.misc_utils import compute_mdhash_id, text_processing
from methods.hipporag.v2_llm_judge import LLMJudgeDetector

BASE = Path("/home/yhchiang/MemoryAgentBench")
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
FACT_PARQUET = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/fact_embeddings/vdb_fact.parquet"
OPENIE = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
SUPERSESSION = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/supersession_index.json"
OUT = BASE / "analysis/results/phase_v1/smoke_v2_sentences.json"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip().rstrip(".,;:!?\"'"))


def split_passage_to_sentences(passage: str) -> Dict[int, str]:
    """Split FC numbered-list passage into {seq_number_in_passage: sentence}.

    FC passages look like:
      "Here is a list of facts:\\n0. Thomas Kyd was born in London. 1. The chairperson..."

    Returns dict mapping the in-passage serial number to its sentence text.
    """
    # Find all "<num>. " markers
    markers = [(m.start(), m.end(), int(m.group(1)))
               for m in re.finditer(r"(\d+)\.\s+", passage)]
    result = {}
    for i, (start, end, num) in enumerate(markers):
        sent_start = end  # text after "N. "
        sent_end = markers[i + 1][0] if i + 1 < len(markers) else len(passage)
        sent = passage[sent_start:sent_end].strip()
        # Strip trailing period(s) and whitespace
        sent = re.sub(r"[\s.]+$", "", sent)
        if sent:
            result[num] = sent
    return result


def build_fact_to_sentence_map(openie_data: dict) -> Dict[str, str]:
    """For each fact_key in OpenIE results, find the source sentence.

    Returns dict: fact_key -> source_sentence (natural text from passage).
    Falls back to formatted triple if sentence not found.
    """
    fact_to_sent = {}
    n_matched = 0
    n_total = 0
    for doc in openie_data["docs"]:
        passage = doc.get("passage", "")
        sentences = split_passage_to_sentences(passage)
        for triple in doc.get("extracted_triples", []):
            if not (isinstance(triple, (list, tuple)) and len(triple) == 3):
                continue
            s_raw, r_raw, o_raw = [str(x).strip() for x in triple]
            if not s_raw or not r_raw or not o_raw:
                continue
            n_total += 1
            # HippoRAG applies text_processing BEFORE hashing → must match.
            triple_processed = [text_processing(x) for x in (s_raw, r_raw, o_raw)]
            fact_key = compute_mdhash_id(content=str(tuple(triple_processed)),
                                          prefix="fact-")
            # Find source sentence using RAW (un-processed) s/o for substring match
            # against original passage text.
            s, o = s_raw, o_raw
            s_norm, o_norm = s.lower(), o.lower()
            best_sent = None
            for num, sent in sentences.items():
                sent_low = sent.lower()
                if s_norm in sent_low and o_norm in sent_low:
                    best_sent = sent
                    break
            if best_sent:
                fact_to_sent[fact_key] = best_sent
                n_matched += 1
            else:
                # Fallback to formatted triple
                fact_to_sent[fact_key] = f"{s_raw} {r_raw} {o_raw}"
    print(f"[sentence reconstruction] matched {n_matched}/{n_total} triples to source sentences "
          f"({n_matched * 100 / max(1, n_total):.1f}%)")
    return fact_to_sent


def text_match(short_text: str, long_text: str) -> bool:
    s, l = norm(short_text), norm(long_text)
    if len(s) < 5 or len(l) < 5:
        return False
    return s in l or l in s


def fact_match(fact_a: str, fact_b: str) -> bool:
    """Token-level Jaccard on content words (≥50% overlap)."""
    import unicodedata
    def tokens(text):
        text = text.lower()
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                       if unicodedata.category(c) != 'Mn')
        text = re.sub(r"[^\w\s]", " ", text)
        stops = {'the', 'is', 'was', 'are', 'were', 'of', 'in', 'on', 'at', 'by',
                 'to', 'from', 'with', 'as', 'be', 'a', 'an', 'and', 'or',
                 'this', 'that', 'these', 'those', 'his', 'her', 'their',
                 'author', 'authored', 'created', 'married', 'spouse', 'citizen',
                 'born', 'died', 'employed', 'founder', 'director', 'chairperson',
                 'position', 'plays', 'associated', 'language', 'official',
                 'capital', 'located', 'country', 'continent', 'sport', 'place',
                 'death', 'work', 'works', 'field', 'ceo', 'chief', 'executive',
                 'officer', 'wrote', 'written', 'composed', 'developed', 'directed',
                 'speaks', 'owned', 'founded'}
        return {t for t in text.split() if t not in stops and len(t) >= 3}
    ta = tokens(fact_a)
    tb = tokens(fact_b)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def get_latest_g11_dump_dir() -> Path:
    candidates = sorted(BASE.glob("monitoring_logs/*g11_phase2_dump"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError("no G.11 dump dir found in monitoring_logs/")
    return candidates[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k-facts", type=int, default=30)
    args = ap.parse_args()

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("HF_HOME", "/home/yhchiang/MemoryAgentBench/.cache/huggingface")
    os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")

    print(f"[load] GT: {GT}")
    gt = json.load(open(GT))

    print(f"[load] OpenIE results: {OPENIE}")
    oie = json.load(open(OPENIE))
    print(f"  n_chunks={len(oie['docs'])}")

    print(f"[build] fact_key → source_sentence map")
    fact_to_sentence = build_fact_to_sentence_map(oie)
    print(f"  n_fact_keys with sentences: {len(fact_to_sentence)}")

    print(f"[load] fact parquet: {FACT_PARQUET}")
    df = pd.read_parquet(FACT_PARQUET)
    # We still need the triple content for triple-form fallback, but for THIS smoke
    # we'll override fact_content_map with the sentence form
    fact_content_map_sentences = {fk: fact_to_sentence.get(fk, "(missing)")
                                   for fk in df["hash_id"]}
    fact_keys_in_order = list(df["hash_id"])
    fact_emb_matrix = np.stack(df["embedding"].values).astype(np.float32)
    fact_emb_matrix = fact_emb_matrix / np.clip(
        np.linalg.norm(fact_emb_matrix, axis=1, keepdims=True), 1e-8, None)
    print(f"  n_facts={len(fact_content_map_sentences)}")

    print(f"[load] supersession_index: {SUPERSESSION}")
    sup = json.load(open(SUPERSESSION))
    chunk_to_fact_keys = sup["chunk_to_fact_keys"]
    chunk_key_to_idx = {ck: i for i, ck in enumerate(chunk_to_fact_keys.keys())}

    dump_dir = get_latest_g11_dump_dir()
    dump_mh = dump_dir / "mh_phase2_dump.jsonl"
    dump_records = [json.loads(l) for l in open(dump_mh) if l.strip()]

    # Init NV-Embed-v2 for query encoding
    print(f"[init] NV-Embed-v2")
    from methods.hipporag.embedding_model.NVEmbedV2 import NVEmbedV2EmbeddingModel
    from methods.hipporag.utils.config_utils import BaseConfig
    from methods.hipporag.prompts.linking import get_query_instruction
    cfg = BaseConfig()
    cfg.embedding_model_name = "nvidia/NV-Embed-v2"
    cfg.embedding_return_as_normalized = True
    query_encoder = NVEmbedV2EmbeddingModel(global_config=cfg)
    query_instr = get_query_instruction("query_to_fact")

    # v2_llm_judge.py:_build_fact_pool now treats non-tuple content as natural text,
    # so we can pass sentences directly without wrapping.
    llm = CacheGemini(
        cache_dir=str(BASE / "outputs/smoke_test_cache"),
        cache_filename=f"smoke_v2_sentences_topk{args.top_k_facts}.sqlite",
        llm_name="gemini-3.1-flash-lite-preview",
        temperature=0.0,
        max_new_tokens=2000,
    )
    detector = LLMJudgeDetector(
        llm_model=llm,
        chunk_to_fact_keys=chunk_to_fact_keys,
        fact_content_map=fact_content_map_sentences,  # values = natural sentences
        chunk_key_to_idx=chunk_key_to_idx,
    )

    sample_qids = [0, 20, 45, 65, 85]
    results = []
    for qid in sample_qids:
        q = next((x for x in gt if x["query_id"] == qid), None)
        rec = next((r for r in dump_records if r["q_idx"] == qid), None)
        if q is None or rec is None:
            continue

        top_n_chunk_keys = [c["chunk_key"] for c in rec["candidates"]]

        gt_chain_old_texts = []
        gt_chain_new_texts = []
        for h in q.get("hops", []):
            if h.get("conflict_type") != "has_pair":
                continue
            gt_chain_old_texts.append(h["old_fact_text"])
            gt_chain_new_texts.append(h["gt_fact_text"])

        # Compute query-fact cosine for top-K filter
        q_emb = query_encoder.batch_encode(q["question"], instruction=query_instr,
                                            norm=True, disable_tqdm=True)
        q_emb = np.asarray(q_emb).flatten().astype(np.float32)
        q_emb = q_emb / max(np.linalg.norm(q_emb), 1e-8)
        scores = fact_emb_matrix @ q_emb
        fact_key_to_score = dict(zip(fact_keys_in_order, scores.tolist()))

        result = detector.detect(
            q["question"], top_n_chunk_keys,
            fact_key_to_query_score=fact_key_to_score,
            top_k_facts=args.top_k_facts,
        )

        # DEBUG for qid=0: also do a direct LLM call with same pool to compare
        if qid == 0:
            from methods.hipporag.v2_llm_judge import build_detection_prompt
            pool = detector._build_fact_pool(top_n_chunk_keys)
            if fact_key_to_score and args.top_k_facts:
                p_scored = sorted([(s,t,fk, fact_key_to_score.get(fk,0)) for s,t,fk in pool],
                                  key=lambda x:-x[3])[:args.top_k_facts]
                pool = sorted([(s,t,fk) for s,t,fk,_ in p_scored], key=lambda x: x[0])
            facts_with_seq = [(s, t) for s, t, _ in pool]
            print(f"\n  [DEBUG qid=0] First 5 facts in prompt:")
            for s, t in facts_with_seq[:5]:
                print(f"    [seq={s}] {t!r}")
            msgs = build_detection_prompt(q["question"], facts_with_seq)
            raw, _, hit = llm.infer(msgs)
            print(f"  [DEBUG] cache_hit={hit}, raw_response (first 500 chars):")
            print(f"    {raw[:500]!r}")

        # Translate flagged fact_keys back to sentences for comparison
        flagged_sentences = [fact_to_sentence.get(fk, "(?)")
                              for fk in result["chain_old_fact_keys"]]

        gt_old_caught = []
        gt_new_falsely_flagged = []
        unclassified = []
        for gt_o in gt_chain_old_texts:
            for fs in flagged_sentences:
                if fact_match(gt_o, fs):
                    gt_old_caught.append(gt_o)
                    break
        for gt_n in gt_chain_new_texts:
            for fs in flagged_sentences:
                if fact_match(gt_n, fs):
                    gt_new_falsely_flagged.append(gt_n)
                    break
        for fs in flagged_sentences:
            matched = False
            for gt_o in gt_chain_old_texts:
                if fact_match(gt_o, fs):
                    matched = True
                    break
            if matched:
                continue
            for gt_n in gt_chain_new_texts:
                if fact_match(gt_n, fs):
                    matched = True
                    break
            if not matched:
                unclassified.append(fs)

        print()
        print("=" * 75)
        print(f"  qid={qid}: n_facts_sent={result['n_facts_sent']}, n_chain_old={len(result['chain_old_fact_keys'])}, n_groups={len(result['conflict_groups'])}")
        print("=" * 75)
        print(f"  Query: {q['question'][:90]}")
        print(f"  GT chain_old: {len(gt_chain_old_texts)}; Caught: {len(gt_old_caught)}/{len(gt_chain_old_texts)}")
        for t in gt_chain_old_texts:
            mark = "✓" if t in gt_old_caught else "✗"
            print(f"    {mark} {t}")
        if gt_new_falsely_flagged:
            print(f"  ⚠️  CHAIN_NEW falsely flagged: {len(gt_new_falsely_flagged)}")
            for t in gt_new_falsely_flagged:
                print(f"    !! {t}")
        if unclassified:
            print(f"  Unclassified flagged ({len(unclassified)}):")
            for t in unclassified[:3]:
                print(f"    ? {t}")
            if len(unclassified) > 3:
                print(f"    ... {len(unclassified) - 3} more")

        results.append({
            "qid": qid,
            "n_facts_sent": result["n_facts_sent"],
            "n_chain_old_flagged": len(result["chain_old_fact_keys"]),
            "n_conflict_groups": len(result["conflict_groups"]),
            "gt_chain_old_texts": gt_chain_old_texts,
            "gt_chain_new_texts": gt_chain_new_texts,
            "flagged_sentences": flagged_sentences,
            "n_gt_old_caught": len(gt_old_caught),
            "n_gt_new_falsely_flagged": len(gt_new_falsely_flagged),
            "n_unclassified": len(unclassified),
            "unclassified_sample": unclassified[:10],
            "conflict_groups_raw": [
                [{"seq": s, "fact_key": fk, "sentence": fact_to_sentence.get(fk, "(?)")}
                 for s, fk in grp]
                for grp in result["conflict_groups"]
            ],
        })

    print(f"\n{'=' * 75}\n  AGGREGATE\n{'=' * 75}")
    tot_gt = sum(len(r["gt_chain_old_texts"]) for r in results)
    tot_caught = sum(r["n_gt_old_caught"] for r in results)
    tot_new_false = sum(r["n_gt_new_falsely_flagged"] for r in results)
    tot_uncl = sum(r["n_unclassified"] for r in results)
    tot_flagged = sum(r["n_chain_old_flagged"] for r in results)
    recall = tot_caught / max(1, tot_gt)
    print(f"  GT chain_old caught: {tot_caught}/{tot_gt} = {recall:.1%}")
    print(f"  CHAIN_NEW falsely flagged: {tot_new_false}")
    print(f"  Unclassified flagged: {tot_uncl}")
    print(f"  Total flagged: {tot_flagged}")
    print()
    print(f"  Comparison vs triple form (smoke_v2_production_scale.py, K=30):")
    print(f"    Triple form: 2/10 = 20.0%")
    print(f"    Sentence form: {tot_caught}/{tot_gt} = {recall:.1%}")
    if recall >= 0.7:
        print("  → Verdict: Sentence form RESCUED recall. Root cause IS surface variation.")
    elif recall >= 0.4:
        print("  → Verdict: Partial improvement. Surface is one factor but not the whole story.")
    else:
        print("  → Verdict: Sentence form did NOT help meaningfully. Root cause may be LLM attention at scale.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_queries": len(results), "top_k_facts": args.top_k_facts,
        "aggregate": {
            "tot_gt": tot_gt, "tot_caught": tot_caught, "recall": recall,
            "tot_chain_new_falsely_flagged": tot_new_false,
            "tot_unclassified": tot_uncl, "tot_flagged": tot_flagged,
        },
        "per_query": results,
    }, open(OUT, "w"), indent=2)
    print(f"\n[wrote] {OUT}")


if __name__ == "__main__":
    main()
