"""Offline reconstruction: apply phase2_resolve on saved retrieved_memories to
produce resolved_pool per query, WITHOUT re-running the pipeline (no OpenAI cost).

For each ours variant × length × query:
  1. Read outputs/rag_retrieved/.../query_<qid>_context_<ctx>.json
  2. If `resolved_pool` field already present -> skip (post-patch run)
  3. Else -> call phase2_resolve(retrieved_memories, message) offline
  4. Add resolved_pool field to the JSON in-place

Env vars are set to match each variant so phase2_resolve's control flow
(structural_pool routing, P3 LLM cluster, P5 conflict-type) matches original
run. Cache paths point to existing on-disk caches to reuse LLM decisions.

Usage:
    python analysis/apply_phase2_resolve.py [--length 6k 32k 64k] [--variant no_p5 struct p3_only]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # methods.phase2_query import

VARIANTS = {
    # (suffix in output dir, env overrides)
    "ours":       ("",             {"MEM0_STRUCTURAL_SKIP": "0", "MEM0_P5_SKIP": "0"}),
    "no_p5":      ("_no_p5",       {"MEM0_STRUCTURAL_SKIP": "0", "MEM0_P5_SKIP": "1"}),
    "struct":     ("_struct",      {"MEM0_STRUCTURAL_SKIP": "0", "MEM0_P5_SKIP": "1", "MEM0_QUERY_MODE_STRUCT": "1"}),
    "p3_only":    ("_p3_only_no_struct", {"MEM0_STRUCTURAL_SKIP": "1", "MEM0_P5_SKIP": "1"}),
}


def load_caches(L: str, variant: str):
    """Set env vars to point to on-disk caches for this length/variant."""
    pc = REPO / "analysis/results/p1_caches"
    os.environ["MEM0_EXTRACTION_CACHE"] = str(pc / f"extraction_cache_p1_{L}.json")
    os.environ["MEM0_TRIPLE_CACHE"] = str(pc / f"triple_cache_p1_{L}.json")
    os.environ["MEM0_SUBJECT_CACHE"] = str(pc / f"subject_cache_p1_{L}.json")
    os.environ["MEM0_PREDICATE_CACHE"] = str(pc / f"predicate_cache_{L}.json")
    cache_map = {
        "ours":       f"grouping_cache_p1_{L}.json",
        "no_p5":      f"grouping_cache_no_p5_{L}.json",
        "struct":     f"grouping_cache_struct_{L}.json",  # unused (struct uses phase0_query not phase2)
        "p3_only":    f"grouping_cache_p3_only_{L}.json",
    }
    conflict_map = {
        "ours":       f"conflict_cache_p1_{L}.json",
        "no_p5":      f"conflict_cache_no_p5_{L}.json",
        "struct":     f"conflict_cache_struct_{L}.json",
        "p3_only":    f"conflict_cache_p3_only_{L}.json",
    }
    os.environ["MEM0_GROUPING_CACHE"] = str(pc / cache_map[variant])
    os.environ["MEM0_CONFLICT_CACHE"] = str(pc / conflict_map[variant])


def _apply_struct_variant(candidates: list) -> list:
    """For ours_struct: reproduce phase0_query.group_and_resolve semantics.
    Same fact-level ordinal (post 9ced3c2)."""
    from collections import defaultdict
    sp_map = defaultdict(list)
    other = []
    for it in candidates:
        md = it.get("metadata") or {}
        t = md.get("triple")
        if t:
            sp_map[(t["subject_id"], t["predicate_norm"])].append(it)
        else:
            other.append(it)
    resolved = list(other)
    for _, items in sp_map.items():
        if len(items) < 2:
            resolved.extend(items); continue
        mx = max((it.get("metadata") or {}).get("ordinal", -1) for it in items)
        resolved.extend(it for it in items if (it.get("metadata") or {}).get("ordinal", -1) == mx)
    return resolved


def _apply_phase2_variant(candidates: list, message: str) -> list:
    """For no_p5 / p3_only / ours (full): use phase2_resolve which honors env flags."""
    from methods.phase2_query import phase2_resolve
    return phase2_resolve(candidates, message)


def apply_to_variant(L: str, variant: str) -> dict:
    load_caches(L, variant)
    for k, v in VARIANTS[variant][1].items():
        os.environ[k] = v
    suf = VARIANTS[variant][0]
    dir_root = REPO / f"outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified{suf}/k_100/factconsolidation_sh_{L}/chunksize_512"
    files = sorted(glob.glob(str(dir_root / "query_*_context_*.json")))
    if not files:
        return {"variant": variant, "L": L, "status": "no_files", "dir": str(dir_root)}
    n_skipped = n_processed = n_error = 0
    for f in files:
        try:
            d = json.load(open(f))
        except Exception as e:
            n_error += 1; continue
        if d.get("resolved_pool") is not None:
            n_skipped += 1; continue
        mems = d.get("retrieved_memories", []) or []
        if not mems:
            d["resolved_pool"] = []
        else:
            message = d.get("user_message", "")
            try:
                if variant == "struct":
                    final = _apply_struct_variant(mems)
                else:
                    final = _apply_phase2_variant(mems, message)
                d["resolved_pool"] = final
            except Exception as e:
                import traceback
                d["resolved_pool"] = None
                d["_resolve_error"] = f"{type(e).__name__}: {str(e)[:200]}"
                if n_error < 3:
                    print(f"[error] {Path(f).name}: {type(e).__name__}: {e}")
                    traceback.print_exc()
                n_error += 1; continue
        # Overwrite file
        with open(f, "w", encoding="utf-8") as out:
            json.dump(d, out, ensure_ascii=False, indent=2)
        n_processed += 1
    return {"variant": variant, "L": L, "n_processed": n_processed,
            "n_skipped": n_skipped, "n_error": n_error, "n_files": len(files)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--length", "-L", nargs="*", default=["6k", "32k", "64k"])
    ap.add_argument("--variant", "-V", nargs="*", default=["ours", "no_p5", "struct", "p3_only"])
    args = ap.parse_args()
    for L in args.length:
        for v in args.variant:
            r = apply_to_variant(L, v)
            print(r)


if __name__ == "__main__":
    main()
