"""
Three analyses extending zep mechanism work:

(A) Zep-native failure taxonomy on SH/MH
    Per question, classify the conflict-resolution mechanism state:
    - SUPERSESSION_PERFECT      : Old has invalid_at AND GT does not (in edges)
    - SUPERSESSION_MISFIRED      : GT has invalid_at (reverse) (in edges)
    - NO_EDGE_SIGNAL_BUT_VISIBLE : GT/Old not both in edges, but both in any-scope union
                                   (LLM sees facts via episodes/nodes; no temporal signal)
    - RETRIEVAL_MISSING          : GT or Old missing from any-scope union

    For MH, classify per-hop then aggregate to question-level via worst-case rule:
      ANY_RETRIEVAL_MISSING > ANY_MISFIRED > ALL_PERFECT > anything-else

(B) 4-way contingency on FC-MH 100q: Zep × HippoRAG-v2 × RPT-min × RPT
    Per-question EM array → 16-cell contingency.

(C) SH vs MH mechanism effectiveness comparison (per-task)
    A small table aggregating triggered/un-triggered EM rates.

Output:
  analysis/results/zep/zep_taxonomy_overlap.json
  analysis/results/zep/zep_taxonomy_overlap.txt
"""
import json
from pathlib import Path
from collections import Counter, defaultdict

BASE = Path("/home/yhchiang/MemoryAgentBench")
OUT_DIR = BASE / "analysis/results/zep"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def classify_hop(hop):
    """Apply the Zep-native taxonomy at hop-level (or per question for SH).
    Inputs: dict with gt_in_edges, old_in_edges, gt_marked_invalid,
            old_marked_invalid, gt_in_any, old_in_any
    """
    if not hop["gt_in_any"] or not hop["old_in_any"]:
        return "RETRIEVAL_MISSING"
    if hop["gt_in_edges"] and hop["old_in_edges"]:
        if hop["gt_marked_invalid"]:
            return "SUPERSESSION_MISFIRED"
        if hop["old_marked_invalid"]:
            return "SUPERSESSION_PERFECT"
        return "EDGES_BOTH_NO_SIGNAL"
    return "NO_EDGE_SIGNAL_BUT_VISIBLE"


def aggregate_question_status(hop_statuses):
    """Worst-case aggregate over a question's has_pair hops."""
    if not hop_statuses:
        return "NO_HAS_PAIR"
    s = set(hop_statuses)
    if "RETRIEVAL_MISSING" in s:
        return "ANY_RETRIEVAL_MISSING"
    if "SUPERSESSION_MISFIRED" in s:
        return "ANY_MISFIRED"
    if s == {"SUPERSESSION_PERFECT"}:
        return "ALL_PERFECT"
    if "SUPERSESSION_PERFECT" in s:
        return "PARTIAL_PERFECT"
    return "NO_SIGNAL_BOTH_VISIBLE"


# ─── (A) ZEP-NATIVE FAILURE TAXONOMY ────────────────────────────────────────
def zep_taxonomy_sh():
    sh = json.load(open(OUT_DIR / "sh_zep_mechanism.json"))
    has_pair = [r for r in sh if r["conflict_type"] == "has_pair"]
    by_status = defaultdict(list)
    for r in has_pair:
        # treat the question itself as one "hop"
        status = classify_hop({
            "gt_in_any": r["gt_in_any"],
            "old_in_any": r["old_in_any"],
            "gt_in_edges": r["gt_in_edges"],
            "old_in_edges": r["old_in_edges"],
            "gt_marked_invalid": r["gt_marked_invalid"],
            "old_marked_invalid": r["old_marked_invalid"],
        })
        by_status[status].append(r)
    return by_status, has_pair


def zep_taxonomy_mh():
    mh = json.load(open(OUT_DIR / "mh_zep_mechanism.json"))
    by_q_status = defaultdict(list)
    hop_status_counter = Counter()
    for r in mh:
        hp = [h for h in r["hops"] if h["conflict_type"] == "has_pair"]
        if not hp:
            continue
        hop_statuses = [classify_hop(h) for h in hp]
        for s in hop_statuses:
            hop_status_counter[s] += 1
        agg = aggregate_question_status(hop_statuses)
        by_q_status[agg].append(r)
    return by_q_status, mh, hop_status_counter


