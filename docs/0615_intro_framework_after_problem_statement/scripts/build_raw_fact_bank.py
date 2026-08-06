#!/usr/bin/env python3
"""Build raw fact bank per FC-SH length from HF dataset context.

Parses `(\\d+)\\.\\s` pattern from `row['context']` — the SAME regex Don't Ask
paper (Reddy & Challaram 2026) uses to load "raw serials + raw facts" for
their as-designed reproduction (71/78/81 on 6k/32k/64k). See
`docs/.../related work/memory-conflict-resolution/scripts/_data.py:_parse_facts`.

Adopted 2026-07-12 as new canonical fact-bank protocol for all KU-mechanism
methods (ours variants, mem0+P1, Q-llm-recency, Don't Ask); vanilla mem0 / Zep
/ LCA keep native ingestion. See `project_raw_fact_bank_canonical` memory.

Usage:
  conda activate MABench
  python docs/0615_intro_framework_after_problem_statement/scripts/build_raw_fact_bank.py
  # → analysis/results/raw_fact_bank/fact_bank_sh_{6k,32k,64k,262k}.json
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "analysis/results/raw_fact_bank"


def parse_facts(context: str) -> list[dict]:
    """Regex-extract numbered facts from FC context.

    Pattern from Reddy & Challaram 2026 `_data.py:_parse_facts`. Each fact
    formatted as 'N. <text>' separated by whitespace; take text between
    consecutive markers, strip trailing period.
    Returns list of {"serial": int, "fact": str}.
    """
    pat = re.compile(r"(\d+)\.\s")
    matches = list(pat.finditer(context))
    facts = []
    for i, m in enumerate(matches):
        idx = int(m.group(1))
        s = m.end()
        e = matches[i + 1].start() if i + 1 < len(matches) else len(context)
        text = context[s:e].strip().rstrip(".")
        facts.append({"serial": idx, "fact": text})
    return facts


def main():
    from datasets import load_dataset

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ds = load_dataset("ai-hyz/MemoryAgentBench",
                      split="Conflict_Resolution", revision="main")
    lengths = ["6k", "32k", "64k", "262k"]
    summary = {}

    for L in lengths:
        source = f"factconsolidation_sh_{L}"
        rows = [s for s in ds if s["metadata"]["source"] == source]
        if not rows:
            print(f"[{L}] no row for {source} — SKIP")
            continue
        row = rows[0]
        ctx = row["context"]
        facts = parse_facts(ctx)
        # dedup by serial (keep first if repeated — shouldn't happen for well-formed FC)
        seen = set()
        uniq = []
        for f in facts:
            key = f["serial"]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(f)
        n_q = len(row.get("questions", []))
        out_path = OUT_DIR / f"fact_bank_sh_{L}.json"
        payload = {
            "length": L,
            "source": source,
            "n_facts_raw": len(facts),
            "n_facts_unique": len(uniq),
            "n_questions": n_q,
            "context_chars": len(ctx),
            "serial_min": min((f["serial"] for f in uniq), default=None),
            "serial_max": max((f["serial"] for f in uniq), default=None),
            "facts": uniq,
        }
        json.dump(payload, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        summary[L] = {
            "n_raw": len(facts), "n_uniq": len(uniq),
            "serial_range": (payload["serial_min"], payload["serial_max"]),
            "n_q": n_q, "ctx_chars": len(ctx),
        }
        print(f"[{L}] raw={len(facts)} uniq={len(uniq)} "
              f"serial=[{payload['serial_min']}..{payload['serial_max']}] "
              f"q={n_q} ctx={len(ctx):,} → {out_path.name}")

    print("\n=== SUMMARY ===")
    for L, s in summary.items():
        print(f"  {L}: {s}")


if __name__ == "__main__":
    main()
