#!/usr/bin/env python3
"""maxserial_fc — reconstruction of "Don't Ask the LLM to Track Freshness"
(Reddy & Challaram, 2026, arXiv 2606.01435) as an FC-SH baseline.

Pipeline (paper §3.1) = BM25 top-10 -> LLM candidate extraction -> Python
max(serial).entity. NO answer-LLM freshness reasoning (that is the point).

Alignment choices (confirmed with the user, 2026-07):
  - fact bank      = OURS' P1 extraction (extraction_cache_p1_<L>.json), i.e.
                     extraction-controlled (like baseline `b`), NOT the raw
                     numbered FC facts.
  - freshness sig  = OURS' ingestion ORDINAL (= running index over the bank in
                     ingestion/context order; validated new_ord>old_ord on 62/62
                     6k has_pair pairs), NOT the in-text serial.
  - retrieval      = BM25 top-10 (paper), rank_bm25 BM25Okapi k1=1.5 b=0.75.
  - metric         = benchmark SubEM (utils.eval_other_utils, same as MAB).
  So this is the paper's RETRIEVAL+RESOLUTION mechanism over ours' bank+ordinal
  -> an aligned baseline (will NOT reproduce the paper's 71/78/81, which uses
  raw serials + raw facts). See narrative_chain / positioning notes.

The candidate-extraction prompt is a faithful RECONSTRUCTION from the paper's
description (§3.1/§3.3/§6.1); the authors' repo is 404 (not open despite the
paper's claim). Faithfulness is checked against observable behaviours
(~2% empty extraction, no prior-override).

Usage:
  # non-LLM sanity (no API key needed): BM25 retrieval recall + plumbing
  python maxserial_fc.py --length 6k --sanity
  # full run (needs OPENAI_API_KEY in env; user sources .env):
  set -a; . .env; set +a; export OPENAI_API_KEY="$OPENAI_API_KEY_A"
  python maxserial_fc.py --length 6k --model gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

_TOK = re.compile(r"[A-Za-z0-9]+")


def tokenize(s: str):
    return _TOK.findall((s or "").lower())


# ── data ────────────────────────────────────────────────────────────────────
def load_bank(length: str):
    """Bank = ours' P1 extraction, flattened in insertion (=ingestion) order.
    ordinal = running index. Returns list[(ordinal:int, fact:str)]."""
    p = REPO / f"analysis/results/p1_caches/extraction_cache_p1_{length}.json"
    cache = json.load(open(p, encoding="utf-8"))
    bank = []
    for facts in cache.values():
        for f in facts:
            bank.append((len(bank), f))
    return bank


def load_queries(length: str):
    p = REPO / f"analysis/results/sh_{length}_mquake_analysis.json"
    return json.load(open(p, encoding="utf-8"))


# ── retrieval ───────────────────────────────────────────────────────────────
def build_bm25(bank):
    from rank_bm25 import BM25Okapi
    corpus_tokens = [tokenize(f) for _, f in bank]
    return BM25Okapi(corpus_tokens, k1=1.5, b=0.75)


def bm25_topk(bm25, bank, question, k=10):
    scores = bm25.get_scores(tokenize(question))
    idx = sorted(range(len(bank)), key=lambda i: scores[i], reverse=True)[:k]
    return [bank[i] for i in idx]  # list[(ordinal, fact)]


# ── candidate-extraction prompt: VERBATIM from the authors' repo ─────────────
# cvikasreddy/memory-conflict-resolution scripts/_pipeline.py CANDIDATE_PROMPT
# (repo went public 2026-07-10). {hop_query}->question, {pool}->retrieved facts.
# NOTE vs our earlier reconstruction: the real prompt (a) DOES reveal
# "higher marker = newer version", and (b) has an explicit Rule 3 telling the
# model to INCLUDE BOTH conflicting versions — both are anti-world-prior cues we
# had dropped. Output = {"candidates":[{serial, fact_text, answer_entity}]},
# json_object mode, NO system prompt (matches authors).
CANDIDATE_PROMPT = """You are given retrieved items from a knowledge pool. Each item has a FRESHNESS marker (the prefix integer) — higher marker = newer version.

Your job: identify EVERY item that DIRECTLY answers the question, and extract the answer entity from each.

Do NOT compare freshness markers. Do NOT pick a "best" one. Include ALL items that match.

Rules:
1. An item directly answers the question only if BOTH its subject AND its predicate exactly match what the question asks about. The predicate noun used in the question (e.g., "spouse", "sport", "profession", "religion") must be the same noun used in the item. Related-but-different predicates do NOT match.
2. The subject named in the question must appear verbatim in the matching item. A different entity with a similar name does NOT match.
3. If a subject has multiple conflicting values (e.g., the same person with two different values at different freshness markers), INCLUDE BOTH as separate candidates. Do not pick.
4. If no item answers the question, return an empty list.
5. Copy the item's text verbatim into `fact_text`.

Question: {hop_query}

Items:
{pool}

