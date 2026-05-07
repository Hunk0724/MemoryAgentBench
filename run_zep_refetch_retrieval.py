"""
Retrieval-only re-fetch for Zep on FC-SH + FC-MH.

Purpose: the original FULL_100queries.json dump truncated episode content to
[:500] chars, undercounting episode-recall in post-hoc analysis. This script
re-calls graph.search (no re-ingest, no LLM, no EM) and saves FULL episode
content for clean recall analysis.

Outputs:
  outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json
  outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json
"""
import os, json, time
from pathlib import Path

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

from zep_cloud import Zep
from methods.zep import get_retrieval_query

client = Zep(api_key=os.environ['ZEP_API_KEY'])

CONFIGS = [
    {
        "task": "sh",
        "graph_id": "graph_0_factconsolidation_sh_6k",
        "thread_id": "thread_0_factconsolidation_sh_6k",
        "hippo_results": "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json",
        "out_dir": "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512",
    },
    {
        "task": "mh",
        "graph_id": "graph_0_factconsolidation_mh_6k",
        "thread_id": "thread_0_factconsolidation_mh_6k",
        "hippo_results": "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json",
        "out_dir": "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512",
    },
]


def serialize_edge(e):
    return {
        "fact": e.fact,
        "name": getattr(e, "name", None),
        "source_node": getattr(e, "source_node_uuid", None),
        "target_node": getattr(e, "target_node_uuid", None),
        "valid_at": str(e.valid_at) if e.valid_at else None,
        "invalid_at": str(e.invalid_at) if e.invalid_at else None,
        "uuid": str(e.uuid_) if hasattr(e, "uuid_") else None,
        "score": getattr(e, "score", None),
        "relevance": getattr(e, "relevance", None),
    }


def serialize_node(n):
    return {
        "name": n.name,
        "summary": n.summary,
        "uuid": str(n.uuid_) if hasattr(n, "uuid_") else None,
        "score": getattr(n, "score", None),
        "relevance": getattr(n, "relevance", None),
    }


def serialize_episode(ep):
    return {
        "content": str(ep.content),                          # full, no truncation
        "uuid": str(ep.uuid_) if hasattr(ep, "uuid_") else None,
        "score": getattr(ep, "score", None),
        "relevance": getattr(ep, "relevance", None),
        "role": getattr(ep, "role", None),
        "source": getattr(ep, "source", None),
    }


for cfg in CONFIGS:
    print(f"\n{'='*70}\nRetrieval-only re-fetch: FC-{cfg['task'].upper()}\n{'='*70}")
    with open(cfg["hippo_results"]) as f:
        hippo = json.load(f)
    queries = [(d["query_id"], d["query"], d["answer"]) for d in hippo["data"]]
    print(f"Queries: {len(queries)}", flush=True)

    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "RETRIEVAL_FULL_100queries.json"

    results = []
    t0 = time.time()
    for i, (qid, query, gt) in enumerate(queries):
        retrieval_query = get_retrieval_query(query)
        try:
            edges_r = client.graph.search(graph_id=cfg["graph_id"], query=retrieval_query[:399], scope="edges", limit=10).edges
            nodes_r = client.graph.search(graph_id=cfg["graph_id"], query=retrieval_query[:399], scope="nodes", limit=10).nodes
            eps_r = client.graph.search(graph_id=cfg["graph_id"], query=retrieval_query[:399], scope="episodes", limit=10).episodes
        except Exception as e:
            print(f"  q{qid} error: {e}", flush=True)
            results.append({"query_id": qid, "error": str(e)})
            continue

        results.append({
            "query_id": qid,
            "edges": [serialize_edge(e) for e in (edges_r or [])],
            "nodes": [serialize_node(n) for n in (nodes_r or [])],
            "episodes": [serialize_episode(ep) for ep in (eps_r or [])],
        })

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(queries)}] elapsed {time.time()-t0:.0f}s", flush=True)

    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  → saved {out_path} ({time.time()-t0:.0f}s)", flush=True)

print("\nDONE", flush=True)
