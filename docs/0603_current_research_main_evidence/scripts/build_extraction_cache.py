"""
Build a frozen, COMPLETE extraction cache for a context, so every run (SH/MH,
6k/32k, re-runs) ingests identical facts and extraction stops being a per-run
variable. Used by the instrumented mem0 via env MEM0_EXTRACTION_CACHE.

Per chunk:
  - extract with the L2 knowledge prompt (reliable on FC general facts)
  - validate completeness: n_extracted == n_numbered_facts
  - on mismatch, fall back to VERBATIM (number-stripped context lines) for that
    chunk and log it — guarantees 100% completeness deterministically
  - key = sha256 of the numbered-fact lines (matches mem0's runtime key, which
    is timestamp-independent)

Run:
  conda run -n MABench python build_extraction_cache.py \
    --ctx analysis/contexts/factconsolidation_6k_context.txt \
    --out analysis/results/extraction_cache_6k.json
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line
from methods.mem0_fc_prompt_fix import make_l2_knowledge_prompt
from methods.mem0_vertex_gemini_llm import VertexGeminiLLM
from mem0.configs.llms.base import BaseLlmConfig

ap = argparse.ArgumentParser()
ap.add_argument("--ctx", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--chunk-size", type=int, default=512)
ap.add_argument("--model", default="gemini-3.1-flash-lite")
args = ap.parse_args()

L2 = make_l2_knowledge_prompt()
llm = VertexGeminiLLM(config=BaseLlmConfig(model=args.model, temperature=0, max_tokens=16384))

chunks = chunk_facts_by_line(Path(args.ctx).read_text(), chunk_size=args.chunk_size)
cache, fallbacks, total = {}, [], 0
for i, chunk in enumerate(chunks):
    fact_lines = re.findall(r"^\s*\d+\.\s.*$", chunk, re.MULTILINE)
    verbatim = [re.sub(r"^\s*\d+\.\s*", "", ln).strip().rstrip(".") for ln in fact_lines]
    key = hashlib.sha256("\n".join(fact_lines).encode("utf-8")).hexdigest()

    resp = llm.generate_response(
        messages=[{"role": "system", "content": L2},
                  {"role": "user", "content": "Input:\n" + chunk}],
        response_format={"type": "json_object"})
    try:
        facts = json.loads(re.sub(r"```json|```", "", resp).strip())["facts"]
    except Exception:
        facts = []

    if len(facts) != len(fact_lines):
        facts = verbatim  # guarantee completeness
        fallbacks.append((i, len(facts)))
    cache[key] = facts
    total += len(facts)
    print(f"chunk{i}: expected {len(fact_lines)} -> cached {len(facts)}"
          f"{'  [VERBATIM fallback]' if i in [f[0] for f in fallbacks] else ''}")

json.dump(cache, open(args.out, "w"), ensure_ascii=False, indent=1)
print(f"\ncached {len(cache)} chunks, {total} facts | verbatim fallbacks: {fallbacks or 'none'}")
print(f"written: {args.out}")
