import json, re, sys
sys.path.insert(0,"/home/yhchiang/MemoryAgentBench")
CTX="analysis/contexts/factconsolidation_32k_context.txt"
GT="analysis/results/sh_32k_RUN_gt.json"

# seq -> text, and (cloze prefix) -> list of (seq, object)
ctx=[(int(m.group(1)),m.group(2).strip().rstrip(".")) for m in
     re.finditer(r"^\s*(\d+)\.\s+(.+)", open(CTX).read(), re.MULTILINE)]
seq_text=dict(ctx)

def cloze_of(fact_text, answer):
    # strip trailing answer to get the (subject+relation) prefix
    ft=fact_text.rstrip(".")
    if ft.lower().endswith(answer.lower()):
        return ft[:len(ft)-len(answer)].strip()
    return None

gt=json.load(open(GT))
# build prefix index: for each context fact, derive prefix by removing last "is/of X" is hard;
# instead, for each query, take its gt cloze and scan context facts that START with that cloze
collisions=[]
for q in gt:
    ans=q["gt_answer"]; gtt=q.get("gt_fact_text"); gs=q.get("gt_seq")
    if not gtt or gs is None: continue
    cl=cloze_of(gtt, ans)
    if not cl: continue
    # all context facts with same cloze prefix
    same=[(s,t) for s,t in ctx if t.lower().startswith(cl.lower())]
    # distinct objects
    objs={}
    for s,t in same:
        o=t[len(cl):].strip(" .")
        objs.setdefault(o,[]).append(s)
    maxseq=max(s for s,_ in same)
    later=[(s,t) for s,t in same if s>gs and t.lower()!=gtt.lower().rstrip(".")]
    if later:
        collisions.append((q["query_id"], gs, ans, maxseq, seq_text[maxseq], len(objs), q["em"] if "em" in q else None))

print(f"=== SH queries whose gt_seq is NOT the largest-serial for its (subj,rel) cloze ===")
print(f"  (under FC 'largest serial wins' rule, these are overridden by a later same-slot fact)")
print(f"  total: {len(collisions)}")
# join EM from conditional
cond={r["qid"]:r for r in json.load(open("docs/0603_current_research_main_evidence/logs/sh_32k_conditional.json"))}
for qid,gs,ans,maxseq,maxtext,nobj,_ in sorted(collisions):
    em=cond[qid]["em"]; oc=cond[qid]["outcome"]
    print(f"  qid{qid}: gt_seq{gs}(ans={ans!r}) <-- larger seq{maxseq}: {maxtext!r}  [n_distinct_obj={nobj}] EM={em} {oc}")
