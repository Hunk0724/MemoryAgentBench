"""D1 + D2 diagnostics for C-v2 C group regression (EM=15).

D1: How many chunks rebuilt per query, vs B group?
    + Are chain_old_pids inflated by bidir?
D2: Random sample 3 queries → show rebuilt chunk text vs original.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

BASE = Path("/home/yhchiang/MemoryAgentBench")
RAG = BASE / ("outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/"
              "chunksize_512/context_id_0/"
              "gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2")

C_DIR = BASE / "monitoring_logs/2026-05-26_174544_C-v2_C_group_bidir_chunk_rebuild"
B_DIR = BASE / "monitoring_logs/2026-05-26_171541_C-v2_B_group_bidir_only"


def load_dump(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path)]


def main():
    chunks_df = pd.read_parquet(RAG / "chunk_embeddings/vdb_chunk.parquet")
    chunk_text_by_id = dict(zip(chunks_df["hash_id"], chunks_df["content"]))
    props = json.load(open(RAG / "proposition_index.json"))["propositions"]
    prop_idx = {p["id"]: p for p in props}

    C_dump = load_dump(C_DIR / "phase2_w13_dump.jsonl")
    B_dump = load_dump(B_DIR / "phase2_w13_dump.jsonl")
    print(f"C dump: {len(C_dump)} events,  B dump: {len(B_dump)} events\n")

    # ─── D1: per-query stats ─────────────────────────────────────────────
    def per_query_stats(dump, label):
        chain_olds_per_q = []
        active_per_q = []
        chains_per_q = []
        verdicts_per_q = []
        for e in dump:
            if e.get("phase2_status") != "RAN":
                continue
            chain_olds_per_q.append(e.get("n_chain_old_props", 0))
            active_per_q.append(e.get("n_active_props", 0))
            chains_per_q.append(e.get("n_chains", 0))
            verdicts_per_q.append(e.get("n_verdicts", 0))
        n = max(len(chain_olds_per_q), 1)
        print(f"=== {label} (n_queries with phase2 RAN = {n}) ===")
        print(f"  chain_old_props/query: mean={sum(chain_olds_per_q)/n:.1f}, "
              f"max={max(chain_olds_per_q) if chain_olds_per_q else 0}, "
              f"sum={sum(chain_olds_per_q)}")
        print(f"  n_active_props/query : mean={sum(active_per_q)/n:.1f}")
        print(f"  n_chains/query       : mean={sum(chains_per_q)/n:.1f}")
        print(f"  n_verdicts/query     : mean={sum(verdicts_per_q)/n:.1f}")
        return chain_olds_per_q

    print("D1 — per-query chain_old aggregation comparison")
    print("-" * 60)
    c_olds = per_query_stats(C_dump, "C group (bidir + chunk_rebuild)")
    print()
    b_olds = per_query_stats(B_dump, "B group (bidir + rescue)")
    print()

    # ─── D2: random 3 queries, look at rebuilt chunks ───────────────────
    print("\nD2 — Random 3 queries: rebuilt chunk content samples (C group)")
    print("=" * 70)
    random.seed(42)
    # Only events where phase2 RAN AND there are chain_olds
    candidates = [e for e in C_dump
                  if e.get("phase2_status") == "RAN"
                  and e.get("n_chain_old_props", 0) > 0]
    print(f"  {len(candidates)} events with chain_old_props > 0\n")
    sample = random.sample(candidates, min(3, len(candidates)))

    # Build chunk_to_prop_ids from prop_idx
    chunk_to_prop_ids: dict[str, list] = defaultdict(list)
    for p in props:
        chunk_to_prop_ids[p["source_chunk_id"]].append(p["id"])

    for i, e in enumerate(sample):
        query = e["query"][:100]
        chain_old_pids = set(e.get("chain_old_pids", []))
        print(f"--- Query {i+1}: {query}... ---")
        print(f"  n_chain_old_props = {e.get('n_chain_old_props', 0)}")
        # Find which chunks in top-20 contain any chain_old
        passages_pre_filter = e.get("passages_pre_filter_chunk_ids", [])
        affected = []
        for cid in passages_pre_filter[:10]:
            pids_in_chunk = chunk_to_prop_ids.get(cid, [])
            olds_here = [p for p in pids_in_chunk if p in chain_old_pids]
            if olds_here:
                affected.append((cid, olds_here, pids_in_chunk))
        print(f"  Top-10 chunks affected by chain_old: {len(affected)}")

        if affected:
            cid, olds, all_pids = affected[0]
            print(f"\n  --- First affected chunk {cid[:24]} ---")
            print(f"  Total props in chunk: {len(all_pids)}, marked old: {len(olds)}")
            print(f"  ORIGINAL chunk text (first 400 char):")
            orig = chunk_text_by_id.get(cid, "<missing>")
            print(f"    {orig[:400]}")
            # Simulate rebuild
            remaining = [p for p in all_pids if p not in chain_old_pids]
            remaining.sort(key=lambda pid: prop_idx[pid]["timestamp"][1])
            rebuilt = " ".join(prop_idx[p]["text"] for p in remaining)
            print(f"  REBUILT chunk text (first 400 char):")
            print(f"    {rebuilt[:400]}")
            print(f"  Original len: {len(orig)} chars, Rebuilt len: {len(rebuilt)} chars")
        print()

    # ─── Summary signal ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    c_mean = sum(c_olds) / max(len(c_olds), 1)
    b_mean = sum(b_olds) / max(len(b_olds), 1)
    print(f"  C group chain_old/query : {c_mean:.1f} (sum={sum(c_olds)})")
    print(f"  B group chain_old/query : {b_mean:.1f} (sum={sum(b_olds)})")
    print(f"  Ratio C/B               : {c_mean/max(b_mean, 0.01):.2f}x")
    if c_mean > 1.5 * b_mean:
        print(f"  → bidir 在 C 跟 B 應該一樣(同 flag)→ 比例接近 1.0 才正常")
        print(f"  → 比例 {c_mean/max(b_mean, 0.01):.2f}x 表示 C 跟 B 的 verdict 結果有真實差異")
    elif abs(c_mean - b_mean) / max(b_mean, 0.01) < 0.05:
        print(f"  → chain_old/query 在 C/B 幾乎相同 → bidir 行為一致")
        print(f"  → C 崩到 EM=15 不是 chain_old 數量問題,是 chunk_rebuild 內容問題(D2)")


if __name__ == "__main__":
    main()
