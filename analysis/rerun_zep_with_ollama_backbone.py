"""Post-hoc Zep answer LLM swap — read Mac's cached Zep per-qid, swap answer
LLM to Ollama backbone (gemma3-Xb / other local model).

Path A (recommended for GX10 weak-model Zep runs; see
paper_current/gx10_backbone_gotchas.md §3.2).

Approach:
  1. For each qid, read Mac's cached per-qid JSON at
     outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_{L}/
     chunksize_512/query_{qid}_context_0.json
  2. Recompose the Zep context using the same TEMPLATE as production
     (methods/zep.py — facts + entities + episodes + context_block)
  3. Call Ollama with `--model gemma3:{size}` as the answer LLM (via OpenAI-
     compatible endpoint at http://localhost:11434/v1)
  4. Save output in MAB-compatible per-qid + aggregated format
  5. Compute EM per MAB `default_post_process` (max of raw / parsed EM)

Why this is preferred over from-scratch (path B):
  - 0 Zep add_memory API calls (no cost)
  - 0 × 360s async waits (graphs already processed by Mac)
  - Same Zep memory across backbones → fair comparison
  - No ZEP_API_KEY needed on GX10

Requirements on GX10:
  - Ollama server running (default http://localhost:11434)
  - gemma3:{1b|4b|12b|27b} model pulled (`ollama pull gemma3:12b`)
  - Mac's Structure_rag_zep per-qid directory synced (already in git after Mac's
    gpt-4o-mini Zep runs)
  - MABench conda env activated (has openai package + tiktoken)

Usage:
    python analysis/rerun_zep_with_ollama_backbone.py \\
        --length 6k --backbone gemma3:12b --limit 5     # smoke
    python analysis/rerun_zep_with_ollama_backbone.py \\
        --length 6k --backbone gemma3:12b               # full
    python analysis/rerun_zep_with_ollama_backbone.py \\
        --length 32k --backbone gemma3:4b --num-ctx 8192

Cost: 0 (Ollama local). Time: N queries × (Ollama latency + retrieval-none).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from methods.zep import TEMPLATE  # noqa: E402 — same context template as prod Zep
from utils.eval_other_utils import (  # noqa: E402
    parse_output, drqa_exact_match_score, drqa_metric_max_over_ground_truths,
)


def compose_context(edges, nodes, episodes, context_block=None):
    """Same shape as methods/zep.py::compose_search_context but takes lists of
    serialized dicts from Mac's cached per-qid file (not zep_cloud objects).
    """
    edges = edges or []
    nodes = nodes or []
    episodes = episodes or []

    def _range(e):
        valid = e.get("valid_at") or "date unknown"
        invalid = e.get("invalid_at") or "present"
        if valid == "None":
            valid = "date unknown"
        if invalid == "None":
            invalid = "present"
        return f"{valid} - {invalid}"

    facts = [f'  - {e.get("fact","")} ({_range(e)})' for e in edges if e]
    entities = [f'  - {n.get("name","")}: {n.get("summary","")}' for n in nodes if n]
    ep_lines = [f'  - Content: {ep.get("content","")}' for ep in episodes if ep]
    ctx = TEMPLATE.format(
        facts="\n".join(facts),
        entities="\n".join(entities),
        episodes="\n".join(ep_lines),
    )
    if context_block:
        ctx = f"{ctx}\n{context_block}\n"
    return ctx


def ollama_answer(model, num_ctx, system_prompt, user_content):
    """Call Ollama via OpenAI-compatible endpoint. num_ctx must be set via
    `extra_body.options` since the OpenAI-compat surface doesn't expose it."""
    from openai import OpenAI
    client = OpenAI(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",  # dummy — Ollama ignores
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=256,
        extra_body={"options": {"num_ctx": num_ctx}} if num_ctx else None,
    )
    return resp.choices[0].message.content or ""


def em_check(response, gt_answer):
    """MAB official: max(EM(raw), EM(parse_output(raw)))."""
    if response is None or gt_answer is None:
        return False, False
    resp_str = str(response)
    raw_em = bool(drqa_metric_max_over_ground_truths(
        drqa_exact_match_score, resp_str, gt_answer))
    parsed = parse_output(resp_str)
    parsed_em = False
    if parsed is not None:
        parsed_em = bool(drqa_metric_max_over_ground_truths(
            drqa_exact_match_score, parsed, gt_answer))
    from utils.eval_other_utils import substring_exact_match_score
    raw_sem = bool(drqa_metric_max_over_ground_truths(
        substring_exact_match_score, resp_str, gt_answer))
    parsed_sem = False
    if parsed is not None:
        parsed_sem = bool(drqa_metric_max_over_ground_truths(
            substring_exact_match_score, parsed, gt_answer))
    return (raw_em or parsed_em), (raw_sem or parsed_sem)


ANSWER_SYSTEM = (
    "You are a helpful expert assistant answering questions from users based on "
    "the provided context."
)

ANSWER_USER_TEMPLATE = """
Your task is to briefly answer the question. You are given the following context
from the previous conversation. If you don't know how to answer the question,
abstain from answering.

{context}

{question}

Answer:
"""


