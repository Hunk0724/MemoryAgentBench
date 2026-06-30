"""U5 Phase-1 smoke test: one (then two) chunk(s) through the U5 update path.

Goals:
  1. Confirm _update_u5 runs end-to-end on a real conflict without crashing.
  2. Time a SINGLE classification call in isolation -> answer "is one update call
     slow, or was prior slowness just rate-limit / many sequential chunks?".
  3. Show the resulting store: old version physically deleted, new version kept.

Run via scripts/run_u5_smoke.sh (activates conda + loads OPENAI_API_KEY).
"""
import os
import sys
import time
import json
from pathlib import Path

# Load OPENAI_API_KEY from .env without printing it.
_envp = Path(__file__).resolve().parents[3] / ".env"
if _envp.exists():
    for _line in _envp.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "methods"))

os.environ["MEM0_UPDATE_MODE"] = "u5_classification"  # gate the U5 path

from mem0.configs.base import MemoryConfig
from mem0.memory.main import Memory
from mem0.configs.prompts import get_conflict_classification_messages
from mem0_fc_prompt_fix import make_l2_knowledge_prompt

STORE = "/tmp/u5_smoke_qdrant"
os.system(f"rm -rf {STORE}")

mem0_config = {
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini", "temperature": 0, "max_tokens": 16384}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
    "vector_store": {"provider": "qdrant", "config": {
        "collection_name": "u5_smoke", "embedding_model_dims": 1536,
        "path": STORE, "on_disk": True}},
    "custom_fact_extraction_prompt": make_l2_knowledge_prompt(),
    "history_db_path": "/tmp/u5_smoke_history.db",
}

print("=== building Memory (U5 mode) ===")
mem = Memory(MemoryConfig(**mem0_config))
USER = "u5_smoke_user"

SYS = "You are a helpful assistant that can read the context and memorize it for future retrieval."
def memorize_msgs(context):
    user = ("Dialogue between User and Assistant \\n<User> The following context is the "
            "facts I have learned: \n" + context + "\n <Assistant> I have learned the facts.")
    return [
        {"role": "system", "content": SYS},
        {"role": "user", "content": user},
        {"role": "assistant", "content": "I'll make sure to add the content into the memory."},
    ]

# Two cross-chunk conflicting facts (single-valued attribute -> should SUPERSEDE).
CHUNK1 = "1. The capital of the Tang Empire is Chang'an."
CHUNK2 = "57. The capital of the Tang Empire is Beaumont."

print("\n=== chunk 1 (no candidate -> straight ADD) ===")
t0 = time.time()
r1 = mem.add(memorize_msgs(CHUNK1), user_id=USER)
t_add1 = time.time() - t0
print(f"chunk1 add() wall = {t_add1:.2f}s; result={json.dumps(r1, ensure_ascii=False)}")

print("\n=== chunk 2 (candidate present -> classify + map) ===")
t0 = time.time()
r2 = mem.add(memorize_msgs(CHUNK2), user_id=USER)
t_add2 = time.time() - t0
print(f"chunk2 add() wall = {t_add2:.2f}s; result={json.dumps(r2, ensure_ascii=False)}")

print("\n=== final store (active memories) ===")
allm = mem.get_all(user_id=USER)
rows = allm.get("results", allm) if isinstance(allm, dict) else allm
for m in rows:
    print(f"  ordinal={m.get('metadata', {}).get('ordinal', m.get('ordinal'))!r:>5}  {m.get('memory')!r}")

print("\n=== ISOLATED single classification-call latency (pure update LLM) ===")
sysp, userp = get_conflict_classification_messages(
    new_facts=[{"new_id": "n0", "text": "The capital of the Tang Empire is Beaumont.", "ordinal": 57}],
    existing_entries=[{"existing_id": "0", "text": "The capital of the Tang Empire is Chang'an.", "ordinal": 1}],
)
lat = []
for i in range(3):
    t0 = time.time()
    resp = mem.llm.generate_response(
        messages=[{"role": "system", "content": sysp}, {"role": "user", "content": userp}],
        response_format={"type": "json_object"},
    )
    lat.append(time.time() - t0)
    if i == 0:
        print(f"  classification raw -> {resp[:300]}")
print(f"  classification call latency (3x) = {[round(x,2) for x in lat]} s  (mean {sum(lat)/len(lat):.2f}s)")

print("\n=== TIMING SUMMARY ===")
print(f"  chunk1 add (extract+add, no classify) = {t_add1:.2f}s")
print(f"  chunk2 add (extract+retrieve+classify+map) = {t_add2:.2f}s")
print(f"  isolated single classification call (mean) = {sum(lat)/len(lat):.2f}s")
print("  -> if isolated classification ~1-3s, prior total slowness = many sequential chunks / rate-limit, not per-call.")
