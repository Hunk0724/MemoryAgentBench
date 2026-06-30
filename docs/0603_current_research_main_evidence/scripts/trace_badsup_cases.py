import json, re, sys
sys.path.insert(0,"/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line

LOGDIR="docs/0603_current_research_main_evidence/logs/sh_32k_l2"
LAYERA="outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware_l2_32k/k_100/factconsolidation_sh_32k/chunksize_512/ingestion_context_0.jsonl"
CTX="analysis/contexts/factconsolidation_32k_context.txt"

def norm(s): return s.strip().rstrip(".").lower() if s else ""
def load_jsonl(p): return [json.loads(l) for l in open(p) if l.strip()]

# seq -> chunk, text
chunks=chunk_facts_by_line(open(CTX).read(),chunk_size=512)
seq_chunk={}; seq_text={}
for cid,ch in enumerate(chunks):
    for ln in ch.split("\n"):
        m=re.match(r"^\s*(\d+)\.\s+(.*)$",ln.strip())
        if m: seq_chunk[int(m.group(1))]=cid; seq_text[int(m.group(1))]=m.group(2).strip().rstrip(".")
txt2seq={norm(t):s for s,t in seq_text.items()}

layerA=load_jsonl(LAYERA)
# build: for each UPDATE event, (prev_norm -> new_memory, chunk_idx)
sup_by_prev={}  # norm(prev) -> list of (new_memory, chunk)
for cid,ln in enumerate(layerA):
    for r in ln["vector_results"]["results"]:
        if r["event"]=="UPDATE":
            sup_by_prev.setdefault(norm(r.get("previous_memory","")),[]).append((r.get("memory",""),cid))
        if r["event"]=="DELETE":
            sup_by_prev.setdefault(norm(r.get("memory","")),[]).append(("<DELETED>",cid))

cands=load_jsonl(LOGDIR+"/candidate_pool.jsonl")

cases=[(8,707,1929),(9,1291,2016),(87,1583,112),(95,1454,1398),(98,324,21)]
for qid,gt_seq,old_seq in cases:
    print("="*80)
    gt_t=seq_text.get(gt_seq); old_t=seq_text.get(old_seq)
    print(f"qid{qid}  gt_seq={gt_seq}(ch{seq_chunk.get(gt_seq)}) old_seq={old_seq}(ch{seq_chunk.get(old_seq)})  winner_by_ingest={max(gt_seq,old_seq)}")
    print(f"  gt  : {gt_t!r}")
    print(f"  old : {old_t!r}")
    # who superseded gt?
    sup=sup_by_prev.get(norm(gt_t))
    print(f"  --> gt SUPERSEDED/deleted by: {sup}")
    sup2=sup_by_prev.get(norm(old_t))
    print(f"  --> old SUPERSEDED/deleted by: {sup2}")
    # If gt superseded, find the contaminating new fact's candidate pool entry
    if sup:
        new_mem,cid=sup[0]
        print(f"  contaminating new fact = {new_mem!r}  (ingested chunk {cid})")
        pf=next((x for x in cands[cid]["per_fact_candidates"] if norm(x["new_fact"])==norm(new_mem)),None)
        if pf:
            print(f"  candidate top5 for contaminating fact (pool_size={cands[cid].get('pool_size_after_dedup')}):")
            for c in pf["top5"]:
                tag=""
                cs=txt2seq.get(norm(c["text"]))
                if cs==gt_seq: tag=" <==GT(overwritten)"
                print(f"     rank{c['rank']} score{c['score']:.3f} seq{cs}: {c['text']!r}{tag}")
        else:
            print("  (could not find contaminating fact in candidate pool)")
