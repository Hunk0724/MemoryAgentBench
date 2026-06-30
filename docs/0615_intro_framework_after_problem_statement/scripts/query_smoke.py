"""Phase 0 — query-time smoke: does M4-M6 keep the NEW fact and drop the OLD?

Loads the 6k SH storage built by ingest_phase0.py and runs the query-time
pipeline on a sample of MQuAKE has_pair conflict queries. For each, checks:
  - structural path fired? (query (S,P) matched a stored (S,P) key)
  - resolved context CONTAINS the gt (new) fact?
  - resolved context DROPPED the old fact? (temporal argmax worked)
No generation yet — this validates the resolution mechanism.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"), override=False)

LEN, TASK = "6k", "sh"
UID = f"phase0_{TASK}_{LEN}"
QDRANT = os.path.join(ROOT, f".cache/phase0_qdrant_{TASK}_{LEN}")
SP_INDEX = os.path.join(ROOT, f"analysis/results/phase0/sp_index_{TASK}_{LEN}.json")
os.environ["MEM0_QUERY_CACHE"] = os.path.join(ROOT, f"analysis/results/phase0/query_cache_{TASK}_{LEN}.json")

from mem0 import Memory  # noqa: E402
from mem0.configs.base import MemoryConfig  # noqa: E402
from methods.phase0_query import analyze_query, assemble_context, group_and_resolve, hybrid_retrieve  # noqa: E402


def norm(t):
    return (t or "").strip().rstrip(".").strip().lower()


def build_memory():
    cfg = {
        "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini", "temperature": 0}},
        "embedder": {"provider": "openai",
                     "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
        "vector_store": {"provider": "qdrant",
                         "config": {"embedding_model_dims": 1536, "path": QDRANT, "on_disk": True,
                                    "collection_name": f"phase0_{TASK}_{LEN}"}},
    }
    return Memory(config=MemoryConfig(**cfg))


def main():
    mem = build_memory()
    sp = json.load(open(SP_INDEX, encoding="utf-8"))
    allm = mem.get_all(user_id=UID, limit=2000)
    items = allm.get("results", allm) if isinstance(allm, dict) else allm
    id2item = {str(m["id"]): m for m in items}
    print(f"storage: {len(id2item)} memories | {len(sp)} (S,P) keys\n")

    an = json.load(open(os.path.join(ROOT, "analysis/results/sh_512_mquake_analysis.json")))
    sample = [r for r in an if r.get("conflict_type") == "has_pair"][:10]

    n_struct = n_new_in = n_old_dropped = 0
    for r in sample:
        q, gt, old = r["question"], r["gt_fact_text"], r["old_fact_text"]
        plan = analyze_query(q, user_id=UID)
        cand = hybrid_retrieve(plan, mem, sp, user_id=UID, k=20)
        resolved, ungrouped = group_and_resolve(cand, id2item)
        ctx = norm(assemble_context(resolved, ungrouped))
        struct_fired = any(f"{s}\x1f{p}" in sp for s, p in plan["structural_keys"])
        new_in = norm(gt) in ctx
        old_in = norm(old) in ctx
        n_struct += struct_fired
        n_new_in += new_in
        n_old_dropped += (new_in and not old_in)
        print(f"Q: {q}")
        print(f"   keys={plan['structural_keys']} structfired={struct_fired} "
              f"| cand={len(cand)} resolved={len(resolved)} ungrouped={len(ungrouped)}")
        print(f"   NEW in ctx={new_in} | OLD in ctx={old_in} "
              f"=> {'RESOLVED✓' if (new_in and not old_in) else 'NOT resolved'}")
    n = len(sample)
    print(f"\nsummary over {n}: structural-fired {n_struct}/{n} | "
          f"new-present {n_new_in}/{n} | old-dropped(resolved) {n_old_dropped}/{n}")


if __name__ == "__main__":
    main()
