"""Verify prop ↔ chunk-line alignment for B3 (inline-remove) filter design.

For each chunk:
  1. Parse chunk.content into list of (list_number, fact_text)
  2. Get all props with source_chunk_id == this chunk, sorted by in_chunk_position
  3. Verify:
     (a) parsed_facts count == props count
     (b) for each (parsed_fact, prop) pair at same position:
         - prop's entities all appear as substrings in parsed_fact
         - prop's entities-set ≈ entities extractable from parsed_fact
  4. Report PASS / FAIL + any mismatches

If 100% PASS → B3 inline-remove is safe.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path("/home/yhchiang/MemoryAgentBench")
RAG = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2"


def parse_chunk_into_facts(chunk_text: str) -> list[tuple[int, str]]:
    """Parse chunk text into ordered list of (number, fact_text).

    FC chunk format:
      "Here is a list of facts:\n0. fact0. 1. fact1. 2. fact2.\n3. fact3. ..."
    Numbers are list indices; fact text ends at the next "N. " or end-of-string.
    Robust against:
      - newlines / spaces between facts
      - intra-fact dots (e.g., "Washington, D.C..")
    """
    # Strip the leading header "Here is a list of facts:\n"
    body = re.sub(r"^Here is a list of facts:\s*", "", chunk_text, count=1)
    # Greedy: capture `N. ` followed by content until the next `\sN. ` (lookahead) or EOS
    # We use re.split on the boundary of `\sN\. ` to identify breaks
    # But splitter approach must preserve numbers. Use finditer with lookahead.
    pattern = re.compile(r"(\d+)\.\s+(.+?)(?=\s+\d+\.\s+|\s*$)", re.DOTALL)
    facts = []
    for m in pattern.finditer(body):
        num = int(m.group(1))
        text = m.group(2).strip()
        facts.append((num, text))
    return facts


def normalize(t: str) -> str:
    t = t.strip().lower().rstrip(".,;:!?\"'").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def entity_in_fact(entity: str, fact_text: str) -> bool:
    """Check if entity appears as substring in fact (loose)."""
    e_n = normalize(entity)
    f_n = normalize(fact_text)
    if not e_n:
        return False
    return e_n in f_n


def main():
    df = pd.read_parquet(RAG / "chunk_embeddings/vdb_chunk.parquet")
    props_all = json.load(open(RAG / "proposition_index.json"))["propositions"]

    # Group props by source_chunk_id
    props_by_chunk: dict[str, list] = defaultdict(list)
    for p in props_all:
        props_by_chunk[p["source_chunk_id"]].append(p)
    # Sort by in_chunk_position
    for cid in props_by_chunk:
        props_by_chunk[cid].sort(key=lambda p: p["timestamp"][1])

    print(f"Chunks: {len(df)}, Props: {len(props_all)}")
    print()

    total_props = 0
    total_aligned = 0
    total_entity_match = 0
    failures = []

    for _, row in df.iterrows():
        cid = row["hash_id"]
        content = row["content"]
        facts = parse_chunk_into_facts(content)
        props = props_by_chunk.get(cid, [])
        total_props += len(props)

        # ─── Check (a): count alignment ───
        if len(facts) != len(props):
            failures.append({
                "chunk_id": cid,
                "fail_reason": "count_mismatch",
                "n_facts_parsed": len(facts),
                "n_props": len(props),
                "first_3_facts": [f for f in facts[:3]],
                "first_3_props_text": [p["text"] for p in props[:3]],
            })
            continue

        # ─── Check (b): per-position entity overlap ───
        per_chunk_aligned = 0
        per_chunk_entity_match = 0
        for i, (fact, prop) in enumerate(zip(facts, props)):
            fact_num, fact_text = fact
            prop_text = prop["text"]
            prop_entities = prop.get("entities", [])
            in_chunk_pos = prop["timestamp"][1]

            # Position check: in_chunk_position should be the i-th
            if in_chunk_pos != i:
                failures.append({
                    "chunk_id": cid,
                    "fail_reason": "position_mismatch",
                    "expected_pos": i,
                    "prop_in_chunk_pos": in_chunk_pos,
                    "fact_text": fact_text[:80],
                    "prop_text": prop_text[:80],
                })
                continue
            per_chunk_aligned += 1

            # Entity match: all entities of prop should be substrings of fact
            entities_in_fact = [e for e in prop_entities if entity_in_fact(e, fact_text)]
            if len(entities_in_fact) == len(prop_entities) and len(prop_entities) > 0:
                per_chunk_entity_match += 1
            else:
                failures.append({
                    "chunk_id": cid,
                    "fail_reason": "entity_mismatch",
                    "position": i,
                    "fact_text": fact_text[:120],
                    "prop_text": prop_text[:120],
                    "prop_entities": prop_entities,
                    "missing_entities": [e for e in prop_entities if not entity_in_fact(e, fact_text)],
                })

        total_aligned += per_chunk_aligned
        total_entity_match += per_chunk_entity_match

    print(f"=== ALIGNMENT VERIFICATION ===")
    print(f"  position-aligned   : {total_aligned}/{total_props} ({100*total_aligned/total_props:.1f}%)")
    print(f"  entity-all-match   : {total_entity_match}/{total_props} ({100*total_entity_match/total_props:.1f}%)")
    print(f"  total failures     : {len(failures)}")

    if failures:
        print()
        print(f"=== FIRST 8 FAILURES ===")
        for f in failures[:8]:
            print(f"  chunk={f['chunk_id'][:24]}.. reason={f['fail_reason']}")
            for k, v in f.items():
                if k in ("chunk_id", "fail_reason"):
                    continue
                print(f"    {k}: {v}")
            print()
        # Save full failure list
        out = BASE / "analysis/results/paper_narrative/prop_chunk_alignment_failures.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        json.dump(failures, open(out, "w"), indent=2, ensure_ascii=False)
        print(f"[wrote] full failure list → {out}")
    else:
        print()
        print("  ✅ 100% PASS — every prop maps cleanly to a chunk fact, "
              "entities all match. B3 is safe to implement.")


if __name__ == "__main__":
    main()