def load_zep_agg(length):
    """Prefer canonical Zep aggregated (size256 chunk_512)."""
    root = REPO / "outputs/gpt-4o-mini-zep/Conflict_Resolution"
    import glob
    for pat in ("size256_shots0_max_samplesunknown", "size256_shots0_max_samples1"):
        for f in sorted(glob.glob(str(root / f"factconsolidation_sh_{length}_*{pat}*_chunk512_results.json"))):
            try:
                d = json.load(open(f))
                if len(d.get("data", [])) >= 50:
                    return d, f
            except Exception:
                continue
    raise FileNotFoundError(f"no canonical Zep aggregated for {length}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--length", choices=["6k", "32k", "64k"], required=True)
    p.add_argument("--backbone", required=True,
                   help="Ollama model, e.g. 'gemma3:12b'")
    p.add_argument("--num-ctx", type=int, default=8192,
                   help="Ollama num_ctx (default 8192; increase for long context)")
    p.add_argument("--limit", type=int, default=None, help="Smoke: only run first N qids")
    p.add_argument("--out-agent-name",
                   help="Output agent_name. Default: gemma3-<size>-zep or "
                        "based on --backbone (e.g. gemma3:12b -> gemma3-12b-zep)")
    args = p.parse_args()

    L = args.length
    per_qid_dir = REPO / f"outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_{L}/chunksize_512"
    if not per_qid_dir.exists():
        raise FileNotFoundError(f"Mac's Zep per-qid missing: {per_qid_dir}. "
                                "Sync git repo or check gpt-4o-mini Zep was run.")

    zep_agg, agg_path = load_zep_agg(L)
    print(f"[load] agg {os.path.relpath(agg_path, REPO)}  n_data={len(zep_agg['data'])}")

    qid_map = {d["query_id"]: (d.get("query", ""), d.get("answer", []))
               for d in zep_agg["data"]}

    out_agent = args.out_agent_name or (
        args.backbone.replace(":", "-") + "-zep"
    )
    per_qid_out = REPO / f"outputs/rag_retrieved/Structure_rag_{out_agent}/k_10/factconsolidation_sh_{L}/chunksize_512"
    per_qid_out.mkdir(parents=True, exist_ok=True)

    results = []
    t0 = time.time()
    for qid, (message, gt_list) in sorted(qid_map.items()):
        if args.limit is not None and qid >= args.limit:
            break
        pqf = per_qid_dir / f"query_{qid}_context_0.json"
        if not pqf.exists():
            print(f"  qid={qid} SKIP (missing per-qid)"); continue
        d = json.load(open(pqf))
        edges = d.get("edges", [])
        nodes = d.get("nodes", [])
        episodes = d.get("episodes", [])
        ctx_block = d.get("context_block", "") or ""
        context = compose_context(edges, nodes, episodes, ctx_block)
        user_prompt = ANSWER_USER_TEMPLATE.format(context=context, question=message)

        try:
            resp = ollama_answer(args.backbone, args.num_ctx, ANSWER_SYSTEM, user_prompt)
        except Exception as e:
            print(f"  qid={qid} ERROR: {e.__class__.__name__}: {e}")
            continue

        em, sem = em_check(resp, gt_list)
        results.append({
            "query_id": qid,
            "qa_pair_id": f"factconsolidation_sh_{L}_no{qid}",
            "output": resp,
            "parsed_output": parse_output(resp) or resp,
            "answer": gt_list,
            "exact_match": em,
            "substring_exact_match": sem,
            "n_edges": len(edges),
            "n_nodes": len(nodes),
            "n_episodes": len(episodes),
        })
        # Per-qid save (mirrors production Zep per-qid format + response)
        json.dump({
            "retrieved_context_paragraphs": [p for p in context.split("\n") if p.strip()],
            "edges": edges,     # unchanged from Mac's cache
            "nodes": nodes,
            "episodes": episodes,
            "context_block": ctx_block,
            "response": resp,
        }, open(per_qid_out / f"query_{qid}_context_0.json", "w"),
            ensure_ascii=False, indent=2)

        if qid % 10 == 0:
            print(f"  qid={qid} EM={int(em)} sEM={int(sem)}  elapsed={time.time()-t0:.0f}s")

    n = len(results)
    n_em = sum(1 for r in results if r["exact_match"])
    n_sem = sum(1 for r in results if r["substring_exact_match"])
    print(f"\n=== {args.backbone} × Zep × {L} — n={n} ===")
    if n:
        print(f"  EM  = {n_em}/{n} ({100*n_em/n:.1f}%)")
        print(f"  sEM = {n_sem}/{n} ({100*n_sem/n:.1f}%)")

    # Aggregated MAB-compat file
    out_agg_dir = REPO / f"outputs/{out_agent}/Conflict_Resolution"
    out_agg_dir.mkdir(parents=True, exist_ok=True)
    tag = "size256_shots0_max_samplesunknown" if args.limit is None else f"size{args.limit}_smoke"
    stem = f"factconsolidation_sh_{L}_unknown_backbone_swap_{tag}_k10_chunk512_results.json"
    out_file = out_agg_dir / stem
    json.dump({
        "agent_config": {
            "name": out_agent,
            "source_zep_run": os.path.relpath(agg_path, REPO),
            "diagnostic": "backbone_answer_swap",
            "answer_llm_backbone": args.backbone,
            "num_ctx": args.num_ctx,
            "temperature": 0.0,
        },
        "data": results,
        "averaged_metrics": {
            "exact_match": (100 * n_em / n) if n else 0.0,
            "substring_exact_match": (100 * n_sem / n) if n else 0.0,
        },
    }, open(out_file, "w"), ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
