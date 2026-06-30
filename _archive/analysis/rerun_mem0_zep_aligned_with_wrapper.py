"""
Re-run Mem0 customized × Gemini AND Zep × Gemini with WRAPPED query (q["query"])
to align with MABench default pipeline (which applies FC seq rule wrapper to all
methods via templates.py).

Original our Phase 0 scripts (run_mem0_gemini.py / run_zep_gemini.py) used
q["question"] (bare) which deviated from MABench default. This script re-runs
inference with q["query"] (wrapped) for paper rigor.

Reuses retrieval cache:
  - Mem0: rebuild via memory.search(query=wrapped_query) on existing Qdrant store
          (.cache/mem0_full100_qdrant_*)
  - Zep:  reuse cached retrieval edges/nodes/episodes from
          analysis/experiments/2026-05-03_writetime_querytime_eval/results/
          zep_full_retrieval_*.json (cached when retrieval_query was bare)

Note: For full MABench-default alignment, both retrieval AND inference should use
wrapped. We document any deviation explicitly. Here:
  - Mem0: re-do retrieval + inference with wrapped (full alignment)
  - Zep:  reuse retrieval cache (was done with bare retrieval_query),
          re-inference with wrapped — partial alignment (retrieval uses bare,
          inference uses wrapped). Documented as deviation.

Writes:
  analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/
    mem0_gemini_aligned_{sh,mh}_results.json
    zep_gemini_aligned_{sh,mh}_results.json
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
SH_MAB = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
MH_MAB = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS = 2048
RETRIEVE_NUM_MEM0 = 100
RETRIEVE_NUM_ZEP = 10


def normalize(s):
    if s is None: return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(pred, gold):
    if pred is None or gold is None: return False
    if isinstance(gold, list):
        return any(fuzzy_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn: return False
    return pn == gn or gn in pn or pn in gn


def get_wrapped_query_map(task):
    """Load q['query'] (FC wrapper-included) from MABench output JSON."""
    p = SH_MAB if task == "SH" else MH_MAB
    d = json.load(open(p))
    return {e["query_id"]: e["query"] for e in d["data"]}


# ============================================================
# Mem0 re-run
# ============================================================

def setup_mem0_client(task):
    """Build Mem0 instance with persistent Qdrant cache (matches Phase 0 setup)."""
    sys.path.insert(0, str(BASE))
    sys.path.insert(0, str(BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/scripts"))
    from mem0 import Memory
    from mem0.configs.base import MemoryConfig
    from mem0.utils.factory import LlmFactory
    LlmFactory.provider_to_class["gemini"] = "mem0_vertex_gemini_llm.VertexGeminiLLM"

    # NOTE: original Phase 0 ingestion was stored in `mem0_eval_qdrant_*` (1.2MB on May 3),
    # not `mem0_full100_qdrant_*` (which got overwritten in a botched run on May 6).
    qdrant_path = str(BASE / f".cache/mem0_eval_qdrant_{task.lower()}")
    if not Path(qdrant_path).exists():
        raise FileNotFoundError(f"Qdrant cache not found at {qdrant_path}; run original ingestion first")

    # Use SAME L1 modified extraction prompt as Phase 0 setup
    sys.path.insert(0, str(BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/scripts"))
    from run_mem0_gemini import make_l1_modified_prompt

    cfg = MemoryConfig(**{
        "llm": {"provider": "gemini",
                "config": {"model": MODEL, "temperature": 0.1, "max_tokens": 8192}},
        "embedder": {"provider": "huggingface",
                     "config": {"model": "sentence-transformers/all-MiniLM-L6-v2"}},
        "vector_store": {"provider": "qdrant",
                         "config": {"embedding_model_dims": 384, "path": qdrant_path,
                                    "collection_name": f"mem0_fc_{task.lower()}"}},
        "custom_fact_extraction_prompt": make_l1_modified_prompt(),
    })
    return Memory(config=cfg)


def call_gemini_inference_mem0(client, system_prompt, user_msg):
    from google.genai.errors import ClientError, ServerError
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=TEMPERATURE, max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        system_instruction=system_prompt,
    )
    contents = [{"role": "user", "parts": [{"text": user_msg}]}]
    for attempt in range(10):
        try:
            r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            return r.text if r.text else ""
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == 9: raise
            mret = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(mret.group(1)) + 2 if mret else min(2 ** attempt * 5, 60))
    return ""


def rerun_mem0_aligned(task):
    out_path = RESULTS / f"mem0_gemini_aligned_{task.lower()}_results.json"

    gt_path = SH_GT if task == "SH" else MH_GT
    gt = json.load(open(gt_path))
    qmap_wrapped = get_wrapped_query_map(task)
    user_id = f"mem0_eval_{task.lower()}"

    print(f"[Mem0 {task}] Setting up client...")
    memory = setup_mem0_client(task)

    from google import genai
    infer_client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    existing = []
    done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume Mem0 {task}] {len(done)} done")

    todo = [q for q in gt if q["query_id"] not in done]
    print(f"[pending Mem0 {task}] {len(todo)}")

    for i, q in enumerate(todo):
        qid = q["query_id"]
        wrapped = qmap_wrapped.get(qid, q["question"])
        gt_ans = q["gt_answer"]

        # Use WRAPPED query for retrieval (MABench default behavior)
        retrieved = memory.search(query=wrapped, user_id=user_id, limit=RETRIEVE_NUM_MEM0)
        results_list = retrieved.get("results", []) if isinstance(retrieved, dict) else []
        memories_str = "\n".join(f"- {entry.get('memory', '')}" for entry in results_list)

        # Inference with WRAPPED query
        system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
        user_msg = wrapped + "\n\nCurrent Time: " + time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            answer = call_gemini_inference_mem0(infer_client, system_prompt, user_msg)
        except Exception as e:
            answer = f"ERROR: {e}"

        em = fuzzy_match(answer, gt_ans)
        entry = {
            "query_id": qid, "question": q["question"], "wrapped_query_used": True,
            "gt_answer": gt_ans, "n_retrieved": len(results_list),
            "retrieved_memories_preview": [m.get("memory") for m in results_list[:5]],
            "pred_answer": answer, "exact_match": em,
        }
        if task == "MH":
            entry["num_hops"] = q.get("num_hops")
            entry["n_conflict"] = sum(1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair")
        existing.append(entry)
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [Mem0 {task} {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


# ============================================================
# Zep re-run (reuse cached retrieval)
# ============================================================

def call_gemini_inference_zep(client, system_prompt, user_msg):
    return call_gemini_inference_mem0(client, system_prompt, user_msg)


def rerun_zep_aligned(task):
    """Reuse cached Zep retrieval, re-do inference with wrapped query."""
    out_path = RESULTS / f"zep_gemini_aligned_{task.lower()}_results.json"
    cache_path = BASE / f"analysis/experiments/2026-05-03_writetime_querytime_eval/results/zep_full_retrieval_{task.lower()}.json"

    if not cache_path.exists():
        print(f"[Zep {task}] retrieval cache not found at {cache_path}; skip")
        return

    cached = {r["query_id"]: r for r in json.load(open(cache_path))}
    gt_path = SH_GT if task == "SH" else MH_GT
    gt = json.load(open(gt_path))
    qmap_wrapped = get_wrapped_query_map(task)

    from google import genai
    infer_client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fc-mh-494213"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )

    # Reuse the compose_search_context from methods/zep.py for fidelity
    sys.path.insert(0, str(BASE))
    from methods.zep import compose_search_context
    from zep_cloud.types import EntityEdge, EntityNode

    existing = []
    done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume Zep {task}] {len(done)} done")

    todo = [q for q in gt if q["query_id"] not in done]
    print(f"[pending Zep {task}] {len(todo)}")

    # Build the prompt structure matching MABench main pipeline (agent.py:llm_response)
    SYSTEM = "You are a helpful expert assistant answering questions from users based on the provided context."

    for i, q in enumerate(todo):
        qid = q["query_id"]
        wrapped = qmap_wrapped.get(qid, q["question"])
        gt_ans = q["gt_answer"]

        cached_q = cached.get(qid, {})
        edges_data = cached_q.get("edges", [])
        nodes_data = cached_q.get("nodes", [])
        eps_data = cached_q.get("episodes", [])
        context_block = cached_q.get("context_block", "") or ""

        # Re-construct compose_search_context content directly (cached fields are dicts)
        facts_lines = []
        for e in edges_data:
            fact = e.get("fact", "")
            valid_at = e.get("valid_at") or "date unknown"
            invalid_at = e.get("invalid_at") or "present"
            facts_lines.append(f'  - {fact} ({valid_at} - {invalid_at})')
        ent_lines = [f'  - {n.get("name","")}: {n.get("summary","")}' for n in nodes_data]
        ep_lines = [f'  - Content: {ep.get("content","")}' for ep in eps_data]

        retrieved_context = (
            f"\nFACTS and ENTITIES represent relevant context to the current conversation.\n\n"
            f"# These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.\n"
            f"# format: FACT (Date range: from - to)\n\n"
            f"{chr(10).join(facts_lines)}\n\n\n"
            f"# These are the most relevant entities\n"
            f"# ENTITY_NAME: entity summary\n\n"
            f"{chr(10).join(ent_lines)}\n\n\n"
            f"# These are the most relevant episodes.\n# format: EPISODE\n\n"
            f"{chr(10).join(ep_lines)}\n\n"
        )

        user_msg = (
            f"Your task is to briefly answer the question. You are given the following context "
            f"from the previous conversation. If you don't know how to answer the question, abstain "
            f"from answering.\n\n{retrieved_context}\n\n{wrapped}\n\nAnswer:"
        )
        try:
            answer = call_gemini_inference_zep(infer_client, SYSTEM, user_msg)
        except Exception as e:
            answer = f"ERROR: {e}"

        em = fuzzy_match(answer, gt_ans)
        entry = {
            "query_id": qid, "question": q["question"], "wrapped_query_used": True,
            "gt_answer": gt_ans,
            "n_edges": len(edges_data), "n_nodes": len(nodes_data), "n_episodes": len(eps_data),
            "retrieval_used_bare": True,  # caveat: cached retrieval used bare
            "pred_answer": answer, "exact_match": em,
        }
        if task == "MH":
            entry["num_hops"] = q.get("num_hops")
            entry["n_conflict"] = sum(1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair")
        existing.append(entry)
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [Zep {task} {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=["mem0", "zep", "both"], default="both")
    parser.add_argument("--task", choices=["SH", "MH", "both"], default="both")
    args = parser.parse_args()
    os.chdir(str(BASE))

    tasks = ["SH", "MH"] if args.task == "both" else [args.task]
    if args.system in ("zep", "both"):
        for t in tasks:
            print(f"\n=== Zep {t} aligned re-run ===")
            rerun_zep_aligned(t)
    if args.system in ("mem0", "both"):
        for t in tasks:
            print(f"\n=== Mem0 {t} aligned re-run ===")
            rerun_mem0_aligned(t)


if __name__ == "__main__":
    main()
