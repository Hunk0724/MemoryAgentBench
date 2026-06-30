"""Diagnose where GT chain_old/chain_new prop is lost in beam search pipeline.

For each has_pair hop, the GT prop should ideally be in candidate chain.
The 26pp attrition (active 94% → chain 67%) breaks into:

  Stage ① Active region: prop in top-50 by prop_ppr_mass?
  Stage ② Seed selection: prop one of top-n_seed (capped to beam_width)?
            ↪ caller-internal info; we infer by mass ranking within active_pids
  Stage ③ Expansion connectivity: does prop have entity-overlap with ANY
          chain prop?
            ↪ if no → expansion connectivity rule (substring entity overlap)
              can never reach this prop from any seed
  Stage ④ Beam pruning / scoring rank: prop connected to chains but not in
          top-M scored chains
            ↪ residual category — beam_width / M / scoring rejection

Categorization (priority order):
  - if GT not in active_pids                          → A. LOST_ACTIVE
  - else if GT in chain_pid_union                     → Z. IN_CHAIN (passed)
  - else if no chain prop has entity overlap with GT  → C. LOST_CONNECTIVITY
  - else                                              → D. LOST_BEAM_OR_SCORE

Reports both for chain_old and chain_new GT, and for either-side.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")


def normalize_query(q: str) -> str:
    p = "Based on the provided Knowledge Pool, "
    if q.startswith(p):
        q = q[len(p):]
    q = q.split("\nAnswer:")[0]
    return q.strip().rstrip("?").strip().lower()


def _norm_entity(e: str) -> str:
    return re.sub(r"\s+", " ", (e or "").strip().lower())


def has_entity_overlap(a_entities: list, b_entities: list, min_len: int = 3) -> bool:
    """Same lenient match rule as path_enumeration._entity_overlap."""
    a_norm = {_norm_entity(e) for e in a_entities if len(e) >= min_len}
    b_norm = {_norm_entity(e) for e in b_entities if len(e) >= min_len}
    for ea in a_norm:
        for eb in b_norm:
            if ea == eb or ea in eb or eb in ea:
                return True
    return False


def load_dump(path: Path) -> dict:
    out = {}
    with open(path) as f:
        for line in f:
            e = json.loads(line)
            if e.get("phase2_status") != "RAN":
                continue
            out[normalize_query(e["query"])] = e
    return out


def categorize(
    gt_pid: str,
    gt_prop: dict,
    active_pids: set,
    chain_pid_union: set,
    chain_props: list,
    prop_idx: dict,
) -> str:
    """Return one of: LOST_ACTIVE / IN_CHAIN / LOST_CONNECTIVITY / LOST_BEAM_OR_SCORE."""
    if gt_pid not in active_pids:
        return "LOST_ACTIVE"
    if gt_pid in chain_pid_union:
        return "IN_CHAIN"
    # In active but not in chain — check connectivity to ANY chain prop
    gt_entities = gt_prop.get("entities", []) if gt_prop else []
    if not chain_props:
        return "LOST_CONNECTIVITY"
    for cp in chain_props:
        cp_entities = cp.get("entities", []) if cp else []
        if has_entity_overlap(gt_entities, cp_entities):
            return "LOST_BEAM_OR_SCORE"
    return "LOST_CONNECTIVITY"


def main():
    labels = json.load(open(BASE / "analysis/results/full100_eval/labels.json"))
    prop_idx_path = (
        BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/"
        "chunksize_512/context_id_0/"
        "gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json"
    )
    prop_idx = {p["id"]: p for p in json.load(open(prop_idx_path))["propositions"]}

    runs = {
        "prior B (adhoc, bidir=OFF)":
            BASE / "monitoring_logs/2026-05-17_182907_ablation_B/phase2_w13_dump.jsonl",
        "T1-pure-relevance (bidir=OFF)":
            BASE / "monitoring_logs/2026-05-27_000617_T1_pure_relevance_bidir-off/phase2_w13_dump.jsonl",
        "T1-proprag-strict (bidir=OFF)":
            BASE / "monitoring_logs/2026-05-26_233338_T1_proprag_strict_bidir-off/phase2_w13_dump.jsonl",
    }

    all_results: dict = {}

    for label, dump_path in runs.items():
        if not dump_path.exists():
            print(f"[skip] {label}")
            continue
        dump = load_dump(dump_path)

        # Per-side accumulators (chain_old, chain_new, either)
        cats_old = defaultdict(int)
        cats_new = defaultdict(int)
        by_hop = defaultdict(lambda: defaultdict(int))   # by_hop[nh][category] for old
        by_hop_new = defaultdict(lambda: defaultdict(int))  # by_hop[nh][category] for new
        total = 0
        unmatched = 0

        for q in labels:
            nq = normalize_query(q["question"])
            if nq not in dump:
                unmatched += 1
                continue
            entry = dump[nq]
            active_pids = set(entry.get("active_pids", []))
            chains = entry.get("chains", [])
            chain_pid_union = set()
            chain_props_list = []  # collect chain props for entity overlap test
            for c in chains:
                for pid in c.get("proposition_ids", []):
                    chain_pid_union.add(pid)
                    if pid in prop_idx:
                        chain_props_list.append(prop_idx[pid])
            nh = q["num_hops"]

            for hop in q["hops"]:
                if hop["conflict_type"] != "has_pair":
                    continue
                if not (hop["chain_old_matches"] and hop["chain_new_matches"]):
                    continue
                gt_old_pid = hop["chain_old_matches"][0]["prop_id"]
                gt_new_pid = hop["chain_new_matches"][0]["prop_id"]
                total += 1

                cat_old = categorize(
                    gt_old_pid, prop_idx.get(gt_old_pid),
                    active_pids, chain_pid_union, chain_props_list, prop_idx,
                )
                cat_new = categorize(
                    gt_new_pid, prop_idx.get(gt_new_pid),
                    active_pids, chain_pid_union, chain_props_list, prop_idx,
                )
                cats_old[cat_old] += 1
                cats_new[cat_new] += 1
                by_hop[nh][cat_old] += 1
                by_hop_new[nh][cat_new] += 1

        all_results[label] = {
            "total_has_pair_hops": total,
            "unmatched_queries": unmatched,
            "cats_old": dict(cats_old),
            "cats_new": dict(cats_new),
            "by_hop_old": {k: dict(v) for k, v in by_hop.items()},
            "by_hop_new": {k: dict(v) for k, v in by_hop_new.items()},
        }

    # Pretty print
    print("\n" + "=" * 80)
    print("BEAM SEARCH ATTRITION STAGE DIAGNOSTIC")
    print("=" * 80)
    cats_order = ["IN_CHAIN", "LOST_ACTIVE", "LOST_CONNECTIVITY", "LOST_BEAM_OR_SCORE"]

    for label, r in all_results.items():
        T = r["total_has_pair_hops"]
        print(f"\n=== {label} (n={T}) ===")
        print(f"\n[chain_OLD GT in each stage]")
        print(f"{'Category':<22} | {'count':>6} | {'pct':>7}")
        for cat in cats_order:
            n = r["cats_old"].get(cat, 0)
            print(f"  {cat:<20} | {n:>6} | {100*n/max(T,1):>6.1f}%")
        print(f"\n[chain_NEW GT in each stage]")
        print(f"{'Category':<22} | {'count':>6} | {'pct':>7}")
        for cat in cats_order:
            n = r["cats_new"].get(cat, 0)
            print(f"  {cat:<20} | {n:>6} | {100*n/max(T,1):>6.1f}%")

        # By hop count
        print(f"\n[chain_OLD by hop count — LOST_* breakdown]")
        hop_list = sorted(r["by_hop_old"].keys())
        header = [f"{'hop':>5}", f"{'n':>4}"] + [f"{c.replace('LOST_','L_'):>16}" for c in cats_order]
        print(" | ".join(header))
        for h in hop_list:
            d = r["by_hop_old"][h]
            n = sum(d.values())
            row = [f"{h:>4}-h", f"{n:>4}"] + [f"{d.get(c, 0):>5} ({100*d.get(c,0)/max(n,1):>5.1f}%)" for c in cats_order]
            print(" | ".join(row))

    # Cross-run comparison: chain_old categorization
    print("\n\n" + "=" * 80)
    print("CROSS-RUN COMPARISON: chain_old attrition stage (%)")
    print("=" * 80)
    labels_list = list(all_results.keys())
    header = [f"{'Category':<22}"] + [f"{l[:24]:>26}" for l in labels_list]
    print(" | ".join(header))
    for cat in cats_order:
        row = [f"{cat:<22}"]
        for label in labels_list:
            T = all_results[label]["total_has_pair_hops"]
            n = all_results[label]["cats_old"].get(cat, 0)
            row.append(f"{n:>3} ({100*n/max(T,1):>5.1f}%)".rjust(26))
        print(" | ".join(row))

    out = BASE / "analysis/results/paper_narrative/beam_attrition_diagnostic.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(all_results, open(out, "w"), indent=2, default=str)
    print(f"\n[wrote] {out}")


if __name__ == "__main__":
    main()
