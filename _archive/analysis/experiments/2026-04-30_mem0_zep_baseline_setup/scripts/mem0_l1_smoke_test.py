"""
Mem0 L1 minimal-mod smoke test (Gemini 3.1 Flash-Lite via Vertex, ingestion-only).

Purpose:
  Verify whether removing the two anti-knowledge few-shots from
  FACT_RETRIEVAL_PROMPT is sufficient to let Mem0 extract FC facts.

LLM backbone:
  Gemini 3.1 Flash-Lite via Vertex AI ADC (matches HippoRAG-v2 setup, no API key).
  Custom Mem0 LLM provider registered via LlmFactory monkey-patch.

Embedding:
  HuggingFace `sentence-transformers/all-MiniLM-L6-v2` (local, no API key).

L1 mod:
  Remove the two `Output: {"facts" : []}` rejection few-shots for "Hi." and
  "There are branches in trees." from FACT_RETRIEVAL_PROMPT, leaving the rest
  of the prompt (role, 7 categories, footer) intact.

Test scope:
  Ingest FC-SH 6k context (12 chunks of 512 tokens). Compare extraction count
  vs known OOB result of 0 facts.

Outputs:
  analysis/results/diagnostic/mem0_l1_smoke_results.json
"""

import json
import os
import re
import sys
from pathlib import Path

# Load .env (for Vertex env vars)
try:
    from dotenv import load_dotenv
    load_dotenv(Path("/home/yhchiang/MemoryAgentBench/.env"))
except ImportError:
    pass

import tiktoken

# Force imports to come from the local mem0 fork at MemoryAgentBench/mem0/
# (otherwise the installed pip mem0 in site-packages takes precedence and our
# monkey patches won't apply).
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(Path(__file__).parent))

# Override the "gemini" provider with our Vertex Gemini wrapper.
# The MemoryConfig validator only accepts provider names from a hardcoded
# whitelist, so we keep provider="gemini" but redirect the factory.
from mem0.utils.factory import LlmFactory
LlmFactory.provider_to_class["gemini"] = "mem0_vertex_gemini_llm.VertexGeminiLLM"
print(f"[setup] Using mem0 from: {LlmFactory.__module__}")

from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.configs.prompts import FACT_RETRIEVAL_PROMPT

BASE = Path("/home/yhchiang/MemoryAgentBench")
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
OUT = BASE / "analysis/experiments/2026-04-30_mem0_zep_baseline_setup/results/mem0_l1_smoke_results.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE_TOKENS = 512
USER_ID = "mem0_l1_smoke"


def make_l1_modified_prompt():
    """L1 = remove the two rejection few-shots from FACT_RETRIEVAL_PROMPT."""
    pattern = re.compile(
        r'Input: Hi\.\s*\n'
        r'Output: \{"facts" : \[\]\}\s*\n\s*\n'
        r'Input: There are branches in trees\.\s*\n'
        r'Output: \{"facts" : \[\]\}\s*\n\s*\n',
        re.MULTILINE,
    )
    modified = pattern.sub('', FACT_RETRIEVAL_PROMPT)
    if modified == FACT_RETRIEVAL_PROMPT:
        raise RuntimeError("Could not locate the two rejection few-shots in FACT_RETRIEVAL_PROMPT")
    return modified


def chunk_context(text, chunk_tokens=CHUNK_SIZE_TOKENS):
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(text)
    return [enc.decode(tokens[i:i + chunk_tokens]) for i in range(0, len(tokens), chunk_tokens)]


def main():
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() != "true":
        raise RuntimeError("GOOGLE_GENAI_USE_VERTEXAI must be 'true'; check .env")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        raise RuntimeError("GOOGLE_CLOUD_PROJECT not set")

    modified_prompt = make_l1_modified_prompt()
    print(f"[L1 mod] original prompt: {len(FACT_RETRIEVAL_PROMPT)} chars")
    print(f"[L1 mod] modified prompt: {len(modified_prompt)} chars (delta {len(modified_prompt)-len(FACT_RETRIEVAL_PROMPT)})")
    print(f"[Vertex] project={os.environ['GOOGLE_CLOUD_PROJECT']}, location={os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1')}")

    config_dict = {
        "llm": {
            "provider": "gemini",  # whitelist requires this; LlmFactory redirected to VertexGeminiLLM above
            "config": {
                "model": "gemini-3.1-flash-lite-preview",
                "temperature": 0.1,
                "max_tokens": 8192,  # Update Memory enumerates all prior memories — needs headroom
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "embedding_model_dims": 384,
                "path": str(BASE / ".cache/mem0_smoke_qdrant"),
            },
        },
        "custom_fact_extraction_prompt": modified_prompt,
    }
    config = MemoryConfig(**config_dict)
    memory = Memory(config=config)
    print("[setup] Memory instantiated with Vertex Gemini + MiniLM embedding")

    context_text = CONTEXT_FILE.read_text()
    chunks = chunk_context(context_text)
    print(f"[chunks] {len(chunks)} chunks of ~{CHUNK_SIZE_TOKENS} tokens each")

    per_chunk = []
    for i, chunk in enumerate(chunks):
        messages = [
            {"role": "system", "content": "You are a helpful assistant that can help memorize details in the conversation."},
            {"role": "user", "content": chunk},
            {"role": "assistant", "content": "I'll make sure to add the content into the memory."},
        ]
        try:
            result = memory.add(messages, user_id=USER_ID)
        except Exception as e:
            print(f"  chunk {i:2d}: ERROR {type(e).__name__}: {e}")
            per_chunk.append({"chunk_idx": i, "n_facts_extracted": 0, "error": str(e)})
            continue

        results_list = result.get("results", []) if isinstance(result, dict) else []
        n_facts = len(results_list)
        per_chunk.append({
            "chunk_idx": i,
            "n_facts_extracted": n_facts,
            "facts_preview": [r.get("memory") for r in results_list[:3]],
        })
        preview = ""
        if n_facts:
            mem = results_list[0].get("memory", "")
            preview = f"  e.g., '{mem[:80]}'"
        print(f"  chunk {i:2d}: {n_facts} facts{preview}")

    total_facts = sum(c["n_facts_extracted"] for c in per_chunk)
    chunks_with_facts = sum(1 for c in per_chunk if c["n_facts_extracted"] > 0)

    summary = {
        "test": "Mem0 L1 minimal-mod smoke (FC-SH 6k ingestion only)",
        "llm_backbone": "gemini-3.1-flash-lite-preview via Vertex AI",
        "embedder": "sentence-transformers/all-MiniLM-L6-v2",
        "chunks": len(chunks),
        "chunks_with_extracted_facts": chunks_with_facts,
        "total_facts_extracted": total_facts,
        "per_chunk": per_chunk,
        "pass_criterion": "total_facts > 0 (vs OOB baseline = 0)",
        "pass": total_facts > 0,
        "comparison": {
            "OOB (existing run, gpt-4o-mini)": "12 chunks × 0 facts",
            "L1 modified (this run, gemini-3.1-flash-lite)": f"{chunks_with_facts}/{len(chunks)} chunks had facts; {total_facts} total",
        },
    }

    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n=== Result ===")
    print(f"Total facts extracted: {total_facts}")
    print(f"Chunks with non-empty extraction: {chunks_with_facts}/{len(chunks)}")
    print(f"Pass: {summary['pass']}")
    print(f"Written to: {OUT}")


if __name__ == "__main__":
    main()
