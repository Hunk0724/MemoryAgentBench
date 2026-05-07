"""
analyze_lca_mquake.py
=====================
LCA (Long-Context Agent) × Fact-Consolidation MQuAKE analysis.

Takes one LCA results JSON + the corresponding fact-pool context txt,
maps each question back to a MQuAKE case via (question_text, new_answer)
and outputs:
  - per-question classification: has_pair / no_conflict_pair + error_type
  - summary table: accuracy by conflict_type, error_type distribution
For MH, a per-hop retrieval analysis is skipped (LCA has no retrieval);
only top-level answer correctness + conflict-pair presence is reported.

Usage:
    python analyze_lca_mquake.py \
        --results   outputs/<model>/Conflict_Resolution/factconsolidation_<sh|mh>_<size>_...json \
        --context   analysis/contexts/factconsolidation_<size>_context.txt \
        --mode      {sh,mh}
        [--out-prefix PATH]
"""

import argparse, json, re, os
from pathlib import Path
from collections import Counter

MQUAKE_PATH = Path("/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")


def load_mquake_index():
    mquake = json.load(open(MQUAKE_PATH, encoding="utf-8"))
    sh_hop_index, mh_q_index = {}, {}
    for c in mquake:
        for i, hop in enumerate(c.get("new_single_hops", [])):
            key = (hop["question"].strip().lower(), hop["answer"].strip().lower())
            sh_hop_index.setdefault(key, (c, i))
        top_a = c.get("new_answer", "").strip().lower()
        aliases = [top_a] + [a.strip().lower() for a in c.get("new_answer_alias", []) if a]
        for q in c.get("questions", []):
            for a in aliases:
                mh_q_index.setdefault((q.strip().lower(), a), c)
    return mquake, sh_hop_index, mh_q_index


