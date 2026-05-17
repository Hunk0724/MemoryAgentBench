"""W1.2 dry-test: enumerate top-5 candidate chains for 5 sample queries.

Per spec §B.11.2 step 4: "dump top-5 chains for 5 sample queries, verify
chains look reasonable".

Method:
  1. Load proposition_index.json (built by build_proposition_index_w1.py)
  2. Encode each query via NV-Embed-v2
  3. Compute prop_ppr_mass PROXY (W1 dry-test: query-prop cosine instead of
     real PPR; real PPR integration deferred to W1.3 when wiring into
     HippoRAG.retrieve()). See §B.14 W1.2 note.
  4. Active region: top-50 props by mass + 1-hop entity expansion
  5. Path enumeration: M=5, depth=L=3, beam=8
  6. Dump top-5 chains per query; eyeball check against GT reasoning chain

Output: analysis/results/phase_v2/w1_2_dry_test.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

import numpy as np

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")

from methods.hipporag.phase1.data_structures import Proposition
from methods.hipporag.phase2a.active_region import (
    compute_prop_mass_proxy_from_query_cosine,
    identify_active_region,
)
from methods.hipporag.phase2a.path_enumeration import enumerate_candidate_chains

BASE = Path("/home/yhchiang/MemoryAgentBench")
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
PROP_INDEX = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json"
OUT = BASE / "analysis/results/phase_v2/w1_2_dry_test.json"


def extract_query_entities_simple(query: str, all_entities: Set[str]) -> Set[str]:
    """Simple substring-based query entity linker.

    For each known KG entity, check if its surface form appears in query
    (case-insensitive, len ≥ 4 to avoid 'the', 'and', etc.).
    """
    q_low = query.lower()
    found = set()
    for e in all_entities:
        e_n = e.lower().strip()
        if len(e_n) >= 4 and e_n in q_low:
            found.add(e)
    return found


def main():
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("HF_HOME", str(BASE / ".cache/huggingface"))
    os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")

    print(f"[load] proposition_index: {PROP_INDEX}")
    payload = json.load(open(PROP_INDEX))
    print(f"  {payload['n_propositions']} propositions across {payload['n_chunks']} chunks")

    # Reconstruct Proposition objects
    propositions: Dict[str, Proposition] = {
        p["id"]: Proposition.from_dict(p)
        for p in payload["propositions"]
    }
    all_entities: Set[str] = set()
    for p in propositions.values():
        all_entities |= set(p.entities)
    print(f"  Total unique entities across propositions: {len(all_entities)}")

    print(f"[load] GT: {GT}")
    gt = json.load(open(GT))

    # Init NV-Embed-v2 for query encoding
    print(f"[init] NV-Embed-v2 for query encoding…")
    from methods.hipporag.embedding_model.NVEmbedV2 import NVEmbedV2EmbeddingModel
    from methods.hipporag.utils.config_utils import BaseConfig
    from methods.hipporag.prompts.linking import get_query_instruction
    cfg = BaseConfig()
    cfg.embedding_model_name = "nvidia/NV-Embed-v2"
    cfg.embedding_return_as_normalized = True
    embedder = NVEmbedV2EmbeddingModel(global_config=cfg)
    query_instr = get_query_instruction("query_to_fact")

    sample_qids = [0, 20, 45, 65, 85]
    results: List[dict] = []

    for qid in sample_qids:
        q = next((x for x in gt if x["query_id"] == qid), None)
        if q is None:
            continue
        query = q["question"]

        # GT chain (extract chain_new and chain_old fact texts)
        gt_chain_new = []
        gt_chain_old = []
        for hop in q.get("hops", []):
            if hop.get("conflict_type") == "has_pair":
                gt_chain_new.append((hop["hop_idx"], hop["gt_fact_text"]))
                gt_chain_old.append((hop["hop_idx"], hop["old_fact_text"]))

        # ──── Encode query ────
        q_emb = embedder.batch_encode(query, instruction=query_instr,
                                      norm=True, disable_tqdm=True)
        q_emb = np.asarray(q_emb, dtype="float32").flatten()
        q_emb /= max(np.linalg.norm(q_emb), 1e-8)

        # ──── PPR proxy (W1 dry-test): query-prop cosine ────
        prop_mass = compute_prop_mass_proxy_from_query_cosine(propositions, q_emb)

        # ──── Query entity linker (simple substring) ────
        q_entities = extract_query_entities_simple(query, all_entities)

        # ──── Active region ────
        active_pids = identify_active_region(
            query=query,
            propositions=propositions,
            prop_ppr_mass=prop_mass,
            query_entities=q_entities,
            region_topK=50,
        )
        active_props = {pid: propositions[pid] for pid in active_pids}

        # ──── Path enumeration ────
        chains = enumerate_candidate_chains(
            query_embedding=q_emb,
            active_propositions=active_props,
            prop_ppr_mass=prop_mass,
            M=5, L=3, beam_width=8, n_seed=20,
            query_entities=q_entities,
        )

        # ──── Eyeball: does any chain contain GT chain_new / chain_old props? ────
        def find_in_chain(chain_text_query: str, chain: any) -> bool:
            ct = re.sub(r"\s+", " ", chain_text_query.lower().strip(".,"))
            for pid in chain.proposition_ids:
                pt = re.sub(r"\s+", " ", propositions[pid].text.lower().strip(".,"))
                if ct == pt or ct in pt or pt in ct:
                    return True
            return False

        # Print
        print()
        print("=" * 90)
        print(f"  qid={qid}: {query[:80]}")
        print(f"  Query entities linked: {sorted(q_entities)}")
        print(f"  Active region size: {len(active_pids)}")
        print("=" * 90)
        print(f"  GT chain_new facts:")
        for hi, ft in gt_chain_new:
            print(f"    hop{hi}: {ft}")
        print(f"  GT chain_old facts:")
        for hi, ft in gt_chain_old:
            print(f"    hop{hi}: {ft}")
        print()
        print(f"  Top-5 enumerated chains:")
        for ci, c in enumerate(chains):
            new_hits = sum(1 for _, t in gt_chain_new if find_in_chain(t, c))
            old_hits = sum(1 for _, t in gt_chain_old if find_in_chain(t, c))
            print(f"    [chain {ci}] score={c.score:.3f} depth={c.depth} new_hits={new_hits} old_hits={old_hits}")
            for j, pid in enumerate(c.proposition_ids):
                p = propositions[pid]
                marker = ""
                if any(find_in_chain(t, type("X", (), {"proposition_ids": [pid]})())
                       for _, t in gt_chain_new):
                    marker = " [chain_NEW]"
                if any(find_in_chain(t, type("X", (), {"proposition_ids": [pid]})())
                       for _, t in gt_chain_old):
                    marker = " [chain_OLD]"
                shared = c.shared_entity_path[j - 1] if j > 0 else None
                shared_str = f" ←{sorted(shared)}" if shared else ""
                print(f"      {j}. {p.text}{marker}{shared_str}")

        results.append({
            "qid": qid,
            "query": query,
            "query_entities_linked": sorted(q_entities),
            "active_region_size": len(active_pids),
            "gt_chain_new": [t for _, t in gt_chain_new],
            "gt_chain_old": [t for _, t in gt_chain_old],
            "top_chains": [
                {
                    **c.to_dict(),
                    "prop_texts": [propositions[pid].text for pid in c.proposition_ids],
                    "gt_new_hits": sum(1 for _, t in gt_chain_new if find_in_chain(t, c)),
                    "gt_old_hits": sum(1 for _, t in gt_chain_old if find_in_chain(t, c)),
                }
                for c in chains
            ],
        })

    # ──── Aggregate summary ────
    print()
    print("=" * 90)
    print("  SUMMARY")
    print("=" * 90)
    print(f"  {'qid':>4}  {'GT new':>7}  {'GT old':>7}  {'top1 new':>9}  {'top1 old':>9}  {'top5_any_new':>13}  {'top5_any_old':>13}")
    for r in results:
        ng = len(r["gt_chain_new"])
        og = len(r["gt_chain_old"])
        t1_new = r["top_chains"][0]["gt_new_hits"] if r["top_chains"] else 0
        t1_old = r["top_chains"][0]["gt_old_hits"] if r["top_chains"] else 0
        any5_new = max((c["gt_new_hits"] for c in r["top_chains"]), default=0)
        any5_old = max((c["gt_old_hits"] for c in r["top_chains"]), default=0)
        print(f"  {r['qid']:>4}  {ng:>7}  {og:>7}  {t1_new:>9}  {t1_old:>9}  {any5_new:>13}  {any5_old:>13}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_queries": len(results),
        "per_query": results,
    }, open(OUT, "w"), indent=2)
    print(f"\n  [wrote] {OUT}")


if __name__ == "__main__":
    main()
