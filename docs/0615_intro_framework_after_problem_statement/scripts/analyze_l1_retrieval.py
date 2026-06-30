"""Level-1 Retrieval Evaluation (phase2_spec.md §5.2), narrative evidence.

For each FC-SH query (top-100 retrieval), classify whether the query-relevant GT
facts are retrieved, split by conflict type:
  has_pair      -> {both, new_only, old_only, neither}
  no_conflict   -> single_fact {retrieved, missing}
Compared across vanilla mem0 (destructive write-time KU) vs ours (conservative
ADD, write-time does nothing) at 6k/32k/64k.

Narrative (intro_zh.md):
  - ours keeps BOTH versions -> conflict pairs retrievable as "both" (recoverable);
    vanilla committed destructively at write-time -> old_only/neither are
    IRREVERSIBLE losses.
  - As history grows, retrieval recall degrades (-> neither / single missing).

Read-only: re-runs Memory.search on existing stores. Run in MABench env:
  python docs/0615_.../scripts/analyze_l1_retrieval.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
os.environ.pop("MEM0_QUERY_MODE", None)  # raw retrieval; we classify ourselves
os.environ.pop("MEM0_ADD_MODE", None)

from mem0 import Memory  # noqa: E402
from mem0.configs.base import MemoryConfig  # noqa: E402

STORES = ROOT / "analysis/results/expanded/stores"
LENGTHS = ["6k", "32k", "64k"]
MODES = {  # tag -> (store collection prefix, store path prefix)
    "vanilla": "rerun",
    "ours": "phase2",  # phase0/phase2 stores share identical conservative content
}


def norm(t):
    return (t or "").strip().rstrip(".").strip().lower()


def open_store(prefix, length):
    # The benchmark (agent.py) suffixes BOTH path and collection_name by dataset.
    path = str(STORES / f"qdrant_gpt4o_512_openai_{prefix}__factconsolidation_sh_{length}")
    coll = f"mem0_gpt4o_l2_512_openai_{prefix}__factconsolidation_sh_{length}"
    cfg = {
        "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
        "embedder": {"provider": "openai",
                     "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
        "vector_store": {"provider": "qdrant",
                         "config": {"embedding_model_dims": 1536, "path": path, "on_disk": True,
                                    "collection_name": coll}},
    }
    mem = Memory(config=MemoryConfig(**cfg))
    pts = mem.vector_store.client.scroll(collection_name=coll, limit=1, with_payload=True)[0]
    uid = pts[0].payload.get("user_id") if pts else None
    n = mem.vector_store.client.count(coll).count
    return mem, uid, n


def wrapped_queries(length):
    """Benchmark wrapped query per query_id (mode-independent), from a results JSON."""
    import glob
    fs = glob.glob(str(ROOT / f"outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-phase2/**/*sh_{length}*results*.json"), recursive=True)
    rows = json.load(open(fs[0]))["data"]
    return {r["query_id"]: r["query"] for r in rows}


def analyze(prefix, length):
    mem, uid, n_store = open_store(prefix, length)
    wq = wrapped_queries(length)
    gt = json.load(open(ROOT / f"analysis/results/sh_{length}_mquake_analysis.json"))

    hp = {"both": 0, "new_only": 0, "old_only": 0, "neither": 0}
    nc = {"retrieved": 0, "missing": 0}
    n_hp = n_nc = 0
    for r in gt:
        if not r.get("matched"):
            continue
        q = wq.get(r["query_id"], r["question"])
        res = mem.search(query=q, user_id=uid, limit=100)
        hits = res.get("results", []) if isinstance(res, dict) else res
        rset = {norm(h.get("memory", "")) for h in hits}
        if r["conflict_type"] == "has_pair":
            n_hp += 1
            new_in = norm(r["gt_fact_text"]) in rset
            old_in = norm(r["old_fact_text"]) in rset
            key = ("both" if new_in and old_in else "new_only" if new_in
                   else "old_only" if old_in else "neither")
            hp[key] += 1
        else:
            n_nc += 1
            nc["retrieved" if norm(r["gt_fact_text"]) in rset else "missing"] += 1
    return hp, n_hp, nc, n_nc, n_store


def pct(d, n):
    return " ".join(f"{k}={v}({v/max(1,n)*100:.0f}%)" for k, v in d.items())


def main():
    print("=== LEVEL 1 RETRIEVAL (top-100) — vanilla vs ours ===\n")
    out = {}
    for length in LENGTHS:
        print(f"--- {length} ---")
        for tag, prefix in MODES.items():
            hp, n_hp, nc, n_nc, n_store = analyze(prefix, length)
            out[f"{tag}_{length}"] = {"store_points": n_store, "has_pair": hp, "n_has_pair": n_hp,
                                      "no_conflict": nc, "n_no_conflict": n_nc}
            print(f"  {tag:8} [store={n_store} pts] has_pair({n_hp}): {pct(hp, n_hp)}")
            print(f"  {tag:8} {'':16} no_conf({n_nc}): {pct(nc, n_nc)}")
        print()
    json.dump(out, open(ROOT / "analysis/results/phase0/l1_retrieval_eval.json", "w"), ensure_ascii=False, indent=2)
    print("-> analysis/results/phase0/l1_retrieval_eval.json")


if __name__ == "__main__":
    main()
