"""Verify prop ↔ chunk-content alignment v2 — entity-match based,
robust to chunk-boundary orphans and prop canonicalization.

For each prop:
  - In its source chunk's content, find all fact-spans (substring sequences
    ending with period, separated by ". " or "N. ").
  - Among those spans, find spans containing ALL of prop's entities.
  - 1 match → unambiguous alignment ✅
  - 0 match → prop's source_chunk_id wrong, or prop text not extractable ❌
  - 2+ match → ambiguous (need disambiguation) ⚠️

If 100% of props get exactly 1 match → B3 inline-remove is safe via entity-anchored find-and-delete.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path("/home/yhchiang/MemoryAgentBench")
RAG = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2"


def normalize(t: str) -> str:
    t = t.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def split_into_facts(chunk_text: str) -> list[str]:
    """Split chunk into individual fact spans.

    Strategy: facts are usually `N. {text}.` or unnumbered orphan `{text}.`
    Split on sentence-ending periods followed by optional `\\s+N. ` OR end-of-string.

    We split on the regex `(?<=[a-z\\)\\]'\"])\\.\\s+(?=\\d+\\.\\s+|[A-Z]|$)` —
    i.e. period after a lowercase/closing-paren, followed by space-then-number
    OR space-then-capital OR end. This isolates each fact.

    Then strip leading "Here is a list of facts:" header.
    """
    body = re.sub(r"^Here is a list of facts:\s*", "", chunk_text)
    # Naive: split on `. ` boundaries that look like fact ends
    # We use a permissive splitter then re-stitch
    parts = re.split(r"(?<=[a-z\)\]'\"])\.\s+(?=\d+\.\s+|[A-Z])", body)
    facts = [p.strip() for p in parts if p.strip()]
    # Each fact may still have trailing junk; normalize whitespace
    facts = [re.sub(r"\s+", " ", f) for f in facts]
    # Re-add trailing period if missing
    facts = [f if f.endswith(".") else f + "." for f in facts]
    return facts


def fact_contains_all_entities(fact_text: str, entities: list[str]) -> bool:
    f_n = normalize(fact_text)
    return all(normalize(e) in f_n for e in entities)


def main():
    df = pd.read_parquet(RAG / "chunk_embeddings/vdb_chunk.parquet")
    props_all = json.load(open(RAG / "proposition_index.json"))["propositions"]

    chunk_text_by_id = dict(zip(df["hash_id"], df["content"]))

    n_total = 0
    n_unambiguous = 0
    n_ambiguous = 0
    n_no_match = 0
    failures = []

    for prop in props_all:
        n_total += 1
        cid = prop["source_chunk_id"]
        if cid not in chunk_text_by_id:
            n_no_match += 1
            failures.append({"prop_id": prop["id"], "reason": "chunk_id_not_found", "prop_text": prop["text"]})
            continue
        chunk_text = chunk_text_by_id[cid]
        entities = prop.get("entities", [])
        if not entities:
            # Without entities can't entity-match; fall back to text substring
            if normalize(prop["text"].rstrip(".")) in normalize(chunk_text):
                n_unambiguous += 1
            else:
                n_no_match += 1
                failures.append({
                    "prop_id": prop["id"], "reason": "no_entities_and_text_not_in_chunk",
                    "prop_text": prop["text"],
                })
            continue
        # Split chunk into fact spans, find those containing all entities
        facts = split_into_facts(chunk_text)
        candidates = [f for f in facts if fact_contains_all_entities(f, entities)]
        if len(candidates) == 1:
            n_unambiguous += 1
        elif len(candidates) >= 2:
            n_ambiguous += 1
            failures.append({
                "prop_id": prop["id"], "reason": "ambiguous_multi_match",
                "prop_text": prop["text"],
                "prop_entities": entities,
                "n_matches": len(candidates),
                "candidates": candidates[:4],
            })
        else:
            n_no_match += 1
            failures.append({
                "prop_id": prop["id"], "reason": "no_entity_match",
                "prop_text": prop["text"],
                "prop_entities": entities,
                "chunk_id_prefix": cid[:30],
                "chunk_content_head": chunk_text[:300],
            })

    print(f"=== Entity-match alignment v2 ===")
    print(f"  total props          : {n_total}")
    print(f"  ✅ unambiguous (1 match) : {n_unambiguous} ({100*n_unambiguous/n_total:.1f}%)")
    print(f"  ⚠️ ambiguous (2+ matches): {n_ambiguous} ({100*n_ambiguous/n_total:.1f}%)")
    print(f"  ❌ no match              : {n_no_match} ({100*n_no_match/n_total:.1f}%)")

    if failures:
        print()
        print(f"=== First 6 failures ===")
        for f in failures[:6]:
            print(f"  reason={f['reason']}")
            for k, v in f.items():
                if k == "reason":
                    continue
                vs = str(v)
                print(f"    {k}: {vs[:200]}")
            print()
        out = BASE / "analysis/results/paper_narrative/prop_chunk_alignment_v2_failures.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        json.dump(failures, open(out, "w"), indent=2, ensure_ascii=False)
        print(f"[wrote] full failure list → {out}")

    if n_unambiguous == n_total:
        print()
        print("  ✅ 100% PASS — every prop entity-matches exactly one fact span in its source chunk. "
              "B3 inline-remove via entity-anchored find-and-delete is safe.")


if __name__ == "__main__":
    main()
