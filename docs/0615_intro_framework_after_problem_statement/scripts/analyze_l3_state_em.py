"""Level-3: final-context STATE  x  per-query EM  (phase2_spec.md §5.4/§5.5).

For the context that actually reaches the inference LLM, classify the has_pair
state {new_only, both, old_only, neither} and cross-tabulate with exact_match.
  - vanilla mem0: final context = raw top-100 (KU done destructively at write).
  - ours phase0/phase2: final context = AFTER query-time resolution.
Shows the causal chain state -> EM, and that vanilla is stuck (irreversibly) in
old_only/neither while ours reaches new_only.

EM source: ours from benchmark result JSONs (already aligned); vanilla from
inference run on its own store (only 6k has a result JSON). Run in MABench env.
"""
import glob
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
for k in ("MEM0_QUERY_MODE", "MEM0_ADD_MODE"):
    os.environ.pop(k, None)

from openai import OpenAI  # noqa: E402
from mem0 import Memory  # noqa: E402
from mem0.configs.base import MemoryConfig  # noqa: E402
from methods.phase0_query import group_and_resolve  # noqa: E402
from methods.phase2_query import phase2_resolve  # noqa: E402

STORES = ROOT / "analysis/results/expanded/stores"
LENGTHS = ["6k", "32k", "64k"]
GC = {"6k": "grouping_cache_sh_6k.json", "32k": "grouping_cache_phase2_sh_32k.json",
      "64k": "grouping_cache_phase2_sh_64k.json"}
MODE_PREFIX = {"vanilla": "rerun", "phase0": "phase2", "phase2": "phase2"}
_cli = OpenAI(timeout=120, max_retries=5)


def norm(t):
    return (t or "").strip().rstrip(".").strip().lower()


def fuzzy(pred, gold):
    pn, gn = norm(pred), norm(gold)
    return bool(pn and gn and (pn == gn or gn in pn or pn in gn))


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
    fs = glob.glob(str(ROOT / f"outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-phase2/**/*sh_{length}*results*.json"), recursive=True)
    return {r["query_id"]: r["query"] for r in json.load(open(fs[0]))["data"]}


def bench_em(tag, length):
    fs = glob.glob(str(ROOT / f"outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-{tag}/**/*sh_{length}*results*.json"), recursive=True)
    if not fs:
        return None
    return {r["query_id"]: bool(r["exact_match"]) for r in json.load(open(fs[0]))["data"]}


def infer(mem_texts, wrapped_q):
    ctx = "\n".join(f"- {t}" for t in mem_texts)
    system = f"You are a helpful AI. Answer the question based on query and memories.\n{ctx}\n"
    user = wrapped_q + "\n\nCurrent Time: " + time.strftime("%Y-%m-%d %H:%M:%S")
    r = _cli.chat.completions.create(model="gpt-4o-mini", temperature=0, max_tokens=256,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content or ""


def bucket(new_in, old_in):
    return ("both" if new_in and old_in else "new_only" if new_in
            else "old_only" if old_in else "neither")


def run(mode, length):
    prefix = MODE_PREFIX[mode]
    mem, uid = open_store(prefix, length)
    wq = wrapped_queries(length)
    gt = json.load(open(ROOT / f"analysis/results/sh_{length}_mquake_analysis.json"))
    if mode == "phase2":
        os.environ["MEM0_GROUPING_CACHE"] = str(ROOT / "analysis/results/phase0" / GC[length])
    em_map = None if mode == "vanilla" else bench_em(mode, length)

    # final-context state x EM, for BOTH subsets
    cells_hp, cells_nc = {}, {}  # state -> [n, n_correct]
    for r in gt:
        if not r.get("matched"):
            continue
        q = wq.get(r["query_id"], r["question"])
        res = mem.search(query=q, user_id=uid, limit=100)
        hits = res.get("results", []) if isinstance(res, dict) else res
        if mode == "vanilla":
            final = hits
        elif mode == "phase0":
            id2 = {str(h["id"]): h for h in hits}
            rs, ug = group_and_resolve(list(id2.keys()), id2)
            final = rs + ug
        else:
            final = phase2_resolve(hits, q)
        tset = {norm(t) for t in (h.get("memory", "") for h in final)}
        correct = em_map.get(r["query_id"], False) if em_map is not None \
            else fuzzy(infer([h.get("memory", "") for h in final], q), r["gt_answer"])
        if r["conflict_type"] == "has_pair":
            st = bucket(norm(r["gt_fact_text"]) in tset, norm(r["old_fact_text"]) in tset)
            cells_hp.setdefault(st, [0, 0])
            cells_hp[st][0] += 1; cells_hp[st][1] += int(correct)
        else:
            st = "present" if norm(r["gt_fact_text"]) in tset else "missing"
            cells_nc.setdefault(st, [0, 0])
            cells_nc[st][0] += 1; cells_nc[st][1] += int(correct)
    return cells_hp, cells_nc


def main():
    out = {}
    for length in LENGTHS:
        print(f"\n========== {length} (final state x EM) ==========")
        for mode in ["vanilla", "phase0", "phase2"]:
            hp, nc = run(mode, length)
            out[f"{mode}_{length}"] = {"cells": hp, "cells_no_conflict": nc}
            ph = " | ".join(f"{s}: {c}/{n}" for s, (n, c) in sorted(hp.items(), key=lambda x: -x[1][0]))
            pn = " | ".join(f"{s}: {c}/{n}" for s, (n, c) in sorted(nc.items(), key=lambda x: -x[1][0]))
            print(f" [{mode:7}] has_pair[{ph}]  no_conflict[{pn}]")
    json.dump(out, open(ROOT / "analysis/results/phase0/l3_state_em.json", "w"), ensure_ascii=False, indent=2)
    print("\n-> analysis/results/phase0/l3_state_em.json")


if __name__ == "__main__":
    main()
