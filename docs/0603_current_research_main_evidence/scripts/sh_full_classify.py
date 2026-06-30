"""
Comprehensive per-query classification for FC-SH (matches doc 02 §C quality).
For each of the 100 SH queries, joins:
  write-time : winner/old fate (Layer A), same-chunk?, A-WT bucket (resolved/H1/H2/same-chunk)
  query-time : gt_retrieved, old_leaked, EM, model output
  -> a single mutually-exclusive class:
     single-fact | clean-resolved | FRAGILE(subtype) | FAIL(structure) | benchmark-defect
"""
import argparse, json, re, glob, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line

ap = argparse.ArgumentParser()
ap.add_argument("--ctx", default="analysis/contexts/factconsolidation_32k_context.txt")
ap.add_argument("--gt", default="analysis/results/sh_32k_RUN_gt.json")
ap.add_argument("--logdir", default="docs/0603_current_research_main_evidence/logs/sh_32k_l2")
ap.add_argument("--layera", default="outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware_l2_32k/k_100/factconsolidation_sh_32k/chunksize_512/ingestion_context_0.jsonl")
ap.add_argument("--rr", default="outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware_l2_32k/k_100/factconsolidation_sh_32k/chunksize_512")
ap.add_argument("--results", default="outputs/gemini-3.1-flash-lite-mem0-chunk512-temp0-factaware-l2-32k/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size10_shots0_max_samplesunknown_k100_chunk512_results.json")
ap.add_argument("--benchmark-defect", default="8,9")
ap.add_argument("--out", default="docs/0603_current_research_main_evidence/logs/sh_32k_full_classify.json")
args = ap.parse_args()
norm = lambda s: s.strip().rstrip(".").lower() if s else ""
defect = set(int(x) for x in args.benchmark_defect.split(",") if x.strip())

# seq -> chunk + text
chunks = chunk_facts_by_line(Path(args.ctx).read_text(), chunk_size=512)
seq_chunk, seq_text = {}, {}
for cid, ch in enumerate(chunks):
    for ln in ch.split("\n"):
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", ln.strip())
        if m: seq_chunk[int(m.group(1))] = cid; seq_text[int(m.group(1))] = m.group(2).strip().rstrip(".")
txt2seq = {norm(t): s for s, t in seq_text.items()}

# Layer A: per-seq op set; also winner->what-it-superseded
layerA = [json.loads(l) for l in Path(args.layera).read_text().splitlines() if l.strip()]
op = defaultdict(set)
superseded_by = {}   # norm(prev) -> norm(new memory)
for ln in layerA:
    for r in ln["vector_results"]["results"]:
        ev = r["event"]; s = txt2seq.get(norm(r.get("memory", "")))
        if ev == "ADD" and s is not None: op[s].add("ADD")
        elif ev == "UPDATE":
            if s is not None: op[s].add("win")
            ps = txt2seq.get(norm(r.get("previous_memory", "")))
            if ps is not None: op[ps].add("sup")
            superseded_by[norm(r.get("previous_memory",""))] = r.get("memory","")
        elif ev == "DELETE" and s is not None: op[s].add("DEL")
def fate(s):
    o = op.get(s, set())
    if "DEL" in o: return "DELETED"
    if "sup" in o: return "SUPERSEDED"
    if o & {"ADD", "win"}: return "STORED"
    return "DROPPED"

results = {d["qa_pair_id"].split("_no")[-1]: d for d in json.load(open(args.results))["data"]}
gt = json.load(open(args.gt))

rows = []
for q in gt:
    qid = q["query_id"]; gs = q.get("gt_seq"); os_ = q.get("old_seq")
    has_pair = q.get("conflict_type") == "has_pair"
    wf = fate(gs) if gs is not None else None
    of = fate(os_) if (has_pair and os_ is not None) else None
    same_chunk = has_pair and os_ is not None and seq_chunk.get(gs) == seq_chunk.get(os_)
    # retrieval
    rj = json.load(open(f"{args.rr}/query_{qid}_context_0.json"))
    retr = {norm(m["memory"]) for m in rj.get("retrieved_memories", [])}
    gt_in = norm(q.get("gt_fact_text")) in retr
    old_in = (norm(q.get("old_fact_text")) in retr) if (has_pair and q.get("old_fact_text")) else False
    d = results.get(str(qid), {}); em = bool(d.get("exact_match")); out = d.get("output", "")

    # who superseded the gt winner (for A4 detection)?
    sup_new = superseded_by.get(norm(q.get("gt_fact_text"))) if wf in ("SUPERSEDED","DELETED") else None

    # classification
    if qid in defect:
        cls, struct = "BENCHMARK-DEFECT", "answer-key vs largest-serial rule"
    elif not has_pair:
        cls, struct = ("single-correct" if em else "single-FAIL"), ("" if em else "inference/artifact")
    else:
        if em:
            if of == "STORED" or old_in:
                cls, struct = "FRAGILE-STALE", "both versions present, inference picked winner"
            elif same_chunk:
                cls, struct = "FRAGILE-SAMECHUNK", "same-chunk arbitrary, kept winner by luck"
            else:
                cls, struct = "clean-resolved", ""
        else:
            if wf in ("SUPERSEDED","DELETED"):
                cls, struct = "FAIL-A4", f"winner {wf} by: {sup_new!r}"
            elif wf == "DROPPED":
                cls, struct = "FAIL-DROPPED", "winner never stored"
            elif not gt_in:
                cls, struct = "FAIL-RETRIEVAL", "winner stored but not retrieved"
            else:
                cls, struct = "FAIL-INFERENCE", "winner retrieved, wrong/empty output"
    rows.append({"qid": qid, "has_pair": has_pair, "same_chunk": same_chunk,
                 "winner_fate": wf, "old_fate": of, "gt_retrieved": gt_in, "old_leaked": old_in,
                 "em": em, "output": out, "class": cls, "struct": struct,
                 "gt_answer": q.get("gt_answer"), "superseded_by": sup_new})

# report
print(f"=== FC-SH 32k full classification (n={len(rows)}, EM={sum(r['em'] for r in rows)}) ===")
cc = Counter(r["class"] for r in rows)
for k in ["single-correct","clean-resolved","FRAGILE-STALE","FRAGILE-SAMECHUNK",
          "BENCHMARK-DEFECT","FAIL-A4","FAIL-DROPPED","FAIL-RETRIEVAL","FAIL-INFERENCE","single-FAIL"]:
    if cc.get(k): print(f"  {k:18s}: {cc[k]}")
print("\n--- all non-clean (fragile + fail + defect) ---")
for r in rows:
    if r["class"] in ("clean-resolved","single-correct"): continue
    print(f"  qid{r['qid']:<3} [{r['class']}] em={r['em']} sc={r['same_chunk']} "
          f"wf={r['winner_fate']} of={r['old_fate']} gtret={r['gt_retrieved']} leak={r['old_leaked']} "
          f"ans={r['gt_answer']!r} out={r['output']!r} :: {r['struct']}")
json.dump(rows, open(args.out, "w"), ensure_ascii=False, indent=1)
print(f"\nwritten: {args.out}")