def parse_context(ctx_text):
    lines = [(int(m.group(1)), m.group(2).strip())
             for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", ctx_text, re.MULTILINE)]
    by_lower = {t.lower(): n for n, t in lines}
    return lines, by_lower


def extract_question(query: str) -> str:
    m = re.search(r"Now Answer the Question:\s*(.+?)(?:\nAnswer:|$)", query, re.DOTALL)
    if not m:
        return ""
    return re.sub(r"Based on the provided Knowledge Pool,\s*", "",
                  m.group(1).strip(), flags=re.IGNORECASE).strip()


def find_hop_gt(hop, ctx_by_lower):
    fact = hop["cloze"] + " " + hop["answer"] + "."
    return ctx_by_lower.get(fact.lower()), fact


def find_hop_old(hop, rws, hop_idx, ctx_lines, ctx_by_lower):
    gt_n, _ = find_hop_gt(hop, ctx_by_lower)
    if hop_idx < len(rws):
        old_ans = rws[hop_idx].get("target_true", {}).get("str", "")
        if old_ans:
            old_fact = hop["cloze"] + " " + old_ans + "."
            n = ctx_by_lower.get(old_fact.lower())
            if n is not None:
                return n, old_fact, old_ans, "direct"
    cloze_l = hop["cloze"].lower().strip()
    candidates = [(n, t) for n, t in ctx_lines
                  if t.lower().startswith(cloze_l)
                  and t.lower() != (hop["cloze"] + " " + hop["answer"] + ".").lower()]
    if candidates:
        below = [(n, t) for n, t in candidates if gt_n is None or n < gt_n]
        pick = max(below, key=lambda x: x[0]) if below else min(candidates, key=lambda x: x[0])
        inferred = pick[1][len(hop["cloze"]) + 1:].rstrip(".")
        return pick[0], pick[1], inferred, "cloze"
    return None, None, "", "none"


def classify_error(parsed, gt_answer, old_answer, ctx_lines):
    p = (parsed or "").strip().lower()
    if not p:
        return "empty"
    if p == gt_answer.strip().lower():
        return "correct"
    if old_answer and p == old_answer.strip().lower():
        return "older_fact"
    for _, fact in ctx_lines:
        if p in fact.lower():
            return "entity_confused"
    return "hallucination"


# ── SH ─────────────────────────────────────────────────────────────────────
def analyze_sh(results, ctx_lines, ctx_by_lower, sh_hop_index):
    entries, no_match = [], 0
    for row in results["data"]:
        qtext = extract_question(row["query"])
        gt_answers = row.get("answer", []) or [""]
        matched = None
        for a in gt_answers:
            matched = sh_hop_index.get((qtext.lower(), a.strip().lower()))
            if matched:
                break
        if not matched:
            no_match += 1
            continue
        case, hop_idx = matched
        hop = case["new_single_hops"][hop_idx]
        rws = case.get("requested_rewrite", [])
        gt_seq, gt_fact = find_hop_gt(hop, ctx_by_lower)
        old_seq, old_fact, old_ans, _ = find_hop_old(hop, rws, hop_idx, ctx_lines, ctx_by_lower)
        err = classify_error(row.get("parsed_output", ""), hop["answer"], old_ans, ctx_lines)
        entries.append({
            "qa_pair_id": row.get("qa_pair_id"),
            "case_id":    case["case_id"],
            "conflict_type": "has_pair" if old_seq is not None else "no_conflict_pair",
            "error_type":  err,
            "gt_seq":  gt_seq, "old_seq": old_seq,
            "update_gap": (gt_seq - old_seq) if (gt_seq is not None and old_seq is not None) else None,
            "parsed_output": row.get("parsed_output"),
            "gt_answer": hop["answer"], "old_answer": old_ans,
            "exact_match": bool(row.get("exact_match")),
        })
    return entries, no_match


# ── MH ─────────────────────────────────────────────────────────────────────
def analyze_mh(results, ctx_lines, ctx_by_lower, mh_q_index):
    entries, no_match = [], 0
    for row in results["data"]:
        qtext = extract_question(row["query"])
        gt_answers = row.get("answer", []) or [""]
        case = None
        for a in gt_answers:
            case = mh_q_index.get((qtext.lower(), a.strip().lower()))
            if case:
                break
        if not case:
            no_match += 1
            continue
        rws = case.get("requested_rewrite", [])
        hops = case.get("new_single_hops", [])
        # per-hop conflict inspection
        hop_infos = []
        for i, hop in enumerate(hops):
            gt_seq, _ = find_hop_gt(hop, ctx_by_lower)
            old_seq, _, _, _ = find_hop_old(hop, rws, i, ctx_lines, ctx_by_lower)
            hop_infos.append({"gt_seq": gt_seq, "old_seq": old_seq,
                              "conflict_type": "has_pair" if old_seq is not None else "no_conflict_pair"})
        any_pair = any(h["conflict_type"] == "has_pair" for h in hop_infos)
        all_pair = all(h["conflict_type"] == "has_pair" for h in hop_infos)
        # final answer error type: compare parsed_output vs top-level new_answer + aliases
        top_new = case.get("new_answer", "")
        top_old = case.get("answer", "")  # MQuAKE's original answer = old
        err = classify_error(row.get("parsed_output", ""), top_new, top_old, ctx_lines)
        entries.append({
            "qa_pair_id": row.get("qa_pair_id"),
            "case_id":    case["case_id"],
            "n_hops":     len(hops),
            "conflict_type_any":  "has_pair" if any_pair else "no_conflict_pair",
            "conflict_type_all":  "has_pair" if all_pair else "partial",
            "hop_infos":  hop_infos,
            "error_type": err,
            "parsed_output": row.get("parsed_output"),
            "gt_answer": top_new, "old_answer": top_old,
            "exact_match": bool(row.get("exact_match")),
        })
    return entries, no_match


def summarize(entries, mode, results_meta):
    model = results_meta["agent_config"]["model"]
    sub   = results_meta["dataset_config"]["sub_dataset"]
    n = len(entries)
    correct = sum(e["exact_match"] for e in entries)
    lines = [
        f"=== {model} × {sub} ({mode.upper()}) ===",
        f"matched={n}   correct={correct}   EM={correct / n:.1%}" if n else "(no matches)",
    ]
    if mode == "sh":
        conf = Counter(e["conflict_type"] for e in entries)
    else:
        conf = Counter(e["conflict_type_any"] for e in entries)
    lines.append("")
    lines.append("Conflict-type breakdown:")
    for k, v in sorted(conf.items()):
        sub_correct = sum(1 for e in entries
                          if (e.get("conflict_type", e.get("conflict_type_any")) == k and e["exact_match"]))
        lines.append(f"  {k:<20s}: n={v:3d}  correct={sub_correct:3d}  acc={sub_correct / v:.1%}" if v else f"  {k}: 0")
    lines.append("")
    lines.append("Error type distribution:")
    err = Counter(e["error_type"] for e in entries)
    for k, v in err.most_common():
        lines.append(f"  {k:<20s}: {v:3d} ({v / n:.1%})")
    if mode == "mh":
        lines.append("")
        lines.append("Hop-count distribution (acc per hop-count):")
        by_hops = {}
        for e in entries:
            by_hops.setdefault(e["n_hops"], []).append(e["exact_match"])
        for h, vs in sorted(by_hops.items()):
            acc = sum(vs) / len(vs)
            lines.append(f"  {h}-hop: n={len(vs):3d}  acc={acc:.1%}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--mode", choices=["sh", "mh"], required=True)
    ap.add_argument("--out-prefix", default=None)
    args = ap.parse_args()

    results = json.load(open(args.results, encoding="utf-8"))
    ctx_text = open(args.context, encoding="utf-8").read()
    ctx_lines, ctx_by_lower = parse_context(ctx_text)
    _, sh_idx, mh_idx = load_mquake_index()

    if args.mode == "sh":
        entries, no_match = analyze_sh(results, ctx_lines, ctx_by_lower, sh_idx)
    else:
        entries, no_match = analyze_mh(results, ctx_lines, ctx_by_lower, mh_idx)

    summary = summarize(entries, args.mode, results)
    summary += f"\nNo MQuAKE match: {no_match}"
    print(summary)

    if args.out_prefix:
        out_json = Path(args.out_prefix + "_mquake.json")
        out_txt  = Path(args.out_prefix + "_mquake.txt")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        json.dump(entries, open(out_json, "w"), ensure_ascii=False, indent=2)
        open(out_txt, "w").write(summary)
        print(f"\nwrote {out_json}\nwrote {out_txt}")


if __name__ == "__main__":
    main()