def hippo_taxonomy_distribution(task: str):
    """Re-use HippoRAG-style taxonomy from existing analysis files for comparison."""
    if task == "sh":
        ana = json.load(open(BASE / "analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json"))
        # SH already has gt_retrieved/old_retrieved/same_passage in each entry
        out = defaultdict(list)
        for e in ana:
            if e.get("conflict_type") != "has_pair":
                continue
            if not e.get("gt_retrieved") or not e.get("old_retrieved"):
                key = "RETRIEVAL_MISSING"
            elif e.get("gt_passage_rank") == e.get("old_passage_rank"):
                key = "SAME_PASSAGE"
            else:
                key = "DIFFERENT_PASSAGE"
            out[key].append(e)
        return out
    else:
        ana = json.load(open(BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"))
        out = defaultdict(list)
        for e in ana:
            hp = [h for h in e["hops"] if h["conflict_type"] == "has_pair"]
            if not hp:
                continue
            statuses = []
            for h in hp:
                if not h.get("gt_retrieved") or not h.get("old_retrieved"):
                    statuses.append("RETRIEVAL_MISSING")
                elif h.get("same_passage"):
                    statuses.append("SAME_PASSAGE")
                else:
                    statuses.append("DIFFERENT_PASSAGE")
            if "RETRIEVAL_MISSING" in statuses:
                key = "ANY_RETRIEVAL_MISSING"
            elif "SAME_PASSAGE" in statuses:
                key = "ANY_SAME_PASSAGE"
            else:
                key = "ALL_DIFFERENT_PASSAGE"
            out[key].append(e)
        return out


# ─── (B) 4-WAY CONTINGENCY ──────────────────────────────────────────────────
def four_way_contingency_mh():
    """For each MH question, get EM from Zep, HippoRAG, RPT-min, RPT."""
    # Zep MH per-q EM
    zep = {r["query_id"]: r["zep_em"]
           for r in json.load(open(OUT_DIR / "mh_zep_mechanism.json"))}
    # HippoRAG MH per-q EM (from inference results)
    hippo_data = json.load(open(BASE / "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"))
    hippo = {e["query_id"]: bool(e.get("exact_match", False)) for e in hippo_data["data"]}
    # RPT, RPT-min full MH
    rpt = {r["query_id"]: bool(r["exact_match"])
           for r in json.load(open(BASE / "analysis/results/oracle_a_gemini/rpt_full_mh_results.json"))}
    rpt_min = {r["query_id"]: bool(r["exact_match"])
               for r in json.load(open(BASE / "analysis/results/oracle_a_gemini/rpt_min_full_mh_results.json"))}
    # PAT for completeness
    pat = {r["query_id"]: bool(r["exact_match"])
           for r in json.load(open(BASE / "analysis/results/oracle_a_gemini/pat_full_mh_results.json"))}

    qids = sorted(set(zep) & set(hippo) & set(rpt) & set(rpt_min) & set(pat))
    rows = []
    for qid in qids:
        rows.append({
            "query_id": qid,
            "zep": zep[qid],
            "hippo": hippo[qid],
            "pat": pat[qid],
            "rpt_min": rpt_min[qid],
            "rpt": rpt[qid],
        })
    return rows


# ─── (C) SH vs MH MECHANISM EFFECTIVENESS ───────────────────────────────────
def sh_vs_mh_mechanism():
    sh = json.load(open(OUT_DIR / "sh_zep_mechanism.json"))
    mh = json.load(open(OUT_DIR / "mh_zep_mechanism.json"))

    def stats(records, has_pair_filter=lambda r: True):
        # records: list of dicts with 'zep_em' and either question-level or hop-level supersession state
        n = len(records)
        em = sum(1 for r in records if r["zep_em"])
        return n, em

    # SH: each question = one hop pair (or no pair)
    sh_hp = [r for r in sh if r["conflict_type"] == "has_pair"]
    sh_perfect = [r for r in sh_hp
                  if r["gt_in_edges"] and r["old_in_edges"]
                  and r["old_marked_invalid"] and not r["gt_marked_invalid"]]
    sh_misfired = [r for r in sh_hp
                   if r["gt_in_edges"] and r["old_in_edges"] and r["gt_marked_invalid"]]
    sh_no_signal_both = [r for r in sh_hp
                         if r["gt_in_any"] and r["old_in_any"]
                         and not (r["gt_in_edges"] and r["old_in_edges"]
                                  and (r["old_marked_invalid"] or r["gt_marked_invalid"]))]
    sh_retrieval_missing = [r for r in sh_hp
                            if not (r["gt_in_any"] and r["old_in_any"])]

    # MH at question-level (using aggregate)
    by_q_status, _, _ = zep_taxonomy_mh()
    mh_perfect = by_q_status.get("ALL_PERFECT", [])
    mh_misfired = by_q_status.get("ANY_MISFIRED", [])
    mh_partial = by_q_status.get("PARTIAL_PERFECT", [])
    mh_no_signal_both = by_q_status.get("NO_SIGNAL_BOTH_VISIBLE", [])
    mh_retrieval_missing = by_q_status.get("ANY_RETRIEVAL_MISSING", [])

    def fmt(records):
        n = len(records)
        em = sum(1 for r in records if r["zep_em"])
        return f"{em}/{n} = {em/n*100:.1f}%" if n else "0/0 = -"

    return {
        "sh_perfect": fmt(sh_perfect),
        "sh_misfired": fmt(sh_misfired),
        "sh_no_signal_both": fmt(sh_no_signal_both),
        "sh_retrieval_missing": fmt(sh_retrieval_missing),
        "sh_perfect_n": len(sh_perfect),
        "sh_misfired_n": len(sh_misfired),
        "sh_no_signal_both_n": len(sh_no_signal_both),
        "sh_retrieval_missing_n": len(sh_retrieval_missing),
        "mh_perfect": fmt(mh_perfect),
        "mh_misfired": fmt(mh_misfired),
        "mh_partial": fmt(mh_partial),
        "mh_no_signal_both": fmt(mh_no_signal_both),
        "mh_retrieval_missing": fmt(mh_retrieval_missing),
        "mh_perfect_n": len(mh_perfect),
        "mh_misfired_n": len(mh_misfired),
        "mh_partial_n": len(mh_partial),
        "mh_no_signal_both_n": len(mh_no_signal_both),
        "mh_retrieval_missing_n": len(mh_retrieval_missing),
    }


# ─── Format & save ──────────────────────────────────────────────────────────
def main():
    lines = []
    lines.append("=" * 70)
    lines.append("(A) Zep-native failure taxonomy")
    lines.append("=" * 70)

    # SH
    sh_by_status, sh_hp = zep_taxonomy_sh()
    lines.append(f"\nSH has_pair (n={len(sh_hp)}):")
    lines.append(f"  {'status':<32} {'n':>3} {'EM':>10}")
    for status in ["SUPERSESSION_PERFECT", "SUPERSESSION_MISFIRED",
                   "EDGES_BOTH_NO_SIGNAL", "NO_EDGE_SIGNAL_BUT_VISIBLE",
                   "RETRIEVAL_MISSING"]:
        rs = sh_by_status.get(status, [])
        n = len(rs)
        em = sum(1 for r in rs if r["zep_em"])
        em_str = f"{em}/{n} = {em/n*100:.0f}%" if n else "—"
        lines.append(f"  {status:<32} {n:>3} {em_str:>10}")

    # HippoRAG SH for comparison
    hippo_sh = hippo_taxonomy_distribution("sh")
    hippo_sh_data = json.load(open(BASE / "analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json"))
    em_map_h_sh = {e["query_id"]: e["exact_match"] for e in hippo_sh_data}
    lines.append(f"\n  HippoRAG-v2 SH has_pair (n={sum(len(v) for v in hippo_sh.values())}):")
    lines.append(f"  {'status':<32} {'n':>3} {'EM':>10}")
    for status in ["DIFFERENT_PASSAGE", "SAME_PASSAGE", "RETRIEVAL_MISSING"]:
        rs = hippo_sh.get(status, [])
        n = len(rs)
        em = sum(1 for r in rs if r.get("exact_match"))
        em_str = f"{em}/{n} = {em/n*100:.0f}%" if n else "—"
        lines.append(f"  {status:<32} {n:>3} {em_str:>10}")

    # MH
    mh_by_status, _, hop_counter = zep_taxonomy_mh()
    total_q = sum(len(v) for v in mh_by_status.values())
    lines.append(f"\nMH (n={total_q}) — Zep question-level taxonomy:")
    lines.append(f"  {'status':<32} {'n':>3} {'EM':>10}")
    for status in ["ALL_PERFECT", "PARTIAL_PERFECT", "NO_SIGNAL_BOTH_VISIBLE",
                   "ANY_MISFIRED", "ANY_RETRIEVAL_MISSING"]:
        rs = mh_by_status.get(status, [])
        n = len(rs)
        em = sum(1 for r in rs if r["zep_em"])
        em_str = f"{em}/{n} = {em/n*100:.0f}%" if n else "—"
        lines.append(f"  {status:<32} {n:>3} {em_str:>10}")

    lines.append(f"\n  hop-level taxonomy distribution:")
    for k, v in hop_counter.most_common():
        lines.append(f"    {k:<32} {v}")

    # HippoRAG MH for comparison
    hippo_mh = hippo_taxonomy_distribution("mh")
    hippo_mh_data = json.load(open(BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"))
    lines.append(f"\n  HippoRAG-v2 MH (n={sum(len(v) for v in hippo_mh.values())}):")
    lines.append(f"  {'status':<32} {'n':>3} {'EM':>10}")
    for status in ["ALL_DIFFERENT_PASSAGE", "ANY_SAME_PASSAGE", "ANY_RETRIEVAL_MISSING"]:
        rs = hippo_mh.get(status, [])
        n = len(rs)
        em = sum(1 for r in rs if r.get("exact_match"))
        em_str = f"{em}/{n} = {em/n*100:.0f}%" if n else "—"
        lines.append(f"  {status:<32} {n:>3} {em_str:>10}")

    # ── (B) 4-way contingency
    lines.append("\n" + "=" * 70)
    lines.append("(B) 4-way EM contingency on FC-MH 100q")
    lines.append("=" * 70)
    rows = four_way_contingency_mh()

    # 5-method per-question table — count combinations
    method_em = {m: sum(1 for r in rows if r[m]) for m in ["zep", "hippo", "pat", "rpt_min", "rpt"]}
    lines.append(f"\nPer-method EM (n={len(rows)}):")
    for m in ["hippo", "zep", "pat", "rpt_min", "rpt"]:
        lines.append(f"  {m:<10} {method_em[m]:>3}/{len(rows)} = {method_em[m]/len(rows)*100:.0f}%")

    # Pairwise contingencies — focus on Zep vs each
    lines.append("\nPairwise contingency vs Zep:")
    lines.append(f"  {'comparison':<22} {'both':>5} {'zep only':>9} {'other only':>11} {'neither':>8}")
    for other in ["hippo", "pat", "rpt_min", "rpt"]:
        both = sum(1 for r in rows if r["zep"] and r[other])
        zep_only = sum(1 for r in rows if r["zep"] and not r[other])
        other_only = sum(1 for r in rows if not r["zep"] and r[other])
        neither = sum(1 for r in rows if not r["zep"] and not r[other])
        lines.append(f"  zep × {other:<14} {both:>5} {zep_only:>9} {other_only:>11} {neither:>8}")

    # Specifically: where RPT-min wins over Zep
    rpt_min_wins = [r for r in rows if r["rpt_min"] and not r["zep"]]
    rpt_wins = [r for r in rows if r["rpt"] and not r["zep"]]
    zep_wins_over_rpt_min = [r for r in rows if r["zep"] and not r["rpt_min"]]
    zep_wins_over_rpt = [r for r in rows if r["zep"] and not r["rpt"]]
    lines.append(f"\n  RPT-min answers correctly where Zep fails: n={len(rpt_min_wins)}")
    lines.append(f"  RPT     answers correctly where Zep fails: n={len(rpt_wins)}")
    lines.append(f"  Zep     answers correctly where RPT-min fails: n={len(zep_wins_over_rpt_min)}")
    lines.append(f"  Zep     answers correctly where RPT     fails: n={len(zep_wins_over_rpt)}")

    # All-pair-fail (the hard core)
    all_fail = [r for r in rows if not any(r[m] for m in ["zep", "hippo", "rpt_min", "rpt"])]
    lines.append(f"\n  All 4 methods fail: n={len(all_fail)}/100 (the hard core)")

    # All correct
    all_correct = [r for r in rows if all(r[m] for m in ["zep", "hippo", "rpt_min", "rpt"])]
    lines.append(f"  All 4 methods correct: n={len(all_correct)}/100")

    # ── (C) SH vs MH mechanism effectiveness
    lines.append("\n" + "=" * 70)
    lines.append("(C) SH vs MH supersession mechanism effectiveness")
    lines.append("=" * 70)
    eff = sh_vs_mh_mechanism()
    lines.append(f"\nSH (per-question, n=74 has_pair):")
    lines.append(f"  {'status':<28} {'n':>3} {'EM':>10}")
    lines.append(f"  {'PERFECT':<28} {eff['sh_perfect_n']:>3} {eff['sh_perfect']:>10}")
    lines.append(f"  {'MISFIRED':<28} {eff['sh_misfired_n']:>3} {eff['sh_misfired']:>10}")
    lines.append(f"  {'NO_SIGNAL_BUT_VISIBLE':<28} {eff['sh_no_signal_both_n']:>3} {eff['sh_no_signal_both']:>10}")
    lines.append(f"  {'RETRIEVAL_MISSING':<28} {eff['sh_retrieval_missing_n']:>3} {eff['sh_retrieval_missing']:>10}")
    lines.append(f"\nMH (per-question, n=100 — all has_pair):")
    lines.append(f"  {'status':<28} {'n':>3} {'EM':>10}")
    lines.append(f"  {'ALL_PERFECT':<28} {eff['mh_perfect_n']:>3} {eff['mh_perfect']:>10}")
    lines.append(f"  {'PARTIAL_PERFECT':<28} {eff['mh_partial_n']:>3} {eff['mh_partial']:>10}")
    lines.append(f"  {'NO_SIGNAL_BOTH_VISIBLE':<28} {eff['mh_no_signal_both_n']:>3} {eff['mh_no_signal_both']:>10}")
    lines.append(f"  {'ANY_MISFIRED':<28} {eff['mh_misfired_n']:>3} {eff['mh_misfired']:>10}")
    lines.append(f"  {'ANY_RETRIEVAL_MISSING':<28} {eff['mh_retrieval_missing_n']:>3} {eff['mh_retrieval_missing']:>10}")

    out_text = "\n".join(lines)
    (OUT_DIR / "zep_taxonomy_overlap.txt").write_text(out_text, encoding="utf-8")
    print(out_text)

    # Save structured
    structured = {
        "sh_taxonomy": {k: [r["query_id"] for r in v] for k, v in sh_by_status.items()},
        "mh_taxonomy": {k: [r["query_id"] for r in v] for k, v in mh_by_status.items()},
        "four_way_rows": rows,
        "sh_vs_mh_effectiveness": eff,
    }
    json.dump(structured, open(OUT_DIR / "zep_taxonomy_overlap.json", "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
