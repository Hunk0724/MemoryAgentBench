"""
Retry failed queries from RETRIEVAL_FULL_100queries.json with throttling + 429 backoff.
Free Zep tier: 300 reqs / 5-min window. We pace at 1.2s/query (3 search calls each).
"""
import os, json, time, re
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
        "hippo_results": "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json",
        "out_path": "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json",
    },
    {
        "task": "mh",
        "graph_id": "graph_0_factconsolidation_mh_6k",
        "hippo_results": "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json",
        "out_path": "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json",
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
        "content": str(ep.content),
        "uuid": str(ep.uuid_) if hasattr(ep, "uuid_") else None,
        "score": getattr(ep, "score", None),
        "relevance": getattr(ep, "relevance", None),
        "role": getattr(ep, "role", None),
        "source": getattr(ep, "source", None),
    }


def search_with_retry(graph_id: str, q: str, scope: str, max_retries: int = 8):
    for attempt in range(max_retries):
        try:
            return client.graph.search(graph_id=graph_id, query=q, scope=scope, limit=10)
        except Exception as e:
            sc = getattr(e, "status_code", None)
            msg = str(e)
            if sc != 429 and "status_code: 429" not in msg:
                raise
            # parse retry-after from headers (attribute or stringified)
            headers = getattr(e, "headers", None) or {}
            ra = headers.get("retry-after") if isinstance(headers, dict) else None
            if ra is None:
                m = re.search(r"'retry-after':\s*'(\d+)'", msg)
                ra = m.group(1) if m else "10"
            sleep_s = int(ra) + 2
            print(f"      [429] retry-after {ra}s, sleeping {sleep_s}s (attempt {attempt+1})", flush=True)
            time.sleep(sleep_s)
            continue
    raise RuntimeError(f"Exceeded retries for scope={scope} q={q[:40]!r}")


for cfg in CONFIGS:
    out_path = Path(cfg["out_path"])
    if not out_path.exists():
        print(f"  {cfg['task']}: {out_path} missing, skipping retry")
        continue
    existing = {r["query_id"]: r for r in json.load(open(out_path))}
    failed = [qid for qid, r in existing.items() if "error" in r]
    if not failed:
        print(f"  {cfg['task']}: no failed queries, skipping")
        continue

    print(f"\n=== Retrying {cfg['task'].upper()}: {len(failed)} failed queries ===")
    with open(cfg["hippo_results"]) as f:
        hippo = json.load(f)
    qmap = {d["query_id"]: d for d in hippo["data"]}

    # throttle: 300 calls / 5min = 1/sec; we make 3 calls per query → sleep 3.5s/query (safer)
    SLEEP = 1.5
    t0 = time.time()
    for i, qid in enumerate(failed):
        d = qmap[qid]
        retrieval_query = get_retrieval_query(d["query"])
        q = retrieval_query[:399]
        try:
            edges_r = search_with_retry(cfg["graph_id"], q, "edges").edges
            time.sleep(SLEEP)
            nodes_r = search_with_retry(cfg["graph_id"], q, "nodes").nodes
            time.sleep(SLEEP)
            eps_r = search_with_retry(cfg["graph_id"], q, "episodes").episodes
            time.sleep(SLEEP)
            existing[qid] = {
                "query_id": qid,
                "edges": [serialize_edge(e) for e in (edges_r or [])],
                "nodes": [serialize_node(n) for n in (nodes_r or [])],
                "episodes": [serialize_episode(ep) for ep in (eps_r or [])],
            }
            print(f"  [{i+1}/{len(failed)}] q{qid} OK ({time.time()-t0:.0f}s elapsed)", flush=True)
        except Exception as e:
            print(f"  [{i+1}/{len(failed)}] q{qid} FAILED: {e}", flush=True)
            existing[qid] = {"query_id": qid, "error": str(e)[:200]}

    # save (preserve original order by query_id)
    sorted_results = [existing[qid] for qid in sorted(existing.keys())]
    with open(out_path, "w") as f:
        json.dump(sorted_results, f, ensure_ascii=False, indent=2)

    still_failed = [qid for qid, r in existing.items() if "error" in r]
    print(f"\n  Saved → {out_path}")
    print(f"  Status: {len(existing) - len(still_failed)}/{len(existing)} OK, {len(still_failed)} still failed")
    if still_failed:
        print(f"  Still failed: {still_failed}")

print("\nDONE", flush=True)
