"""Build full proposition_index.json for FC-MH 6k (all 12 chunks).

This is the input artifact for W1.2 (Phase 2.a chain detection).
Each proposition has:
  - id, text, entities (mention strings)
  - source_chunk_id
  - timestamp = (chunk_idx, in_chunk_position)
  - embedding (NV-Embed-v2 4096-d) — added on top of W1.1 module output
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")

from methods.hipporag.llm.gemini_llm import CacheGemini
from methods.hipporag.phase1.proposition_extractor import (
    count_numbered_facts,
    derive_chunk_triple_entities,
    extract_with_batch_fallback,
)

BASE = Path("/home/yhchiang/MemoryAgentBench")
OPENIE = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
SENTINEL_LOG = BASE / "logs/proposition_extraction_sentinels.jsonl"
PROP_INDEX = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json"
LLM_CACHE_DIR = BASE / "outputs/smoke_test_cache"


def embed_propositions(propositions: List, embedder) -> None:
    """In-place: assign p.embedding for each proposition via NV-Embed-v2.

    Encodes proposition text (not triple form). Uses query_to_fact instruction
    so embeddings are aligned with HippoRAG-v2's fact embedding space.
    """
    if not propositions:
        return
    from methods.hipporag.prompts.linking import get_query_instruction
    texts = [p.text for p in propositions]
    instr = get_query_instruction("query_to_fact")
    # batch encode
    embs = embedder.batch_encode(texts, instruction=instr, norm=True, disable_tqdm=True)
    embs = np.asarray(embs)
    if embs.ndim == 1:
        embs = embs.reshape(1, -1)
    # Normalize defensively
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    embs = embs / np.clip(norms, 1e-8, None)
    for p, e in zip(propositions, embs):
        p.embedding = e.astype(np.float32).tolist()


def main():
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("HF_HOME", str(BASE / ".cache/huggingface"))
    os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")

    print(f"[load] OpenIE: {OPENIE}")
    oie = json.load(open(OPENIE))
    n_chunks = len(oie["docs"])
    print(f"  n_chunks={n_chunks}")

    # Reset sentinel log for this run
    if SENTINEL_LOG.exists():
        SENTINEL_LOG.unlink()

    llm = CacheGemini(
        cache_dir=str(LLM_CACHE_DIR),
        cache_filename="w1_1_proposition.sqlite",
        llm_name="gemini-3.1-flash-lite-preview",
        temperature=0.0,
        max_new_tokens=2048,
    )

    all_propositions = []
    chunk_stats = []

    for chunk_idx, doc in enumerate(oie["docs"]):
        passage = doc.get("passage", "")
        triples = doc.get("extracted_triples", [])
        chunk_id = doc.get("idx") or f"chunk-fallback-{chunk_idx}"

        n_numbered = count_numbered_facts(passage)
        triple_ents = derive_chunk_triple_entities(triples)

        print(f"\n  [chunk {chunk_idx:2d}/{n_chunks}] id={chunk_id[:20]}... "
              f"n_numbered={n_numbered} n_triples={len(triples)} n_ents={len(triple_ents)}")

        propositions, sentinel_history = extract_with_batch_fallback(
            chunk_id=chunk_id,
            chunk_idx=chunk_idx,
            passage=passage,
            triple_entities=triple_ents,
            llm_model=llm,
            sentinel_log_path=SENTINEL_LOG,
        )

        final_sent = sentinel_history[-1]
        print(f"     → {len(propositions)} propositions, yield={final_sent.proposition_yield_ratio:.2f}, "
              f"alarms={final_sent.alarms()}")

        all_propositions.extend(propositions)
        chunk_stats.append({
            "chunk_idx": chunk_idx,
            "chunk_id": chunk_id,
            "n_numbered_facts": n_numbered,
            "n_triples": len(triples),
            "n_propositions": len(propositions),
            "yield_ratio": final_sent.proposition_yield_ratio,
            "alarms": final_sent.alarms(),
            "attempts": len(sentinel_history),
        })

    print(f"\n[total] {len(all_propositions)} propositions across {n_chunks} chunks")

    # Embed propositions (this loads NV-Embed-v2, ~1 min cold start)
    print(f"\n[embed] loading NV-Embed-v2 for proposition encoding…")
    from methods.hipporag.embedding_model.NVEmbedV2 import NVEmbedV2EmbeddingModel
    from methods.hipporag.utils.config_utils import BaseConfig
    cfg = BaseConfig()
    cfg.embedding_model_name = "nvidia/NV-Embed-v2"
    cfg.embedding_return_as_normalized = True
    embedder = NVEmbedV2EmbeddingModel(global_config=cfg)
    print(f"[embed] encoding {len(all_propositions)} propositions…")
    embed_propositions(all_propositions, embedder)
    print(f"[embed] done")

    # Save
    PROP_INDEX.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v2.0.2_w1.1",
        "n_chunks": n_chunks,
        "n_propositions": len(all_propositions),
        "chunk_stats": chunk_stats,
        "propositions": [p.to_dict() for p in all_propositions],
    }
    json.dump(payload, open(PROP_INDEX, "w"), indent=2)
    print(f"\n[wrote] {PROP_INDEX}")

    # Summary
    avg_yield = sum(s["yield_ratio"] for s in chunk_stats) / max(1, len(chunk_stats))
    total_alarms = sum(len(s["alarms"]) for s in chunk_stats)
    print(f"\n=== SUMMARY ===")
    print(f"  Avg proposition yield: {avg_yield:.3f}")
    print(f"  Total alarms: {total_alarms}")
    print(f"  Total propositions: {len(all_propositions)}")
    print(f"  Avg propositions per chunk: {len(all_propositions)/n_chunks:.1f}")


if __name__ == "__main__":
    main()
