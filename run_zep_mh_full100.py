"""Run all 100 FC-MH queries against existing Zep chunk=512 graph."""
import os, json, time, asyncio
from pathlib import Path

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

from zep_cloud import Zep
from methods.zep import compose_search_context, llm_response, get_retrieval_query, OpenAIAgent

client = Zep(api_key=os.environ['ZEP_API_KEY'])
oai_client = OpenAIAgent(model="gpt-4o-mini", source="openai", api_dict={}, temperature=0.7)

graph_id = "graph_0_factconsolidation_mh_6k"
thread_id = "thread_0_factconsolidation_mh_6k"

# Load MH queries from HippoRAG baseline results (same 100 queries)
with open('outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json') as f:
    hippo = json.load(f)
all_queries = [(d['query_id'], d['query'], d['answer']) for d in hippo['data']]
print(f"Total MH queries: {len(all_queries)}", flush=True)

# Extra warmup wait to be safe
print("Waiting 60s for safety before starting queries...", flush=True)
time.sleep(60)

all_results = []
start = time.time()
for i, (qid, query, gt) in enumerate(all_queries):
    gt_text = gt[0] if isinstance(gt, list) else gt
    retrieval_query = get_retrieval_query(query)

    try:
        edges_r = client.graph.search(graph_id=graph_id, query=retrieval_query[:399], scope='edges', limit=10).edges
        nodes_r = client.graph.search(graph_id=graph_id, query=retrieval_query[:399], scope='nodes', limit=10).nodes
        eps_r = client.graph.search(graph_id=graph_id, query=retrieval_query[:399], scope='episodes', limit=10).episodes
    except Exception as e:
        print(f"  q{qid} retrieve error: {e}", flush=True)
        continue

    try:
        memory = client.thread.get_user_context(thread_id=thread_id)
        context_block = memory.context
    except:
        context_block = ""

    retrieved_context = compose_search_context(edges_r, nodes_r, context_block, eps_r)
    response = asyncio.run(llm_response(oai_client, retrieved_context, query))

    pred = response.strip().rstrip('.').rstrip(',')
    if "Answer:" in pred:
        pred = pred.split("Answer:")[-1].strip()

    em = pred.lower().strip('.,') == gt_text.lower().strip('.,')

    all_results.append({
        "query_id": qid, "gt": gt_text, "pred": pred, "raw_response": response,
        "exact_match": em,
        "edges": [{"fact": e.fact,
                   "valid_at": str(e.valid_at) if e.valid_at else None,
                   "invalid_at": str(e.invalid_at) if e.invalid_at else None} for e in (edges_r or [])],
        "nodes": [{"name": n.name, "summary": n.summary} for n in (nodes_r or [])],
        "episodes": [{"content": str(ep.content)} for ep in (eps_r or [])],
    })

    if (i+1) % 10 == 0:
        c = sum(1 for r in all_results if r['exact_match'])
        elapsed = time.time() - start
        print(f"  [{i+1}/100] Acc so far: {c}/{i+1} = {c/(i+1)*100:.1f}%, elapsed {elapsed:.0f}s", flush=True)

out_dir = Path('outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512')
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / 'FULL_100queries.json'
with open(out_path, 'w') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

correct = sum(1 for r in all_results if r['exact_match'])
print(f"\nSaved to {out_path}", flush=True)
print(f"=== FINAL: Zep chunk=512 FC-MH 100 queries ===", flush=True)
print(f"Acc: {correct}/{len(all_results)} = {correct/len(all_results)*100:.1f}%", flush=True)
