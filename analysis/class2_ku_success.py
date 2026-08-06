#!/usr/bin/env python3
"""CLASS-2 (write-time KU) SUCCESS indicators for FC-SH 5.2.2 (gpt-4o-mini, committed data).

This measures whether the WRITE-TIME KU judgment SUCCEEDED. It is a KU-SUCCESS rate,
NOT a world-prior attribution — write-time failure cannot be pinned to world-prior
(the answer LLM never sees a clean pool to revert from). has_pair subset, per length.

TASK A — Mem0 gt_new-recall @ query-time top-100 (KU success = gt_new survived write-time):
    Mem0+P1 (dest): pool-state on retrieved_memories (compute_pool_acc_crosstab.classify_pool_state).
        gt_new-recall (KU success) = PP-New + PP-Both ;  KU-failed = PP-OldOnly + PP-Missing.
    Mem0 Vanilla (native): its answering pool is NOT recoverable from committed dumps
        (retrieved_memories / memories_str are EMPTY in all query_*_context.json; user_message
        holds only the QA template, no facts) -> reported COARSE / unrecoverable.

TASK B — Zep gt_old-invalidated @ top-10 (KU success = gt_old edge marked invalid):
    edges carry fact / valid_at / invalid_at (+expired_at if present). Per has_pair:
      (1) both-retrieved  : gt_old AND gt_new edge both in top-10 (match_pair on edge.fact)
      (2) gt_old-invalidated (KU SUCCESS): a gt_old-matching edge present AND carries
          invalid_at (or expired_at)
      (3) KU-failed = complement: gt_old-present-but-still-valid  +  gt_old-not-retrieved.

Committed paths:
    GT      : analysis/results/sh_{L}_mquake_analysis.json
    Mem0+P1 : outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/**/query_*.json
    Zep     : outputs/rag_retrieved/Structure_rag_zep/k_10/**/query_*.json

Run (MABench env, repo root):  python analysis/class2_ku_success.py
"""
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "analysis"))

from rescore_canonical import load_haspair                       # noqa: E402
from compute_pool_acc_crosstab import classify_pool_state, extract_pool_texts  # noqa: E402
from compute_m1_m2_m3 import match_pair                          # noqa: E402

LENGTHS = ["6k", "32k", "64k", "262k"]
DEST = REPO / "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100"
ZEP = REPO / "outputs/rag_retrieved/Structure_rag_zep/k_10"


def _qjson(root, L, qid):
    fs = glob.glob(str(root / f"factconsolidation_sh_{L}/chunksize_512/query_{qid}_context_*.json"))
    return json.load(open(fs[0], encoding="utf-8")) if fs else None


# ==================== TASK A — Mem0+P1 gt_new-recall ==================== #
def taskA_mem0_dest():
    out = {}
    for L in LENGTHS:
        hp = load_haspair(L)
        n = recall = 0
        buckets = {"PP-New": 0, "PP-Both": 0, "PP-OldOnly": 0, "PP-Missing": 0}
        for qid, row in hp.items():
            j = _qjson(DEST, L, qid)
            if j is None:
                continue
            pool = extract_pool_texts(j, "retrieved_memories")
            st = classify_pool_state(pool, row.get("gt_fact_text", ""), row.get("old_fact_text", ""))
            buckets[st] = buckets.get(st, 0) + 1
            n += 1
            if st in ("PP-New", "PP-Both"):
                recall += 1
        out[L] = {"n": n, "recall": recall, "buckets": buckets}
    return out


# ==================== TASK B — Zep gt_old-invalidated ==================== #
def _invalidated(edge):
    return bool(edge.get("invalid_at") or edge.get("expired_at"))


def taskB_zep():
    out = {}
    for L in LENGTHS:
        hp = load_haspair(L)
        n = 0
        both = 0                 # both gt_old and gt_new edge retrieved
        old_present = 0          # gt_old edge retrieved (any)
        old_invalid = 0          # gt_old edge retrieved AND carries invalid_at/expired_at (KU success)
        old_valid = 0            # gt_old retrieved but all its edges still valid
        old_absent = 0           # gt_old not retrieved at all
        for qid, row in hp.items():
            j = _qjson(ZEP, L, qid)
            if j is None:
                continue
            edges = j.get("edges", []) or []
            gt_new = row.get("gt_fact_text") or ""
            gt_old = row.get("old_fact_text") or ""
            olds = [e for e in edges if match_pair(e.get("fact", ""), gt_new, gt_old, "old")]
            news = [e for e in edges if match_pair(e.get("fact", ""), gt_new, gt_old, "new")]
            n += 1
            if olds and news:
                both += 1
            if olds:
                old_present += 1
                if any(_invalidated(e) for e in olds):
                    old_invalid += 1
                else:
                    old_valid += 1
            else:
                old_absent += 1
        out[L] = {"n": n, "both": both, "old_present": old_present,
                  "old_invalid": old_invalid, "old_valid": old_valid, "old_absent": old_absent}
    return out


def pct(a, b):
    return f"{100*a/b:.0f}%" if b else "—"


def main():
    A = taskA_mem0_dest()
    B = taskB_zep()

    print("=" * 78)
    print("CLASS-2 write-time KU SUCCESS indicators (gpt-4o-mini, has_pair). NOT world-prior.")
    print("=" * 78)

    print("\nTASK A — Mem0 gt_new-recall @ query-time top-100  (KU success = gt_new survived write)")
    print(f"{'method':<22}{'length':<8}{'gt_new-recall (KU ok)':<24}{'KU-failed (new destroyed)':<26}")
    for L in LENGTHS:
        d = A[L]
        r, n = d["recall"], d["n"]
        print(f"{'Mem0+P1 (dest)':<22}{L:<8}{f'{r}/{n} ({pct(r,n)})':<24}{f'{n-r}/{n} ({pct(n-r,n)})':<26}  buckets={d['buckets']}")
    for L in LENGTHS:
        print(f"{'Mem0 Vanilla (native)':<22}{L:<8}{'COARSE — pool not recoverable (retrieved_memories/memories_str empty in all dumps)'}")

    print("\nTASK B — Zep gt_old-invalidated @ top-10  (KU success = gt_old edge marked invalid)")
    print(f"{'length':<8}{'both-retrieved':<18}{'gt_old present':<16}{'gt_old-INVALID (KU ok)':<24}{'KU-failed':<28}")
    for L in LENGTHS:
        d = B[L]
        n = d["n"]
        kf = d["old_valid"] + d["old_absent"]
        c_both = f"{d['both']}/{n} ({pct(d['both'], n)})"
        c_pres = f"{d['old_present']}/{n} ({pct(d['old_present'], n)})"
        c_inv = f"{d['old_invalid']}/{n} ({pct(d['old_invalid'], n)})"
        c_kf = f"{kf}/{n} ({pct(kf, n)})  [valid={d['old_valid']} absent={d['old_absent']}]"
        print(f"{L:<8}{c_both:<18}{c_pres:<16}{c_inv:<24}{c_kf:<28}")
        # cross-check hint: retrieved-old-with-invalid among gt_old-present
        print(f"        cross-check: of gt_old-present ({d['old_present']}), invalidated = "
              f"{d['old_invalid']}/{d['old_present']} ({pct(d['old_invalid'], d['old_present'])})")


if __name__ == "__main__":
    main()
