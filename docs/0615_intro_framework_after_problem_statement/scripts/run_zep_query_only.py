"""Re-query an EXISTING Zep graph (no re-ingest) with the fixed get_retrieval_query
(bare raw question) at Zep's NATIVE retrieve_num (10). Benchmark SubEM scoring
(consistent with ours/vanilla/LCA). For FC-SH where the graph is already built.
  Usage: RUN_OAI_KEY_NAME=OPENAI_API_KEY_C python run_zep_query_only.py <L>
"""
import os, sys, json, glob, asyncio
from collections import defaultdict

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); os.environ.setdefault(k, v)
kn = os.environ.get("RUN_OAI_KEY_NAME")
if kn and os.environ.get(kn):
    os.environ["OPENAI_API_KEY"] = os.environ[kn]

sys.path.insert(0, os.path.abspath('.'))
from zep_cloud import Zep
from methods.zep import compose_search_context, llm_response, get_retrieval_query, OpenAIAgent
from utils.eval_other_utils import normalize_answer

L = sys.argv[1]
K = 10  # Zep native retrieve_num
client = Zep(api_key=os.environ['ZEP_API_KEY'])
oai = OpenAIAgent(model="gpt-4o-mini", source="openai", api_dict={}, temperature=0)
graph_id, thread_id = f"graph_0_factconsolidation_sh_{L}", f"thread_0_factconsolidation_sh_{L}"

gtct = {r["query_id"]: r.get("conflict_type") for r in json.load(open(f"analysis/results/sh_{L}_mquake_analysis.json")) if "query_id" in r}
src = glob.glob(f"outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified/**/*sh_{L}*results*.json", recursive=True)[0]
rows = json.load(open(src))["data"]

agg = defaultdict(lambda: [0, 0])
out = []
for i, r in enumerate(rows):
    qid, query, ans = r["query_id"], r["query"], r["answer"]
    gt = ans[0] if isinstance(ans, list) else ans
    rq = get_retrieval_query(query)
    try:
        edges = client.graph.search(graph_id=graph_id, query=rq[:399], scope="edges", limit=K).edges
        nodes = client.graph.search(graph_id=graph_id, query=rq[:399], scope="nodes", limit=K).nodes
        eps = client.graph.search(graph_id=graph_id, query=rq[:399], scope="episodes", limit=K).episodes
    except Exception as e:
        print(f"  q{qid} search err: {e}"); continue
    try:
        cb = client.thread.get_user_context(thread_id=thread_id).context
    except Exception:
        cb = ""
    ctx = compose_search_context(edges, nodes, cb, eps)
    pred = asyncio.run(llm_response(oai, ctx, query))
    if "Answer:" in pred:
        pred = pred.split("Answer:")[-1]
    em = normalize_answer(gt) in normalize_answer(pred)
    c = gtct.get(qid, "?"); agg[c][0] += 1; agg[c][1] += int(em)
    out.append({"query_id": qid, "gt": gt, "pred": pred.strip()[:60], "exact_match": em, "conflict_type": c})
    if (i + 1) % 20 == 0:
        tot = sum(v[1] for v in agg.values()); print(f"  [{i+1}/{len(rows)}] acc {tot}", flush=True)

os.makedirs("outputs/gpt-4o-mini-zep/Conflict_Resolution", exist_ok=True)
json.dump(out, open(f"outputs/gpt-4o-mini-zep/Conflict_Resolution/zep_rawq_sh_{L}_k{K}.json", "w"), ensure_ascii=False, indent=2)
hp, nc = agg["has_pair"], agg["no_conflict_pair"]; n = sum(v[0] for v in agg.values()); em = sum(v[1] for v in agg.values())
print(f"\n=== Zep FC-SH {L} (bare-raw-q, native k={K}, SubEM) ===")
print(f"  has_pair {hp[1]}/{hp[0]} | no_conf {nc[1]}/{nc[0]} | overall {em}/{n}")
