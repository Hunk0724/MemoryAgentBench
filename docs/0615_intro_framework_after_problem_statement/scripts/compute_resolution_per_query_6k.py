"""Per-query pool-based Resolution dump for FC-SH 6k has_pair, per backbone.
Same code path as compute_resolution_acc_6k.py (top-100 retrieve -> group_and_resolve
-> assemble_context), but logs PER QUERY whether the resolved pool isolates NEW,
plus the subject-scoped pool lines that carry the OLD value -> pins down exactly
which queries are reader-RESCUE (pool not isolated, EM ok) vs DRAG/WRONG, and the
mechanism for weak models (why OLD leaks into the pool).

Key: reads OPENAI_API_KEY_FOR_GX10 (this machine's key), fallback OPENAI_API_KEY_A.
No .env sourcing. Needs the per-size struct qdrant stores present.
  python docs/0615_.../scripts/compute_resolution_per_query_6k.py [sizes...]
-> writes analysis/results/resolution_per_query_6k_<size>.json + prints not-isolated.
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/MemoryAgentBench"))
import json, glob, re
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from methods.phase0_query import group_and_resolve, assemble_context

os.chdir(os.path.expanduser("~/MemoryAgentBench"))
KEY = os.environ.get("OPENAI_API_KEY_FOR_GX10") or os.environ.get("OPENAI_API_KEY_A")
if not KEY:
    sys.exit("ERROR: set OPENAI_API_KEY_FOR_GX10 (or OPENAI_API_KEY_A) in the shell profile")
oc = OpenAI(api_key=KEY)
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


def resfile(size):
    fs = glob.glob(f"outputs/*unified_struct__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    return {r["query_id"]: bool(r["exact_match"]) for r in json.load(open(fs[0]))["data"]}


def wb(val, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(val) + r"(?![a-z0-9])", text) is not None


for size in SIZES:
    store = f"analysis/results/expanded/stores/qdrant_gpt4o_512_openai_unified_struct__gemma3-{size}__factconsolidation_sh_6k"
    if not os.path.isdir(store):
        print(f"{size}: SKIP (store missing)"); continue
    c = QdrantClient(path=store); col = c.get_collections().collections[0].name
    EM = resfile(size)
    per = {}
    counts = {"isolated": 0, "rescue": 0, "drag": 0, "wrong_notiso": 0, "new_absent": 0}
    notiso = []
    for q in HP:
        r = gt[q]; nv = str(r["gt_answer"]).strip(STRIP).lower(); ov = str(r["old_answer"]).strip(STRIP).lower()
        subj = (r["gt_fact_text"].split(" is ")[0].split(" plays ")[0].split(" was ")[0])[:12].lower()
        hits = c.query_points(collection_name=col, query=emb(r["question"]), limit=100,
                              query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=UID))])).points
        id2 = {str(h.id): {"memory": h.payload.get("data"),
                           "metadata": {"triple": h.payload.get("triple"), "ordinal": h.payload.get("ordinal")}} for h in hits}
        resolved, ung = group_and_resolve(list(id2.keys()), id2)
        pool = [ln for ln in assemble_context(resolved, ung).split("\n") if ln.strip()]
        new_in = any(subj in ln.lower() and wb(nv, ln.lower()) for ln in pool)
        old_lines = [ln for ln in pool if subj in ln.lower() and wb(ov, ln.lower())]
        old_in = len(old_lines) > 0
        e = EM.get(q, False)
        iso = new_in and not old_in
        if iso:
            cls = "isolated" if e else "drag"; counts["isolated"] += 1
            if not e: counts["drag"] += 1
        else:
            if not new_in: counts["new_absent"] += 1
            cls = "rescue" if e else "wrong_notiso"
            counts["rescue" if e else "wrong_notiso"] += 1
            notiso.append((q, cls, new_in, old_lines))
        per[q] = {"cls": cls, "new_in": new_in, "old_in": old_in, "em": e,
                  "old_lines": old_lines[:4]}
    c.close()
    json.dump(per, open(f"analysis/results/resolution_per_query_6k_{size}.json", "w"), indent=1, ensure_ascii=False)
    print(f"\n==== gemma3-{size} ====  isolated(res)={counts['isolated']} "
          f"rescue={counts['rescue']} drag={counts['drag']} wrong_notiso={counts['wrong_notiso']} "
          f"new_absent={counts['new_absent']}  EM={sum(EM[q] for q in HP)}/{len(HP)}")
    print(f"  not-isolated queries ({len(notiso)}):")
    for q, cls, ni, ol in notiso:
        print(f"   q{q} [{cls}] new_in={ni} | OLD-carrying pool lines:")
        for ln in ol[:3]:
            print(f"       {ln[:110]}")
