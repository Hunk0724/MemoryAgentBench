"""Smoke test — port PropRAG-style beam search to use HippoRAG-v2 cached data.

Goal: given an FC-MH query, find top-N reasoning paths through fact triples.
Evaluate: do GT chain_old + chain_new facts appear inside the discovered paths?

This is a minimal port — does NOT use PropRAG's fancy multi-stage scoring,
just:
  - Score facts by cosine(query_emb, fact_emb)
  - Connect facts that share ≥1 entity (entity substring match, not synonym)
  - Beam search depth=3, beam_width=4

If recall is decent, the discovered path facts become a clean candidate pool
for LLM judge detection.
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from methods.hipporag.embedding_model.NVEmbedV2 import NVEmbedV2EmbeddingModel
from methods.hipporag.utils.config_utils import BaseConfig

BASE = Path("/home/yhchiang/MemoryAgentBench")
FACT_PARQUET = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/fact_embeddings/vdb_fact.parquet"
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
OUT = BASE / "analysis/results/phase_v1/smoke_proprag_paths.json"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip().rstrip(".,;:!?\"'"))


def extract_entities_from_triple_str(content_str: str) -> Set[str]:
    """Parse ('s', 'r', 'o') → {s_norm, o_norm}."""
    try:
        triple = eval(content_str)
        if len(triple) != 3:
            return set()
        s, _, o = [str(x).strip().lower() for x in triple]
        return {s, o}
    except Exception:
        return set()


def parse_triple(content_str: str) -> Tuple[str, str, str]:
    try:
        t = eval(content_str)
        return tuple(str(x).strip().lower() for x in t)
    except Exception:
        return ("", "", "")


def build_entity_to_facts(fact_contents: List[str]) -> Dict[str, List[int]]:
    """Map: entity_text → list of fact_indices that mention the entity."""
    m: Dict[str, List[int]] = {}
    for idx, content in enumerate(fact_contents):
        ents = extract_entities_from_triple_str(content)
        for e in ents:
            if len(e) < 3:
                continue
            m.setdefault(e, []).append(idx)
    return m


def find_connected_facts(fact_idx: int,
                         fact_entities: List[Set[str]],
                         entity_to_facts: Dict[str, List[int]]) -> Set[int]:
    """Find facts that share ≥1 entity with given fact (excl self)."""
    connected = set()
    for ent in fact_entities[fact_idx]:
        for other_idx in entity_to_facts.get(ent, []):
            if other_idx != fact_idx:
                connected.add(other_idx)
    return connected


def beam_search_paths(query_emb: np.ndarray,
                      fact_emb: np.ndarray,
                      fact_entities: List[Set[str]],
                      entity_to_facts: Dict[str, List[int]],
                      beam_width: int = 4,
                      max_depth: int = 3,
                      n_seed: int = 30) -> List[Dict]:
    """Beam search over fact graph. Returns top paths.

    Path = sequence of fact_indices; score = mean cosine(query, fact) across path facts.
    """
    # Score all facts
    scores = fact_emb @ query_emb  # (n_facts,)

    # Seed beam: top-n_seed facts
    seed_idxs = np.argsort(scores)[-n_seed:][::-1]
    beam = [
        {"path": [int(i)], "score": float(scores[i]), "entities": set(fact_entities[i])}
        for i in seed_idxs[:beam_width]
    ]
    all_paths = [dict(p) for p in beam]

    for depth in range(2, max_depth + 1):
        new_candidates = []
        for path in beam:
            last_idx = path["path"][-1]
            connected = find_connected_facts(last_idx, fact_entities, entity_to_facts)
            for next_idx in connected:
                if next_idx in path["path"]:
                    continue  # avoid cycles
                new_path = path["path"] + [next_idx]
                new_score = float(np.mean([scores[i] for i in new_path]))
                new_candidates.append({
                    "path": new_path, "score": new_score,
                    "entities": path["entities"] | fact_entities[next_idx],
                })
        new_candidates.sort(key=lambda x: -x["score"])
        # Dedup paths (frozenset of path indices)
        seen = set()
        unique = []
        for c in new_candidates:
            key = frozenset(c["path"])
            if key not in seen:
                seen.add(key)
                unique.append(c)
        beam = unique[:beam_width]
        all_paths.extend([dict(p) for p in beam])

    # Final ranking: dedup all_paths by path content, take top-N
    seen = set()
    unique_paths = []
    for p in all_paths:
        key = tuple(sorted(p["path"]))
        if key not in seen:
            seen.add(key)
            unique_paths.append(p)
    unique_paths.sort(key=lambda x: -x["score"])
    return unique_paths[:20]


def find_fact_idx_for_text(fact_contents: List[str], fact_text: str) -> int:
    """For a GT fact text, find the corresponding fact embedding row.

    Reuse parse + substring matching from variant_b script.
    """
    text = norm(fact_text)
    # Naive: take first 2 words as s candidate, last 2 words as o candidate
    words = text.split()
    if len(words) < 4:
        return -1
    # Try multiple windows
    for s_take in [3, 2, 1]:
        for o_take in [3, 2, 1]:
            s_cand = " ".join(words[:s_take])
            o_cand = " ".join(words[-o_take:])
            for idx, content in enumerate(fact_contents):
                triple = parse_triple(content)
                if not triple[0]:
                    continue
                s, r, o = triple
                if (s_cand in s or s in s_cand) and (o_cand in o or o in o_cand) \
                        and len(s) >= 3 and len(o) >= 3:
                    return idx
    return -1


def main():
    print(f"[load] {FACT_PARQUET}")
    df = pd.read_parquet(FACT_PARQUET)
    fact_contents = df["content"].tolist()
    fact_emb = np.stack(df["embedding"].values).astype(np.float32)
    norms = np.linalg.norm(fact_emb, axis=1, keepdims=True)
    fact_emb = fact_emb / np.clip(norms, 1e-8, None)
    print(f"  n_facts={len(df)}")

    # Build entity index
    fact_entities = [extract_entities_from_triple_str(c) for c in fact_contents]
    entity_to_facts = build_entity_to_facts(fact_contents)
    print(f"  n_unique_entities={len(entity_to_facts)}")

    # Init NV-Embed-v2 for query encoding (uses same fp16 path as HippoRAG-v2)
    cfg = BaseConfig()
    cfg.embedding_model_name = "nvidia/NV-Embed-v2"
    cfg.embedding_return_as_normalized = True
    print(f"[init] NV-Embed-v2 (this may take ~30s to load model)")
    embedder = NVEmbedV2EmbeddingModel(global_config=cfg)

    print(f"[load] {GT}")
    gt = json.load(open(GT))

    sample_qids = [0, 20, 45, 65, 85]
    results = []
    for qid in sample_qids:
        q = next((x for x in gt if x["query_id"] == qid), None)
        if q is None:
            continue
        query = q["question"]
        print(f"\n{'='*75}\n  qid={qid}: {query[:90]}\n{'='*75}")

        # Encode query (NVEmbed needs explicit instruction prefix)
        from methods.hipporag.prompts.linking import get_query_instruction
        instr = get_query_instruction("query_to_fact")
        q_emb = embedder.batch_encode(query, instruction=instr, norm=True, disable_tqdm=True)
        q_emb = np.asarray(q_emb).flatten()
        if q_emb.shape[0] != fact_emb.shape[1]:
            q_emb = q_emb.reshape(-1)[:fact_emb.shape[1]]

        # Beam search
        paths = beam_search_paths(q_emb, fact_emb, fact_entities, entity_to_facts,
                                   beam_width=4, max_depth=3, n_seed=20)

        # Get GT chain facts (chain_new + chain_old)
        gt_facts = {}  # fact_idx -> ('chain_new'/'chain_old', hop_idx)
        for hop in q.get("hops", []):
            if hop.get("conflict_type") != "has_pair":
                continue
            gt_idx = find_fact_idx_for_text(fact_contents, hop["gt_fact_text"])
            old_idx = find_fact_idx_for_text(fact_contents, hop["old_fact_text"])
            if gt_idx >= 0:
                gt_facts[gt_idx] = ("chain_new", hop["hop_idx"])
            if old_idx >= 0:
                gt_facts[old_idx] = ("chain_old", hop["hop_idx"])

        # Check coverage: which GT facts appear in top-N paths?
        path_facts_top10 = set()
        for p in paths[:10]:
            path_facts_top10.update(p["path"])

        coverage = {idx: (role, idx in path_facts_top10) for idx, (role, _) in gt_facts.items()}
        n_gt = len(gt_facts)
        n_covered = sum(1 for _, hit in coverage.values() if hit)

        print(f"\n  Top-3 paths discovered (depth-3, beam_width=4):")
        for rank, p in enumerate(paths[:3]):
            print(f"    Path {rank} (score={p['score']:.4f}):")
            for fi in p["path"]:
                marker = "  "
                if fi in gt_facts:
                    role, hidx = gt_facts[fi]
                    marker = f"[{role[5:]}hop{hidx}]"
                print(f"      {marker} {fact_contents[fi]}")

        print(f"\n  GT fact coverage in top-10 paths: {n_covered}/{n_gt}")
        for idx, (role, hit) in coverage.items():
            mark = "✓" if hit else "✗"
            print(f"    {mark} [{role}] {fact_contents[idx]}")

        results.append({
            "qid": qid, "query": query,
            "n_paths": len(paths),
            "top3_paths": [
                {"score": p["score"], "path": p["path"],
                 "fact_texts": [fact_contents[i] for i in p["path"]]}
                for p in paths[:3]
            ],
            "gt_facts": [
                {"fact_idx": int(idx), "role": role, "hop_idx": int(hop_idx),
                 "content": fact_contents[idx],
                 "covered_in_top10": idx in path_facts_top10}
                for idx, (role, hop_idx) in gt_facts.items()
            ],
            "n_gt": n_gt, "n_covered": n_covered,
        })

    # Aggregate
    print(f"\n{'='*75}\n  AGGREGATE\n{'='*75}")
    tot_gt = sum(r["n_gt"] for r in results)
    tot_cov = sum(r["n_covered"] for r in results)
    print(f"  GT fact coverage in top-10 paths: {tot_cov}/{tot_gt} = "
          f"{tot_cov*100/max(1,tot_gt):.1f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_queries": len(results),
        "aggregate": {"tot_gt": tot_gt, "tot_covered": tot_cov,
                      "coverage_rate": tot_cov / max(1, tot_gt)},
        "per_query": results,
    }, open(OUT, "w"), indent=2)
    print(f"\n[wrote] {OUT}")


if __name__ == "__main__":
    main()
