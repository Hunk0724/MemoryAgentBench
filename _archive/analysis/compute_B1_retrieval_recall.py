"""B1a / B1b / B1c — vanilla HippoRAG-v2 retrieval recall on FC-MH 100Q.

Key insight: ablation A's retrieval == ablation B's `passages_pre_filter_chunk_ids`
(Phase 2 filter runs ON TOP of A's PPR retrieval; hyperedge adds 0 edges so PPR is identical).
So we can compute these metrics from B's dump without re-running anything (zero GPU).

Metrics:
  B1a  New-version Recall  — per-hop hit rate: chain_new's source_chunk ∈ retrieved top-K
  B1b  Old-version Retrieval Rate — per-hop: chain_old's source_chunk ∈ retrieved top-K  (=noise gap)
  B1c  Multi-hop Path Recall — per-query: ALL hops' chain_new chunks present in top-K

Reported at K=5 (LLM-visible after qa_top_k cut) and K=10 (full retrieval).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/results/paper_narrative'
OUT.mkdir(parents=True, exist_ok=True)


def normalize_query(q: str) -> str:
    p = 'Based on the provided Knowledge Pool, '
    if q.startswith(p):
        q = q[len(p):]
    q = q.split('\nAnswer:')[0]
    return q.strip().rstrip('?').strip().lower()


# ─── Load proposition index → pid → source_chunk_id ───
prop_file = (BASE / 'outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/'
             'chunksize_512/context_id_0/'
             'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json')
prop_idx = {p['id']: p for p in json.load(open(prop_file))['propositions']}

# ─── Load labels ───
labels = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))

# ─── Load ablation B's pre_filter chunks per query (= A's retrieval) ───
dump_lines = open(BASE / 'monitoring_logs/2026-05-17_182907_ablation_B/phase2_w13_dump.jsonl').readlines()
query_to_chunks = {}
for line in dump_lines:
    e = json.loads(line)
    query_to_chunks[normalize_query(e['query'])] = list(e.get('passages_pre_filter_chunk_ids') or [])


def hit(prop_id, chunks_topk):
    """Is prop_id's source_chunk in the top-K retrieved chunks?"""
    p = prop_idx.get(prop_id)
    if not p:
        return None
    return p['source_chunk_id'] in chunks_topk


def compute(K: int):
    """Returns dict with all B1 metrics at given K."""
    # Per-hop counters (B1a / B1b)
    new_hit = new_total = 0
    old_hit = old_total = 0
    # By hop count
    by_nh_new = defaultdict(lambda: [0, 0])   # [hit, total]
    by_nh_old = defaultdict(lambda: [0, 0])
    # By conflict_type
    by_ct_new = defaultdict(lambda: [0, 0])

    # B1c: per-query, all hops' chain_new present
    path_all = path_hit = 0
    by_nh_path = defaultdict(lambda: [0, 0])

    matched = unmatched = 0

    for q in labels:
        nq = normalize_query(q['question'])
        chunks_all = query_to_chunks.get(nq)
        if chunks_all is None:
            unmatched += 1
            continue
        matched += 1
        topk = chunks_all[:K]
        nhops = q['num_hops']

        all_new_hit = True
        any_new = False
        for hop in q['hops']:
            ct = hop['conflict_type']
            new_matches = hop.get('chain_new_matches') or []
            old_matches = hop.get('chain_old_matches') or []

            # B1a — new-version recall
            if new_matches:
                any_new = True
                h = hit(new_matches[0]['prop_id'], topk)
                if h is not None:
                    new_total += 1
                    by_nh_new[nhops][1] += 1
                    by_ct_new[ct][1] += 1
                    if h:
                        new_hit += 1
                        by_nh_new[nhops][0] += 1
                        by_ct_new[ct][0] += 1
                    else:
                        all_new_hit = False

            # B1b — old-version retrieval rate (only has_pair hops have chain_old)
            if ct == 'has_pair' and old_matches:
                h = hit(old_matches[0]['prop_id'], topk)
                if h is not None:
                    old_total += 1
                    by_nh_old[nhops][1] += 1
                    if h:
                        old_hit += 1
                        by_nh_old[nhops][0] += 1

        # B1c — all-hops new path recall
        if any_new:
            path_all += 1
            by_nh_path[nhops][1] += 1
            if all_new_hit:
                path_hit += 1
                by_nh_path[nhops][0] += 1

    return {
        'K': K,
        'matched_queries': matched,
        'unmatched_queries': unmatched,
        'B1a_new_recall': (new_hit, new_total),
        'B1b_old_retrieval_rate': (old_hit, old_total),
        'B1c_path_recall': (path_hit, path_all),
        'by_hop_new': dict(by_nh_new),
        'by_hop_old': dict(by_nh_old),
        'by_hop_path': dict(by_nh_path),
        'by_conflict_type_new': dict(by_ct_new),
    }


