"""Stage 1 smoke test: verify enriched dump contains expected fields.

Runs 3 queries (one each from 2-hop / 3-hop / 4-hop bucket) and validates
the dump has all the new fields needed for post-hoc analysis:
  - active_pids
  - chain_old_pids
  - enriched_context_text (raw)
  - passages_pre_filter_chunk_ids
  - passages_kept_chunk_ids
  - passages_dropped_chunk_ids
  - chains[i].props (with prop_text + timestamp)

Configures with W3 full ON (filter ON, Hints+Updates ON) — exercises ALL paths.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
SELECTION = BASE / "analysis/results/mini_eval_w14/selection.json"

TS = time.strftime("%Y-%m-%d_%H%M%S")
DUMP_DIR = BASE / f"monitoring_logs/{TS}_stage1_smoke"
DUMP_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("HF_HOME", str(BASE / ".cache/huggingface"))
os.environ["HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION"] = "1"
os.environ["HIPPORAG_V2_PHASE2_REGION_TOPK"] = "50"
os.environ["HIPPORAG_V2_PHASE2_M"] = "5"
os.environ["HIPPORAG_V2_PHASE2_L"] = "3"
os.environ["HIPPORAG_V2_PHASE2_BEAM"] = "8"
os.environ["HIPPORAG_ENABLE_PHASE3_V2_ENRICHED"] = "1"
os.environ["HIPPORAG_ENABLE_PHASE3_V2_HINTS"] = "1"     # exercise hints path
os.environ["HIPPORAG_ENABLE_PHASE3_V2_UPDATES"] = "1"
os.environ["HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES"] = "1"  # exercise filter path
os.environ["HIPPORAG_PHASE2_W13_DUMP_PATH"] = str(DUMP_DIR / "phase2_w13_dump.jsonl")
os.environ["HIPPORAG_PHASE2_W13_VERDICT_LOG"] = str(DUMP_DIR / "verdict_events.jsonl")
os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")

sys.path.insert(0, str(BASE))

# Pick 3 from selection: one 2h / 3h / 4h, all with chain_old to exercise filter
selection = json.load(open(SELECTION))
picks = []
for hops in (2, 3, 4):
    for s in selection:
        if s["num_hops"] == hops and s["all_pair"]:
            picks.append(s)
            break

print(f"[smoke] picks ({len(picks)} queries):")
for s in picks:
    print(f"  - {s['qa_pair_id']} ({s['num_hops']}h): {s['question'][:80]}")

save_dir = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0"
print("\n[smoke] init HippoRAG…")
from methods.hipporag import HippoRAG

hipporag = HippoRAG(
    save_dir=str(save_dir),
    llm_model_name="gemini-3.1-flash-lite-preview",
    embedding_model_name="nvidia/NV-Embed-v2",
)
hipporag.index(docs=[])

print("\n[smoke] running retrieve + rag_qa per query…")
for s in picks:
    retrieval_results, _ = hipporag.retrieve(queries=[s["question"]], num_to_retrieve=10)
    _ = hipporag.rag_qa(retrieval_results)

# Validate dump
print(f"\n[smoke] validating dump at {DUMP_DIR / 'phase2_w13_dump.jsonl'}…")
required_fields = {
    "active_pids": list,
    "chain_old_pids": list,
    "enriched_context_text": str,
    "passages_pre_filter_chunk_ids": list,
    "passages_kept_chunk_ids": list,
    "passages_dropped_chunk_ids": list,
    "chains": list,
}
all_ok = True
events = [json.loads(l) for l in open(DUMP_DIR / "phase2_w13_dump.jsonl")]
print(f"  {len(events)} events in dump")
for i, e in enumerate(events):
    print(f"\n  --- Event {i+1} ({e['query'][:60]}) ---")
    for fname, ftype in required_fields.items():
        v = e.get(fname, None)
        ok = isinstance(v, ftype)
        if fname == "chains":
            has_props_text = (len(v) > 0 and "props" in v[0]
                              and len(v[0]["props"]) > 0
                              and "text" in v[0]["props"][0])
            ok = ok and has_props_text
        marker = "✓" if ok else "✗"
        all_ok &= ok
        if fname in ("enriched_context_text",):
            print(f"    {marker} {fname}: {ftype.__name__}, len={len(v) if v is not None else 'NULL'}")
        elif fname == "chains":
            print(f"    {marker} {fname}: {len(v) if v else 0} chains, "
                  f"first chain has props_with_text: {has_props_text}")
        else:
            n = len(v) if v is not None else None
            print(f"    {marker} {fname}: {ftype.__name__}, count={n}")
    # Print enriched_context body
    print(f"\n    enriched_context_text[:400]:")
    print(f"    {e.get('enriched_context_text', '<empty>')[:400]}")

print(f"\n[smoke] all required fields present: {'YES' if all_ok else 'NO'}")
print(f"[smoke] dump dir: {DUMP_DIR}")
