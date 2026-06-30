"""Phase 0 — end-to-end storage ingestion (validates M1/M3 integration).

Runs the REAL mem0 add path with MEM0_ADD_MODE=phase0_structural:
    chunk_facts_by_line(512) -> memory.add per chunk
      -> L2 extraction (FROZEN cache, offline)
      -> phase0 branch: triple extraction (FROZEN cache, offline)
      -> _create_memory: MiniLM embed + qdrant insert (payload incl. triple+ordinal)
      -> (S,P) inverted index commit + JSON persist
No Vertex / no live LLM calls (both caches hit; llm=openai only constructed).

Run: python docs/0615_.../scripts/ingest_phase0.py 6k SH
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"), override=False)

LEN = sys.argv[1] if len(sys.argv) > 1 else "6k"
TASK = (sys.argv[2] if len(sys.argv) > 2 else "SH").lower()
UID = f"phase0_{TASK}_{LEN}"

# Frozen caches + outputs (must be set BEFORE importing/constructing Memory).
os.environ["MEM0_ADD_MODE"] = "phase0_structural"
os.environ["MEM0_EXTRACTION_CACHE"] = os.path.join(ROOT, f"analysis/results/extraction_cache_{LEN}.json")
os.environ["MEM0_TRIPLE_CACHE"] = os.path.join(ROOT, f"analysis/results/triple_cache_{LEN}.json")
SP_INDEX = os.path.join(ROOT, f"analysis/results/phase0/sp_index_{TASK}_{LEN}.json")
LOG_DIR = os.path.join(ROOT, f"analysis/results/phase0/logs_{TASK}_{LEN}")
os.environ["MEM0_SP_INDEX_PATH"] = SP_INDEX
os.environ["MEM0_CAND_LOG_DIR"] = LOG_DIR
QDRANT = os.path.join(ROOT, f".cache/phase0_qdrant_{TASK}_{LEN}")
os.makedirs(os.path.dirname(SP_INDEX), exist_ok=True)
# fresh storage each run
import shutil  # noqa: E402
for p in (SP_INDEX, QDRANT, LOG_DIR):
    if os.path.exists(p):
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

from mem0 import Memory  # noqa: E402
from mem0.configs.base import MemoryConfig  # noqa: E402
from methods.mem0_fc_prompt_fix import make_l2_knowledge_prompt  # noqa: E402
from utils.eval_other_utils import chunk_facts_by_line  # noqa: E402

CTX = os.path.join(ROOT, f"analysis/contexts/factconsolidation_{LEN}_context.txt")


def build_memory():
    cfg = {
        "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini", "temperature": 0}},
        # MABench mem0 default embedder (gpt line): OpenAI text-embedding-3-small (1536d).
        # Phase 0 keeps the embedder intact (guide §1.2) for apples-to-apples vs vanilla.
        "embedder": {"provider": "openai",
                     "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
        "vector_store": {"provider": "qdrant",
                         "config": {"embedding_model_dims": 1536, "path": QDRANT, "on_disk": True,
                                    "collection_name": f"phase0_{TASK}_{LEN}"}},
        "custom_fact_extraction_prompt": make_l2_knowledge_prompt(),
    }
    return Memory(config=MemoryConfig(**cfg))


def main():
    mem = build_memory()
    chunks = chunk_facts_by_line(open(CTX, encoding="utf-8").read(), chunk_size=512)
    print(f"[{UID}] {len(chunks)} chunks -> {len(chunks)} memory.add() calls (offline)")
    total = 0
    for i, chunk in enumerate(chunks):
        res = mem.add([{"role": "user", "content": chunk}], user_id=UID)
        n = len(res.get("results", res) if isinstance(res, dict) else res)
        total += n
        print(f"  chunk {i:2d}: +{n} memories", end="\r")
    print(f"\n  total memories added: {total}")

    # ---- storage verification ----
    allm = mem.get_all(user_id=UID)
    items = allm.get("results", allm) if isinstance(allm, dict) else allm
    with_triple = sum(1 for m in items if (m.get("metadata") or {}).get("triple"))
    sp = json.load(open(SP_INDEX, encoding="utf-8")) if os.path.exists(SP_INDEX) else {}
    multi = {k: v for k, v in sp.items() if len(v) > 1}
    print(f"\n=== STORAGE VERIFY ===")
    print(f"  qdrant memories: {len(items)}")
    print(f"  payload has triple: {with_triple}/{len(items)}")
    print(f"  (S,P) index keys: {len(sp)} | multi-version groups (len>1): {len(multi)}")
    # sample payload
    s = next((m for m in items if (m.get('metadata') or {}).get('triple')), None)
    if s:
        md = s["metadata"]
        print(f"  sample payload: data={s.get('memory','')[:50]!r}")
        print(f"     ordinal={md.get('ordinal')} triple={md.get('triple')}")
    # sample a multi-version (S,P) group (= a conflict captured structurally)
    if multi:
        k, v = next(iter(multi.items()))
        print(f"  sample multi-version group: ({k.replace(chr(31),' | ')}) -> {len(v)} versions")
    print(f"\n  sp_index -> {SP_INDEX}")
    print(f"  triple log -> {LOG_DIR}/phase0_triples.jsonl")


if __name__ == "__main__":
    main()