def pct(num, den):
    return f"{100*num/den:.1f}%" if den else "n/a"


def fmt_pair(p):
    h, t = p
    return f"{h}/{t} ({pct(h,t)})"


# ─── Compute & report ───
results = {K: compute(K) for K in [5, 10]}

# JSON dump
json.dump(
    {str(K): {k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()} for K, r in results.items()},
    open(OUT / 'B1_retrieval_recall.json', 'w'),
    indent=2, default=lambda o: dict(o) if hasattr(o,'items') else str(o),
)

# Markdown report
with open(OUT / 'B1_retrieval_recall.md', 'w') as f:
    f.write("# B1 — Vanilla HippoRAG-v2 Retrieval Recall on FC-MH 100Q\n\n")
    f.write("**Data source**: ablation B's `passages_pre_filter_chunk_ids` (= ablation A retrieval, since Phase 2 filter runs on top of identical PPR retrieval; hyperedge adds 0 edges).\n\n")
    f.write(f"Matched queries: **{results[5]['matched_queries']}/100** "
            f"(unmatched: {results[5]['unmatched_queries']})\n\n")

    f.write("## Overall — per-hop / per-query\n\n")
    f.write("| Metric | K=5 (LLM-visible) | K=10 (full retrieval) |\n|---|---|---|\n")
    f.write(f"| **B1a** New-version Recall(per-hop)         | {fmt_pair(results[5]['B1a_new_recall'])} | {fmt_pair(results[10]['B1a_new_recall'])} |\n")
    f.write(f"| **B1b** Old-version Retrieval Rate(per-hop) | {fmt_pair(results[5]['B1b_old_retrieval_rate'])} | {fmt_pair(results[10]['B1b_old_retrieval_rate'])} |\n")
    f.write(f"| **B1c** Multi-hop Path Recall(per-query,所有 hop 都 hit) | {fmt_pair(results[5]['B1c_path_recall'])} | {fmt_pair(results[10]['B1c_path_recall'])} |\n")

    for K in [5, 10]:
        r = results[K]
        f.write(f"\n## By hop count — K={K}\n\n")
        f.write("| Hop | B1a New-Recall | B1b Old-Rate | B1c Path-Recall |\n|---|---|---|---|\n")
        for h in sorted(set(list(r['by_hop_new']) + list(r['by_hop_old']) + list(r['by_hop_path']))):
            f.write(f"| {h}-hop | {fmt_pair(r['by_hop_new'].get(h,[0,0]))} | "
                    f"{fmt_pair(r['by_hop_old'].get(h,[0,0]))} | "
                    f"{fmt_pair(r['by_hop_path'].get(h,[0,0]))} |\n")

    f.write("\n## By conflict_type (B1a only) — K=10\n\n")
    f.write("| conflict_type | new-recall |\n|---|---|\n")
    for ct, p in sorted(results[10]['by_conflict_type_new'].items()):
        f.write(f"| {ct} | {fmt_pair(p)} |\n")

    f.write("\n## Reading the gap\n\n")
    n_p5 = results[5]['B1a_new_recall']
    o_p5 = results[5]['B1b_old_retrieval_rate']
    n_p10 = results[10]['B1a_new_recall']
    o_p10 = results[10]['B1b_old_retrieval_rate']
    f.write(f"- 在 K=5 LLM-visible window:**找到 new = {pct(*n_p5)},同時也撈到 old = {pct(*o_p5)}** → 兩者並存 = 髒 context\n")
    f.write(f"- 在 K=10:new = {pct(*n_p10)}, old = {pct(*o_p10)} —— B1b 高就是「沒衝突機制」的代價\n")
    f.write(f"- **B1c(完整 path 都 hit)只有 K=5 {pct(*results[5]['B1c_path_recall'])} / K=10 {pct(*results[10]['B1c_path_recall'])}** → 多跳 retrieval 完整性問題\n")

print("=== B1 retrieval recall — overall ===")
for K in [5, 10]:
    r = results[K]
    print(f"\n[K={K}] matched={r['matched_queries']}/100")
    print(f"  B1a new-recall:    {fmt_pair(r['B1a_new_recall'])}")
    print(f"  B1b old-retrieval: {fmt_pair(r['B1b_old_retrieval_rate'])}")
    print(f"  B1c path-recall:   {fmt_pair(r['B1c_path_recall'])}")
print(f"\n[wrote] {OUT}/B1_retrieval_recall.md + .json")
