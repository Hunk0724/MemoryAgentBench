"""Level-2 Resolution Evaluation (phase2_spec.md §5.3).

For ours (phase0 structural / phase2 +LLM grouping), apply the SAME query-time
resolution as the benchmark to the top-100, then classify the FINAL context:
  has_pair    -> {both, new_only, old_only, neither}  (ideal after resolve: new_only)
  no_conflict -> singleton {kept, dropped}
Reports the L1->L2 transition and, conditioned on L1==both (where resolution can
act), the resolution_clean_rate (= new kept AND old removed).

This is the demand-driven KU evidence: past methods resolve at write-time
(destructive, L1 already lost info); ours resolves at query-time on the
conservative store. Run in MABench env.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
os.environ.pop("MEM0_QUERY_MODE", None)
os.environ.pop("MEM0_ADD_MODE", None)

from mem0 import Memory  # noqa: E402
from mem0.configs.base import MemoryConfig  # noqa: E402
from methods.phase0_query import assemble_context, group_and_resolve  # noqa: E402
from methods.phase2_query import phase2_resolve  # noqa: E402

STORES = ROOT / "analysis/results/expanded/stores"
LENGTHS = ["6k", "32k", "64k"]
GROUPING_CACHE = {  # phase2 frozen grouping cache per length (deterministic, no live calls)
    "6k": ROOT / "analysis/results/phase0/grouping_cache_sh_6k.json",
    "32k": ROOT / "analysis/results/phase0/grouping_cache_phase2_sh_32k.json",
    "64k": ROOT / "analysis/results/phase0/grouping_cache_phase2_sh_64k.json",
}


def norm(t):
    return (t or "").strip().rstrip(".").strip().lower()


def open_store(prefix, length):
    path = str(STORES / f"qdrant_gpt4o_512_openai_{prefix}__factconsolidation_sh_{length}")
    coll = f"mem0_gpt4o_l2_512_openai_{prefix}__factconsolidation_sh_{length}"
    cfg = {"llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
           "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
           "vector_store": {"provider": "qdrant", "config": {"embedding_model_dims": 1536, "path": path,
                            "on_disk": True, "collection_name": coll}}}
    mem = Memory(config=MemoryConfig(**cfg))
    pts = mem.vector_store.client.scroll(collection_name=coll, limit=1, with_payload=True)[0]
    return mem, (pts[0].payload.get("user_id") if pts else None)


def wrapped_queries(length):
    import glob
    fs = glob.glob(str(ROOT / f"outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-phase2/**/*sh_{length}*results*.json"), recursive=True)
    return {r["query_id"]: r["query"] for r in json.load(open(fs[0]))["data"]}


def bucket(new_in, old_in):
    return ("both" if new_in and old_in else "new_only" if new_in
            else "old_only" if old_in else "neither")


def analyze(mode, length):
    prefix = "phase2"  # phase0/phase2 stores share identical conservative content
    mem, uid = open_store(prefix, length)
    wq = wrapped_queries(length)
    gt = json.load(open(ROOT / f"analysis/results/sh_{length}_mquake_analysis.json"))
    if mode == "phase2":
        os.environ["MEM0_GROUPING_CACHE"] = str(GROUPING_CACHE[length])

    L1 = {"both": 0, "new_only": 0, "old_only": 0, "neither": 0}
    L2 = {"both": 0, "new_only": 0, "old_only": 0, "neither": 0}
    both_to = {"new_only": 0, "both": 0, "old_only": 0, "neither": 0}  # transition from L1==both
    nc = {"l1_retrieved": 0, "l2_kept": 0, "n": 0}
    n_hp = 0
    for r in gt:
        if not r.get("matched"):
            continue
        q = wq.get(r["query_id"], r["question"])
        res = mem.search(query=q, user_id=uid, limit=100)
        hits = res.get("results", []) if isinstance(res, dict) else res
        # resolution
        if mode == "phase0":
            id2 = {str(h["id"]): h for h in hits}
            resolved, ungrouped = group_and_resolve(list(id2.keys()), id2)
            final = resolved + ungrouped
        else:
            final = phase2_resolve(hits, q)
        rset1 = {norm(h.get("memory", "")) for h in hits}
        rset2 = {norm(h.get("memory", "")) for h in final}

        if r["conflict_type"] == "has_pair":
            n_hp += 1
            b1 = bucket(norm(r["gt_fact_text"]) in rset1, norm(r["old_fact_text"]) in rset1)
            b2 = bucket(norm(r["gt_fact_text"]) in rset2, norm(r["old_fact_text"]) in rset2)
            L1[b1] += 1
            L2[b2] += 1
            if b1 == "both":
                both_to[b2] += 1
        else:
            nc["n"] += 1
            nc["l1_retrieved"] += norm(r["gt_fact_text"]) in rset1
            nc["l2_kept"] += norm(r["gt_fact_text"]) in rset2
    return L1, L2, both_to, nc, n_hp


def pct(d, n):
    return " ".join(f"{k}={v}({v/max(1,n)*100:.0f}%)" for k, v in d.items())


def main():
    out = {}
    for length in LENGTHS:
        print(f"\n========== {length} ==========")
        for mode in ["phase0", "phase2"]:
            L1, L2, bt, nc, n_hp = analyze(mode, length)
            nb = sum(bt.values())
            out[f"{mode}_{length}"] = {"L1": L1, "L2": L2, "both_transition": bt, "no_conflict": nc}
            print(f" [{mode}] has_pair({n_hp})")
            print(f"    L1 retrieval : {pct(L1, n_hp)}")
            print(f"    L2 resolved  : {pct(L2, n_hp)}")
            print(f"    of L1=both({nb}) -> {pct(bt, nb)}  [clean_rate={bt['new_only']/max(1,nb)*100:.0f}%]")
            print(f"    no_conflict  : L1_ret={nc['l1_retrieved']}/{nc['n']} L2_kept={nc['l2_kept']}/{nc['n']}")
    json.dump(out, open(ROOT / "analysis/results/phase0/l2_resolution_eval.json", "w"), ensure_ascii=False, indent=2)
    print("\n-> analysis/results/phase0/l2_resolution_eval.json")


if __name__ == "__main__":
    main()
