"""Phase 0 — end-to-end FC-SH QA: RAW top-100 vs top-100 + (S,P) resolve.

Same conservative-ADD store, same retrieval (cosine top-100), same FC inference
template (verbatim), same scorer. The ONLY difference between the two configs is
whether M6 group+temporal-resolve runs before handing memories to inference.
=> isolates the contribution of triple-based resolution on vanilla retrieval.

Run (MABench env): python docs/0615_.../scripts/qa_end2end.py
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"), override=False)

LEN, TASK = "6k", "sh"
UID = f"phase0_{TASK}_{LEN}"
QDRANT = os.path.join(ROOT, f".cache/phase0_qdrant_{TASK}_{LEN}")
RETRIEVE_NUM = 100
GEN_MODEL = "gpt-4o-mini"
OUT = os.path.join(ROOT, f"analysis/results/phase0/qa_{TASK}_{LEN}.json")

from openai import OpenAI  # noqa: E402
from mem0 import Memory  # noqa: E402
from mem0.configs.base import MemoryConfig  # noqa: E402
from methods.phase0_query import assemble_context, group_and_resolve  # noqa: E402

_cli = OpenAI(timeout=120, max_retries=5)


def normalize(s):
    return "" if s is None else str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(pred, gold):
    if pred is None or gold is None:
        return False
    if isinstance(gold, list):
        return any(fuzzy_match(pred, g) for g in gold)
    pn, gn = normalize(pred), normalize(gold)
    return bool(pn and gn and (pn == gn or gn in pn or pn in gn))


def infer(memories_str, wrapped_q):
    system = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
    user = wrapped_q + "\n\nCurrent Time: " + time.strftime("%Y-%m-%d %H:%M:%S")
    r = _cli.chat.completions.create(
        model=GEN_MODEL, temperature=0, max_tokens=256,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return r.choices[0].message.content or ""


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
    allm = mem.get_all(user_id=UID, limit=2000)
    items = allm.get("results", allm) if isinstance(allm, dict) else allm
    id2item = {str(m["id"]): m for m in items}

    gt = json.load(open(os.path.join(ROOT, f"analysis/results/{TASK}_512_mquake_analysis.json")))
    mab = os.path.join(ROOT, f"outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_{TASK}_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json")
    wrapped = {e["query_id"]: e["query"] for e in json.load(open(mab))["data"]} if os.path.exists(mab) else {}
    print(f"storage {len(id2item)} mem | {len(gt)} queries | wrapped={'yes' if wrapped else 'NO(bare)'}")

    rows = []
    for i, q in enumerate(gt):
        qid, qbare, ans = q["query_id"], q["question"], q["gt_answer"]
        wq = wrapped.get(qid, qbare)
        retrieved = mem.search(query=wq, user_id=UID, limit=RETRIEVE_NUM)
        rl = retrieved.get("results", []) if isinstance(retrieved, dict) else retrieved

        raw_ctx = "\n".join(f"- {e.get('memory','')}" for e in rl)
        ids = [str(e["id"]) for e in rl]
        resolved, ungrouped = group_and_resolve(ids, id2item)
        res_ctx = assemble_context(resolved, ungrouped)

        a_raw = infer(raw_ctx, wq)
        a_res = infer(res_ctx, wq)
        rows.append({
            "query_id": qid, "gt_answer": ans, "conflict": q.get("conflict_type"),
            "n_retrieved": len(rl), "n_resolved": len(resolved) + len(ungrouped),
            "em_raw": fuzzy_match(a_raw, ans), "em_resolved": fuzzy_match(a_res, ans),
            "pred_raw": a_raw, "pred_resolved": a_res,
        })
        if (i + 1) % 20 == 0:
            er = sum(r["em_raw"] for r in rows); ee = sum(r["em_resolved"] for r in rows)
            print(f"  [{i+1}/{len(gt)}] raw={er} resolved={ee}")

    json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=2)
    n = len(rows)
    hp = [r for r in rows if r["conflict"] == "has_pair"]
    nc = [r for r in rows if r["conflict"] != "has_pair"]
    def acc(rs, k): return f"{sum(r[k] for r in rs)}/{len(rs)} = {sum(r[k] for r in rs)/max(1,len(rs))*100:.1f}%"
    print(f"\n=== FC-SH 6k EM (gpt-4o-mini, top-100) ===")
    print(f"  ALL ({n}):        raw {acc(rows,'em_raw')}  |  resolved {acc(rows,'em_resolved')}")
    print(f"  has_pair ({len(hp)}): raw {acc(hp,'em_raw')}  |  resolved {acc(hp,'em_resolved')}")
    print(f"  no_conflict ({len(nc)}): raw {acc(nc,'em_raw')}  |  resolved {acc(nc,'em_resolved')}")
    avg_raw = sum(r["n_retrieved"] for r in rows) / n
    avg_res = sum(r["n_resolved"] for r in rows) / n
    print(f"  avg context size: raw {avg_raw:.0f} -> resolved {avg_res:.0f} memories")
    print(f"  -> {OUT}")


if __name__ == "__main__":
    main()
