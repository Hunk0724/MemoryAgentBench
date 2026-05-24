"""Mini-eval driver for W2 Step 1 (I3c real PPR aggregation, option B).

Reuses existing FC-MH 6k vectorstore + KG; runs only the 16 selected queries
(analysis/results/mini_eval_w14/selection.json). Each query triggers
HippoRAG.retrieve() → _v2_phase2_pipeline → dumps to phase2_w13_dump.jsonl
+ verdict_events.jsonl (env-var configured).

Then evaluator can be run via:
    python analysis/eval_mini_w14_phase2b.py
(pointing to the new dump location).

Compared to running full 100Q via main.py (~15 min), this driver runs 16 queries
in ~3 min and is enough to verify the real PPR aggregation impact on chain coverage.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
SELECTION = BASE / "analysis/results/mini_eval_w14/selection.json"

# Set environment BEFORE importing HippoRAG modules
TS = time.strftime("%Y-%m-%d_%H%M%S")
DUMP_DIR = BASE / f"monitoring_logs/{TS}_w2_step1_mini"
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
os.environ["HIPPORAG_PHASE2_W13_DUMP_PATH"] = str(DUMP_DIR / "phase2_w13_dump.jsonl")
os.environ["HIPPORAG_PHASE2_W13_VERDICT_LOG"] = str(DUMP_DIR / "verdict_events.jsonl")
os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")
os.environ.setdefault("HIPPORAG_EMBED_BATCH_SIZE", "8")
os.environ.setdefault("HIPPORAG_ENABLE_SUPERSESSION", "0")
os.environ.setdefault("HIPPORAG_ENABLE_PHASE2_FILTER", "0")
os.environ.setdefault("HIPPORAG_ENABLE_PHASE3_SCAFFOLD", "0")
os.environ.setdefault("HIPPORAG_ENABLE_V2_DETECT", "0")

sys.path.insert(0, str(BASE))

print(f"[mini-eval] dump dir: {DUMP_DIR}")

# ─── Load 16 selected queries ───
selection = json.load(open(SELECTION))
print(f"[mini-eval] {len(selection)} selected queries from {SELECTION}")

# ─── Init HippoRAG against existing FC-MH 6k vectorstore ───
save_dir = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0"
assert save_dir.exists(), f"vectorstore not found: {save_dir}"

print("[mini-eval] importing HippoRAG…")
from methods.hipporag import HippoRAG

hipporag = HippoRAG(
    save_dir=str(save_dir),
    llm_model_name="gemini-3.1-flash-lite-preview",
    embedding_model_name="nvidia/NV-Embed-v2",
)

print("[mini-eval] calling index() with empty docs (reuses cached vectorstore)…")
hipporag.index(docs=[])

# ─── Run retrieve() on each of 16 queries ───
print(f"\n[mini-eval] running retrieve() on {len(selection)} queries…")
t0 = time.time()
for i, sel in enumerate(selection):
    q = sel["question"]
    qa_id = sel["qa_pair_id"]
    print(f"  [{i+1}/{len(selection)}] {qa_id} ({sel['num_hops']}h): {q[:80]}")
    try:
        retrieval_results, top_k_docs = hipporag.retrieve(queries=[q], num_to_retrieve=10)
    except Exception as e:
        print(f"     ✗ retrieve failed: {e}")
        continue
print(f"\n[mini-eval] done in {time.time()-t0:.1f}s")
print(f"[mini-eval] dump dir: {DUMP_DIR}")

# Pointer file for evaluator
with open(BASE / "analysis/results/mini_eval_w14/latest_run.txt", "w") as f:
    f.write(str(DUMP_DIR) + "\n")
print(f"[mini-eval] pointer written to analysis/results/mini_eval_w14/latest_run.txt")
