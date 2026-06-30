"""Cache FC contexts (6k/32k/64k/262k) from HF dataset arrow to analysis/contexts/.

Run once. 6k and 32k are already cached but we overwrite with the canonical version
from the dataset to ensure consistency.

Usage:
    python analysis/cache_fc_contexts.py
"""
import os
from pathlib import Path

import pyarrow as pa
from pyarrow import ipc

ARROW = "/home/yhchiang/MemoryAgentBench/.cache/huggingface/datasets/ai-hyz___memory_agent_bench/default/0.0.0/00d1946269e29b41eed74511997afa8171b91e08/memory_agent_bench-Conflict_Resolution.arrow"
OUT_DIR = Path("/home/yhchiang/MemoryAgentBench/analysis/contexts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Each (sh|mh, length) shares the same context, so we only emit per-length.
LENGTHS = ["6k", "32k", "64k", "262k"]

with open(ARROW, "rb") as f:
    table = ipc.open_stream(f).read_all()
rows = table.to_pylist()

for length in LENGTHS:
    # 取 sh_{length} 作為 canonical(sh 和 mh 共享 context)
    src = f"factconsolidation_sh_{length}"
    matched = [r for r in rows if (r.get("metadata") or {}).get("source") == src]
    if not matched:
        print(f"[WARN] {src} not found in arrow")
        continue
    ctx = matched[0]["context"]
    out = OUT_DIR / f"factconsolidation_{length}_context.txt"
    out.write_text(ctx)

    # 同時驗證 mh 一致
    mh_src = f"factconsolidation_mh_{length}"
    mh_matched = [r for r in rows if (r.get("metadata") or {}).get("source") == mh_src]
    same = mh_matched and mh_matched[0]["context"] == ctx

    n_facts = sum(1 for ln in ctx.split("\n") if ln and ln[0].isdigit())
    print(f"[OK] {out.name}: {len(ctx):>10} chars, {n_facts:>5} facts, sh==mh: {bool(same)}")

print("\nDone.")
