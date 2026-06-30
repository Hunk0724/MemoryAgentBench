"""
Zep cloud × Vertex Gemini inference × FC-SH/MH × full 100 questions.

Standalone runner.

Asymmetry caveat (PAPER-RELEVANT):
  Zep cloud does ingestion, entity/edge extraction, supersession (invalid_at),
  and search using its OWN internal LLM. We CANNOT change Zep's internal LLM.
  We only change the FINAL QA reading step to Gemini 3.1 Flash-Lite via Vertex.

Pipeline mirrors agent.py:_handle_zep_agent but with:
  - Inference-side LLM swapped to Vertex Gemini (matches HippoRAG-v2 / oracles)
  - New session IDs (avoid colliding with prior gpt-4o-mini Zep run)
  - Single shared graph per task (re-ingest happens once, then 100 queries)

Usage:
  python run_zep_gemini.py --task SH
  python run_zep_gemini.py --task MH
  python run_zep_gemini.py --task both

Resume-safe: skip qids already in output.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

# Load .env (need ZEP_API_KEY, Vertex env vars)
try:
    from dotenv import load_dotenv
    load_dotenv("/home/yhchiang/MemoryAgentBench/.env")
except ImportError:
    pass

# Add project root for methods.zep imports
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")

from zep_cloud import Zep
from methods.zep import compose_search_context, get_retrieval_query

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

import tiktoken

BASE = Path("/home/yhchiang/MemoryAgentBench")
EXP_DIR = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100"
RESULTS_DIR = EXP_DIR / "results"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS_INFERENCE = 2048
CHUNK_SIZE_TOKENS = 512
RETRIEVE_NUM = 10  # match agent.py default for Zep
SESSION_PREFIX = "gemini_full100"  # new session, avoid colliding with prior run
ZEP_INGEST_WAIT_SECONDS = 360  # 6 min for async processing


def chunk_context(text, chunk_tokens=CHUNK_SIZE_TOKENS):
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(text)
    return [enc.decode(tokens[i:i + chunk_tokens]) for i in range(0, len(tokens), chunk_tokens)]


def normalize(s):
    if s is None:
        return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(pred, gold):
    if pred is None or gold is None:
        return False
    if isinstance(gold, list):
        return any(fuzzy_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn:
        return False
    return pn == gn or gn in pn or pn in gn


def init_zep_client():
    api_key = os.environ.get("ZEP_API_KEY")
    if not api_key:
        raise RuntimeError("ZEP_API_KEY not set")
    return Zep(api_key=api_key)


def init_gemini_client():
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() != "true":
        raise RuntimeError("GOOGLE_GENAI_USE_VERTEXAI must be 'true'")
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )


def call_gemini_inference(client, system_prompt, user_msg):
    cfg = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_TOKENS_INFERENCE,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        system_instruction=system_prompt,
    )
    contents = [{"role": "user", "parts": [{"text": user_msg}]}]
    for attempt in range(8):
        try:
            r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            return r.text or ""
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == 7:
                raise
            m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            time.sleep(float(m.group(1)) + 2 if m else min(2 ** attempt * 5, 60))
    return ""


def setup_zep_session(zep, task):
    """Create user/thread/graph for this task. Idempotent."""
    suffix = f"factconsolidation_{task.lower()}_6k"
    user_id = f"user_{SESSION_PREFIX}_{suffix}"
    thread_id = f"thread_{SESSION_PREFIX}_{suffix}"
    graph_id = f"graph_{SESSION_PREFIX}_{suffix}"

    for op_name, op in [
        ("user.add", lambda: zep.user.add(user_id=user_id)),
        ("thread.create", lambda: zep.thread.create(thread_id=thread_id, user_id=user_id)),
        ("graph.create", lambda: zep.graph.create(graph_id=graph_id)),
    ]:
        try:
            op()
            print(f"  [zep] {op_name} ok")
        except Exception as e:
            if "already exists" in str(e).lower() or "400" in str(e):
                print(f"  [zep] {op_name} skipped (already exists)")
            else:
                raise

    return user_id, thread_id, graph_id


def ingest_into_zep(zep, graph_id, thread_id, user_id):
    """Ingest 6k context. If already ingested (session re-used), skip."""
    text = CONTEXT_FILE.read_text()
    chunks = chunk_context(text)
    print(f"[ingest] {len(chunks)} chunks of ~{CHUNK_SIZE_TOKENS} tokens")

    # Cheap "already ingested" probe: search and see if any edges exist
    try:
        probe = zep.graph.search(graph_id=graph_id, query="test", scope="edges", limit=1)
        if probe and probe.edges and len(probe.edges) > 0:
            print(f"[ingest skip] graph already has edges ({len(probe.edges)} probed)")
            return False
    except Exception:
        pass

    for i, chunk in enumerate(chunks):
        zep.graph.add(graph_id=graph_id, type="text", data=chunk[:9998])
        # also thread for thread.context (not strictly required but matches agent.py)
        try:
            from zep_cloud import Message
            messages = [Message(role="user", role_type="user", content=chunk[:9998], name="user")]
            zep.thread.add_messages(thread_id=thread_id, messages=messages)
        except Exception:
            pass
        print(f"  chunk {i:2d}: ingested", flush=True)

    print(f"[ingest done] sleeping {ZEP_INGEST_WAIT_SECONDS}s for Zep async processing...")
    time.sleep(ZEP_INGEST_WAIT_SECONDS)
    return True


def search_zep(zep, graph_id, query):
    """Three-scope search like agent.py."""
    rq = query[:399]
    edges = zep.graph.search(graph_id=graph_id, query=rq, scope="edges", limit=RETRIEVE_NUM).edges
    nodes = zep.graph.search(graph_id=graph_id, query=rq, scope="nodes", limit=RETRIEVE_NUM).nodes
    episodes = zep.graph.search(graph_id=graph_id, query=rq, scope="episodes", limit=RETRIEVE_NUM).episodes
    return edges, nodes, episodes


def llm_response_gemini(client, retrieved_context, question):
    """Mirrors methods/zep.py:llm_response but with Gemini."""
    system_prompt = "You are a helpful expert assistant answering questions from users based on the provided context."
    user_msg = (
        f"Your task is to briefly answer the question. You are given the following context "
        f"from the previous conversation. If you don't know how to answer the question, abstain "
        f"from answering.\n\n{retrieved_context}\n\n{question}\n\nAnswer:"
    )
    return call_gemini_inference(client, system_prompt, user_msg)


def run_task(task, zep, gemini_client):
    gt_path = BASE / f"analysis/results/{task.lower()}_512_mquake_analysis.json"
    out_path = RESULTS_DIR / f"zep_gemini_{task.lower()}_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    gt = json.load(open(gt_path))
    print(f"\n=== Task {task} === ({len(gt)} questions)")

    user_id, thread_id, graph_id = setup_zep_session(zep, task)

    # Ingest (skip if already done)
    ingest_into_zep(zep, graph_id, thread_id, user_id)

    existing = []
    done = set()
    if out_path.exists():
        existing = json.load(open(out_path))
        done = {r["query_id"] for r in existing}
        print(f"[resume] {len(done)} done")

    todo = [q for q in gt if q["query_id"] not in done]
    print(f"[pending] {len(todo)}")

    for i, q in enumerate(todo):
        qid = q["query_id"]
        question = q["question"]
        gt_ans = q["gt_answer"]

        retrieval_query = get_retrieval_query(question)

        try:
            edges, nodes, episodes = search_zep(zep, graph_id, retrieval_query)
        except Exception as e:
            print(f"  [zep search error] qid={qid}: {e}")
            edges, nodes, episodes = [], [], []

        try:
            ctx_resp = zep.thread.get_user_context(thread_id=thread_id)
            context_block = ctx_resp.context if ctx_resp else ""
        except Exception:
            context_block = ""

        retrieved_context = compose_search_context(edges, nodes, context_block, episodes)

        try:
            answer = llm_response_gemini(gemini_client, retrieved_context, question)
        except Exception as e:
            answer = f"ERROR: {e}"

        em = fuzzy_match(answer, gt_ans)

        out_entry = {
            "query_id": qid,
            "question": question,
            "gt_answer": gt_ans,
            "retrieval_query": retrieval_query,
            "n_edges": len(edges) if edges else 0,
            "n_nodes": len(nodes) if nodes else 0,
            "n_episodes": len(episodes) if episodes else 0,
            "context_block_chars": len(context_block) if context_block else 0,
            "retrieved_context_preview": retrieved_context[:500] if retrieved_context else "",
            "pred_answer": answer,
            "exact_match": em,
        }
        if task == "MH":
            out_entry["num_hops"] = q.get("num_hops")
            out_entry["n_conflict"] = sum(
                1 for h in q.get("hops", []) if h.get("conflict_type") == "has_pair"
            )

        existing.append(out_entry)
        with open(out_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        if (i + 1) % 5 == 0 or i == len(todo) - 1:
            ok = sum(1 for r in existing if r["exact_match"])
            print(f"  [{task} {i+1}/{len(todo)}] qid={qid} acc={ok}/{len(existing)}={ok/len(existing)*100:.1f}%")

    return existing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["SH", "MH", "both"], default="both")
    args = parser.parse_args()

    zep = init_zep_client()
    gemini = init_gemini_client()
    print(f"[init] Zep cloud + Vertex Gemini ({MODEL})")

    if args.task in ("MH", "both"):
        run_task("MH", zep, gemini)
    if args.task in ("SH", "both"):
        run_task("SH", zep, gemini)


if __name__ == "__main__":
    main()
