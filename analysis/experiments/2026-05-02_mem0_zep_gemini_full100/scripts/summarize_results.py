"""
Summarize Mem0 / Zep × Gemini × FC-SH/MH results.

Outputs Markdown table + per-num_hops / per-n_conflict breakdowns.
"""

import json
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"


def load(name):
    p = RESULTS / name
    return json.load(open(p)) if p.exists() else None


def overall(rs):
    if rs is None:
        return None
    n_correct = sum(1 for r in rs if r["exact_match"])
    return n_correct, len(rs), n_correct / len(rs) * 100 if rs else 0


def by_key(rs, key):
    if rs is None:
        return {}
    d = defaultdict(list)
    for r in rs:
        if key in r:
            d[r[key]].append(r["exact_match"])
    return {k: (sum(v), len(v), sum(v) / len(v) * 100) for k, v in d.items()}


def main():
    sets = {
        "Mem0 customized × Gemini × FC-SH": "mem0_gemini_sh_results.json",
        "Mem0 customized × Gemini × FC-MH": "mem0_gemini_mh_results.json",
        "Zep × Gemini × FC-SH": "zep_gemini_sh_results.json",
        "Zep × Gemini × FC-MH": "zep_gemini_mh_results.json",
    }

    out = []
    out.append("# Mem0 / Zep × Gemini full 100 results\n")
    out.append("## Overall EM\n")
    out.append("| System | n correct | n total | EM |")
    out.append("|---|:---:|:---:|:---:|")

    for label, fname in sets.items():
        rs = load(fname)
        ov = overall(rs)
        if ov:
            out.append(f"| {label} | {ov[0]} | {ov[1]} | **{ov[2]:.1f}%** |")
        else:
            out.append(f"| {label} | — | — | (not found: {fname}) |")

    # MH breakdowns
    for label, fname in sets.items():
        if "MH" not in label:
            continue
        rs = load(fname)
        if rs is None:
            continue
        out.append(f"\n## {label} — by num_hops\n")
        out.append("| num_hops | n correct | n total | EM |")
        out.append("|:---:|:---:|:---:|:---:|")
        bh = by_key(rs, "num_hops")
        for k in sorted(bh):
            c, t, p = bh[k]
            out.append(f"| {k} | {c} | {t} | {p:.1f}% |")

        out.append(f"\n## {label} — by n_conflict\n")
        out.append("| n_conflict | n correct | n total | EM |")
        out.append("|:---:|:---:|:---:|:---:|")
        bn = by_key(rs, "n_conflict")
        for k in sorted(bn):
            c, t, p = bn[k]
            out.append(f"| {k} | {c} | {t} | {p:.1f}% |")

    text = "\n".join(out)
    print(text)
    out_path = RESULTS / "summary.md"
    out_path.write_text(text)
    print(f"\nWritten to: {out_path}")


if __name__ == "__main__":
    main()
