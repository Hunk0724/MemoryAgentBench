"""W3 ablation: passages NOT filtered + Recent Updates only (no Reasoning Hints).

Per user's design decision: Reasoning Hints has too many degrees of freedom
(top-1 chain selection, hedged language, chain coverage); Recent Updates is
more mechanically grounded (verdict.status='superseded' + mechanical direction).

Setup vs full W3 baseline:
  enable_phase2_filter_passages       = False  (don't drop passages; pure W3 effect)
  enable_phase3_v2_enriched           = True
  enable_phase3_v2_reasoning_hints    = False  ← OFF
  enable_phase3_v2_recent_updates     = True   ← ON only
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
DUMP_DIR = BASE / f"monitoring_logs/{TS}_w3_updates_only_mini"
DUMP_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("HF_HOME", str(BASE / ".cache/huggingface"))

# Phase 2 chain detection ON (needed for verdict → supersession_events)
os.environ["HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION"] = "1"
os.environ["HIPPORAG_V2_PHASE2_REGION_TOPK"] = "50"
os.environ["HIPPORAG_V2_PHASE2_M"] = "5"
os.environ["HIPPORAG_V2_PHASE2_L"] = "3"
os.environ["HIPPORAG_V2_PHASE2_BEAM"] = "8"

# W3 enriched ON, but only Recent Updates
os.environ["HIPPORAG_ENABLE_PHASE3_V2_ENRICHED"] = "1"
os.environ["HIPPORAG_ENABLE_PHASE3_V2_HINTS"] = "0"     # ← OFF
os.environ["HIPPORAG_ENABLE_PHASE3_V2_UPDATES"] = "1"   # ← ON

# Disable passage filter (pure W3 effect, no W1.3 drop)
os.environ["HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES"] = "0"

os.environ["HIPPORAG_PHASE2_W13_DUMP_PATH"] = str(DUMP_DIR / "phase2_w13_dump.jsonl")
os.environ["HIPPORAG_PHASE2_W13_VERDICT_LOG"] = str(DUMP_DIR / "verdict_events.jsonl")
os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")
os.environ.setdefault("HIPPORAG_EMBED_BATCH_SIZE", "8")
os.environ.setdefault("HIPPORAG_ENABLE_SUPERSESSION", "0")
os.environ.setdefault("HIPPORAG_ENABLE_PHASE2_FILTER", "0")
os.environ.setdefault("HIPPORAG_ENABLE_PHASE3_SCAFFOLD", "0")
os.environ.setdefault("HIPPORAG_ENABLE_V2_DETECT", "0")

sys.path.insert(0, str(BASE))

print(f"[ablation] dump dir: {DUMP_DIR}")
print(f"[ablation] config: passages NOT filtered + Recent Updates only (Hints OFF)")
selection = json.load(open(SELECTION))
print(f"[ablation] {len(selection)} selected queries")

save_dir = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0"

print("[ablation] importing HippoRAG…")
from methods.hipporag import HippoRAG

hipporag = HippoRAG(
    save_dir=str(save_dir),
    llm_model_name="gemini-3.1-flash-lite-preview",
    embedding_model_name="nvidia/NV-Embed-v2",
)

print("[ablation] index() to reload graph + lazy-load propositions…")
hipporag.index(docs=[])

print(f"[ablation] flag check:")
for flag in ['enable_phase3_v2_enriched', 'enable_phase3_v2_reasoning_hints',
             'enable_phase3_v2_recent_updates', 'enable_phase2_filter_passages']:
    print(f"           {flag} = {getattr(hipporag.global_config, flag, '<not set>')}")

print(f"\n[ablation] running per-query retrieve+rag_qa on {len(selection)} queries…")
t0 = time.time()
queries_solutions: list = []
for i, sel in enumerate(selection):
    q = sel["question"]
    print(f"  [{i+1}/{len(selection)}] {sel['qa_pair_id']} ({sel['num_hops']}h)")
    retrieval_results, _top_k_docs = hipporag.retrieve(queries=[q], num_to_retrieve=10)
    qa_results = hipporag.rag_qa(retrieval_results)
    if isinstance(qa_results, tuple):
        q_sols = qa_results[0]
    else:
        q_sols = qa_results
    queries_solutions.append(q_sols[0])

# Sample first 3 enriched contexts
samples = []
for sel, q_sol in zip(selection[:3], queries_solutions[:3]):
    enriched = hipporag._v2_enriched_context_by_query.get(sel["question"], "<empty>")
    samples.append({
        "qa_pair_id": sel["qa_pair_id"],
        "question": sel["question"],
        "answer": q_sol.answer,
        "expected": sel["gt_answer"],
        "enriched_context": enriched,
        "enriched_context_chars": len(enriched),
    })
with open(DUMP_DIR / "qa_prompt_samples.json", "w") as f:
    json.dump(samples, f, indent=2, ensure_ascii=False)

# Tally EM
n_correct = 0
em_per_q = []
for sel, q_sol in zip(selection, queries_solutions):
    pred = (q_sol.answer or "").strip().lower()
    gold = sel["gt_answer"].strip().lower()
    correct = gold in pred or pred in gold
    em_per_q.append({
        "qa_pair_id": sel["qa_pair_id"],
        "num_hops": sel["num_hops"],
        "predicted": q_sol.answer,
        "expected": sel["gt_answer"],
        "correct": correct,
        "w13_baseline_correct": sel["w13_correct"],
    })
    if correct:
        n_correct += 1

with open(DUMP_DIR / "em_per_query.json", "w") as f:
    json.dump(em_per_q, f, indent=2, ensure_ascii=False)

print(f"\n[ablation] done in {time.time()-t0:.1f}s")
print(f"[ablation] EM (substring-match): {n_correct}/{len(selection)}")
print(f"[ablation] vs W1.3 baseline ({sum(1 for s in selection if s['w13_correct'])}/{len(selection)})")
print(f"[ablation] dir: {DUMP_DIR}")

with open(BASE / "analysis/results/mini_eval_w14/latest_run.txt", "w") as f:
    f.write(str(DUMP_DIR) + "\n")
