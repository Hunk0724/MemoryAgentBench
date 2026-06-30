"""
Reconstruct a mem0 store from SAVED ingestion output (vector_results = mem0's
actual add/update/delete returns, with uuid+event+text) and run QA WITHOUT
re-running the ingestion update-LLM. Only embeddings are recomputed (cheap).

Faithfulness: replays the exact operations mem0 logged -> exact final memory set;
embeds with the SAME embedder mem0 used (VertexADCEmbedding, text-embedding-004,
RETRIEVAL_DOCUMENT for memories / RETRIEVAL_QUERY for the query, cosine top-k);
answers with the SAME prompt/config as agent._answer_with_client. So retrieval
and answer should match a live mem0 run on the same ingestion.

VALIDATE before trusting: --validate-against a live-mem0 QA result.json; the
script reports per-item agreement. Use reconstruction only if agreement is ~100%.

vector_results files are APPENDED across runs -> select ONE clean run with
--slice (python slice on the line list, e.g. "-12" = last 12, "0:64" = first 64).
"""
import argparse, json, os, sys, time
import numpy as np
from pathlib import Path

BASE = "/home/yhchiang/MemoryAgentBench"
sys.path.insert(0, BASE)
from methods.mem0_vertex_adc_embedder import VertexADCEmbedding
from mem0.configs.embeddings.base import BaseEmbedderConfig
from utils.templates import get_template
from utils.eval_other_utils import drqa_exact_match_score, substring_exact_match_score, normalize_answer
from google import genai
from google.genai import types as gt

ap = argparse.ArgumentParser()
ap.add_argument("--vr-file", required=True, help="ingestion_context_0.jsonl (has vector_results)")
ap.add_argument("--slice", required=True, help="python slice over lines, e.g. '-12' or '0:64'")
ap.add_argument("--priority-gt", required=True, help="tagged priority GT (items to ask)")
ap.add_argument("--sub-dataset", required=True, help="e.g. factconsolidation_sh_6k")
ap.add_argument("--agent-name", default="Structure_rag_mem0")  # -> rag_agent template
ap.add_argument("--retrieve-num", type=int, default=100)
ap.add_argument("--out", required=True)
ap.add_argument("--validate-against", default=None)
ap.add_argument("--expected-final", type=int, default=0, help="sanity: expected final memory count")
args = ap.parse_args()


def parse_slice(s):
    if ":" in s:
        a, b = s.split(":"); return slice(int(a) if a else None, int(b) if b else None)
    return slice(int(s), None) if int(s) < 0 else slice(int(s), int(s) + 1)


# ---- 1. replay vector_results -> final memory texts ----
lines = [json.loads(l) for l in open(args.vr_file)]
sel = lines[parse_slice(args.slice)]
mem = {}
ev = {"ADD": 0, "UPDATE": 0, "DELETE": 0, "NONE": 0}
for ln in sel:
    for r in ln["vector_results"]["results"]:
        e = r["event"]; ev[e] = ev.get(e, 0) + 1
        if e in ("ADD", "UPDATE"):
            mem[r["id"]] = r["memory"]
        elif e == "DELETE":
            mem.pop(r["id"], None)
texts = list(mem.values())
print(f"[recon] replayed {len(sel)} chunks events={ev} -> final memories={len(texts)}", flush=True)
if args.expected_final:
    print(f"[recon] expected_final≈{args.expected_final} (diff {len(texts)-args.expected_final})", flush=True)

# ---- 2. embed all memory texts (RETRIEVAL_DOCUMENT), batched ----
emb = VertexADCEmbedding(BaseEmbedderConfig(model="text-embedding-004", embedding_dims=768))
def embed_batch(contents, task):
    return emb._embed_with_retry([c.replace("\n", " ") for c in contents], task)
M = []
for i in range(0, len(texts), 100):
    M.extend(embed_batch(texts[i:i+100], "RETRIEVAL_DOCUMENT"))
    print(f"[recon] embedded {min(i+100,len(texts))}/{len(texts)} memories", flush=True)
M = np.array(M, dtype=np.float32)
M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)

# ---- 3. QA per priority item ----
client = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                      location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
qtmpl = get_template(args.sub_dataset, "query", args.agent_name)

off = {}
if args.validate_against:
    vd = json.load(open(args.validate_against))
    rowsrc = vd["rows"] if "rows" in vd else vd["data"]
    for r in rowsrc:
        key = r.get("qa_id") or r.get("query")
        off[key] = r.get("output")

def answer(query, mems_str):
    sysp = f"You are a helpful AI. Answer the question based on query and memories.\n{mems_str}\n"
    prompt = sysp + "\n\n" + query + "\n\nCurrent Time: 2026-06-08 00:00:00"
    cfg = gt.GenerateContentConfig(max_output_tokens=256, temperature=0,
                                   thinking_config=gt.ThinkingConfig(thinking_level="minimal"))
    for attempt in range(8):
        try:
            return client.models.generate_content(model="gemini-3.1-flash-lite",
                                                   contents=prompt, config=cfg).text or ""
        except Exception as e:
            if ("429" not in str(e) and "503" not in str(e)) or attempt == 7: raise
            time.sleep(min(2**attempt*10, 120))

items = json.load(open(args.priority_gt))
rows = []
n_em = n_leak = n_val = n_match = 0
for it in items:
    q = qtmpl.format(question=it["question"])
    qv = np.array(embed_batch([q], "RETRIEVAL_QUERY")[0], dtype=np.float32)
    qv /= (np.linalg.norm(qv) + 1e-12)
    sims = M @ qv
    top = np.argsort(-sims)[: args.retrieve_num]
    mems_str = "\n".join(f"- {texts[j]}" for j in top)
    out = answer(q, mems_str)
    gts = [it["gt_answer"]] + [a for a in it.get("gt_answer_aliases", []) if a]
    em = any(drqa_exact_match_score(out, g) for g in gts) or any(substring_exact_match_score(out, g) for g in gts)
    leak = substring_exact_match_score(out, it["old_answer"]) if it.get("old_answer") else False
    n_em += em; n_leak += leak
    vm = None
    if it["qa_id"] in off and off[it["qa_id"]] is not None:
        n_val += 1; vm = normalize_answer(out) == normalize_answer(off[it["qa_id"]]); n_match += bool(vm)
    rows.append({"qa_id": it["qa_id"], "fate": it.get("write_time_fate"), "question": it["question"],
                 "gt_answer": it["gt_answer"], "output": out, "EM": em, "stale_leak": leak,
                 "live_output": off.get(it["qa_id"]), "validate_match": vm})

n = len(items)
summary = {"n": n, "EM": round(100*n_em/n, 1), "stale_leak_pct": round(100*n_leak/n, 1),
           "final_memories": len(texts),
           "validate_n": n_val, "validate_agreement": (round(100*n_match/n_val, 1) if n_val else None)}
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
json.dump({"summary": summary, "rows": rows}, open(args.out, "w"), ensure_ascii=False, indent=1)
print("\n=== RECONSTRUCTION QA ===")
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("written:", args.out)
