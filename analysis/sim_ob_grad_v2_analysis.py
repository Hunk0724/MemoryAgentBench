"""
Analyze sim_ob_grad_v2 results — three modes side-by-side with stratification.

Reads:
  analysis/results/diagnostic/sim_ob_grad_v2_chain_only_olds_results.json
  analysis/results/diagnostic/sim_ob_grad_v2_grad_pure_results.json
  analysis/results/diagnostic/sim_ob_grad_v2_grad_injection_results.json

Also reads existing baselines for context:
  analysis/results/diagnostic/sim_ob_chain_only_origprompt_results.json   (chain_new only, orig prompt)
  analysis/results/diagnostic/oracle_a_fact_level_origprompt_results.json (OA2 orig prompt)

Writes:
  analysis/results/diagnostic/sim_ob_grad_v2_summary.md
"""

import json
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
DIAG = BASE / "analysis/results/diagnostic"


def load(p):
    if not Path(p).exists():
        return None
    return json.load(open(p))


def acc(rows):
    if not rows:
        return None
    ok = sum(1 for r in rows if r["exact_match"])
    return (ok, len(rows), ok / len(rows) * 100)


def stratify(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r.get(key)].append(r)
    return {k: acc(v) for k, v in sorted(g.items()) if k is not None}


def fmt(a):
    if a is None:
        return "—"
    ok, n, p = a
    return f"{ok}/{n} ({p:.0f}%)"


def main():
    out_lines = ["# Sim-OB grad v2 — clean variable isolation (orig prompt)\n"]

    # ===== Reference baselines =====
    out_lines.append("## Reference baselines (orig prompt)\n")
    chain_only_new = load(DIAG / "sim_ob_chain_only_origprompt_results.json")
    oa2 = load(DIAG / "oracle_a_fact_level_origprompt_results.json")
    refs = []
    if chain_only_new:
        refs.append(("Sim-OB chain-only (chain new only, no distractors)", acc(chain_only_new)))
    if oa2:
        refs.append(("OA2 fact-level filter (HippoRAG top-10, chain old excised)", acc(oa2)))
    out_lines.append("| Setup | overall |")
    out_lines.append("|---|---|")
    for name, a in refs:
        out_lines.append(f"| {name} | {fmt(a)} |")
    out_lines.append("")

    # ===== Mode A: chain_only_olds =====
    out_lines.append("## Mode A: chain-only with chain-old (no other distractors)\n")
    out_lines.append("Context = chain_new + chain_old facts. Tests pure conflict-pair effect.\n")
    a_data = load(DIAG / "sim_ob_grad_v2_chain_only_olds_results.json")
    if a_data:
        out_lines.append(f"**Overall**: {fmt(acc(a_data))}\n")
        out_lines.append("**By num_hops**:\n")
        out_lines.append("| num_hops | acc |")
        out_lines.append("|---|---|")
        for k, v in stratify(a_data, "num_hops").items():
            out_lines.append(f"| {k} | {fmt(v)} |")
        out_lines.append("\n**By n_conflict (chain old count)**:\n")
        out_lines.append("| n_conflict | acc |")
        out_lines.append("|---|---|")
        for k, v in stratify(a_data, "n_conflict").items():
            out_lines.append(f"| {k} | {fmt(v)} |")
        out_lines.append("")
    else:
        out_lines.append("(not run yet)\n")

    # ===== Mode B: grad_pure =====
    out_lines.append("## Mode B: grad-pure (chain old EXCLUDED from distractor pool)\n")
    out_lines.append("Context = chain_new + k distractors (sampled from facts \\ chain_new \\ chain_old).\n")
    b_data = load(DIAG / "sim_ob_grad_v2_grad_pure_results.json")
    if b_data:
        out_lines.append("**Overall accuracy by (source, k)**:\n")
        out_lines.append("| source | k=10 | k=50 | k=100 | k=200 | k=447 |")
        out_lines.append("|---|---|---|---|---|---|")
        for source in ["random", "ppr-nearby"]:
            cells = [source]
            for k in [10, 50, 100, 200, 447]:
                rows = [r for r in b_data if r["source"] == source and r["noise_level"] == k]
                cells.append(fmt(acc(rows)))
            out_lines.append("| " + " | ".join(cells) + " |")
        out_lines.append("")
        # By hops at k=full (most stressful)
        out_lines.append("**At k=447, by num_hops (ppr-nearby)**:\n")
        out_lines.append("| num_hops | acc |")
        out_lines.append("|---|---|")
        rows = [r for r in b_data if r["source"] == "ppr-nearby" and r["noise_level"] == 447]
        for k, v in stratify(rows, "num_hops").items():
            out_lines.append(f"| {k} | {fmt(v)} |")
        out_lines.append("")
    else:
        out_lines.append("(not run yet)\n")

    # ===== Mode C: grad_injection =====
    out_lines.append("## Mode C: grad-injection (chain old gradually injected into saturated noise)\n")
    out_lines.append("Context = chain_new + ALL non_chain_pure + n chain_olds (n=0..N cumulative in hop order).\n")
    c_data = load(DIAG / "sim_ob_grad_v2_grad_injection_results.json")
    if c_data:
        out_lines.append("**Accuracy by n_old_injected** (only questions with N≥n included):\n")
        out_lines.append("| n_old_injected | n_questions | acc |")
        out_lines.append("|---|---|---|")
        for k, v in stratify(c_data, "n_old_injected").items():
            ok, n, p = v
            out_lines.append(f"| {k} | {n} | {ok}/{n} ({p:.0f}%) |")
        out_lines.append("")
        # Cross-tab: n_inject × num_hops
        out_lines.append("**Cross-tab num_hops × n_old_injected (acc)**:\n")
        n_injects = sorted(set(r["n_old_injected"] for r in c_data))
        nhops = sorted(set(r["num_hops"] for r in c_data if r.get("num_hops") is not None))
        out_lines.append("| num_hops | " + " | ".join(f"n={n}" for n in n_injects) + " |")
        out_lines.append("|" + "---|" * (len(n_injects) + 1))
        for nh in nhops:
            cells = [f"{nh}-hop"]
            for n in n_injects:
                rows = [r for r in c_data if r["num_hops"] == nh and r["n_old_injected"] == n]
                cells.append(fmt(acc(rows)))
            out_lines.append("| " + " | ".join(cells) + " |")
        out_lines.append("")
    else:
        out_lines.append("(not run yet)\n")

    # Write
    out_path = DIAG / "sim_ob_grad_v2_summary.md"
    out_path.write_text("\n".join(out_lines))
    print(f"Written: {out_path}")
    print("\n" + "\n".join(out_lines))


if __name__ == "__main__":
    main()
