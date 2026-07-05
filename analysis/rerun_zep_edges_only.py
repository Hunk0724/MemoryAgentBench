"""Post-hoc diagnostic: Zep(only-return-fact) — rerun answer LLM with edges-only context.

Motivation
==========
Current Zep(k=10) crosstab: PP-Both dominates (93-97% share); Acc-in-bucket
55-72% at 6k/64k, catastrophic 6% at 32k. Two possible failure modes:
  (A) No query-time KU: edges themselves don't resolve new vs old versions;
      LLM must pick from top-k mixed edges.
  (B) Multi-granularity distraction: nodes/episodes/context_block clutter the
      answer LLM's judgment.

This script isolates (A) by removing (B): rerender the prompt with FACTS only,
same edges as production, then call gpt-4o-mini and re-measure EM.

Pool-state (PP-New/PP-Both/...) is UNCHANGED (same edges) — only Acc-in-bucket
can shift. If Acc-in-bucket rises significantly → (B) contributed.
If unchanged → (A) is dominant (Zep has no query-time KU, period).

Data
====
Reuses cached `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_{L}/
chunksize_512/query_*_context_*.json` (edges list from graph.search).

Aggregated Zep result (`outputs/gpt-4o-mini-zep/Conflict_Resolution/*.json`) provides
the per-qid `query` (message to answer LLM) and `answer` (GT list).

Output
======
- Per-qid: `outputs/rag_retrieved/Structure_rag_zep-edges-only/k_10/.../query_*.json`
- Aggregated: `outputs/gpt-4o-mini-zep-edges-only/Conflict_Resolution/*_edges_only_*_results.json`

Cost: ~74/65/66 gpt-4o-mini calls per length. Full 3-length ≈ 205 calls (~$0.30).

Env: OPENAI_API_KEY must be set (source your usual .sh).
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from methods.zep import TEMPLATE, llm_response, OpenAIAgent  # noqa: E402


def compose_facts_only(edges: list[dict]) -> str:
    """Render TEMPLATE with FACTS only (entities/episodes suppressed).

    Matches `methods/zep.py::format_edge_date_range` string form.
    """
    edges = edges or []
    facts = []
    for e in edges:
        valid = e.get("valid_at") or "date unknown"
        invalid = e.get("invalid_at") or "present"
        # NOTE: original format used `edge.valid_at` object; we already stringified in
        # agent.py::_serialize_edges (see L1231-1233). "None" string → treat as absent.
        if valid == "None":
            valid = "date unknown"
        if invalid == "None":
            invalid = "present"
        facts.append(f'  - {e.get("fact","")} ({valid} - {invalid})')
    return TEMPLATE.format(facts="\n".join(facts), entities="", episodes="")


def load_agg(length: str) -> tuple[dict, Path]:
    zep_agg_dir = REPO / "outputs/gpt-4o-mini-zep/Conflict_Resolution"
    # Prefer the standard size256 unknown pattern
    candidates = sorted(
        zep_agg_dir.glob(f"factconsolidation_sh_{length}_*size256*_chunk512_results.json")
    )
    if not candidates:
        candidates = sorted(zep_agg_dir.glob(f"factconsolidation_sh_{length}_*_chunk512_results.json"))
    if not candidates:
        raise FileNotFoundError(f"No Zep aggregated file for {length}")
    # Pick the largest n_data
    best = None
    best_n = -1
    for c in candidates:
        try:
            d = json.load(open(c))
            n = len(d.get("data", []))
            if n > best_n:
                best_n = n
                best = c
        except Exception:
            continue
    return json.load(open(best)), best


def em_check(response: str, gt_list: list) -> tuple[bool, bool]:
    r = (response or "").strip().lower()
    gts = [str(g).strip().lower() for g in (gt_list or [])]
    exact = any(r == g for g in gts)
    substring = any(g and g in r for g in gts)
    return exact, substring


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--length", choices=["6k", "32k", "64k"], required=True)
    p.add_argument("--limit", type=int, default=None,
                   help="Only run first N qids (smoke test)")
    p.add_argument("--out-agent", default="gpt-4o-mini-zep-edges-only")
    args = p.parse_args()

    L = args.length
    sub_ds = f"factconsolidation_sh_{L}"
    per_qid_dir = REPO / f"outputs/rag_retrieved/Structure_rag_zep/k_10/{sub_ds}/chunksize_512"
    if not per_qid_dir.exists():
        raise FileNotFoundError(f"Zep per-qid folder missing: {per_qid_dir}")

    agg, agg_path = load_agg(L)
    print(f"[load] agg: {agg_path.name}  n_data={len(agg['data'])}")

    qid_map = {d["query_id"]: (d["query"], d.get("answer", [])) for d in agg["data"]}

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠ OPENAI_API_KEY not in env — call will fail. Source your keys .sh first.")

    llm_agent = OpenAIAgent(model="gpt-4o-mini", source="openai", api_dict={}, temperature=0.0)

    per_qid_out = (
        REPO
        / f"outputs/rag_retrieved/Structure_rag_zep-edges-only/k_10/{sub_ds}/chunksize_512"
    )
    per_qid_out.mkdir(parents=True, exist_ok=True)

    results = []
    t0 = time.time()
    for qid, (msg, gt_list) in sorted(qid_map.items()):
        if args.limit is not None and qid >= args.limit:
            break
        pfile = per_qid_dir / f"query_{qid}_context_0.json"
        if not pfile.exists():
            print(f"  qid={qid} SKIP: {pfile.name} missing")
            continue
        d = json.load(open(pfile))
        edges = d.get("edges", [])
        context = compose_facts_only(edges)
        try:
            resp = asyncio.run(llm_response(llm_agent, context, msg))
        except Exception as e:
            print(f"  qid={qid} ERROR: {e.__class__.__name__}: {e}")
            continue
        em, sem = em_check(resp, gt_list)
        results.append({
            "query_id": qid,
            "qa_pair_id": f"{sub_ds}_no{qid}",
            "output": resp,
            "parsed_output": resp,
            "answer": gt_list,
            "exact_match": em,
            "substring_exact_match": sem,
            "n_edges": len(edges),
        })
        json.dump({
            "retrieved_context_paragraphs": [p for p in context.split("\n") if p.strip()],
            "edges": edges,
            "nodes": [],  # SUPPRESSED
            "episodes": [],  # SUPPRESSED
            "context_block": "",  # SUPPRESSED
            "response": resp,
        }, open(per_qid_out / f"query_{qid}_context_0.json", "w"),
            ensure_ascii=False, indent=2)
        if qid % 10 == 0:
            elapsed = time.time() - t0
            print(f"  qid={qid} EM={int(em)} sEM={int(sem)}  elapsed={elapsed:.0f}s")

    n = len(results)
    n_em = sum(1 for r in results if r["exact_match"])
    n_sem = sum(1 for r in results if r["substring_exact_match"])

    print()
    print(f"=== Zep(edges-only) {L} — n={n} ===")
    if n:
        print(f"  EM  = {n_em}/{n}  ({100*n_em/n:.1f}%)")
        print(f"  sEM = {n_sem}/{n}  ({100*n_sem/n:.1f}%)")

    # Compare to production Zep on same qid set
    prod = [d for d in agg["data"] if (args.limit is None or d["query_id"] < args.limit)]
    p_em = sum(1 for d in prod if d.get("exact_match"))
    p_sem = sum(1 for d in prod if d.get("substring_exact_match"))
    print(f"  vs prod Zep: EM={p_em}/{len(prod)} ({100*p_em/len(prod):.1f}%)  "
          f"sEM={p_sem}/{len(prod)} ({100*p_sem/len(prod):.1f}%)")

    out_agg_dir = REPO / f"outputs/{args.out_agent}/Conflict_Resolution"
    out_agg_dir.mkdir(parents=True, exist_ok=True)
    tag = "size256_shots0_max_samplesunknown" if args.limit is None else f"size{args.limit}_smoke"
    stem = f"factconsolidation_sh_{L}_unknown_edges_only_{tag}_k10_chunk512_results.json"
    out_file = out_agg_dir / stem
    json.dump({
        "agent_config": {
            "name": args.out_agent,
            "source_agent": "Structure_rag_zep",
            "diagnostic": "edges_only",
            "answer_llm": "gpt-4o-mini",
            "temperature": 0.0,
        },
        "source_zep_result": agg_path.name,
        "data": results,
        "averaged_metrics": {
            "exact_match": (100 * n_em / n) if n else 0.0,
            "substring_exact_match": (100 * n_sem / n) if n else 0.0,
        },
    }, open(out_file, "w"), ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
