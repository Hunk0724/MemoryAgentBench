import json, re, sys
sys.path.insert(0,"/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line
from collections import Counter

LOGDIR="docs/0603_current_research_main_evidence/logs/sh_32k_l2"
LAYERA="outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware_l2_32k/k_100/factconsolidation_sh_32k/chunksize_512/ingestion_context_0.jsonl"
CTX="analysis/contexts/factconsolidation_32k_context.txt"
PAIRS="analysis/results/mh_32k_FULLPAIRS_gt.json"

def norm(s): return s.strip().rstrip(".").lower() if s else ""
def load_jsonl(p): return [json.loads(l) for l in open(p) if l.strip()]

chunks=chunk_facts_by_line(open(CTX).read(),chunk_size=512)
seq_chunk={}; seq_text={}
for cid,ch in enumerate(chunks):
    for ln in ch.split("\n"):
        m=re.match(r"^\s*(\d+)\.\s+(.*)$",ln.strip())
        if m: seq_chunk[int(m.group(1))]=cid; seq_text[int(m.group(1))]=m.group(2).strip().rstrip(".")
txt2seq={norm(t):s for s,t in seq_text.items()}

# pairs: winner=larger seq, loser=smaller
pairs=json.load(open(PAIRS))
winner_loser={}  # winner_seq -> loser_seq
gt_is_winner={}  # winner_seq(by ingest) -> is MQuAKE gt the winner?
for q in pairs:
    h=q["hops"][0]; o,g=h["old_seq"],h["gt_seq"]
    lo,wi=min(o,g),max(o,g)
    winner_loser[wi]=lo
    gt_is_winner[wi]=(g==wi)

# Layer A: for each fact text, find UPDATE event that superseded it (prev->new,chunk)
layerA=load_jsonl(LAYERA)
sup_by_prev={}
for cid,ln in enumerate(layerA):
    for r in ln["vector_results"]["results"]:
        if r["event"]=="UPDATE":
            sup_by_prev.setdefault(norm(r.get("previous_memory","")),(r.get("memory",""),cid))
        elif r["event"]=="DELETE":
            sup_by_prev.setdefault(norm(r.get("memory","")),("<DELETED>",cid))

cands=load_jsonl(LOGDIR+"/candidate_pool.jsonl")
def topN_for(cid,new_mem):
    if cid>=len(cands): return None
    pf=next((x for x in cands[cid]["per_fact_candidates"] if norm(x["new_fact"])==norm(new_mem)),None)
    return pf

# For each winner (the fact that SHOULD remain stored), check its fate
cats=Counter()
a4_rows=[]
benchmark_anom=[]
for wi,lo in winner_loser.items():
    wt=seq_text.get(wi); lot=seq_text.get(lo)
    sup=sup_by_prev.get(norm(wt))
    if sup is None:
        cats["winner_stored_or_ok"]+=1; continue
    new_mem,cid=sup
    # is the superseding fact the legitimate partner (same-subject conflict)? 
    # legitimate = the loser fact OR same (subject,relation) slot as winner
    if norm(new_mem)==norm(lot):
        cats["winner_superseded_by_partner(benchmark_anom?)"]+=1
        benchmark_anom.append((wi,lo)); continue
    # else: contaminated by a DIFFERENT fact = A4
    cats["A4_contamination"]+=1
    # was gt(winner) in the contaminating fact's top5? (=> update-LLM overfire, not A1)
    pf=topN_for(cid,new_mem)
    gt_rank=None
    if pf:
        for c in pf["top5"]:
            if txt2seq.get(norm(c["text"]))==wi: gt_rank=c["rank"]; break
    a4_rows.append({"winner_seq":wi,"winner":wt,"superseded_by":new_mem,
                    "gt_in_contaminator_top5_rank":gt_rank})

print("=== Winner fate across all", len(winner_loser),"in-store pairs (32k SH run) ===")
for k,v in cats.most_common(): print(f"  {k}: {v}")
print(f"\n=== A4 contaminations: {len(a4_rows)} ===")
present=sum(1 for r in a4_rows if r["gt_in_contaminator_top5_rank"] is not None)
print(f"  gt present in contaminator top5 (=> update-LLM overfire, NOT A1 miss): {present}/{len(a4_rows)}")
rk=Counter(r["gt_in_contaminator_top5_rank"] for r in a4_rows)
print(f"  rank distribution of overwritten gt in contaminator top5: {dict(rk)}")
print("\n  sample A4 rows:")
for r in a4_rows[:12]:
    print(f"   seq{r['winner_seq']} rank={r['gt_in_contaminator_top5_rank']}  {r['winner'][:45]!r} <- {r['superseded_by'][:55]!r}")
print(f"\n=== benchmark-anomaly (winner superseded by its own partner; gt<old) : {len(benchmark_anom)} ===")
print("  (these = mem0 mechanically correct, only 'wrong' vs MQuAKE gt because gt=smaller seq)")
