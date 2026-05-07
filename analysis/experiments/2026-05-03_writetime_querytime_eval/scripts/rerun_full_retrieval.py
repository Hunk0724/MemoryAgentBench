"""
Re-run query phase only — store FULL retrieved content for both Mem0 + Zep.

Reuses existing vector stores (Mem0 qdrant under .cache/) and Zep cloud graphs
(gemini_full100_*) — no re-ingestion needed. Just queries with each FC question
and saves complete retrieved content per question.

Outputs:
  results/mem0_full_retrieval_{sh,mh}.json
  results/zep_full_retrieval_{sh,mh}.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/home/yhchiang/MemoryAgentBench/.env")
except ImportError:
    pass

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench/analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts")

from mem0.utils.factory import LlmFactory
LlmFactory.provider_to_class["gemini"] = "mem0_vertex_gemini_llm.VertexGeminiLLM"

from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.configs.prompts import FACT_RETRIEVAL_PROMPT
from zep_cloud import Zep
from methods.zep import get_retrieval_query

import re

BASE = Path("/home/yhchiang/MemoryAgentBench")
EXP_DIR = BASE / "analysis/experiments/2026-05-03_writetime_querytime_eval"
RESULTS = EXP_DIR / "results"

MODEL = "gemini-3.1-flash-lite-preview"
RETRIEVE_NUM_MEM0 = 100
RETRIEVE_NUM_ZEP = 10
SESSION_PREFIX = "gemini_full100"


def make_l1_modified_prompt():
    pattern = re.compile(
        r'Input: Hi\.\s*\nOutput: \{"facts" : \[\]\}\s*\n\s*\n'
        r'Input: There are branches in trees\.\s*\nOutput: \{"facts" : \[\]\}\s*\n\s*\n',
        re.MULTILINE,
    )
    return pattern.sub('', FACT_RETRIEVAL_PROMPT)


def init_mem0(task):
    qdrant_path = str(BASE / f".cache/mem0_eval_qdrant_{task.lower()}")
    config_dict = {
        "llm": {
            "provider": "gemini",
            "config": {"model": MODEL, "temperature": 0.1, "max_tokens": 8192},
        },
        "embedder": {
            "provider": "huggingface",
            "config": {"model": "sentence-transformers/all-MiniLM-L6-v2"},
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "embedding_model_dims": 384,
                "path": qdrant_path,
                "collection_name": f"mem0_fc_{task.lower()}",
                "on_disk": True,  # persist vectors to disk (needed across processes)
            },
        },
        "custom_fact_extraction_prompt": make_l1_modified_prompt(),
    }
    return Memory(config=MemoryConfig(**config_dict))


def ingest_if_empty(memory, user_id):
    """Ingest 6k context if vector store is empty."""
    import tiktoken
    try:
        existing = memory.get_all(user_id=user_id)
        n_existing = len(existing.get("results", [])) if isinstance(existing, dict) else len(existing)
    except Exception:
        n_existing = 0
    if n_existing > 0:
        print(f"  [ingest skip] {n_existing} facts already in store")
        return n_existing

    text = (BASE / "analysis/contexts/factconsolidation_6k_context.txt").read_text()
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(text)
    chunks = [enc.decode(tokens[i:i + 512]) for i in range(0, len(tokens), 512)]
    print(f"  [ingest] {len(chunks)} chunks of ~512 tokens")
    n_added = 0
    for i, chunk in enumerate(chunks):
        messages = [
            {"role": "system", "content": "You are a helpful assistant that can help memorize details in the conversation."},
            {"role": "user", "content": chunk},
            {"role": "assistant", "content": "I'll make sure to add the content into the memory."},
        ]
        result = memory.add(messages, user_id=user_id)
        n = len(result.get("results", [])) if isinstance(result, dict) else 0
        n_added += n
        print(f"    chunk {i:2d}: {n} facts (total: {n_added})", flush=True)
    return n_added


def serialize_edge(e):
    return {
        "fact": getattr(e, "fact", ""),
        "name": getattr(e, "name", ""),
        "valid_at": str(getattr(e, "valid_at", "")) if getattr(e, "valid_at", None) else None,
        "invalid_at": str(getattr(e, "invalid_at", "")) if getattr(e, "invalid_at", None) else None,
        "source_node_uuid": str(getattr(e, "source_node_uuid", "")) if getattr(e, "source_node_uuid", None) else None,
        "target_node_uuid": str(getattr(e, "target_node_uuid", "")) if getattr(e, "target_node_uuid", None) else None,
        "uuid": str(getattr(e, "uuid_", "")) if getattr(e, "uuid_", None) else None,
    }


def serialize_node(n):
    return {
        "name": getattr(n, "name", ""),
        "summary": getattr(n, "summary", ""),
        "uuid": str(getattr(n, "uuid_", "")) if getattr(n, "uuid_", None) else None,
    }


def serialize_episode(ep):
    return {
        "content": getattr(ep, "content", ""),
        "name": getattr(ep, "name", ""),
        "uuid": str(getattr(ep, "uuid_", "")) if getattr(ep, "uuid_", None) else None,
    }


def rerun_mem0(task):
    print(f"\n=== Mem0 ingest+query rerun — task {task} ===")
    memory = init_mem0(task)
    user_id = f"mem0_eval_{task.lower()}"
    n_facts = ingest_if_empty(memory, user_id)
    print(f"  [ingest done] {n_facts} facts in store")
    gt_path = BASE / f"analysis/results/{task.lower()}_512_mquake_analysis.json"
    gt = json.load(open(gt_path))
    out = []
    for i, q in enumerate(gt):
        try:
            r = memory.search(query=q["question"], user_id=user_id, limit=RETRIEVE_NUM_MEM0)
            results_list = r.get("results", []) if isinstance(r, dict) else []
        except Exception as e:
            print(f"  [err qid={q['query_id']}] {e}")
            results_list = []
        out.append({
            "query_id": q["query_id"],
            "question": q["question"],
            "gt_answer": q["gt_answer"],
            "retrieved_full": [
                {
                    "memory": m.get("memory"),
                    "id": m.get("id"),
                    "score": m.get("score"),
                }
                for m in results_list
            ],
            "n_retrieved": len(results_list),
        })
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(gt)}] qid={q['query_id']} retrieved={len(results_list)}")
    out_path = RESULTS / f"mem0_full_retrieval_{task.lower()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  Written: {out_path}")


def rerun_zep(task):
    print(f"\n=== Zep query rerun — task {task} ===")
    zep = Zep(api_key=os.environ["ZEP_API_KEY"])
    suffix = f"factconsolidation_{task.lower()}_6k"
    graph_id = f"graph_{SESSION_PREFIX}_{suffix}"
    thread_id = f"thread_{SESSION_PREFIX}_{suffix}"

    gt_path = BASE / f"analysis/results/{task.lower()}_512_mquake_analysis.json"
    gt = json.load(open(gt_path))
    out = []
    for i, q in enumerate(gt):
        rq = get_retrieval_query(q["question"])[:399]
        try:
            edges = zep.graph.search(graph_id=graph_id, query=rq, scope="edges", limit=RETRIEVE_NUM_ZEP).edges or []
            nodes = zep.graph.search(graph_id=graph_id, query=rq, scope="nodes", limit=RETRIEVE_NUM_ZEP).nodes or []
            episodes = zep.graph.search(graph_id=graph_id, query=rq, scope="episodes", limit=RETRIEVE_NUM_ZEP).episodes or []
        except Exception as e:
            print(f"  [search err qid={q['query_id']}] {e}")
            edges, nodes, episodes = [], [], []
        try:
            ctx_resp = zep.thread.get_user_context(thread_id=thread_id)
            ctx_block = ctx_resp.context if ctx_resp else ""
        except Exception:
            ctx_block = ""
        out.append({
            "query_id": q["query_id"],
            "question": q["question"],
            "gt_answer": q["gt_answer"],
            "retrieval_query": rq,
            "edges": [serialize_edge(e) for e in edges],
            "nodes": [serialize_node(n) for n in nodes],
            "episodes": [serialize_episode(ep) for ep in episodes],
            "context_block": ctx_block,
        })
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(gt)}] qid={q['query_id']} edges={len(edges)} nodes={len(nodes)} episodes={len(episodes)}")
    out_path = RESULTS / f"zep_full_retrieval_{task.lower()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  Written: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=["mem0", "zep", "both"], default="both")
    parser.add_argument("--task", choices=["SH", "MH", "both"], default="both")
    args = parser.parse_args()

    tasks = ["MH", "SH"] if args.task == "both" else [args.task]
    if args.system in ("mem0", "both"):
        for t in tasks:
            rerun_mem0(t)
    if args.system in ("zep", "both"):
        for t in tasks:
            rerun_zep(t)


if __name__ == "__main__":
    main()
