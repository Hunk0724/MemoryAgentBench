"""Phase 3 of Zep-on-LongMemEval (KU): query each per-question Zep graph and emit
hypotheses for the OFFICIAL judge. Mirrors run_zep_query_only.py but over the
LongMemEval per-question graphs built by zep_lme_ingest.py.

Per question (same idx%NSHARD==SHARD mapping as ingest, so we hit the account that
built the graph): search edges+nodes+episodes with the BARE question (raw-question
fairness), compose Zep's multi-granularity context (facts w/ valid_at..invalid_at +
entities + episodes), answer with gpt-4o-mini via llm_response (which already asks
for a brief answer), write {question_id, hypothesis}.

Usage (one shard):
  ZEP_API_KEY=... OPENAI_API_KEY=... python zep_lme_query.py --data <json> \
      --out <hyp.jsonl> --nshard N --shard I [--limit M] [--k 10]
"""
import argparse, asyncio, json, os, sys, time

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from zep_cloud import Zep
from methods.zep import compose_search_context, llm_response, OpenAIAgent

GRAPH = lambda cid: f"lme_ku_{cid}"


def search_retry(client, g, q, scope, k, retries=3, wait=20):
    for a in range(retries):
        try:
            r = client.graph.search(graph_id=g, query=q[:399], scope=scope, limit=k)
            return getattr(r, scope, None)
        except Exception as e:
            if a < retries - 1:
                time.sleep(wait)
            else:
                print(f"    search {scope} err: {repr(e)[:100]}", flush=True)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--qtype", default="knowledge-update")
    ap.add_argument("--nshard", type=int, default=1)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=10)  # Zep native retrieve_num
    args = ap.parse_args()

    client = Zep(api_key=os.environ["ZEP_API_KEY"])
    oai = OpenAIAgent(model="gpt-4o-mini", source="openai", api_dict={}, temperature=0)
    data = json.load(open(args.data))
    items = [d for d in data if d.get("question_type") == args.qtype]
    if args.limit:
        items = items[: args.limit]
    if args.nshard > 1:
        items = [d for i, d in enumerate(items) if i % args.nshard == args.shard]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    done = set()
    if os.path.exists(args.out):
        for ln in open(args.out):
            try: done.add(json.loads(ln)["question_id"])
            except Exception: pass
    out_f = open(args.out, "a", encoding="utf-8")
    print(f"[zep-query] {len(items)} '{args.qtype}' (shard {args.shard}/{args.nshard}) k={args.k}", flush=True)

    for qi, d in enumerate(items):
        qid = d["question_id"]
        if qid in done:
            continue
        cid = qid.replace("-", "_"); g = GRAPH(cid); bare = d["question"]
        edges = search_retry(client, g, bare, "edges", args.k)
        nodes = search_retry(client, g, bare, "nodes", args.k)
        eps = search_retry(client, g, bare, "episodes", args.k)
        ctx = compose_search_context(edges, nodes, "", eps)
        try:
            pred = asyncio.run(llm_response(oai, ctx, bare))
        except Exception as e:
            print(f"  [{qid}] answer err: {repr(e)[:100]}", flush=True); pred = ""
        if "Answer:" in pred:
            pred = pred.split("Answer:")[-1].strip()
        out_f.write(json.dumps({"question_id": qid, "hypothesis": pred}, ensure_ascii=False) + "\n")
        out_f.flush()
        print(f"[zep-query] ({qi+1}/{len(items)}) {qid} | edges={len(edges or [])} eps={len(eps or [])} "
              f"| ans: {pred[:70]!r}", flush=True)

    out_f.close()
    print(f"[zep-query] DONE shard {args.shard}/{args.nshard} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
