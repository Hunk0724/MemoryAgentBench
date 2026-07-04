"""Per-query pool-based Resolution for no_p5 (= ours_struct + P3 LLM identity
grouping) — Figure C (F_p3_backbone_6k) data, the analog of Figure B for the +P3
variant. Faithfully REPLICATES phase2_resolve INLINE (structural (S,P) routing +
P3 identity clusters + argmax, P5 skipped) but reads P3 clusters straight from the
FROZEN grouping cache (grouping_cache_no_p5_6k.json) — NEVER calls gemma, never
writes the cache. Cache key MUST use the wrapped agent query (`message`, stored as
results.json 'query'), not the bare GT question — that is what agent.py:1046 passes.

Prints the cache hit-rate; a miss falls back to empty clusters (= struct-like),
which is correct for the ~99% of queries where P3 formed no cluster anyway.
Embedding-only, no GPU. Key: OPENAI_API_KEY_FOR_GX10 (fallback A).
  python docs/0615_.../scripts/compute_resolution_per_query_no_p5.py [sizes...]
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/MemoryAgentBench"))
import json, glob, re
from collections import Counter, defaultdict
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
os.environ["MEM0_P5_SKIP"] = "1"
KEY = os.environ.get("OPENAI_API_KEY_FOR_GX10") or os.environ.get("OPENAI_API_KEY_A")
if not KEY:
    sys.exit("ERROR: set OPENAI_API_KEY_FOR_GX10 (or OPENAI_API_KEY_A)")
oc = OpenAI(api_key=KEY)
from methods.phase2_query import (conditional_structural_routing, _grouping_cache_key,
                                  _text, _id, _ordinal, _drop_older, _subject_consistent)

UID = "context_0_factconsolidation_sh_6k"
gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
HP = [q for q, r in gt.items() if r["conflict_type"] == "has_pair"]
STRIP = "[]'"
SIZES = sys.argv[1:] or ["1b", "4b", "12b", "27b"]
embc = {}


def emb(t):
    if t not in embc:
        embc[t] = oc.embeddings.create(model="text-embedding-3-small", input=t,
                                       dimensions=1536).data[0].embedding
    return embc[t]


def results(size):
    fs = glob.glob(f"outputs/*unified_no_p5__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    return {r["query_id"]: r for r in json.load(open(fs[0]))["data"]} if fs else {}


def wb(val, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(val) + r"(?![a-z0-9])", text) is not None


def resolve(cands, wrapped_query, cache):
    """Inline phase2_resolve (P5_SKIP), clusters from frozen cache; no LLM."""
    structural_pool, dynamic_pool = conditional_structural_routing(cands)
    key = _grouping_cache_key(wrapped_query, dynamic_pool)
    gc = cache.get(key)
    hit = gc is not None
    clusters = []
    if gc:
        t2i = defaultdict(list)
        for it in dynamic_pool:
            t2i[_text(it)].append(it)
        for gtexts in gc:
            members = [m for t in gtexts for m in t2i.get(t, [])]
            if len(members) >= 2 and _subject_consistent(members):
                clusters.append(members)
    groups = list(structural_pool.values()) + clusters
    drop = set()
    for g in groups:
        if len(g) >= 2:
            drop |= _drop_older(g)[0]
    return [it for it in cands if _id(it) not in drop], hit


SUMMARY = {}
if os.path.exists("analysis/results/resolution_vs_em_no_p5_6k.json"):
    SUMMARY = json.load(open("analysis/results/resolution_vs_em_no_p5_6k.json"))

for size in SIZES:
    store = f"analysis/results/expanded/stores/qdrant_gpt4o_512_openai_unified_no_p5__gemma3-{size}__factconsolidation_sh_6k"
    if not os.path.isdir(store):
        print(f"{size}: SKIP (no_p5 store missing)"); continue
    gcache_path = f"analysis/results/p1_caches__gemma3-{size}/grouping_cache_no_p5_6k.json"
    cache = json.load(open(gcache_path, encoding="utf-8")) if os.path.exists(gcache_path) else {}
    R = results(size)
    c = QdrantClient(path=store); col = c.get_collections().collections[0].name
    per = {}; cnt = Counter(); hits = 0
    for q in HP:
        r = gt[q]; nv = str(r["gt_answer"]).strip(STRIP).lower(); ov = str(r["old_answer"]).strip(STRIP).lower()
        subj = (r["gt_fact_text"].split(" is ")[0].split(" plays ")[0].split(" was ")[0])[:12].lower()
        wq = str(R.get(q, {}).get("query") or r["question"])          # wrapped agent query
        hitpts = c.query_points(collection_name=col, query=emb(r["question"]), limit=100,
                                query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=UID))])).points
        cands = [{"id": h.id, "memory": h.payload.get("data"),
                  "metadata": {"triple": h.payload.get("triple"), "ordinal": h.payload.get("ordinal")}} for h in hitpts]
        retained, hit = resolve(cands, wq, cache); hits += hit
        pool = [(_text(it) or "").lower() for it in retained]
        new_in = any(subj in ln and wb(nv, ln) for ln in pool)
        old_in = any(subj in ln and wb(ov, ln) for ln in pool)
        e = bool(R.get(q, {}).get("exact_match"))
        iso = new_in and not old_in
        cls = ("isolated" if e else "drag") if iso else \
              ("rescue" if e else ("new_absent_wrong" if not new_in else "wrong_notiso"))
        cnt[cls] += 1
        per[q] = {"cls": cls, "new_in": new_in, "old_in": old_in, "em": e, "cache_hit": hit}
    c.close()
    res = cnt["isolated"] + cnt["drag"]; em = sum(1 for v in per.values() if v["em"])
    newabs = sum(1 for v in per.values() if not v["new_in"])
    json.dump(per, open(f"analysis/results/resolution_per_query_no_p5_6k_{size}.json", "w"), indent=1, ensure_ascii=False)
    SUMMARY[size] = {"N": len(HP), "em": em, "res": res, "drag": cnt["drag"], "rescue": cnt["rescue"],
                     "new_absent": newabs}
    print(f"{size}: no_p5 Res={res}/{len(HP)} EM={em}/{len(HP)} drag={cnt['drag']} rescue={cnt['rescue']} "
          f"new_absent={newabs} | cache_hit={hits}/{len(HP)}")

SUMMARY.setdefault("gpt-4o-mini", {"N": 74, "em": None, "res": None})
json.dump(SUMMARY, open("analysis/results/resolution_vs_em_no_p5_6k.json", "w"), indent=1)
print("saved analysis/results/resolution_vs_em_no_p5_6k.json")
