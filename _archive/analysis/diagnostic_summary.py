"""
Unified summary of all diagnostic experiments (A1/A2/B/Sim-OB/Sim-OB-grad/C).

Produces a single text report with:
  - Headline accuracies for every condition
  - Per-(num_hops, n_conflict) breakdowns
  - Sim-OB-grad noise curve: accuracy vs noise_level, faceted by source
  - Cross-tab between A2 (in-chain per-hop) and B (single-hop ablation)
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
DIAG = BASE / "analysis/results/diagnostic"

A1_MH = DIAG / "a1_modified_baseline_mh.json"
A1_SH = DIAG / "a1_modified_baseline_sh.json"
A2 = DIAG / "a2_per_hop_diagnosis.json"
B = DIAG / "b_hop_ablation_results.json"
SIM_OB = DIAG / "sim_ob_chain_only_results.json"
GRAD = DIAG / "sim_ob_grad_results.json"
C = DIAG / "c_no_distractor_conflicts_results.json"
OA2_MH = DIAG / "oracle_a_fact_level_mh_results.json"
OA2_SH = DIAG / "oracle_a_fact_level_sh_results.json"

OUT = DIAG / "diagnostic_summary.txt"


def load(p):
    return json.load(open(p)) if p.exists() else None


def headline_em(rows, em_field="exact_match"):
    n = len(rows)
    ok = sum(1 for r in rows if r.get(em_field))
    return ok, n, (ok / n * 100 if n else 0.0)


def per_group_breakdown(rows, group_keys=("num_hops", "n_conflict"), em_field="exact_match"):
    grp = defaultdict(lambda: [0, 0])
    for r in rows:
        key = tuple(r.get(k) for k in group_keys)
        grp[key][1] += 1
        if r.get(em_field):
            grp[key][0] += 1
    return grp


def main():
    lines = []
    P = lines.append

    P("=" * 78)
    P("FC-MH Multi-hop Diagnostic Summary")
    P("=" * 78)

    # ── A1 / A2 ────────────────────────────────────────────────────────────────
    a1_mh = load(A1_MH) or []
    a1_sh = load(A1_SH) or []
    a2 = load(A2) or []
    P("\n[A1] Modified-prompt vanilla baseline (top-10 retrieved, 6k context)")
    if a1_mh:
        ok, n, acc = headline_em(a1_mh)
        P(f"  FC-MH: {ok}/{n} = {acc:.1f}%")
    if a1_sh:
        ok, n, acc = headline_em(a1_sh)
        P(f"  FC-SH: {ok}/{n} = {acc:.1f}%")

    if a2:
        n_wrong = sum(1 for r in a2 if not r.get("exact_match"))
        fe_conflict = Counter()
        fe_class = Counter()
        fe_pos = Counter()
        for r in a2:
            if r.get("exact_match"):
                continue
            fe_conflict[r.get("first_error_conflict_type")] += 1
            fe_class[r.get("first_error_class")] += 1
            fe_pos[r.get("first_error_hop")] += 1
        P("\n[A2] First-error-hop diagnosis among wrong questions ({} wrong)".format(n_wrong))
        P(f"  conflict_type at first error:")
        for k, v in fe_conflict.most_common():
            P(f"    {str(k):<22} {v:>3} ({v/max(n_wrong,1)*100:.0f}%)")
        P(f"  class at first error:")
        for k, v in fe_class.most_common():
            P(f"    {str(k):<22} {v:>3} ({v/max(n_wrong,1)*100:.0f}%)")
        P(f"  hop position of first error:")
        for k in sorted(fe_pos):
            P(f"    hop {k}: {fe_pos[k]}")

    # ── B ──────────────────────────────────────────────────────────────────────
    b = load(B) or []
    P("\n[B] Hop-by-hop ablation: each hop run as standalone FC-SH")
    if b:
        ok = sum(1 for r in b if r.get("exact_match_gt"))
        n = len(b)
        P(f"  Overall single-hop EM: {ok}/{n} = {ok/n*100:.1f}%")
        # By conflict_type
        by_ct = defaultdict(lambda: [0, 0])
        for r in b:
            ct = r.get("conflict_type")
            by_ct[ct][1] += 1
            if r.get("exact_match_gt"):
                by_ct[ct][0] += 1
        P(f"  By conflict_type:")
        for ct, (c, t) in by_ct.items():
            P(f"    {str(ct):<22} {c}/{t} = {c/max(t,1)*100:.1f}%")
        # By hop_idx (was this the 1st/2nd/3rd hop?)
        by_hi = defaultdict(lambda: [0, 0])
        for r in b:
            hi = r.get("hop_idx")
            by_hi[hi][1] += 1
            if r.get("exact_match_gt"):
                by_hi[hi][0] += 1
        P(f"  By hop position in chain:")
        for hi, (c, t) in sorted(by_hi.items()):
            P(f"    hop_idx={hi:<3} {c}/{t} = {c/max(t,1)*100:.1f}%")

    # Cross-tab A2 vs B per-hop
    if a2 and b:
        P("\n[A2 x B] Cross-tab: in-chain (A2) vs ablation (B) per-hop accuracy")
        # Build B index by (qid, hop_idx)
        b_idx = {(r["query_id"], r["hop_idx"]): r.get("exact_match_gt") for r in b}
        ct = Counter()
        for q in a2:
            qid = q["query_id"]
            for h in q.get("per_hop", []):
                hi = h["hop_idx"]
                in_chain_correct = (h["class"] == "correct")
                ablation_correct = b_idx.get((qid, hi))
                if ablation_correct is None:
                    continue
                key = ("A2_correct" if in_chain_correct else "A2_wrong",
                       "B_correct" if ablation_correct else "B_wrong")
                ct[key] += 1
        total = sum(ct.values())
        P(f"  total per-hop pairs: {total}")
        for k in [("A2_correct", "B_correct"), ("A2_wrong", "B_correct"),
                  ("A2_correct", "B_wrong"), ("A2_wrong", "B_wrong")]:
            v = ct.get(k, 0)
            P(f"    {k[0]:<13} & {k[1]:<10} : {v:>4} ({v/max(total,1)*100:.1f}%)")
        wrong_in_chain_correct_alone = ct.get(("A2_wrong", "B_correct"), 0)
        wrong_in_both = ct.get(("A2_wrong", "B_wrong"), 0)
        if wrong_in_chain_correct_alone + wrong_in_both:
            ratio = wrong_in_chain_correct_alone / (wrong_in_chain_correct_alone + wrong_in_both)
            P(f"  Of all in-chain failures, {ratio*100:.0f}% would be solved if hop "
              f"ran alone (i.e. attributable to chain context interference, not skill)")

    # ── Sim-OB ─────────────────────────────────────────────────────────────────
    sim_ob = load(SIM_OB) or []
    P("\n[Sim-OB] Chain-only context (zero-noise zero-conflict ceiling)")
    if sim_ob:
        ok, n, acc = headline_em(sim_ob)
        P(f"  Overall: {ok}/{n} = {acc:.1f}%")
        grp = per_group_breakdown(sim_ob)
        P(f"  Per-group:")
        for key in sorted(grp.keys()):
            c, t = grp[key]
            P(f"    {key[0]}-hop, {key[1]}-conflict: {c}/{t} = {c/max(t,1)*100:.1f}%")

    # ── Sim-OB-grad ───────────────────────────────────────────────────────────
    grad = load(GRAD) or []
    P("\n[Sim-OB-grad] Noise gradient curve (chain + k distractors)")
    if grad:
        # group by (source, noise_level)
        agg = defaultdict(lambda: [0, 0])
        for r in grad:
            key = (r["source"], r["noise_level"])
            agg[key][1] += 1
            if r.get("exact_match"):
                agg[key][0] += 1
        sources = sorted({k[0] for k in agg.keys()})
        ks = sorted({k[1] for k in agg.keys()})
        P(f"  source              " + " ".join(f"k={k:>4}" for k in ks))
        for src in sources:
            row = []
            for k in ks:
                c, t = agg[(src, k)]
                row.append(f"{c/max(t,1)*100:5.1f}%" if t else "  -  ")
            P(f"  {src:<20}" + " ".join(row))
        # Drop curve interpretation
        for src in sources:
            curve = []
            for k in ks:
                c, t = agg[(src, k)]
                curve.append((k, c, t))
            P(f"  [{src}] N per cell: " + ",".join(f"k={k}:{t}" for k, c, t in curve))

    # ── Oracle A v2 (fact-level) ──────────────────────────────────────────────
    oa2_mh = load(OA2_MH) or []
    oa2_sh = load(OA2_SH) or []
    P("\n[Oracle A v2] Fact-level removal of chain old facts (full 100 / 100)")
    if oa2_mh:
        ok, n, acc = headline_em(oa2_mh)
        P(f"  FC-MH: {ok}/{n} = {acc:.1f}%")
        grp = per_group_breakdown(oa2_mh)
        P(f"  Per-group:")
        for key in sorted(grp.keys()):
            cc, tt = grp[key]
            P(f"    {key[0]}-hop, {key[1]}-conflict: {cc}/{tt} = {cc/max(tt,1)*100:.1f}%")
    if oa2_sh:
        ok, n, acc = headline_em(oa2_sh)
        P(f"  FC-SH: {ok}/{n} = {acc:.1f}%")

    # ── C ──────────────────────────────────────────────────────────────────────
    c_rows = load(C) or []
    P("\n[C] MH without non-chain old facts (full 6k minus other-question olds)")
    if c_rows:
        ok, n, acc = headline_em(c_rows)
        P(f"  Overall: {ok}/{n} = {acc:.1f}%")
        grp = per_group_breakdown(c_rows)
        P(f"  Per-group:")
        for key in sorted(grp.keys()):
            cc, tt = grp[key]
            P(f"    {key[0]}-hop, {key[1]}-conflict: {cc}/{tt} = {cc/max(tt,1)*100:.1f}%")

    # ── Comparison table (key paper figure) ────────────────────────────────────
    P("\n" + "=" * 78)
    P("Headline comparison (FC-MH all 100 questions where applicable)")
    P("=" * 78)
    P(f"  {'condition':<55} {'EM':>10} {'note'}")
    P(f"  {'-'*55:<55} {'-'*10:>10} ----")
    if a1_mh:
        ok, n, acc = headline_em(a1_mh)
        P(f"  {'A1: vanilla baseline (top-10 retrieved, modified prompt)':<55} {f'{ok}/{n}={acc:.1f}%':>10} same as before")
    if c_rows:
        ok, n, acc = headline_em(c_rows)
        P(f"  {'C: 6k minus non-chain olds (only chain conflicts kept)':<55} {f'{ok}/{n}={acc:.1f}%':>10} non-chain conflicts removed")
    if oa2_mh:
        ok, n, acc = headline_em(oa2_mh)
        P(f"  {'Oracle A v2: fact-level removal of chain olds (full 100)':<55} {f'{ok}/{n}={acc:.1f}%':>10} chain conflicts removed too")
    if sim_ob:
        ok, n, acc = headline_em(sim_ob)
        P(f"  {'Sim-OB: chain-only (zero noise / zero conflict)':<55} {f'{ok}/{n}={acc:.1f}%':>10} pure chain reasoning ceiling")
    if b:
        # compute query-level by checking if all hops of a query passed
        bymap = defaultdict(list)
        for r in b:
            bymap[r["query_id"]].append(r.get("exact_match_gt"))
        n = len(bymap)
        ok = sum(1 for hs in bymap.values() if all(hs))
        P(f"  {'B: all hops pass standalone (=AND of single-hop EMs)':<55} {f'{ok}/{n}={ok/n*100:.1f}%':>10} per-hop ceiling, AND combined")
        # Per-hop
        ph_ok = sum(1 for r in b if r.get("exact_match_gt"))
        P(f"  {'B: per-hop EM rate (all 254 sub-questions)':<55} {f'{ph_ok}/{len(b)}={ph_ok/len(b)*100:.1f}%':>10} single-hop ceiling")

    P("=" * 78)

    txt = "\n".join(lines)
    OUT.write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
