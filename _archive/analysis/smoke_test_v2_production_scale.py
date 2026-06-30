"""Pre-flight smoke test for v2 LLM judge at PRODUCTION SCALE.

Original smoke (smoke_test_llm_judge_detection.py) fed only 7-11 curated
facts (GT conflict pairs + 5 random distractors). Real v2 pipeline feeds
ALL facts from top-N passages — at FC-MH 6k that's ~449 facts (entire
corpus, since corpus = 12 chunks ≤ top-N=20).

This script:
  1. For each of 5 sample queries, load top-N chunk_keys from G.11 dump
  2. Reconstruct fact_pool from chunk_to_fact_keys + fact contents
  3. Run LLMJudgeDetector on this real-scale input
  4. Compare flagged chain_old facts to GT chain_old by substring match

If detection holds up (≥80% recall, ≤20% FP) → proceed to full v2 pipeline.
If detection collapses → revisit prompt / consider pre-filtering candidate pool.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from methods.hipporag.llm.gemini_llm import CacheGemini
from methods.hipporag.v2_llm_judge import LLMJudgeDetector

BASE = Path("/home/yhchiang/MemoryAgentBench")
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
FACT_PARQUET = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/fact_embeddings/vdb_fact.parquet"
SUPERSESSION = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/supersession_index.json"
OUT = BASE / "analysis/results/phase_v1/smoke_v2_production_scale.json"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip().rstrip(".,;:!?\"'"))


def text_match(short_text: str, long_text: str) -> bool:
    """Legacy: whole-string substring (kept for back-compat)."""
    s, l = norm(short_text), norm(long_text)
    if len(s) < 5 or len(l) < 5:
        return False
    return s in l or l in s


def extract_subject_object(fact_text: str) -> Optional[tuple]:
    """Heuristic: split natural fact text into (subject_phrase, object_phrase)
    by matching common FC predicate patterns. Returns None if can't parse.
    """
    text = norm(fact_text)
    patterns = [
        r"\bis a citizen of\b", r"\bis married to\b", r"\bwas married to\b",
        r"\bis associated with\b", r"\bwas associated with\b",
        r"\bplays the position of\b", r"\bplays position\b",
        r"\bis the chairperson of\b", r"\bwas the chairperson of\b",
        r"\bwas born in\b", r"\bis born in\b",
        r"\bdied in\b", r"\bwas employed by\b", r"\bis employed by\b",
        r"\bwas founded by\b", r"\bis founded by\b",
        r"\bwas performed by\b", r"\bis performed by\b",
        r"\bwas developed by\b", r"\bis developed by\b",
        r"\bwas created by\b", r"\bis created by\b", r"\bcreated by\b",
        r"\bwas authored by\b", r"\bis authored by\b", r"\bauthored by\b",
        r"\bauthor of\b", r"\bauthor\b",
        r"\bwas composed by\b", r"\bis composed by\b",
        r"\bwas directed by\b", r"\bis directed by\b",
        r"\bdirector of\b",
        r"\bis located in the continent of\b",
        r"\bis located in\b", r"\bwas located in\b", r"\blocated in\b",
        r"\bis the capital of\b", r"\bwas the capital of\b",
        r"\bis the founder of\b", r"\bwas the founder of\b",
        r"\bspeaks\b", r"\bwrote\b", r"\bcomposed\b",
        r"\bis owned by\b", r"\bwas owned by\b",
        r"\bworks for\b", r"\bworked for\b",
        r"\bworks in field of\b", r"\bworked in field of\b",
        r"\bis the author of\b", r"\bwas the author of\b",
        r"\bis the director of\b", r"\bwas the director of\b",
        r"\bis the country of citizenship of\b",
        r"\bcountry of citizenship of\b",
        r"\bofficial language\b",
        r"\bfounded in\b", r"\bcreated in\b",
        r"\bplace of death\b",
        r"\bwritten in\b",
        r"\bceo of\b", r"\bchief executive officer of\b",
        r"\bemployed by\b",
        r"\bis the\b", r"\bwas the\b", r"\bis\b", r"\bwas\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            s_phrase = text[:m.start()].strip()
            o_phrase = text[m.end():].strip()
            s_phrase = re.sub(r"^(the |a |an )", "", s_phrase)
            o_phrase = re.sub(r"^(the |a |an )", "", o_phrase)
            if len(s_phrase) >= 3 and len(o_phrase) >= 3:
                return (s_phrase, o_phrase)
    return None


def fact_match(fact_a: str, fact_b: str) -> bool:
    """Robust fact equivalence: token-level Jaccard on content words.

    Handles OpenIE surface variation:
      - 'pesäpallo was created in the country of Finland.' ↔ 'pes pallo created in finland'
      - 'The author of X is Y' ↔ 'X author Y'
    """
    import unicodedata
    def tokens(text):
        text = text.lower()
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                       if unicodedata.category(c) != 'Mn')
        text = re.sub(r"[^\w\s]", " ", text)
        stops = {
            'the', 'is', 'was', 'are', 'were', 'of', 'in', 'on', 'at', 'by',
            'to', 'from', 'with', 'as', 'be', 'a', 'an', 'and', 'or',
            'this', 'that', 'these', 'those', 'his', 'her', 'their',
            'author', 'authored', 'created', 'married', 'spouse', 'citizen',
            'born', 'died', 'employed', 'founder', 'director', 'chairperson',
            'position', 'plays', 'associated', 'language', 'official',
            'capital', 'located', 'country', 'continent', 'sport', 'place',
            'death', 'work', 'works', 'field',
            'ceo', 'chief', 'executive', 'officer',
            'wrote', 'written', 'composed', 'developed', 'directed', 'speaks',
            'owned', 'founded',
        }
        return {t for t in text.split() if t not in stops and len(t) >= 3}
    ta = tokens(fact_a)
    tb = tokens(fact_b)
    if not ta or not tb:
        return False
    inter = ta & tb
    # Match if ≥50% of smaller-side content tokens overlap
    return len(inter) / min(len(ta), len(tb)) >= 0.5


def get_latest_g11_dump_dir() -> Path:
    """Find the latest monitoring_logs/*_g11_phase2_dump/ directory."""
    candidates = sorted(BASE.glob("monitoring_logs/*g11_phase2_dump"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError("no G.11 dump dir found in monitoring_logs/")
    return candidates[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k-facts", type=int, default=None,
                    help="Top-K cosine pre-filter (None = send all corpus facts).")
    args = ap.parse_args()

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("HF_HOME", "/home/yhchiang/MemoryAgentBench/.cache/huggingface")
    os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")

    # --- Load all artifacts ---
    print(f"[load] GT: {GT}")
    gt = json.load(open(GT))

    print(f"[load] fact parquet: {FACT_PARQUET}")
    df = pd.read_parquet(FACT_PARQUET)
    fact_content_map = dict(zip(df["hash_id"], df["content"]))
    # Pre-compute normalized fact embeddings for cosine
    fact_keys_in_order = list(df["hash_id"])
    fact_emb_matrix = np.stack(df["embedding"].values).astype(np.float32)
    fact_emb_matrix = fact_emb_matrix / np.clip(
        np.linalg.norm(fact_emb_matrix, axis=1, keepdims=True), 1e-8, None)
    print(f"  n_facts={len(fact_content_map)}, embedding shape={fact_emb_matrix.shape}")

    print(f"[load] supersession_index (for chunk_to_fact_keys): {SUPERSESSION}")
    sup = json.load(open(SUPERSESSION))
    chunk_to_fact_keys = sup["chunk_to_fact_keys"]
    print(f"  n_chunks={len(chunk_to_fact_keys)}")

    dump_dir = get_latest_g11_dump_dir()
    dump_mh = dump_dir / "mh_phase2_dump.jsonl"
    print(f"[load] G.11 MH dump: {dump_mh}")
    dump_records = []
    with open(dump_mh) as f:
        for line in f:
            line = line.strip()
            if line:
                dump_records.append(json.loads(line))
    print(f"  {len(dump_records)} query records")

    # chunk_key → chunk_idx (seq). We use insertion order of chunk_to_fact_keys
    # which is dict-preserving in py3.7+. This should match the chunk_idx in
    # G.11 dump's natural order. We'll cross-verify against dump's ordering.
    chunk_key_to_idx = {ck: i for i, ck in enumerate(chunk_to_fact_keys.keys())}

    # --- Init NV-Embed-v2 for query encoding (when top-K filter is active) ---
    query_encoder = None
    if args.top_k_facts is not None:
        print(f"[init] NV-Embed-v2 (for query embedding, top_k_facts={args.top_k_facts})")
        from methods.hipporag.embedding_model.NVEmbedV2 import NVEmbedV2EmbeddingModel
        from methods.hipporag.utils.config_utils import BaseConfig
        from methods.hipporag.prompts.linking import get_query_instruction
        cfg = BaseConfig()
        cfg.embedding_model_name = "nvidia/NV-Embed-v2"
        cfg.embedding_return_as_normalized = True
        query_encoder = NVEmbedV2EmbeddingModel(global_config=cfg)
        query_instr = get_query_instruction("query_to_fact")

    # --- Init LLM detector ---
    llm = CacheGemini(
        cache_dir=str(BASE / "outputs/smoke_test_cache"),
        cache_filename=f"smoke_v2_topk{args.top_k_facts or 'all'}.sqlite",
        llm_name="gemini-3.1-flash-lite-preview",
        temperature=0.0,
        max_new_tokens=2000,  # large output for many conflict groups
    )
    detector = LLMJudgeDetector(
        llm_model=llm,
        chunk_to_fact_keys=chunk_to_fact_keys,
        fact_content_map=fact_content_map,
        chunk_key_to_idx=chunk_key_to_idx,
    )

    # --- Test 5 queries ---
    sample_qids = [0, 20, 45, 65, 85]
    results = []
    for qid in sample_qids:
        q = next((x for x in gt if x["query_id"] == qid), None)
        if q is None:
            continue
        # Find this query's dump record
        rec = next((r for r in dump_records if r["q_idx"] == qid), None)
        if rec is None:
            print(f"[skip] qid={qid} no dump record")
            continue

        # Top-N chunk_keys (from real PPR ordering)
        top_n_chunk_keys = [c["chunk_key"] for c in rec["candidates"]]

        # GT chain_old / chain_new texts
        gt_chain_old_texts = []
        gt_chain_new_texts = []
        for h in q.get("hops", []):
            if h.get("conflict_type") != "has_pair":
                continue
            gt_chain_old_texts.append(h["old_fact_text"])
            gt_chain_new_texts.append(h["gt_fact_text"])

        # Compute fact_key → query cosine score (when top-K filter active)
        fact_key_to_score = None
        if query_encoder is not None:
            q_emb = query_encoder.batch_encode(
                q["question"], instruction=query_instr, norm=True, disable_tqdm=True)
            q_emb = np.asarray(q_emb).flatten().astype(np.float32)
            q_emb = q_emb / max(np.linalg.norm(q_emb), 1e-8)
            scores = fact_emb_matrix @ q_emb  # (n_facts,)
            fact_key_to_score = dict(zip(fact_keys_in_order, scores.tolist()))

        # --- Run LLM judge ---
        result = detector.detect(
            q["question"], top_n_chunk_keys,
            fact_key_to_query_score=fact_key_to_score,
            top_k_facts=args.top_k_facts,
        )

        # Build natural-text versions of flagged chain_old facts
        flagged_old_texts = []
        for fk in result["chain_old_fact_keys"]:
            content = fact_content_map.get(fk, "")
            try:
                tup = eval(content)
                if len(tup) == 3:
                    flagged_old_texts.append(f"{tup[0]} {tup[1]} {tup[2]}")
                else:
                    flagged_old_texts.append(content)
            except Exception:
                flagged_old_texts.append(content)

        # --- Score: match flagged vs GT ---
        gt_old_caught = []     # GT chain_old that LLM correctly flagged
        gt_new_falsely_flagged = []  # LLM flagged chain_new (very bad)
        unclassified_flagged = []   # LLM flagged something not in GT (could be real conflict between distractor facts in corpus, OR pure FP)

        for gt_o in gt_chain_old_texts:
            for flagged in flagged_old_texts:
                if fact_match(gt_o, flagged):
                    gt_old_caught.append(gt_o)
                    break

        for gt_n in gt_chain_new_texts:
            for flagged in flagged_old_texts:
                if fact_match(gt_n, flagged):
                    gt_new_falsely_flagged.append(gt_n)
                    break

        # Unclassified = flagged texts that don't match any GT old or new for THIS query
        for flagged in flagged_old_texts:
            matched_any_gt = False
            for gt_o in gt_chain_old_texts:
                if fact_match(gt_o, flagged):
                    matched_any_gt = True
                    break
            if matched_any_gt:
                continue
            for gt_n in gt_chain_new_texts:
                if fact_match(gt_n, flagged):
                    matched_any_gt = True
                    break
            if not matched_any_gt:
                unclassified_flagged.append(flagged)

        print()
        print("=" * 80)
        print(f"  qid={qid}: n_facts_sent={result['n_facts_sent']}, "
              f"n_chain_old_fk={len(result['chain_old_fact_keys'])}, "
              f"n_conflict_groups={len(result['conflict_groups'])}")
        print("=" * 80)
        print(f"  Query: {q['question'][:100]}")
        print(f"  GT chain_old (this query): {len(gt_chain_old_texts)} facts")
        for t in gt_chain_old_texts:
            print(f"    GT_OLD: {t}")
        print(f"  Caught: {len(gt_old_caught)}/{len(gt_chain_old_texts)}")
        for t in gt_old_caught:
            print(f"    ✓ {t}")
        for t in gt_chain_old_texts:
            if t not in gt_old_caught:
                print(f"    ✗ MISSED: {t}")
        if gt_new_falsely_flagged:
            print(f"  ⚠️  CHAIN_NEW falsely flagged ({len(gt_new_falsely_flagged)}):")
            for t in gt_new_falsely_flagged:
                print(f"    !! {t}")
        if unclassified_flagged:
            print(f"  Unclassified flagged ({len(unclassified_flagged)} — could be other queries' conflicts OR true FP):")
            for t in unclassified_flagged[:5]:
                print(f"    ? {t}")
            if len(unclassified_flagged) > 5:
                print(f"    ... and {len(unclassified_flagged) - 5} more")

        # Dump pool content for debug
        pool_dump = []
        if fact_key_to_score is not None:
            # Sort and take top-K by cosine, then by seq for stable order
            scored_pool = []
            for ck in top_n_chunk_keys:
                seq = chunk_key_to_idx[ck]
                for fk in chunk_to_fact_keys.get(ck, []):
                    if fk not in fact_content_map:
                        continue
                    content = fact_content_map[fk]
                    try:
                        tup = eval(content)
                        nat = f"{tup[0]} {tup[1]} {tup[2]}" if len(tup) == 3 else content
                    except Exception:
                        nat = content
                    scored_pool.append((seq, nat, fk, fact_key_to_score.get(fk, 0.0)))
            # Dedup by fact_key (keep min seq)
            seen = {}
            for seq, nat, fk, sc in scored_pool:
                if fk not in seen or seq < seen[fk][0]:
                    seen[fk] = (seq, nat, fk, sc)
            scored_pool = sorted(seen.values(), key=lambda x: -x[3])[:args.top_k_facts]
            scored_pool.sort(key=lambda x: x[0])  # back to seq order
            pool_dump = [{"seq": s, "text": n, "fact_key": fk, "cosine": float(c)}
                         for s, n, fk, c in scored_pool]

        results.append({
            "qid": qid,
            "n_facts_sent": result["n_facts_sent"],
            "n_chain_old_flagged": len(result["chain_old_fact_keys"]),
            "n_conflict_groups": len(result["conflict_groups"]),
            "gt_chain_old_texts": gt_chain_old_texts,
            "gt_chain_new_texts": gt_chain_new_texts,
            "flagged_old_texts": flagged_old_texts,
            "n_gt_old_caught": len(gt_old_caught),
            "n_gt_new_falsely_flagged": len(gt_new_falsely_flagged),
            "n_unclassified_flagged": len(unclassified_flagged),
            "unclassified_flagged_sample": unclassified_flagged[:10],
            "pool_sent_to_llm": pool_dump,
            "conflict_groups_raw": [
                [{"seq": s, "text": next((p["text"] for p in pool_dump if p["fact_key"] == fk), "?"),
                  "fact_key": fk}
                 for s, fk in grp]
                for grp in result["conflict_groups"]
            ],
        })

    # --- Aggregate ---
    print(f"\n{'=' * 80}\n  AGGREGATE\n{'=' * 80}")
    tot_gt_old = sum(len(r["gt_chain_old_texts"]) for r in results)
    tot_caught = sum(r["n_gt_old_caught"] for r in results)
    tot_new_false = sum(r["n_gt_new_falsely_flagged"] for r in results)
    tot_unclassified = sum(r["n_unclassified_flagged"] for r in results)
    tot_flagged = sum(r["n_chain_old_flagged"] for r in results)
    tot_facts_sent = sum(r["n_facts_sent"] for r in results)

    recall = tot_caught / max(1, tot_gt_old)
    print(f"  --- For these 5 queries: GT chain_old = {tot_gt_old} ---")
    print(f"  Recall (GT chain_old caught):       {tot_caught}/{tot_gt_old} = {recall:.1%}")
    print(f"  False CHAIN_NEW flagged (very bad): {tot_new_false}")
    print(f"  Unclassified flagged (other Qs?):   {tot_unclassified}")
    print(f"  Total LLM-flagged chain_old:        {tot_flagged}")
    print(f"  Total facts sent to LLM:            {tot_facts_sent} "
          f"(avg {tot_facts_sent/max(1,len(results)):.0f} per query)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_queries": len(results),
        "aggregate": {
            "tot_gt_chain_old": tot_gt_old,
            "tot_caught": tot_caught,
            "recall": recall,
            "tot_chain_new_falsely_flagged": tot_new_false,
            "tot_unclassified_flagged": tot_unclassified,
            "tot_flagged": tot_flagged,
            "avg_facts_sent": tot_facts_sent / max(1, len(results)),
        },
        "per_query": results,
    }, open(OUT, "w"), indent=2)
    print(f"\n[wrote] {OUT}")


if __name__ == "__main__":
    main()
