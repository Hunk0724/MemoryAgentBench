"""
Task A2 - Per-hop diagnosis from Task A1 outputs.

For each FC-MH question, compare LLM's intermediate per-hop predictions against
MQuAKE per-hop ground truth (and old-fact answer) to figure out:

  Q1.  When the question is wrong, is the FIRST error hop a has_conflict hop
       or a no_conflict hop?
  Q2.  At a has_conflict hop, does the LLM tend to pick the OLD answer
       (older_fact) or something else?
  Q3.  How does this break down by num_hops and n_conflict_hops?

This directly answers the framing question: "Is MH failure mostly conflict
resolution failure that propagates, or does the chain itself break on clean
hops too?"

Reads:
  analysis/results/diagnostic/a1_modified_baseline_mh.json   <- LLM intermediates
  analysis/results/mh_512_mquake_analysis.json               <- per-hop GT/old/conflict_type

Writes:
  analysis/results/diagnostic/a2_per_hop_diagnosis.json
  analysis/results/diagnostic/a2_per_hop_summary.txt
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
A1_OUT = BASE / "analysis/results/diagnostic/a1_modified_baseline_mh.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
OUT_JSON = BASE / "analysis/results/diagnostic/a2_per_hop_diagnosis.json"
OUT_TXT = BASE / "analysis/results/diagnostic/a2_per_hop_summary.txt"


def normalize(s):
    if s is None:
        return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def fuzzy_match(pred, gold):
    """Substring match (matches HippoRAG eval semantics)."""
    if pred is None or gold is None:
        return False
    pn, gn = normalize(pred), normalize(gold)
    if not pn or not gn:
        return False
    return pn == gn or gn in pn or pn in gn


def classify_hop(pred, gt, old, conflict_type):
    """Return one of: correct / older_fact / other / missing."""
    if pred is None or pred == "":
        return "missing"
    if fuzzy_match(pred, gt):
        return "correct"
    if conflict_type == "has_pair" and old and fuzzy_match(pred, old):
        return "older_fact"
    return "other"


def analyze():
    a1 = {r["query_id"]: r for r in json.load(open(A1_OUT))}
    gt = {r["query_id"]: r for r in json.load(open(MH_GT))}

    common = sorted(set(a1.keys()) & set(gt.keys()))
    print(f"Joined {len(common)} questions (a1={len(a1)}, gt={len(gt)})")

    rows = []
    for qid in common:
        ar, gr = a1[qid], gt[qid]
        intermediates = ar.get("intermediate_answers") or []
        hops = gr.get("hops", [])
        num_hops = gr.get("num_hops", len(hops))
        n_conflict = sum(1 for h in hops if h.get("conflict_type") == "has_pair")

        # Align LLM intermediates with hops (truncate or pad)
        per_hop = []
        first_error_idx = None
        for k, h in enumerate(hops):
            pred = intermediates[k] if k < len(intermediates) else None
            cls = classify_hop(
                pred,
                h.get("gt_answer"),
                h.get("old_answer"),
                h.get("conflict_type"),
            )
            per_hop.append({
                "hop_idx": k,
                "conflict_type": h.get("conflict_type"),
                "gt_answer": h.get("gt_answer"),
                "old_answer": h.get("old_answer"),
                "pred": pred,
                "class": cls,
            })
            if cls != "correct" and first_error_idx is None:
                first_error_idx = k

        rows.append({
            "query_id": qid,
            "num_hops": num_hops,
            "n_conflict": n_conflict,
            "exact_match": ar.get("exact_match"),
            "final_pred": ar.get("pred_answer"),
            "gt_answer": ar.get("gt_answer"),
            "intermediates": intermediates,
            "n_intermediates": len(intermediates),
            "per_hop": per_hop,
            "first_error_hop": first_error_idx,
            "first_error_conflict_type": (
                per_hop[first_error_idx]["conflict_type"] if first_error_idx is not None else None
            ),
            "first_error_class": (
                per_hop[first_error_idx]["class"] if first_error_idx is not None else None
            ),
        })

    return rows


def summarize(rows):
    n = len(rows)
    n_correct = sum(1 for r in rows if r["exact_match"])
    n_wrong = n - n_correct

    # Per-hop pred-class distribution by conflict_type
    hop_class_by_conflict = defaultdict(Counter)
    for r in rows:
        for h in r["per_hop"]:
            hop_class_by_conflict[h["conflict_type"]][h["class"]] += 1

    # First error hop distribution among wrong questions
    fe_by_conflict = Counter()
    fe_by_class = Counter()
    fe_by_position = Counter()
    fe_by_num_hops = defaultdict(Counter)  # num_hops -> {has_pair: x, no_conflict_pair: y}
    for r in rows:
        if r["exact_match"]:
            continue
        ct = r.get("first_error_conflict_type")
        cls = r.get("first_error_class")
        pos = r.get("first_error_hop")
        if ct is not None:
            fe_by_conflict[ct] += 1
            fe_by_class[cls] += 1
            fe_by_num_hops[r["num_hops"]][ct] += 1
        if pos is not None:
            fe_by_position[pos] += 1

    # n_intermediates alignment check
    align = Counter()
    for r in rows:
        diff = r["n_intermediates"] - r["num_hops"]
        if diff == 0:
            align["match"] += 1
        elif diff > 0:
            align["over"] += 1
        else:
            align["under"] += 1

    # Per-group breakdown: (num_hops, n_conflict)
    grp = defaultdict(lambda: {"n": 0, "correct": 0, "fe_has": 0, "fe_no": 0})
    for r in rows:
        key = (r["num_hops"], r["n_conflict"])
        g = grp[key]
        g["n"] += 1
        if r["exact_match"]:
            g["correct"] += 1
        else:
            ct = r.get("first_error_conflict_type")
            if ct == "has_pair":
                g["fe_has"] += 1
            elif ct == "no_conflict_pair":
                g["fe_no"] += 1

    lines = []
    add = lines.append
    add("=" * 70)
    add(f"Task A2 — Per-hop diagnosis for FC-MH (modified-prompt baseline)")
    add("=" * 70)
    add(f"Total questions: {n}  |  EM correct: {n_correct} ({n_correct/n*100:.1f}%)  |  wrong: {n_wrong}")
    add("")
    add("[1] Intermediate-answer alignment vs num_hops")
    for k in ("match", "over", "under"):
        add(f"  {k:>6}: {align[k]}")
    add("")
    add("[2] Per-hop prediction class distribution by conflict_type")
    add(f"  {'conflict_type':<20} {'correct':>8} {'older_fact':>12} {'other':>8} {'missing':>8}")
    for ct, cnt in hop_class_by_conflict.items():
        total_ct = sum(cnt.values())
        add(f"  {str(ct):<20} {cnt['correct']:>4}/{total_ct:<3} {cnt['older_fact']:>4}/{total_ct:<7} {cnt['other']:>4}/{total_ct:<3} {cnt['missing']:>4}/{total_ct:<3}")
    add("")
    add(f"[3] First-error-hop distribution among {n_wrong} WRONG questions")
    add(f"  conflict_type at 1st-error-hop:")
    for ct, c in fe_by_conflict.most_common():
        add(f"    {ct or 'NULL':<22} {c:>3} ({c/max(n_wrong,1)*100:.0f}%)")
    add(f"  pred class at 1st-error-hop:")
    for cls, c in fe_by_class.most_common():
        add(f"    {cls:<22} {c:>3} ({c/max(n_wrong,1)*100:.0f}%)")
    add(f"  hop position of 1st-error:")
    for pos, c in sorted(fe_by_position.items()):
        add(f"    hop {pos}                    {c:>3}")
    add("")
    add("[4] First-error-hop conflict_type by num_hops")
    add(f"  {'num_hops':<10} {'has_pair':>10} {'no_conflict':>12} {'total wrong':>12}")
    for nh in sorted(fe_by_num_hops.keys()):
        cc = fe_by_num_hops[nh]
        tot = sum(cc.values())
        add(f"  {nh:<10} {cc.get('has_pair', 0):>10} {cc.get('no_conflict_pair', 0):>12} {tot:>12}")
    add("")
    add("[5] Per-group (num_hops, n_conflict) summary")
    add(f"  {'group':<22} {'N':>4} {'EM':>6} {'fe_has':>8} {'fe_no':>8}")
    for key in sorted(grp.keys()):
        nh, nc = key
        g = grp[key]
        add(f"  {nh}-hop, {nc}-conflict      {g['n']:>4} {g['correct']:>3}/{g['n']:<2} {g['fe_has']:>8} {g['fe_no']:>8}")
    add("")
    add("[6] Interpretation hints")
    add("  - If [3] has_pair >> no_conflict_pair => MH failure dominated by conflict-hop "
        "errors; conflict resolution is the bottleneck.")
    add("  - If [3] has notable no_conflict_pair share => chain reasoning itself fails on "
        "clean hops in noisy context (chain accumulation error).")
    add("  - [2] older_fact rate at has_pair hops tells us how often LLM picks the OLD "
        "version even with the 'larger serial = newer' rule in prompt.")
    add("=" * 70)

    return "\n".join(lines)


if __name__ == "__main__":
    rows = analyze()
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"per-hop JSON -> {OUT_JSON}")
    txt = summarize(rows)
    OUT_TXT.write_text(txt)
    print(txt)
