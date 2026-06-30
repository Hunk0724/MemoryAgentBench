"""
FC-SH query pipeline, CONDITIONED on ingestion outcome of the query's needed
memory. Connects write-time (fact-fate) to query-time (retrieval -> inference).

For each SH query (single hop):
  needed memory = the winner/current fact (gt_seq). If has_pair, the old fact
  (old_seq) should be GONE from the DB after conflict resolution.

  INGESTION OUTCOME (from per-fact fate on this run's Layer A):
    CORRECT    : winner STORED  AND old not-STORED (clean: new in, old gone)
                 (no_pair: gt STORED)
    DROPPED    : winner DROPPED (counterfactual never stored -> DB keeps world fact)
    STALE      : winner STORED  AND old STORED (both versions present)
    BAD-SUP    : winner SUPERSEDED (wrong-direction)

Then within each outcome, the query-time pipeline:
    retrieval : was the winner fact in the top-100? did the old fact leak in?
    inference : exact_match
"""
import argparse
import json
import glob
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line

ap = argparse.ArgumentParser()
ap.add_argument("--ctx", required=True)
ap.add_argument("--pairs", required=True)        # FULLPAIRS gt (all 161 in-store pairs)
ap.add_argument("--layera", required=True)       # SH run Layer A
ap.add_argument("--rr", required=True)           # SH retrieval dir
ap.add_argument("--results", required=True)
ap.add_argument("--gt", required=True)           # sh_512 analysis (per-query hop)
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return s.strip().rstrip(".").lower() if s else ""


# seq -> context text / chunk
seq_text, seq_chunk = {}, {}
for cid, ch in enumerate(chunk_facts_by_line(Path(args.ctx).read_text(), chunk_size=512)):
    for ln in ch.split("\n"):
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", ln.strip())
        if m:
            seq_text[int(m.group(1))] = m.group(2).strip().rstrip(".")
            seq_chunk[int(m.group(1))] = cid
txt2seq = {norm(t): s for s, t in seq_text.items()}

# per-fact fate from Layer A (same logic as audit_deviation)
op = defaultdict(set)
for ln in [json.loads(l) for l in Path(args.layera).read_text().splitlines() if l.strip()]:
    for r in ln["vector_results"]["results"]:
        ev, s = r["event"], txt2seq.get(norm(r.get("memory", "")))
        if ev == "ADD" and s is not None:
            op[s].add("ADD")
        elif ev == "UPDATE":
            if s is not None:
                op[s].add("win")
            ps = txt2seq.get(norm(r.get("previous_memory", "")))
            if ps is not None:
                op[ps].add("sup")
        elif ev == "DELETE" and s is not None:
            op[s].add("DEL")
def fate(s):
    o = op.get(s, set())
    if "DEL" in o: return "DELETED"
    if "sup" in o: return "SUPERSEDED"
    if o & {"ADD", "win"}: return "STORED"
    return "DROPPED"

# query GT + retrieval + results
gt = {q["query_id"]: q for q in json.load(open(args.gt))}
results = {d["qa_pair_id"].split("_no")[-1]: d for d in json.load(open(args.results))["data"]}

rows = []
for f in sorted(glob.glob(f"{args.rr}/query_*_context_0.json"),
                key=lambda p: int(re.search(r"query_(\d+)_", p).group(1))):
    qid = int(re.search(r"query_(\d+)_", f).group(1))
    if qid not in gt: continue
    q = gt[qid]
    gt_seq, old_seq = q.get("gt_seq"), q.get("old_seq")
    has_pair = q.get("conflict_type") == "has_pair"
    wf = fate(gt_seq) if gt_seq is not None else None
    of = fate(old_seq) if (has_pair and old_seq is not None) else None

    # ingestion outcome
    if wf == "DROPPED":
        outcome = "DROPPED(winner gone)"
    elif wf == "SUPERSEDED":
        outcome = "BAD-SUP(winner superseded)"
    elif has_pair and of == "STORED":
        outcome = "STALE(both present)"
    else:
        outcome = "CORRECT"

    # query-time
    rj = json.load(open(f))
    retr = {norm(m["memory"]) for m in rj.get("retrieved_memories", [])}
    gt_in = norm(q.get("gt_fact_text")) in retr if q.get("gt_fact_text") else None
    old_in = (norm(q.get("old_fact_text")) in retr) if (has_pair and q.get("old_fact_text")) else False
    em = bool(results.get(str(qid), {}).get("exact_match"))
    rows.append({"qid": qid, "has_pair": has_pair, "outcome": outcome,
                 "winner_fate": wf, "old_fate": of, "gt_retrieved": gt_in,
                 "old_leaked": old_in, "em": em})

# report
n = len(rows)
print(f"=== FC-SH query pipeline conditioned on ingestion | n={n} | EM={sum(r['em'] for r in rows)/n*100:.0f}% ===")
print(f"has_pair {sum(1 for r in rows if r['has_pair'])} | no_pair {sum(1 for r in rows if not r['has_pair'])}\n")
by_out = defaultdict(list)
for r in rows: by_out[r["outcome"]].append(r)
for out in ["CORRECT", "DROPPED(winner gone)", "STALE(both present)", "BAD-SUP(winner superseded)"]:
    g = by_out.get(out, [])
    if not g: continue
    em = sum(r["em"] for r in g)
    gtin = sum(1 for r in g if r["gt_retrieved"])
    leak = sum(1 for r in g if r["old_leaked"])
    print(f"[{out}] n={len(g)}  EM={em}/{len(g)} | gt_retrieved={gtin}/{len(g)} | old_leaked={leak}/{len(g)}")
    # failures within this outcome
    for r in g:
        if not r["em"]:
            print(f"    qid{r['qid']} WRONG: gt_retrieved={r['gt_retrieved']} old_leaked={r['old_leaked']}"
                  f" winner_fate={r['winner_fate']} old_fate={r['old_fate']}")

json.dump(rows, open(args.out, "w"), ensure_ascii=False, indent=1)
print(f"\nwritten: {args.out}")
