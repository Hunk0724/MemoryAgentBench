"""Variant B feasibility — cosine distribution of (chain_old, chain_new) fact pairs.

Goal: before committing to query-time fact-pairwise detection, verify that
known conflict pairs (chain_old vs chain_new) have a separable cosine
distribution from random non-conflict pairs.

If conflict pair median cosine >> random pair max → bimodal, Variant B viable.
If overlap large → need richer signal (LLM judge / per-relation gate).

Output: histogram + threshold sweep (precision/recall at various cosine cuts).
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("/home/yhchiang/MemoryAgentBench")
FACT_PARQUET = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/fact_embeddings/vdb_fact.parquet"
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
OUT = BASE / "analysis/results/phase_v1/variant_b_cosine_distribution.json"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip().rstrip(".,;:!?\"'"))


def parse_fact_text(fact_text: str):
    """Parse 'X <predicate> Y.' into (subject_phrase, object_phrase).

    Returns (None, None) if can't parse.
    """
    text = norm(fact_text)
    # Common FC predicate boundaries (matches utils/templates.py)
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
        r"\bwas created by\b", r"\bis created by\b",
        r"\bwas authored by\b", r"\bis authored by\b",
        r"\bwas composed by\b", r"\bis composed by\b",
        r"\bwas directed by\b", r"\bis directed by\b",
        r"\bis located in the continent of\b",
        r"\bis located in\b", r"\bwas located in\b",
        r"\bis the capital of\b", r"\bwas the capital of\b",
        r"\bis the founder of\b", r"\bwas the founder of\b",
        r"\bspeaks\b", r"\bwrote\b", r"\bcomposed\b",
        r"\bis owned by\b", r"\bwas owned by\b",
        r"\bworks for\b", r"\bworked for\b",
        r"\bworks in field of\b", r"\bworked in field of\b",
        r"\bis the author of\b", r"\bwas the author of\b",
        r"\bis the director of\b", r"\bwas the director of\b",
        r"\bis the country of citizenship of\b",
        r"\bofficial language\b",
        r"\bfounded in\b",
        r"\bis the\b", r"\bwas the\b",
        r"\bis\b", r"\bwas\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            s_phrase = text[:m.start()].strip()
            o_phrase = text[m.end():].strip()
            # Strip leading "the " from subject
            s_phrase = re.sub(r"^(the |a |an )", "", s_phrase)
            o_phrase = re.sub(r"^(the |a |an )", "", o_phrase)
            return s_phrase, o_phrase
    return None, None


def find_fact_idx(fact_content_list, s_phrase, o_phrase) -> int:
    """Find row idx in fact embeddings whose content (s,r,o) tuple matches
    s_phrase as subject AND o_phrase as object.

    Substring matching on either direction. Returns -1 if no match.
    """
    if not s_phrase or not o_phrase or len(s_phrase) < 3 or len(o_phrase) < 3:
        return -1
    # Try exact endpoint match first
    for idx, content in enumerate(fact_content_list):
        try:
            triple = eval(content)
            if len(triple) != 3:
                continue
            s, r, o = [str(x).lower() for x in triple]
            # Substring matching on subject and object
            s_match = (s_phrase in s or s in s_phrase) and len(s) >= 3
            o_match = (o_phrase in o or o in o_phrase) and len(o) >= 3
            if s_match and o_match:
                return idx
        except Exception:
            continue
    return -1


def main():
    print(f"[load] {FACT_PARQUET}")
    df = pd.read_parquet(FACT_PARQUET)
    fact_contents = df["content"].tolist()
    fact_emb = np.stack(df["embedding"].values).astype(np.float32)
    # Normalize defensively (should be already)
    norms = np.linalg.norm(fact_emb, axis=1, keepdims=True)
    fact_emb = fact_emb / np.clip(norms, 1e-8, None)
    print(f"  n_facts={len(df)}, dim={fact_emb.shape[1]}")

    print(f"[load] {GT}")
    gt = json.load(open(GT))

    # ===== 1. For each has_pair hop, find chain_old and chain_new fact indices =====
    pair_data = []  # list of {hop info, gt_idx, old_idx, cosine}
    n_total_hops = 0
    n_both_found = 0
    n_gt_only = 0
    n_old_only = 0
    n_neither = 0

    for q in gt:
        for hop in q.get("hops", []):
            if hop.get("conflict_type") != "has_pair":
                continue
            n_total_hops += 1
            gt_text = hop.get("gt_fact_text", "")
            old_text = hop.get("old_fact_text", "")
            gt_s, gt_o = parse_fact_text(gt_text)
            old_s, old_o = parse_fact_text(old_text)

            gt_idx = find_fact_idx(fact_contents, gt_s, gt_o)
            old_idx = find_fact_idx(fact_contents, old_s, old_o)

            if gt_idx >= 0 and old_idx >= 0:
                n_both_found += 1
                cos = float(np.dot(fact_emb[gt_idx], fact_emb[old_idx]))
                pair_data.append({
                    "qid": q["query_id"], "hop_idx": hop["hop_idx"],
                    "gt_text": gt_text, "old_text": old_text,
                    "gt_idx": gt_idx, "old_idx": old_idx,
                    "cosine": cos,
                })
            elif gt_idx >= 0:
                n_gt_only += 1
            elif old_idx >= 0:
                n_old_only += 1
            else:
                n_neither += 1

    print(f"\n--- GT hop coverage (n_total={n_total_hops}) ---")
    print(f"  Both fact embeddings found:  {n_both_found}  ← Variant B potential recall ceiling")
    print(f"  Only chain_new found:        {n_gt_only}")
    print(f"  Only chain_old found:        {n_old_only}")
    print(f"  Neither found:               {n_neither}")

    if not pair_data:
        print("\n[fatal] no matched pairs found, can't compute distribution")
        return

    cosines = np.array([p["cosine"] for p in pair_data])
    print(f"\n--- Conflict pair cosine distribution (n={len(cosines)}) ---")
    print(f"  mean   = {cosines.mean():.4f}")
    print(f"  median = {np.median(cosines):.4f}")
    print(f"  min    = {cosines.min():.4f}")
    print(f"  max    = {cosines.max():.4f}")
    print(f"  std    = {cosines.std():.4f}")
    print(f"  percentiles (5/25/50/75/95):")
    for p in [5, 25, 50, 75, 95]:
        print(f"    p{p}  = {np.percentile(cosines, p):.4f}")
    print()
    print(f"  histogram (10 bins from {cosines.min():.3f} to {cosines.max():.3f}):")
    hist, edges = np.histogram(cosines, bins=10)
    for i, h in enumerate(hist):
        bar = "#" * int(h * 50 / max(hist.max(), 1))
        print(f"    [{edges[i]:.3f}-{edges[i+1]:.3f}]  {h:3d}  {bar}")

    # ===== 2. Random non-conflict pair baseline =====
    print(f"\n--- Random non-conflict pair baseline (n=2000 random pairs) ---")
    rng = np.random.default_rng(42)
    n_rand = 2000
    idx_pairs = rng.integers(0, len(fact_emb), size=(n_rand, 2))
    # exclude self-pairs
    valid_mask = idx_pairs[:, 0] != idx_pairs[:, 1]
    idx_pairs = idx_pairs[valid_mask]
    rand_cosines = np.sum(fact_emb[idx_pairs[:, 0]] * fact_emb[idx_pairs[:, 1]], axis=1)
    print(f"  mean   = {rand_cosines.mean():.4f}")
    print(f"  median = {np.median(rand_cosines):.4f}")
    print(f"  max    = {rand_cosines.max():.4f}")
    print(f"  p95    = {np.percentile(rand_cosines, 95):.4f}")
    print(f"  p99    = {np.percentile(rand_cosines, 99):.4f}")

    # ===== 3. Threshold sweep — precision / recall as function of cosine cut =====
    print(f"\n--- Threshold sweep (conflict pairs above thresh = recall, "
          f"random pairs above thresh = false positives) ---")
    print(f"  {'thresh':>7s}  {'conflict pairs above':>20s}  "
          f"{'recall %':>9s}  {'random false-pos %':>20s}")
    for t in [0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95, 0.98]:
        conf_above = (cosines >= t).sum()
        rand_above = (rand_cosines >= t).sum()
        recall_pct = conf_above * 100 / max(len(cosines), 1)
        fp_pct = rand_above * 100 / max(len(rand_cosines), 1)
        print(f"  {t:7.2f}  {conf_above:20d}  {recall_pct:9.1f}  {fp_pct:20.2f}")

    # ===== Save =====
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_total_hops": n_total_hops,
        "n_both_found": n_both_found, "n_gt_only": n_gt_only,
        "n_old_only": n_old_only, "n_neither": n_neither,
        "conflict_cosine_stats": {
            "n": int(len(cosines)), "mean": float(cosines.mean()),
            "median": float(np.median(cosines)),
            "min": float(cosines.min()), "max": float(cosines.max()),
            "std": float(cosines.std()),
            "percentiles": {f"p{p}": float(np.percentile(cosines, p)) for p in [5, 25, 50, 75, 95]},
        },
        "random_cosine_stats": {
            "n": int(len(rand_cosines)),
            "mean": float(rand_cosines.mean()),
            "max": float(rand_cosines.max()),
            "p95": float(np.percentile(rand_cosines, 95)),
            "p99": float(np.percentile(rand_cosines, 99)),
        },
        "pair_data_sample": pair_data[:20],
    }, open(OUT, "w"), indent=2)
    print(f"\n[wrote] {OUT}")

    # Print decision guidance
    overlap = cosines.min() < np.percentile(rand_cosines, 99)
    median_gap = np.median(cosines) - np.percentile(rand_cosines, 95)
    print(f"\n--- Variant B viability decision ---")
    print(f"  conflict median - random p95 gap: {median_gap:+.4f}")
    print(f"  conflict min < random p99?       : {overlap}  (True → overlap; False → clean separation)")
    if median_gap > 0.05 and not overlap:
        print(f"  → Verdict: STRONG separation, Variant B viable with single threshold")
    elif median_gap > 0.02:
        print(f"  → Verdict: PARTIAL separation, need additional gate (same S match? LLM judge?)")
    else:
        print(f"  → Verdict: WEAK separation, Variant B alone won't work")


if __name__ == "__main__":
    main()
