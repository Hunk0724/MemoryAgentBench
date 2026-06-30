"""
Mem0 customized + Vertex Gemini × FC-SH/MH × full 100 questions.

Standalone runner (does not use main.py/agent.py).

Pipeline mirrors agent.py:_handle_mem0_agent but with:
  - L1 minimal-mod fact-extraction prompt (remove 2 anti-knowledge few-shots)
  - Vertex Gemini 3.1 Flash-Lite (matches HippoRAG-v2 / 9 oracles backbone)
  - max_tokens=8192 (Update Memory step output budget)
  - HuggingFace MiniLM embedding (no API key)
  - Single shared user_id (one Mem0 vector store per task, ingested once)

Usage:
  python run_mem0_gemini.py --task SH    # FC-SH 100
  python run_mem0_gemini.py --task MH    # FC-MH 100
  python run_mem0_gemini.py --task both  # both, sequentially

Resume-safe: skip qids already in output JSON.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv("/home/yhchiang/MemoryAgentBench/.env")
except ImportError:
    pass

import tiktoken

# Force local mem0 fork + custom Vertex Gemini provider
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench/analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts")

from mem0.utils.factory import LlmFactory
LlmFactory.provider_to_class["gemini"] = "mem0_vertex_gemini_llm.VertexGeminiLLM"

from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.configs.prompts import FACT_RETRIEVAL_PROMPT

# Inference-side LLM (Vertex Gemini direct, mirrors HippoRAG-v2)
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

BASE = Path("/home/yhchiang/MemoryAgentBench")
EXP_DIR = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100"
RESULTS_DIR = EXP_DIR / "results"
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"

MODEL = "gemini-3.1-flash-lite-preview"
TEMPERATURE = 0
MAX_TOKENS_INFERENCE = 2048
CHUNK_SIZE_TOKENS = 512
RETRIEVE_NUM = 100  # match agent.py default for Mem0


def make_l1_modified_prompt():
    pattern = re.compile(
        r'Input: Hi\.\s*\nOutput: \{"facts" : \[\]\}\s*\n\s*\n'
        r'Input: There are branches in trees\.\s*\nOutput: \{"facts" : \[\]\}\s*\n\s*\n',
        re.MULTILINE,
    )
    modified = pattern.sub('', FACT_RETRIEVAL_PROMPT)
    if modified == FACT_RETRIEVAL_PROMPT:
        raise RuntimeError("Could not locate the rejection few-shots")
    return modified


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


def build_mem0(task):
    """Init Mem0 with customizations. Each task gets its own qdrant collection."""
    qdrant_path = str(BASE / f".cache/mem0_aligned_qdrant_{task.lower()}")
    config_dict = {
        "llm": {
            "provider": "gemini",  # redirected to VertexGeminiLLM
            "config": {
                "model": MODEL,
                "temperature": 0.1,
                "max_tokens": 8192,
            },
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
            },
        },
        "custom_fact_extraction_prompt": make_l1_modified_prompt(),
    }
    return Memory(config=MemoryConfig(**config_dict)), qdrant_path


def ingest_context_into_mem0(memory, user_id, force=False):
    """Ingest 6k context into Mem0. Skip if already done (resume-safe)."""
    text = CONTEXT_FILE.read_text()
    chunks = chunk_context(text)
    print(f"[ingest] {len(chunks)} chunks of ~{CHUNK_SIZE_TOKENS} tokens")

    # Check if memory has facts already (resume case)
    try:
        existing = memory.get_all(user_id=user_id)
        n_existing = len(existing.get("results", [])) if isinstance(existing, dict) else len(existing)
    except Exception:
        n_existing = 0
    if n_existing > 0 and not force:
        print(f"[ingest skip] {n_existing} existing facts in vector store; use force=True to re-ingest")
        return n_existing

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
        print(f"  chunk {i:2d}: {n} facts (running total: {n_added})", flush=True)
    return n_added


def init_inference_client():
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


def run_task(task, infer_client):
    """task in {'SH','MH'}."""
    gt_path = BASE / f"analysis/results/{task.lower()}_512_mquake_analysis.json"
    out_path = RESULTS_DIR / f"mem0_gemini_aligned_{task.lower()}_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    gt = json.load(open(gt_path))
    # Load wrapped query (with FC seq rule wrapper) from MABench output JSON,
    # to ALIGN with MABench main pipeline default (HippoRAG-v2 etc. use this).
    mab_path = BASE / f"outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_{task.lower()}_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
    mab_data = json.load(open(mab_path))
    wrapped_qmap = {e["query_id"]: e["query"] for e in mab_data["data"]}
    print(f"\n=== Task {task} === ({len(gt)} questions, using WRAPPED query)")

    memory, qdrant_path = build_mem0(task)
    user_id = f"mem0_aligned_{task.lower()}"

    # Ingestion phase
    n_ingested = ingest_context_into_mem0(memory, user_id)
    print(f"[ingest done] {n_ingested} facts in store\n")

    # Resume support
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
        question_bare = q["question"]
        question = wrapped_qmap.get(qid, question_bare)  # use WRAPPED for retrieval + inference
        gt_ans = q["gt_answer"]

        # Search memory
        retrieved = memory.search(query=question, user_id=user_id, limit=RETRIEVE_NUM)
        results_list = retrieved.get("results", []) if isinstance(retrieved, dict) else []
        memories_str = "\n".join(f"- {entry.get('memory', '')}" for entry in results_list)

        # Inference (mirrors agent.py:_handle_mem0_agent prompt)
        system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
        user_msg = question + "\n\nCurrent Time: " + time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            answer = call_gemini_inference(infer_client, system_prompt, user_msg)
        except Exception as e:
            answer = f"ERROR: {e}"

        em = fuzzy_match(answer, gt_ans)

        out_entry = {
            "query_id": qid,
            "question": question,
            "gt_answer": gt_ans,
            "n_retrieved": len(results_list),
            "retrieved_memories_preview": [m.get("memory") for m in results_list[:5]],
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

    infer_client = init_inference_client()
    print(f"[init] inference client: Vertex Gemini ({os.environ['GOOGLE_CLOUD_PROJECT']} / {os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1')})")

    if args.task in ("MH", "both"):
        run_task("MH", infer_client)
    if args.task in ("SH", "both"):
        run_task("SH", infer_client)


if __name__ == "__main__":
    main()
