"""
Build the CORRECT per-query SH GT for a SPECIFIC run, by aligning the RUN'S OWN
queries (which differ per context length!) to MQuAKE-CF, then locating gt/old
facts in THAT run's context. Replicates analyze_sh_512_mquake.py alignment.

Why: FC-SH queries are length-specific (6k qid0 answer=pesäpallo, 32k qid0=
basketball). Remapping 6k sh_512 GT onto a 32k run mis-aligns every query.
"""
import argparse, json, re, glob
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--results", required=True)   # the run's results json (has query+answer)
ap.add_argument("--ctx", required=True)        # that run's context
ap.add_argument("--mquake", default="/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")
ap.add_argument("--out", required=True)
args = ap.parse_args()

ctx_lines = [(int(m.group(1)), m.group(2).strip())
             for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", Path(args.ctx).read_text(), re.MULTILINE)]
ctx_by_lower = {t.lower(): n for n, t in ctx_lines}

mquake = json.load(open(args.mquake))
sh_hop_index = {}
for c in mquake:
    for i, hop in enumerate(c.get("new_single_hops", [])):
        key = (hop["question"].strip().lower(), hop["answer"].strip().lower())
        sh_hop_index.setdefault(key, (c, i))

def extract_question(query):
    m = re.search(r"Now Answer the Question:\s*(.+?)(?:\nAnswer:|$)", query, re.DOTALL)
    if not m: return ""
    return re.sub(r"Based on the provided Knowledge Pool,\s*", "", m.group(1).strip(), flags=re.IGNORECASE).strip()

def find_gt(case, hi):
    hop = case["new_single_hops"][hi]
    fact = hop["cloze"] + " " + hop["answer"] + "."
    return ctx_by_lower.get(fact.lower()), fact

def find_old(case, hi):
    hop = case["new_single_hops"][hi]; rws = case.get("requested_rewrite", [])
    cl = hop["cloze"].lower().strip()
    if hi < len(rws):
        oa = rws[hi].get("target_true", {}).get("str", "")
        if oa:
            of = hop["cloze"] + " " + oa + "."
            n = ctx_by_lower.get(of.lower())
            if n is not None: return n, of, oa
    gt_n, _ = find_gt(case, hi)
    cands = [(n, t) for n, t in ctx_lines
             if t.lower().startswith(cl) and t.lower() != (hop["cloze"] + " " + hop["answer"] + ".").lower()]
    if cands:
        below = [(n, t) for n, t in cands if gt_n is None or n < gt_n]
        bn, bt = (max(below, key=lambda x: x[0]) if below else min(cands, key=lambda x: x[0]))
        return bn, bt, bt[len(hop["cloze"]) + 1:].rstrip(".")
    return None, None, None

res = json.load(open(args.results))["data"]
out, n_match, n_pair = [], 0, 0
for d in res:
    qid = int(d["qa_pair_id"].split("_no")[-1])
    q = extract_question(d["query"])
    ans = d["answer"][0] if isinstance(d.get("answer"), list) and d["answer"] else ""
    key = (q.lower(), ans.lower())
    rec = {"query_id": qid, "question": q, "gt_answer": ans, "conflict_type": "no_pair"}
    if key in sh_hop_index:
        n_match += 1
        case, hi = sh_hop_index[key]
        gs, gf = find_gt(case, hi)
        rec["gt_seq"], rec["gt_fact_text"] = gs, gf
        os_, of, oa = find_old(case, hi)
        if os_ is not None:
            n_pair += 1
            rec.update({"conflict_type": "has_pair", "old_seq": os_, "old_fact_text": of, "old_answer": oa})
    out.append(rec)

json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
print(f"queries={len(out)} | matched MQuAKE={n_match} | has_pair={n_pair} | written {args.out}")
