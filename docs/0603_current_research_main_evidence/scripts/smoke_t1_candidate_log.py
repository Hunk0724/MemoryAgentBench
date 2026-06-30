"""
Smoke test for T1 — Component-2 candidate-pool instrumentation.

What this verifies (NOT a research run — just that the patch emits correct log):
  1. With MEM0_CAND_LOG_DIR set, mem0's _add_to_vector_store writes
     candidate_pool.jsonl, one line per memory.add() (= per chunk).
  2. Each line has the expected schema:
       {user_id, n_new_facts, pool_size_after_dedup, per_fact_candidates:[...]}
     and each top5 entry has {rank, id, score, text}.
  3. At least one later chunk has a NON-EMPTY top5 — proves the candidate
     retrieval path (the thing assumption-2 depends on) was actually exercised,
     i.e. earlier-chunk facts are searchable when a later chunk is ingested.

Setup mirrors the existing precedent
  analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts/mem0_l1_smoke_test.py
  - Vertex Gemini (ADC) as mem0 internal LLM, via LlmFactory redirect
  - L1-modified extraction prompt (remove 2 anti-knowledge few-shots)
  - Vertex `text-embedding-004` (768-dim) via ADC — the SAME embedder the real
    Plan A run uses, so this smoke faithfully mirrors production. (Component 2
    candidate membership is embedder-dependent, so for any run whose candidate
    numbers we will interpret, the embedder must match the aligned setup.)
  - temp=0 (diagnostic determinism, per 00_research_axis_and_setup.md §2)

Scope: ingest only the first N_CHUNKS chunks of FC-SH 6k (cheap).

Run:
  conda run -n MABench python \
    docs/0603_current_research_main_evidence/scripts/smoke_t1_candidate_log.py
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path("/home/yhchiang/MemoryAgentBench/.env"))
except ImportError:
    pass

import tiktoken

# Use the local mem0 fork (so our T1 patch is the one that runs, not a pip copy)
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")

from mem0.utils.factory import LlmFactory, EmbedderFactory
# Redirect providers to our Vertex/ADC wrappers — identical to the real pipeline
# (agent.py:317 / agent.py:322-323).
LlmFactory.provider_to_class["gemini"] = "methods.mem0_vertex_gemini_llm.VertexGeminiLLM"
EmbedderFactory.provider_to_class["vertexai"] = "methods.mem0_vertex_adc_embedder.VertexADCEmbedding"

from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.configs.prompts import FACT_RETRIEVAL_PROMPT
from utils.eval_other_utils import chunk_facts_by_line  # same chunker the real FC run now uses

BASE = Path("/home/yhchiang/MemoryAgentBench")
CONTEXT_FILE = BASE / "analysis/contexts/factconsolidation_6k_context.txt"
SMOKE_DIR = BASE / "docs/0603_current_research_main_evidence/scripts/_smoke_out"
CAND_LOG_DIR = SMOKE_DIR / "cand_log"
QDRANT_PATH = SMOKE_DIR / "qdrant"

CHUNK_SIZE_TOKENS = 512
N_CHUNKS = 4                      # enough to populate store + get candidates
USER_ID = "smoke_t1"

# Gate the instrumentation ON (env read at add()-time inside main.py)
os.environ["MEM0_CAND_LOG_DIR"] = str(CAND_LOG_DIR)


def make_l1_modified_prompt():
    pattern = re.compile(
        r'Input: Hi\.\s*\n'
        r'Output: \{"facts" : \[\]\}\s*\n\s*\n'
        r'Input: There are branches in trees\.\s*\n'
        r'Output: \{"facts" : \[\]\}\s*\n\s*\n',
        re.MULTILINE,
    )
    modified = pattern.sub('', FACT_RETRIEVAL_PROMPT)
    if modified == FACT_RETRIEVAL_PROMPT:
        raise RuntimeError("Could not locate the two rejection few-shots")
    return modified


def ingest():
    # Fresh state so the candidate population across chunks is deterministic
    if SMOKE_DIR.exists():
        shutil.rmtree(SMOKE_DIR)
    CAND_LOG_DIR.mkdir(parents=True, exist_ok=True)
    QDRANT_PATH.mkdir(parents=True, exist_ok=True)

    config = MemoryConfig(**{
        "llm": {"provider": "gemini", "config": {
            "model": "gemini-3.1-flash-lite-preview",
            "temperature": 0,
            "max_tokens": 8192,
        }},
        "embedder": {"provider": "vertexai", "config": {
            "model": "text-embedding-004",
            "embedding_dims": 768,
        }},
        "vector_store": {"provider": "qdrant", "config": {
            "embedding_model_dims": 768,
            "path": str(QDRANT_PATH),
        }},
        "custom_fact_extraction_prompt": make_l1_modified_prompt(),
    })
    memory = Memory(config=config)

    chunks = chunk_facts_by_line(CONTEXT_FILE.read_text(), chunk_size=CHUNK_SIZE_TOKENS)[:N_CHUNKS]
    print(f"[ingest] {len(chunks)} chunks, user_id={USER_ID}, temp=0")
    for i, chunk in enumerate(chunks):
        messages = [
            {"role": "system", "content": "You are a helpful assistant that can help memorize details in the conversation."},
            {"role": "user", "content": chunk},
            {"role": "assistant", "content": "I'll make sure to add the content into the memory."},
        ]
        res = memory.add(messages, user_id=USER_ID)
        n = len(res.get("results", [])) if isinstance(res, dict) else 0
        print(f"  chunk {i}: {n} events")


def verify():
    log_file = CAND_LOG_DIR / "candidate_pool.jsonl"
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    exists = log_file.exists()
    check("candidate_pool.jsonl exists", exists, str(log_file))
    if not exists:
        return checks, []

    lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
    check("one line per add() (==N_CHUNKS)", len(lines) == N_CHUNKS, f"got {len(lines)} lines")

    required_top = {"user_id", "n_new_facts", "pool_size_after_dedup", "per_fact_candidates"}
    schema_ok = all(required_top <= set(l.keys()) for l in lines)
    check("every line has required top-level keys", schema_ok, str(required_top))

    # top5 entry schema
    top5_keys = {"rank", "id", "score", "text"}
    entry_ok = True
    for l in lines:
        for pf in l["per_fact_candidates"]:
            if "new_fact" not in pf or "top5" not in pf:
                entry_ok = False
            for c in pf["top5"]:
                if not (top5_keys <= set(c.keys())):
                    entry_ok = False
    check("per_fact top5 entries have {rank,id,score,text}", entry_ok)

    # candidate path exercised: some chunk produced a non-empty top5
    any_cand = any(
        len(pf["top5"]) > 0
        for l in lines for pf in l["per_fact_candidates"]
    )
    check("at least one non-empty top5 (candidate path exercised)", any_cand)

    # user_id correctly propagated
    uid_ok = all(l["user_id"] == USER_ID for l in lines)
    check("user_id propagated from filters", uid_ok)

    # --- T2: extraction.jsonl (Component 1) ---
    ext_file = CAND_LOG_DIR / "extraction.jsonl"
    ext_exists = ext_file.exists()
    check("[T2] extraction.jsonl exists", ext_exists, str(ext_file))
    if ext_exists:
        ext = [json.loads(l) for l in ext_file.read_text().splitlines() if l.strip()]
        check("[T2] one extraction line per add()", len(ext) == N_CHUNKS, f"got {len(ext)}")
        req = {"user_id", "n_facts", "facts", "custom_extraction_prompt"}
        check("[T2] extraction lines have required keys", all(req <= set(e.keys()) for e in ext))
        check("[T2] facts is a non-empty list each chunk",
              all(isinstance(e["facts"], list) and len(e["facts"]) > 0 for e in ext))
        check("[T2] n_facts == len(facts)", all(e["n_facts"] == len(e["facts"]) for e in ext))
        check("[T2] custom (L1) extraction prompt was used",
              all(e["custom_extraction_prompt"] is True for e in ext))
        # cross-check: extraction n_facts matches candidate-log n_new_facts per chunk
        cand_n = [l["n_new_facts"] for l in lines]
        ext_n = [e["n_facts"] for e in ext]
        check("[T2] extraction n_facts matches candidate-log n_new_facts", cand_n == ext_n,
              f"cand={cand_n} ext={ext_n}")

    # --- T3: update_decision.jsonl (Component 3) ---
    upd_file = CAND_LOG_DIR / "update_decision.jsonl"
    upd_exists = upd_file.exists()
    check("[T3] update_decision.jsonl exists", upd_exists, str(upd_file))
    if upd_exists:
        upd = [json.loads(l) for l in upd_file.read_text().splitlines() if l.strip()]
        check("[T3] one update line per add()", len(upd) == N_CHUNKS, f"got {len(upd)}")
        req = {"update_prompt", "raw_response", "parsed_actions", "event_counts",
               "referenced_ids", "hallucinated_ids", "n_candidates", "id_to_uuid"}
        check("[T3] update lines have required keys", all(req <= set(u.keys()) for u in upd))
        check("[T3] update_prompt is a non-empty str", all(isinstance(u["update_prompt"], str) and u["update_prompt"] for u in upd))
        check("[T3] hallucinated_ids is a list each line", all(isinstance(u["hallucinated_ids"], list) for u in upd))
        # referenced ids must be subset-checkable against pool size; hallucinated ⊆ referenced
        check("[T3] hallucinated_ids ⊆ referenced_ids",
              all(set(u["hallucinated_ids"]) <= set(u["referenced_ids"]) for u in upd))
        # surface the actual hallucinated-id signal we expect to see
        total_halluc = sum(len(u["hallucinated_ids"]) for u in upd)
        halluc_detail = "; ".join(
            f"chunk{i}:n_cand={u['n_candidates']},halluc={u['hallucinated_ids']}"
            for i, u in enumerate(upd) if u["hallucinated_ids"]
        ) or "none this run"
        check("[T3] hallucinated-id detection wired (informational)", True,
              f"total={total_halluc} | {halluc_detail}")

    return checks, lines


def main():
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() != "true":
        raise RuntimeError("GOOGLE_GENAI_USE_VERTEXAI must be 'true'; check .env")
    ingest()
    checks, lines = verify()

    print("\n=== T1 smoke verification ===")
    all_pass = True
    for name, ok, detail in checks:
        all_pass &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    if lines:
        # show one populated example for eyeball check
        for l in lines:
            pop = [pf for pf in l["per_fact_candidates"] if pf["top5"]]
            if pop:
                print("\n[sample] one per_fact_candidate with a hit:")
                print(json.dumps(pop[0], ensure_ascii=False, indent=2)[:800])
                break

    print(f"\nRESULT: {'ALL PASS' if all_pass else 'FAIL'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
