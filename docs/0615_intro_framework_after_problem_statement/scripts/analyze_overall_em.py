"""Complete EM table: has_pair / no_conflict / overall, for vanilla/phase0/phase2.
ours (phase0/phase2): read benchmark result JSONs (free), split by conflict_type.
vanilla: re-run inference on the vanilla store (raw top-100, no resolution).
Run in MABench env.
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

STORES = ROOT / "analysis/results/expanded/stores"
LENGTHS = ["6k", "32k", "64k"]
_cli = OpenAI(timeout=120, max_retries=5)


def norm(t):
    return (t or "").strip().rstrip(".").strip().lower()


def fuzzy(pred, gold):
    pn, gn = norm(pred), norm(gold)
    return bool(pn and gn and (pn == gn or gn in pn or pn in gn))


def conflict_map(length):
    return {r["query_id"]: r.get("conflict_type")
            for r in json.load(open(ROOT / f"analysis/results/sh_{length}_mquake_analysis.json"))}


def split_em(em_by_qid, cmap):
    hp = [v for q, v in em_by_qid.items() if cmap.get(q) == "has_pair"]
    nc = [v for q, v in em_by_qid.items() if cmap.get(q) != "has_pair"]
    allv = list(em_by_qid.values())
    f = lambda L: (sum(L), len(L))
    return f(hp), f(nc), f(allv)


def ours_em(tag, length):
    fs = glob.glob(str(ROOT / f"outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-{tag}/**/*sh_{length}*results*.json"), recursive=True)
    rows = json.load(open(fs[0]))["data"]
    return {r["query_id"]: int(bool(r["exact_match"])) for r in rows}


def vanilla_em(length):
    path = str(STORES / f"qdrant_gpt4o_512_openai_rerun__factconsolidation_sh_{length}")
    coll = f"mem0_gpt4o_l2_512_openai_rerun__factconsolidation_sh_{length}"
    cfg = {"llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
           "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
           "vector_store": {"provider": "qdrant", "config": {"embedding_model_dims": 1536, "path": path,
                            "on_disk": True, "collection_name": coll}}}
    mem = Memory(config=MemoryConfig(**cfg))
    uid = mem.vector_store.client.scroll(collection_name=coll, limit=1, with_payload=True)[0][0].payload.get("user_id")
    fs = glob.glob(str(ROOT / f"outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-phase2/**/*sh_{length}*results*.json"), recursive=True)
    rows = json.load(open(fs[0]))["data"]
    wq = {r["query_id"]: r["query"] for r in rows}
    gt = {r["query_id"]: r for r in json.load(open(ROOT / f"analysis/results/sh_{length}_mquake_analysis.json"))}
    em = {}
    for qid, q in wq.items():
        res = mem.search(query=q, user_id=uid, limit=100)
        hits = res.get("results", []) if isinstance(res, dict) else res
        ctx = "\n".join(f"- {h.get('memory','')}" for h in hits)
        system = f"You are a helpful AI. Answer the question based on query and memories.\n{ctx}\n"
        user = q + "\n\nCurrent Time: " + time.strftime("%Y-%m-%d %H:%M:%S")
        a = _cli.chat.completions.create(model="gpt-4o-mini", temperature=0, max_tokens=256,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]).choices[0].message.content
        em[qid] = int(fuzzy(a, gt[qid]["gt_answer"]))
    return em


def main():
    print(f"{'':22}| has_pair        | no_conflict     | overall")
    for length in LENGTHS:
        cmap = conflict_map(length)
        for tag in ["vanilla", "phase0", "phase2"]:
            em = vanilla_em(length) if tag == "vanilla" else ours_em(tag, length)
            (hpc, hpn), (ncc, ncn), (ac, an) = split_em(em, cmap)
            print(f"{tag+'_'+length:22}| {hpc:3}/{hpn} = {hpc/hpn*100:4.0f}% | "
                  f"{ncc:3}/{ncn} = {ncc/ncn*100:4.0f}% | {ac:3}/{an} = {ac/an*100:4.0f}%")
        print("-" * 70)


if __name__ == "__main__":
    main()
