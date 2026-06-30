"""
Minimal prototype of OUR METHOD vs vanilla mem0, on FC-SH.

Insight: mem0 makes an IRREVERSIBLE, QUERY-AGNOSTIC conflict verdict at write time
(UPDATE/DELETE) and STRIPS the recency signal at extraction. Our method instead:
  - NON-DESTRUCTIVE ingestion: keep ALL extracted facts (no UPDATE/DELETE).
  - PRESERVE recency: tag each fact with its ingestion-order index (a real signal
    every system has — NOT the benchmark's printed serial; for FC they coincide).
  - QUERY-TIME resolution: retrieve top-k for THIS query, present the candidates
    WITH their order, and let the answer LLM pick the newest (largest order).

This is the minimal change (keep history, reversible, query-time). It needs no
write-time update LLM at all (cheaper) and recovers the pairs mem0 destroyed.

Compares directly to the mem0 baseline on the SAME questions / same answer LLM.
"""
import argparse, json, os, time
import numpy as np
from pathlib import Path
import sys
BASE = "/home/yhchiang/MemoryAgentBench"
sys.path.insert(0, BASE)
from methods.mem0_vertex_adc_embedder import VertexADCEmbedding
from mem0.configs.embeddings.base import BaseEmbedderConfig
from utils.templates import get_template
from utils.eval_other_utils import drqa_exact_match_score, substring_exact_match_score
from openai import OpenAI
from google import genai
from google.genai import types as gt

ap = argparse.ArgumentParser()
ap.add_argument("--cache", required=True, help="extraction_cache_<L>.json (all facts, ingestion order)")
ap.add_argument("--gt", required=True, help="question GT (sh_<L>_RUN_gt.json or BATTLEFIELD)")
ap.add_argument("--sub-dataset", required=True)
ap.add_argument("--answer-model", default="gpt-4o-mini", help="gpt-4o-mini | gemini-3.1-flash-lite")
ap.add_argument("--retrieve-num", type=int, default=100)
ap.add_argument("--out", required=True)
args = ap.parse_args()

# --- non-destructive store: all facts in ingestion order ---
cache = json.load(open(args.cache))
facts = [f for v in cache.values() for f in (v if isinstance(v, list) else [])]
print(f"[proto] non-destructive store = {len(facts)} facts (vs mem0's consolidated subset)", flush=True)

emb = VertexADCEmbedding(BaseEmbedderConfig(model="text-embedding-004", embedding_dims=768))
def embed_batch(contents, task):
    return emb._embed_with_retry([c.replace("\n", " ") for c in contents], task)
M = []
for i in range(0, len(facts), 100):
    M.extend(embed_batch(facts[i:i+100], "RETRIEVAL_DOCUMENT"))
    print(f"[proto] embedded {min(i+100,len(facts))}/{len(facts)}", flush=True)
M = np.array(M, dtype=np.float32); M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)

# --- answer client ---
use_gemini = "gemini" in args.answer_model
if use_gemini:
    gclient = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                           location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
else:
    oclient = OpenAI()
qtmpl = get_template(args.sub_dataset, "query", "Structure_rag_mem0")  # FC rag_agent template

def answer(query, mems_str):
    sysp = f"You are a helpful AI. Answer the question based on query and memories.\n{mems_str}\n"
    user = query + "\n\nCurrent Time: 2026-06-09 00:00:00"
    for attempt in range(8):
        try:
            if use_gemini:
                prompt = sysp + "\n\n" + user
                return gclient.models.generate_content(model=args.answer_model, contents=prompt,
                    config=gt.GenerateContentConfig(max_output_tokens=256, temperature=0,
                        thinking_config=gt.ThinkingConfig(thinking_level="minimal"))).text or ""
            r = oclient.chat.completions.create(model=args.answer_model,
                messages=[{"role": "system", "content": sysp}, {"role": "user", "content": user}],
                temperature=0, max_tokens=256)
            return r.choices[0].message.content or ""
        except Exception as e:
            if ("429" not in str(e) and "503" not in str(e)) or attempt == 7: raise
            time.sleep(min(2**attempt*8, 90))

items = json.load(open(args.gt))
rows = []; n_em = n_leak = 0
for it in items:
    if it.get("conflict_type") == "no_pair" and "gt_fact_text" not in it:
        pass
    q = qtmpl.format(question=it["question"])
    qv = np.array(embed_batch([q], "RETRIEVAL_QUERY")[0], dtype=np.float32); qv /= (np.linalg.norm(qv)+1e-12)
    top = np.argsort(-(M @ qv))[: args.retrieve_num]
    # present retrieved facts WITH ingestion-order index (smaller idx = older, larger = newer)
    top_sorted = sorted(top.tolist())
    mems_str = "\n".join(f"{j}. {facts[j]}" for j in top_sorted)
    out = answer(q, mems_str)
    gts = [it["gt_answer"]] + [a for a in it.get("gt_answer_aliases", []) if a]
    em = any(drqa_exact_match_score(out, g) for g in gts) or any(substring_exact_match_score(out, g) for g in gts)
    leak = substring_exact_match_score(out, it["old_answer"]) if it.get("old_answer") else False
    n_em += em; n_leak += leak
    rows.append({"qa_id": it.get("qa_id", it.get("query_id")), "question": it["question"],
                 "gt_answer": it["gt_answer"], "output": out, "EM": em, "stale_leak": leak,
                 "final_store_mem0": it.get("final_store"), "write_time_fate": it.get("write_time_fate")})

n = len(items)
summary = {"method": "prototype-nondestructive-querytime", "answer_model": args.answer_model,
           "store_facts": len(facts), "n": n, "EM": round(100*n_em/n, 1),
           "stale_leak_pct": round(100*n_leak/n, 1)}
# breakdown by mem0's final-store error mode if available
bd = {}
for r in rows:
    k = r.get("final_store_mem0")
    if k:
        b = bd.setdefault(k, {"n": 0, "em": 0}); b["n"] += 1; b["em"] += bool(r["EM"])
if bd:
    summary["by_mem0_final_store"] = {k: {"n": v["n"], "EM": round(100*v["em"]/v["n"], 1)} for k, v in bd.items()}
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
json.dump({"summary": summary, "rows": rows}, open(args.out, "w"), ensure_ascii=False, indent=1)
print("\n=== PROTOTYPE QA ==="); print(json.dumps(summary, ensure_ascii=False, indent=1))
print("written:", args.out)
