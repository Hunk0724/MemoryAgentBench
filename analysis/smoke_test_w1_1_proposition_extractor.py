"""W1.1 dry-test: run proposition_extractor on 2-3 FC-MH 6k chunks.

Goals (per spec §B.7 W1.1 deliverable):
  - Validate PropRAG prompt port works end-to-end with our LLM
  - Inspect 3 sentinels: proposition_yield_ratio, entities_not_in_input,
    finish_reason_length
  - Surface any obvious issues before W1.2 development

Chunks selected: 0, 1, 7
  - chunk 0: extracted_entities=[] from OpenIE (NER skipped) but 37 triples OK
  - chunk 1: extracted_entities=69 (NER worked) + 35 triples
  - chunk 7: extracted_entities=[] (NER skipped again) + 38 triples
  This mix tests robustness across OpenIE NER variance.

Output:
  - logs/proposition_extraction_sentinels.jsonl (per spec §B.11.7)
  - analysis/results/phase_v2/w1_1_dry_test.json (propositions + sentinels)
  - terminal summary table
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List

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
OUT_JSON = BASE / "analysis/results/phase_v2/w1_1_dry_test.json"
LLM_CACHE_DIR = BASE / "outputs/smoke_test_cache"


def main():
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

    print(f"[load] {OPENIE}")
    oie = json.load(open(OPENIE))
    print(f"  n_chunks={len(oie['docs'])}")

    # Fresh sentinel log for this run
    if SENTINEL_LOG.exists():
        SENTINEL_LOG.unlink()

    llm = CacheGemini(
        cache_dir=str(LLM_CACHE_DIR),
        cache_filename="w1_1_proposition.sqlite",
        llm_name="gemini-3.1-flash-lite-preview",
        temperature=0.0,
        max_new_tokens=2048,
    )

    selected_chunks = [0, 1, 7]
    results: List[dict] = []

    for chunk_idx in selected_chunks:
        doc = oie["docs"][chunk_idx]
        passage = doc.get("passage", "")
        triples = doc.get("extracted_triples", [])
        # doc['idx'] from OpenIE results already has "chunk-<hash>" canonical
        # prefix (matches HippoRAG's chunk_embedding_store key format).
        chunk_id = doc.get("idx") or f"chunk-fallback-{chunk_idx}"

        n_numbered = count_numbered_facts(passage)
        triple_ents = derive_chunk_triple_entities(triples)

        print()
        print("=" * 80)
        print(f"  chunk_idx={chunk_idx}  (numbered_facts={n_numbered}, "
              f"triples={len(triples)}, triple_entities={len(triple_ents)})")
        print("=" * 80)
        print(f"  passage[:200]: {passage[:200]!r}")
        print(f"  triple_entities sample: {sorted(triple_ents)[:5]}")

        propositions, sentinel_history = extract_with_batch_fallback(
            chunk_id=chunk_id,
            chunk_idx=chunk_idx,
            passage=passage,
            triple_entities=triple_ents,
            llm_model=llm,
            sentinel_log_path=SENTINEL_LOG,
        )

        print(f"\n  → extracted {len(propositions)} propositions "
              f"({len(sentinel_history)} attempt(s))")
        final_sent = sentinel_history[-1]
        print(f"  → final sentinels:")
        print(f"      yield_ratio = {final_sent.proposition_yield_ratio:.2f}  "
              f"({final_sent.proposition_count_per_chunk}/{final_sent.expected_proposition_count})")
        print(f"      entities_not_in_input = {final_sent.entities_not_in_input}")
        print(f"      finish_reason_length = {final_sent.finish_reason_length}")
        print(f"      raw_response_chars = {final_sent.raw_response_char_count}")
        print(f"      cache_hit = {final_sent.cache_hit}")
        print(f"      alarms = {final_sent.alarms()}")

        print(f"\n  Sample propositions (first 3):")
        for p in propositions[:3]:
            print(f"    [seq={p.timestamp[1]:>2}] {p.text}")
            print(f"          entities: {p.entities}")

        results.append({
            "chunk_idx": chunk_idx,
            "chunk_id": chunk_id,
            "n_numbered_facts": n_numbered,
            "n_triples": len(triples),
            "n_triple_entities": len(triple_ents),
            "passage_chars": len(passage),
            "propositions": [p.to_dict() for p in propositions],
            "sentinel_history": [s.to_dict() for s in sentinel_history],
            "final_alarms": final_sent.alarms(),
        })

    # ===== Aggregate report =====
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print(f"  {'chunk':>6}  {'n_fact':>7}  {'n_prop':>7}  {'yield':>6}  "
          f"{'ent_oot':>8}  {'trunc':>6}  {'attempts':>8}  alarms")
    avg_yield = 0.0
    total_oot = 0
    for r in results:
        last = r["sentinel_history"][-1]
        yr = last["proposition_yield_ratio"]
        avg_yield += yr
        total_oot += last["entities_not_in_input"]
        print(f"  {r['chunk_idx']:>6}  {r['n_numbered_facts']:>7}  "
              f"{last['proposition_count_per_chunk']:>7}  "
              f"{yr:>6.2f}  {last['entities_not_in_input']:>8}  "
              f"{str(last['finish_reason_length']):>6}  "
              f"{len(r['sentinel_history']):>8}  "
              f"{r['final_alarms']}")
    avg_yield /= max(1, len(results))
    print(f"\n  Avg proposition yield ratio: {avg_yield:.2f} (target ≥ 0.85)")
    print(f"  Total entities_not_in_input:  {total_oot}")

    # Save results
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "config": {
            "n_chunks": len(selected_chunks),
            "selected_chunk_indices": selected_chunks,
            "llm": "gemini-3.1-flash-lite-preview",
            "max_new_tokens": 2048,
        },
        "summary": {
            "avg_proposition_yield_ratio": avg_yield,
            "total_entities_not_in_input": total_oot,
        },
        "per_chunk": results,
    }, open(OUT_JSON, "w"), indent=2)
    print(f"\n  [wrote] {OUT_JSON}")
    print(f"  [wrote] {SENTINEL_LOG}")


if __name__ == "__main__":
    main()