Return ONLY valid JSON: {"candidates": [{"serial": <int>, "fact_text": "<verbatim>", "answer_entity": "<extracted>"}, ...]}"""


def build_candidate_prompt(question, retrieved):
    pool = "\n".join(f"{ordn}. {fact}" for ordn, fact in retrieved)  # authors: "{fact_idx}. {text}"
    return CANDIDATE_PROMPT.replace("{hop_query}", question).replace("{pool}", pool)


def parse_candidates(raw: str):
    """Authors: json.loads(raw)['candidates']. Robust fallback if not wrapped."""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj.get("candidates", []) or []
        if isinstance(obj, list):
            return obj
    except Exception:
        pass
    m = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return []
    return []


def resolve_answer(cands, retrieved):
    """max(serial).entity. Robust: trust an LLM serial only if it is one of the
    retrieved ordinals; otherwise recover the ordinal by matching the candidate
    text to a retrieved fact. Returns (answer, chosen_serial) or ("no answer", None)."""
    valid_ords = {o for o, _ in retrieved}
    ord2fact = {o: f for o, f in retrieved}
    picks = []  # (ordinal, entity)
    for c in cands:
        if not isinstance(c, dict) or not c.get("answer_entity"):
            continue
        ent = str(c["answer_entity"]).strip()
        s = c.get("serial")
        try:
            s = int(s)
        except (TypeError, ValueError):
            s = None
        if s not in valid_ords:  # recover by text match
            ctext = tokenize(c.get("fact_text", ""))
            best, bo = 0, None
            for o, f in retrieved:
                ov = len(set(ctext) & set(tokenize(f)))
                if ov > best:
                    best, bo = ov, o
            s = bo
        if s is not None:
            picks.append((s, ent))
    if not picks:
        return "no answer", None
    s, ent = max(picks, key=lambda x: x[0])
    return ent, s


# ── metric (benchmark SubEM) ─────────────────────────────────────────────────
def subem(prediction, gt_answer):
    from utils.eval_other_utils import (
        substring_exact_match_score, drqa_metric_max_over_ground_truths,
    )
    gts = gt_answer if isinstance(gt_answer, list) else [gt_answer]
    gts = [str(g) for g in gts if g is not None]
    return bool(drqa_metric_max_over_ground_truths(
        substring_exact_match_score, prediction, gts))


# ── LLM ──────────────────────────────────────────────────────────────────────
def llm_extract(client, model, question, retrieved):
    # authors: response_format json_object, NO system prompt, single user message
    resp = client.chat.completions.create(
        model=model, temperature=0.0,
        response_format={"type": "json_object"},
        messages=[{"role": "user",
                   "content": build_candidate_prompt(question, retrieved)}],
    )
    return parse_candidates(resp.choices[0].message.content or "{}")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--length", default="6k")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--sanity", action="store_true",
                    help="no-LLM: report BM25 retrieval recall + plumbing")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    bank = load_bank(args.length)
    queries = load_queries(args.length)
    if args.limit:
        queries = queries[: args.limit]
    bm25 = build_bm25(bank)
    print(f"bank={len(bank)} facts | queries={len(queries)} | topk={args.topk}")

    # ---- sanity: BM25 retrieval recall (does top-k contain the gt-answer fact?) ----
    if args.sanity:
        hp = [q for q in queries if q.get("conflict_type") == "has_pair"]
        hit = 0
        for q in hp:
            retrieved = bm25_topk(bm25, bank, q["question"], args.topk)
            ga = q.get("gt_answer")
            gts = ga if isinstance(ga, list) else [ga]
            ok = any(any(str(g).lower() in f.lower() for g in gts if g)
                     for _, f in retrieved)
            hit += ok
        print(f"[sanity] has_pair BM25 top-{args.topk} recall of gt_answer: "
              f"{hit}/{len(hp)} ({100*hit/len(hp):.0f}%)")
        print("[sanity] plumbing OK (bank/BM25/format). Run without --sanity for full LLM eval.")
        return

    # ---- full pipeline (needs OPENAI_API_KEY) ----
    from openai import OpenAI
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("ERROR: OPENAI_API_KEY not set. Source .env and export it first.")
    client = OpenAI(api_key=key)

    rows = []
    n_overall = n_correct = 0
    hp_total = hp_correct = 0
    n_empty = 0
    for i, q in enumerate(queries):
        retrieved = bm25_topk(bm25, bank, q["question"], args.topk)
        cands = llm_extract(client, args.model, q["question"], retrieved)
        answer, serial = resolve_answer(cands, retrieved)
        if answer == "no answer":
            n_empty += 1
        correct = subem(answer, q.get("gt_answer")) if answer != "no answer" else False
        n_overall += 1
        n_correct += correct
        if q.get("conflict_type") == "has_pair":
            hp_total += 1
            hp_correct += correct
        rows.append({
            "query_id": q.get("query_id"), "question": q.get("question"),
            "conflict_type": q.get("conflict_type"),
            "retrieved_ords": [o for o, _ in retrieved],
            "n_candidates": len(cands), "chosen_serial": serial,
            "answer": answer, "gt_answer": q.get("gt_answer"), "subem": correct,
        })
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(queries)}")

    print(f"\n=== maxserial_fc  {args.length} × {args.model} (SubEM) ===")
    print(f"overall : {n_correct}/{n_overall} ({100*n_correct/n_overall:.1f}%)")
    print(f"has_pair: {hp_correct}/{hp_total} ({100*hp_correct/hp_total:.1f}%)")
    print(f"empty extraction (no answer): {n_empty}/{n_overall} "
          f"({100*n_empty/n_overall:.1f}%)  [paper: ~2%]")

    out = args.out or str(REPO / f"outputs/maxserial_fc/{args.length}_{args.model}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"length": args.length, "model": args.model,
               "overall": [n_correct, n_overall], "has_pair": [hp_correct, hp_total],
               "n_empty": n_empty, "rows": rows},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
