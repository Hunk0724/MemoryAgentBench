"""Detection recall by top-K candidate chains — scoring variants ablation.

Question: does path scoring change move GT chain_old / chain_new into the
top-K candidate chains? Independent of filter or LLM inference.

Per has_pair hop:
  GT_old = chain_old_matches[0].prop_id
  GT_new = chain_new_matches[0].prop_id
  union_K = ∪{chain.proposition_ids for chain in top-K candidate chains}

Metrics(per K):
  chain_old@K        = % has_pair hops with GT_old in union_K
  chain_new@K        = % has_pair hops with GT_new in union_K
  either-side@K      = % with at least one of them in union_K
                       (bidir-feasibility — verdict can fire if either side
                        in candidate chain + the other in related pool)
  both@K             = % with BOTH in union_K (strict — old AND new same time)

Broken down by hop count (2/3/4-hop queries).

Runs compared(supplied as args; loads each one's phase2_w13_dump.jsonl):
  - prior B (adhoc, bidir=OFF):       monitoring_logs/2026-05-17_182907_ablation_B/
  - T1-proprag-strict (proprag, off): monitoring_logs/2026-05-26_233338_T1_proprag_strict_bidir-off/
  - T1-pure-relevance (pure, off):    monitoring_logs/2026-05-27_000617_T1_pure_relevance_bidir-off/  (after run completes)

Limitation: dumps have M=5 chains (capped). Top-K only meaningful for K ≤ 5.
For K ∈ {7, 10}, need rerun with bigger M (out of scope here).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")


def normalize_query(q: str) -> str:
    p = "Based on the provided Knowledge Pool, "
    if q.startswith(p):
        q = q[len(p):]
    q = q.split("\nAnswer:")[0]
    return q.strip().rstrip("?").strip().lower()


def load_dump(path: Path) -> dict:
    """Returns dict: normalized_query → dump entry."""
    out = {}
    with open(path) as f:
        for line in f:
            e = json.loads(line)
            if e.get("phase2_status") != "RAN":
                continue
            out[normalize_query(e["query"])] = e
    return out


def union_props_top_K(chains: list, K: int) -> set[str]:
    """chains is dump['chains'], list sorted by score desc (capped at M).
    Returns union of prop_ids across top-K chains."""
    if not chains:
        return set()
    s: set[str] = set()
    for c in chains[:K]:
        s.update(c.get("proposition_ids", []))
    return s


def compute_recall(dump: dict, labels: list, K_list: list[int]) -> dict:
    """Returns metrics dict.

    Per K:
      'chain_old_at_K'[K], 'chain_new_at_K'[K], 'either_at_K'[K], 'both_at_K'[K]
      with same broken down by num_hops:
      'by_hop'[K][num_hops] = {old, new, either, both, total}
    """
    out: dict = {
        "total_has_pair_hops": 0,
        "matched_queries": 0,
        "unmatched_queries": 0,
        "K_list": K_list,
        "chain_old_at_K": {K: 0 for K in K_list},
        "chain_new_at_K": {K: 0 for K in K_list},
        "either_at_K": {K: 0 for K in K_list},
        "both_at_K": {K: 0 for K in K_list},
        "by_hop": {K: defaultdict(lambda: {"old": 0, "new": 0, "either": 0, "both": 0, "total": 0})
                   for K in K_list},
    }

    for q in labels:
        nq = normalize_query(q["question"])
        if nq not in dump:
            out["unmatched_queries"] += 1
            continue
        out["matched_queries"] += 1
        entry = dump[nq]
        chains = entry.get("chains", [])
        nh = q["num_hops"]

        for hop in q["hops"]:
            if hop["conflict_type"] != "has_pair":
                continue
            if not (hop["chain_old_matches"] and hop["chain_new_matches"]):
                continue
            gt_old = hop["chain_old_matches"][0]["prop_id"]
            gt_new = hop["chain_new_matches"][0]["prop_id"]
            out["total_has_pair_hops"] += 1

            for K in K_list:
                u = union_props_top_K(chains, K)
                in_old = gt_old in u
                in_new = gt_new in u
                in_either = in_old or in_new
                in_both = in_old and in_new

                if in_old:
                    out["chain_old_at_K"][K] += 1
                if in_new:
                    out["chain_new_at_K"][K] += 1
                if in_either:
                    out["either_at_K"][K] += 1
                if in_both:
                    out["both_at_K"][K] += 1

                d = out["by_hop"][K][nh]
                d["total"] += 1
                d["old"] += int(in_old)
                d["new"] += int(in_new)
                d["either"] += int(in_either)
                d["both"] += int(in_both)

    return out


def fmt_pct(n: int, d: int) -> str:
    return f"{100*n/d:.1f}%" if d else "n/a"


def print_summary(label: str, metrics: dict):
    T = metrics["total_has_pair_hops"]
    print(f"\n=== {label} (has_pair hops = {T}, matched queries = "
          f"{metrics['matched_queries']}/{metrics['matched_queries']+metrics['unmatched_queries']}) ===")
    print(f"{'K':>3} | {'chain_old':>10} | {'chain_new':>10} | "
          f"{'either':>10} | {'both':>10}")
    print("-" * 60)
    for K in metrics["K_list"]:
        c_old = metrics["chain_old_at_K"][K]
        c_new = metrics["chain_new_at_K"][K]
        eit = metrics["either_at_K"][K]
        bot = metrics["both_at_K"][K]
        print(f"{K:>3} | {fmt_pct(c_old, T):>10} | {fmt_pct(c_new, T):>10} | "
              f"{fmt_pct(eit, T):>10} | {fmt_pct(bot, T):>10}")

    print("\nBy hop count (either-side recall at K=5):")
    header_parts = [f"{'hops':>5}", f"{'n_hops':>7}"] + [f"K={K}".rjust(8) for K in metrics["K_list"]]
    print(" | ".join(header_parts))
    for h in sorted(metrics["by_hop"][metrics["K_list"][0]].keys()):
        row = [f"{h:>4}-h"]
        row.append(f"{metrics['by_hop'][metrics['K_list'][0]][h]['total']:>7}")
        for K in metrics["K_list"]:
            d = metrics["by_hop"][K][h]
            row.append(f"{fmt_pct(d['either'], d['total']):>8}")
        print(" | ".join(row))


def main():
    K_list = [1, 3, 5]  # M=5 cap in current dumps

    labels = json.load(open(BASE / "analysis/results/full100_eval/labels.json"))

    runs = {
        "prior B (adhoc, bidir=OFF)":
            BASE / "monitoring_logs/2026-05-17_182907_ablation_B/phase2_w13_dump.jsonl",
        "T1-proprag-strict (bidir=OFF)":
            BASE / "monitoring_logs/2026-05-26_233338_T1_proprag_strict_bidir-off/phase2_w13_dump.jsonl",
    }
    # T1-pure-relevance dump if exists
    pure_path = BASE / "monitoring_logs/2026-05-27_000617_T1_pure_relevance_bidir-off/phase2_w13_dump.jsonl"
    if pure_path.exists():
        runs["T1-pure-relevance (bidir=OFF)"] = pure_path

    all_metrics = {}
    for label, dump_path in runs.items():
        if not dump_path.exists():
            print(f"[skip] {label} — dump not found at {dump_path}")
            continue
        dump = load_dump(dump_path)
        metrics = compute_recall(dump, labels, K_list)
        all_metrics[label] = metrics

    print("\n" + "=" * 70)
    print("DETECTION RECALL BY TOP-K CANDIDATE CHAINS")
    print("Metric: % has_pair hops with GT prop_id in union of top-K chains")
    print("=" * 70)

    for label, m in all_metrics.items():
        print_summary(label, m)

    # Direct comparison table (either-side @ K=5)
    print("\n\n=== Cross-run COMPARISON: either-side recall @ K=5, by hop count ===")
    label_list = list(all_metrics.keys())
    print(f"{'hops':>5} | {'n':>4} | " + " | ".join(f"{l[:30]:>30}" for l in label_list))
    if label_list:
        hops = sorted(all_metrics[label_list[0]]["by_hop"][5].keys())
        for h in hops:
            n = all_metrics[label_list[0]]["by_hop"][5][h]["total"]
            row = [f"{h:>4}-h", f"{n:>4}"]
            for label in label_list:
                d = all_metrics[label]["by_hop"][5][h]
                row.append(f"{fmt_pct(d['either'], d['total']):>30}")
            print(" | ".join(row))

    out_json = BASE / "analysis/results/paper_narrative/detection_recall_by_K.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    json.dump({k: {kk: (dict(vv) if hasattr(vv, "items") else vv)
                    for kk, vv in m.items()}
               for k, m in all_metrics.items()},
              open(out_json, "w"), indent=2, default=str)
    print(f"\n[wrote] {out_json}")


if __name__ == "__main__":
    main()
