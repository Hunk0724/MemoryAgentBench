"""Recompute FC-SH 6k has_pair Resolution Accuracy (method) + EM (reader) per
gemma backbone, from the *struct* stores + outputs. Overwrites
analysis/results/resolution_vs_em_6k.json (consumed by make_struct_backbone_6k.py).

Resolution = the resolved pool ISOLATES the NEW version: GT_new present AND
GT_old absent, matched subject-scoped + word-boundary over the actual
group_and_resolve() output (same code path as query time). This is the METHOD's
contribution, independent of the reader. EM read live from the results.json.

Run AFTER any struct re-run (e.g. NEW code: normalize L1/L2 + fact-level ordinal)
so the figure numbers stay consistent across all sizes. Needs OPENAI_API_KEY_A
(embedding) + the per-size struct qdrant stores present.
  python docs/0615_.../scripts/compute_resolution_acc_6k.py [sizes...]
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/MemoryAgentBench"))
import json, glob, re
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from methods.phase0_query import group_and_resolve, assemble_context

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
oc = OpenAI(api_key=os.environ["OPENAI_API_KEY_A"])
UID = "context_0_factconsolidation_sh_6k"
gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
hp = [q for q, r in gt.items() if r["conflict_type"] == "has_pair"]
STRIP = "[]'"
SIZES = sys.argv[1:] or ["1b", "4b", "12b", "27b"]
embc = {}


def emb(t):
    if t not in embc:
        embc[t] = oc.embeddings.create(model="text-embedding-3-small", input=t,
                                       dimensions=1536).data[0].embedding
    return embc[t]


def resfile(size):
    fs = glob.glob(f"outputs/*unified_struct__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    return {r["query_id"]: r for r in json.load(open(fs[0]))["data"]}


def wb(val, text):  # word-boundary exact value in text
    return re.search(r"(?<![a-z0-9])" + re.escape(val) + r"(?![a-z0-9])", text) is not None


OUT = {}
if os.path.exists("analysis/results/resolution_vs_em_6k.json"):
    OUT = json.load(open("analysis/results/resolution_vs_em_6k.json"))  # preserve untouched sizes

for size in SIZES:
    store = f"analysis/results/expanded/stores/qdrant_gpt4o_512_openai_unified_struct__gemma3-{size}__factconsolidation_sh_6k"
    if not os.path.isdir(store):
        print(f"{size}: SKIP (store missing: {store})")
        continue
    c = QdrantClient(path=store); col = c.get_collections().collections[0].name
    R = resfile(size)
    em = rescorr = drag = rescue = both = newabs = 0
    for q in hp:
        r = gt[q]; nv = str(r["gt_answer"]).strip(STRIP).lower(); ov = str(r["old_answer"]).strip(STRIP).lower()
        subj = (r["gt_fact_text"].split(" is ")[0].split(" plays ")[0].split(" was ")[0])[:12].lower()
        hits = c.query_points(collection_name=col, query=emb(r["question"]), limit=100,
                              query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=UID))])).points
        id2 = {str(h.id): {"memory": h.payload.get("data"),
                           "metadata": {"triple": h.payload.get("triple"), "ordinal": h.payload.get("ordinal")}} for h in hits}
        resolved, ung = group_and_resolve(list(id2.keys()), id2)
        pool = [ln.lower() for ln in assemble_context(resolved, ung).split("\n")]
        new_in = any(subj in ln and wb(nv, ln) for ln in pool)
        old_in = any(subj in ln and wb(ov, ln) for ln in pool)
        e = bool(R[q]["exact_match"]); em += e
        if new_in and not old_in:
            rescorr += 1
            if not e: drag += 1
        else:
            if old_in: both += 1
            else: newabs += 1
            if e: rescue += 1
    c.close()
    OUT[size] = {"N": len(hp), "em": em, "res": rescorr, "drag": drag, "rescue": rescue,
                 "pool_not_isolated": both, "new_absent": newabs}
    print(f"{size}: EM={em}/{len(hp)}  Resolution={rescorr}/{len(hp)}  drag={drag} rescue={rescue} "
          f"old_still_in={both} new_absent={newabs}  (EM==res-drag+rescue: {rescorr-drag+rescue})")

OUT.setdefault("gpt-4o-mini", {"N": 74, "em": 69, "res": None})  # Table3 EM only; store on Mac
json.dump(OUT, open("analysis/results/resolution_vs_em_6k.json", "w"), indent=1)
print("\nsaved analysis/results/resolution_vs_em_6k.json")
