"""Print detailed per-case info for FC-SH 6k, to understand specific cases."""
import json, re, glob, sys
from pathlib import Path
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line

AG = "Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware_l2"
BASE = Path("/home/yhchiang/MemoryAgentBench")
RR = BASE / f"outputs/rag_retrieved/{AG}/k_100/factconsolidation_sh_6k/chunksize_512"
LA = RR / "ingestion_context_0.jsonl"
RESULTS = next((BASE / "outputs/gemini-3.1-flash-lite-mem0-chunk512-temp0-factaware-l2/Conflict_Resolution").glob("factconsolidation_sh_6k_*results.json"))
GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
PAIRS = BASE / "analysis/results/mh_6k_FULLPAIRS_gt.json"
COND = BASE / "docs/0603_current_research_main_evidence/logs/sh_6k_conditional.json"

def norm(s): return s.strip().rstrip(".").lower() if s else ""

# seq -> chunk
seq_chunk = {}
for cid, ch in enumerate(chunk_facts_by_line((BASE/"analysis/contexts/factconsolidation_6k_context.txt").read_text(), chunk_size=512)):
    for ln in ch.split("\n"):
        m = re.match(r"^\s*(\d+)\.", ln.strip())
        if m: seq_chunk[int(m.group(1))] = cid
# role + samechunk from pairs
role, samechunk = {}, {}
for q in json.load(open(PAIRS)):
    h=q["hops"][0]; o,g=h["old_seq"],h["gt_seq"]; lo,wi=min(o,g),max(o,g)
    role[lo]="loser"; role[wi]="winner"; sc=seq_chunk.get(lo)==seq_chunk.get(wi); samechunk[lo]=samechunk[wi]=sc
# fate from Layer A
op={}
import collections
op=collections.defaultdict(set)
for ln in [json.loads(l) for l in open(LA)]:
    for r in ln["vector_results"]["results"]:
        ev,s=r["event"],{norm(v):k for k,v in {kk:vv for kk,vv in []}}  # placeholder
txt2seq={}
ctx_seq_text={}
for ln in open(BASE/"analysis/contexts/factconsolidation_6k_context.txt"):
    m=re.match(r"^\s*(\d+)\.\s+(.*)$", ln.strip())
    if m: ctx_seq_text[int(m.group(1))]=m.group(2).rstrip("."); txt2seq[norm(m.group(2))]=int(m.group(1))
op=collections.defaultdict(set)
for ln in [json.loads(l) for l in open(LA)]:
    for r in ln["vector_results"]["results"]:
        ev,s=r["event"],txt2seq.get(norm(r.get("memory","")))
        if ev=="ADD" and s is not None: op[s].add("ADD")
        elif ev=="UPDATE":
            if s is not None: op[s].add("win")
            ps=txt2seq.get(norm(r.get("previous_memory","")));
            if ps is not None: op[ps].add("sup")
        elif ev=="DELETE" and s is not None: op[s].add("DEL")
def fate(s):
    o=op.get(s,set())
    return "DELETED" if "DEL" in o else "SUPERSEDED" if "sup" in o else "STORED" if o&{"ADD","win"} else "DROPPED"

gt={q["query_id"]:q for q in json.load(open(GT))}
results={d["qa_pair_id"].split("_no")[-1]:d for d in json.load(open(RESULTS))["data"]}
cond={r["qid"]:r for r in json.load(open(COND))}

def show(qid, show_retr=False):
    q=gt[qid]; res=results.get(str(qid),{})
    gs,os_=q.get("gt_seq"),q.get("old_seq"); hp=q.get("conflict_type")=="has_pair"
    print(f"\n--- qid{qid} [{cond[qid]['outcome']}] error_type={q.get('error_type')} ---")
    print(f"  Q: {q['question']}")
    print(f"  gt(反事實)={q.get('gt_answer')!r}  old(世界)={q.get('old_answer')!r}")
    print(f"  model output={res.get('output')!r}  parsed={res.get('parsed_output')!r}  answer(GT list)={res.get('answer')}  exact_match={res.get('exact_match')}")
    if hp:
        rl_w=role.get(gs,'?'); sc='SAME-chunk' if samechunk.get(gs) else 'cross-chunk'
        print(f"  ingestion: winner seq{gs}({rl_w},{sc}) fate={fate(gs)} | loser seq{os_} fate={fate(os_)}")
    else:
        print(f"  ingestion: no_pair single fact seq{gs} fate={fate(gs)}")
    print(f"  retrieval: gt_retrieved={cond[qid]['gt_retrieved']} old_leaked={cond[qid]['old_leaked']}")
    if show_retr:
        rj=json.load(open(RR/f"query_{qid}_context_0.json"))
        mems=[m["memory"] for m in rj["retrieved_memories"]]
        gtt=norm(q.get("gt_fact_text")); oldt=norm(q.get("old_fact_text"))
        for i,m in enumerate(mems):
            tag = "  <-- GT(新)" if norm(m)==gtt else ("  <-- OLD(世界)" if norm(m)==oldt else "")
            if tag: print(f"    retrieved[{i}]: {m!r}{tag}")

print("="*70); print("EM 計分假象 (qid1/89/97)"); print("="*70)
for q in [1,89,97]: show(q)
print("\n"+"="*70); print("inference H2 (qid66)"); print("="*70)
show(66, show_retr=True)
print("\n"+"="*70); print("DROPPED (qid7/34/42/52) — role×fate 對應"); print("="*70)
for q in [7,34,42,52]: show(q)
print("\n"+"="*70); print("STALE (新舊都在卻答對) — 印 retrieval 看為何選新版"); print("="*70)
stale=[qid for qid,r in cond.items() if r["outcome"].startswith("STALE")]
for q in stale: show(q, show_retr=True)

print("\n"+"="*70); print("CORRECT 93 組成: has_pair(衝突解決成功) vs no_pair(單一事實,與衝突無關)"); print("="*70)
corr=[qid for qid,r in cond.items() if r["outcome"]=="CORRECT"]
hp=sum(1 for q in corr if gt[q].get("conflict_type")=="has_pair")
print(f"  CORRECT total {len(corr)} = has_pair {hp}(衝突成功解決) + no_pair {len(corr)-hp}(單一事實)")
