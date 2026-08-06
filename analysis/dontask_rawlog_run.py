#!/usr/bin/env python3
"""Don't Ask (authors' pipeline) re-run WITH raw-output capture — gpt-4o-mini, 6k/32k.

Mirrors the committed runner
    docs/0615_intro_framework_after_problem_statement/scripts/maxserial_theircode.py
EXACTLY (same bank = analysis/results/p1_caches/extraction_cache_p1_{L}.json, same
vector top-100 retrieval, same authors' `_extract_candidates` CANDIDATE_PROMPT +
`_freshness_pick`), by IMPORTING that runner module and reusing its helpers. The ONLY
addition is a wrapper on `chat.completions.create` that records the verbatim raw LLM
output string per query, so we can persist:

    raw_llm_text          : verbatim LLM output (the JSON string it emitted)
    candidates_raw        : parsed candidate list BEFORE the schema/malformed drop
    candidates_valid      : after drop (dict has answer_entity + int serial)
    n_candidates          : len(candidates_valid)
    n_malformed_dropped   : len(candidates_raw) - len(candidates_valid)
    cand_extract_status   : ok | partial_malformed | malformed_all | empty_parse
    chosen_serial, answer, gt_answer, subem, retrieved_ords, conflict_type, query_id

GUARDRAILS: writes ONLY to `outputs/maxserial_theircode/rawlog_{L}_gpt-4o-mini_vector100.json`
(never the committed canonical `{L}_gpt-4o-mini_vector100.json`). Does not modify the
committed runner or vendored `_pipeline.py`. Never reads/prints any API key.

Usage (MABench env, repo root):
    export PIPELINE_MODEL=gpt-4o-mini
    set -a; . .env; set +a; export OPENAI_API_KEY="$OPENAI_API_KEY_A"
    python analysis/dontask_rawlog_run.py --length 6k
    python analysis/dontask_rawlog_run.py --length 32k
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "docs/0615_intro_framework_after_problem_statement/scripts"))

# Import the committed runner module verbatim (this triggers its _install_lf_stub()
# and `import _pipeline as A`, giving us the authors' exact pipeline + all helpers).
import maxserial_theircode as M   # noqa: E402
A = M.A                           # authors' vendored pipeline module


def run_length(L: str, out_path: str):
    api = os.environ.get("OPENAI_API_KEY")
    if not api:
        sys.exit("ERROR: OPENAI_API_KEY not set. `set -a; . .env; set +a; "
                 "export OPENAI_API_KEY=\"$OPENAI_API_KEY_A\"` first.")
    model = A.MODEL
    client = A.OpenAI(api_key=api)

    # ---- wrap chat.completions.create: strip authors' name= kwarg (plain SDK) AND
    #      capture the verbatim raw content for the current query ----
    holder = {"raw": None}
    _comp = client.chat.completions
    _orig = _comp.create

    def _create(*a, **kw):
        kw = {k: v for k, v in kw.items() if k != "name"}
        resp = _orig(*a, **kw)
        try:
            holder["raw"] = resp.choices[0].message.content
        except Exception:
            holder["raw"] = None
        return resp

    _comp.create = _create

    # ---- same setup as the committed runner (reuse its helpers) ----
    fact_indices, fact_texts = M.load_bank(L)
    queries = M.load_queries(L)
    bank_emb = M._load_or_build_bank_emb(client, L, fact_texts)   # uses cached npy
    q_emb = M._embed(client, [q["question"] for q in queries])
    print(f"[rawlog] bank={len(fact_texts)} queries={len(queries)} model={model} "
          f"retrieval=vector topk=100 THEIR_REPO={M.THEIR_REPO.name}")

    rows = []
    n = ncorr = hp = hpcorr = n_empty = 0
    step_stats = {}
    for i, q in enumerate(queries):
        retrieved = M.vector_retrieve(q_emb[i], bank_emb, fact_indices, fact_texts, 100)
        holder["raw"] = None
        # authors' verbatim extraction (single chat.completions.create inside)
        cands_raw = A._extract_candidates(client, q["question"], retrieved)
        raw_text = holder["raw"]
        # mirror the committed runner's malformed-schema drop
        cands = []
        for _c in cands_raw:
            if not (isinstance(_c, dict) and "answer_entity" in _c and "serial" in _c):
                continue
            try:
                _c = {**_c, "serial": int(_c["serial"])}
            except (TypeError, ValueError):
                continue
            cands.append(_c)
        n_dropped = len(cands_raw) - len(cands)
        if len(cands_raw) == 0:
            status = "empty_parse"
        elif len(cands) == 0:
            status = "malformed_all"
        elif n_dropped:
            status = "partial_malformed"
        else:
            status = "ok"
        step_stats[status] = step_stats.get(status, 0) + 1
        chosen = A._freshness_pick(cands)
        answer = (chosen["answer_entity"] if chosen else "no answer") or "no answer"
        if answer == "no answer":
            n_empty += 1
            correct = False
        else:
            correct = M.official_subem(answer, q.get("gt_answer"))
        n += 1
        ncorr += correct
        if q.get("conflict_type") == "has_pair":
            hp += 1
            hpcorr += correct
        rows.append({
            "query_id": q.get("query_id"),
            "conflict_type": q.get("conflict_type"),
            "retrieved_ords": [r["fact_idx"] for r in retrieved],
            "raw_llm_text": raw_text,
            "candidates_raw": cands_raw,
            "candidates_valid": cands,
            "n_candidates": len(cands),
            "n_malformed_dropped": n_dropped,
            "cand_extract_status": status,
            "chosen_serial": chosen["serial"] if chosen else None,
            "answer": answer,
            "gt_answer": q.get("gt_answer"),
            "subem": correct,
        })
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(queries)}")

    print(f"\n=== rawlog {L} × {model} (vector top100, official SubEM) ===")
    print(f"overall : {ncorr}/{n} ({100*ncorr/n:.1f}%)")
    print(f"has_pair: {hpcorr}/{hp} ({100*hpcorr/hp:.1f}%)")
    print(f"n_empty : {n_empty}/{n}")
    print("cand-extract step: " + " | ".join(f"{k}={v}" for k, v in sorted(step_stats.items())))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump({
        "length": L, "model": model, "source": "authors_pipeline_rawlog",
        "retrieval": "vector", "topk": 100,
        "overall": [ncorr, n], "has_pair": [hpcorr, hp], "n_empty": n_empty,
        "cand_extract_step_stats": step_stats,
        "note": "raw-capture re-run; NOT the committed canonical file",
        "rows": rows,
    }, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--length", default="6k", choices=["6k", "32k", "64k", "262k"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or str(REPO / f"outputs/maxserial_theircode/"
                          f"rawlog_{args.length}_gpt-4o-mini_vector100.json")
    # hard guard: never write the committed canonical filename
    assert "rawlog_" in os.path.basename(out), "refusing to write non-rawlog path"
    run_length(args.length, out)


if __name__ == "__main__":
    main()
