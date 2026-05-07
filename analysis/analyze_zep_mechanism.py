"""
Zep conflict mechanism analysis (standalone, mirrors HippoRAG-v2 step1a style).

For each question's Zep retrieval (top-10 edges with valid_at/invalid_at):
  - Match each edge.fact against per-question gt_fact_text / old_fact_text
    (normalized: lowercase, strip trailing punctuation, collapse spaces).
  - Categorize as GT-edge / Old-edge / OTHER.
  - Record valid_at/invalid_at for GT and Old edges.

Outputs:
  analysis/results/zep/sh_zep_mechanism.json   (per-question SH)
  analysis/results/zep/mh_zep_mechanism.json   (per-hop MH)
  analysis/results/zep/zep_mechanism_summary.txt
"""
import json
import re
import unicodedata
from pathlib import Path
from collections import Counter

BASE = Path("/home/yhchiang/MemoryAgentBench")
SH_ANALYSIS = BASE / "analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json"
MH_ANALYSIS = BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"

# For failure-mode classification: need old_final_answer (MH) and old_answer (SH)
# Both are already present in SH/MH analysis JSON.

# Inference-time dump (carries pred/zep_em; episodes are truncated to 500 chars — DO NOT use for episode recall)
ZEP_SH_INFER = BASE / "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/FULL_100queries.json"
ZEP_MH_INFER = BASE / "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/FULL_100queries.json"
# Retrieval-only re-fetch (full episode content; preferred for retrieval/supersession analysis)
ZEP_SH_REFETCH = BASE / "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json"
ZEP_MH_REFETCH = BASE / "outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/RETRIEVAL_FULL_100queries.json"


def load_zep(task: str):
    """Return dict {qid: {edges, nodes, episodes, exact_match, pred}}.
    Prefers re-fetch file for retrieval; pulls pred/em from inference file.
    """
    infer_path = ZEP_SH_INFER if task == "sh" else ZEP_MH_INFER
    refetch_path = ZEP_SH_REFETCH if task == "sh" else ZEP_MH_REFETCH

    infer = {r["query_id"]: r for r in json.load(open(infer_path))}
    by_q = {}
    if refetch_path.exists():
        for r in json.load(open(refetch_path)):
            qid = r["query_id"]
            inf = infer.get(qid, {})
            by_q[qid] = {
                "edges": r.get("edges", []),
                "nodes": r.get("nodes", []),
                "episodes": r.get("episodes", []),
                "exact_match": inf.get("exact_match", False),
                "pred": inf.get("pred", ""),
                "_source": "refetch",
            }
        # If some queries missing from refetch, fill from infer
        for qid, inf in infer.items():
            if qid not in by_q:
                by_q[qid] = {
                    "edges": inf.get("edges", []),
                    "nodes": inf.get("nodes", []),
                    "episodes": inf.get("episodes", []),
                    "exact_match": inf.get("exact_match", False),
                    "pred": inf.get("pred", ""),
                    "_source": "infer_fallback",
                }
    else:
        for qid, inf in infer.items():
            by_q[qid] = {
                "edges": inf.get("edges", []),
                "nodes": inf.get("nodes", []),
                "episodes": inf.get("episodes", []),
                "exact_match": inf.get("exact_match", False),
                "pred": inf.get("pred", ""),
                "_source": "infer_only",
            }
    return by_q

OUT_DIR = BASE / "analysis/results/zep"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def norm(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s).lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(" .,;:!?\"'")
    return s


def classify_edge(edge_fact: str, gt_fact: str, old_fact: str) -> str:
    """Return 'GT', 'OLD', or 'OTHER'."""
    e = norm(edge_fact)
    g = norm(gt_fact)
    o = norm(old_fact)
    if g and (e == g or g in e or e in g):
        # Be careful: GT and Old often differ only in last word; require exact match
        if e == g:
            return "GT"
        # If both g and o appear in e (rare), prefer exact
    if o and e == o:
        return "OLD"
    if g and e == g:
        return "GT"
    return "OTHER"


def classify_zep_error(zep_pred: str, gt_answer: str, old_answer: str, em: bool) -> str:
    """Mirror analyze_sh_512_mquake's classify_error (best-effort, normalized substring)."""
    if em:
        return "correct"
    p = norm(zep_pred)
    g = norm(gt_answer)
    o = norm(old_answer or "")
    if not p:
        return "empty"
    if o and (p == o or o in p or p in o):
        return "older_fact"
    return "hallucination_or_other"


def find_edges_for_facts(edges, gt_fact, old_fact):
    """Return (gt_indices, old_indices, classifications[list[str]])."""
    classifications = []
    gt_idx, old_idx = [], []
    g = norm(gt_fact)
    o = norm(old_fact)
    for i, ed in enumerate(edges):
        e = norm(ed["fact"])
        cls = "OTHER"
        if g and e == g:
            cls = "GT"
            gt_idx.append(i)
        elif o and e == o:
            cls = "OLD"
            old_idx.append(i)
        classifications.append(cls)
    return gt_idx, old_idx, classifications


def fact_in_nodes(nodes, fact_text):
    """Substring search: is the fact present in any node's summary?"""
    f = norm(fact_text)
    if not f:
        return False, []
    hits = []
    for i, n in enumerate(nodes):
        s = norm(n.get("summary", ""))
        if s and (f == s or f in s):
            hits.append(i)
    return bool(hits), hits


def fact_in_episodes(episodes, fact_text):
    """Substring search: is the fact present in any episode's content?
    Episode content has raw chunks with seq prefixes, so plain substring on
    normalized text works."""
    f = norm(fact_text)
    if not f:
        return False, []
    hits = []
    for i, ep in enumerate(episodes):
        c = norm(ep.get("content", ""))
        if c and f in c:
            hits.append(i)
    return bool(hits), hits


# ─────────────────────────────────────────────────────────────────────────────
# SH analysis: 1 question = 1 (gt, old?) pair
# ─────────────────────────────────────────────────────────────────────────────
def analyze_sh():
    sh = json.load(open(SH_ANALYSIS))
    zep_by_q = load_zep("sh")

    out = []
    for entry in sh:
        qid = entry["query_id"]
        z = zep_by_q.get(qid)
        if not z:
            continue
        edges = z["edges"]
        nodes = z.get("nodes", [])
        episodes = z.get("episodes", [])
        ct = entry["conflict_type"]
        gt_fact = entry.get("gt_fact_text", "") or ""
        old_fact = entry.get("old_fact_text", "") or ""

        gt_idx, old_idx, cls = find_edges_for_facts(edges, gt_fact, old_fact)
        gt_in_nodes, gt_node_idx = fact_in_nodes(nodes, gt_fact)
        old_in_nodes, old_node_idx = fact_in_nodes(nodes, old_fact)
        gt_in_episodes, gt_ep_idx = fact_in_episodes(episodes, gt_fact)
        old_in_episodes, old_ep_idx = fact_in_episodes(episodes, old_fact)

        gt_invalid_set = [edges[i].get("invalid_at") for i in gt_idx]
        old_invalid_set = [edges[i].get("invalid_at") for i in old_idx]

        # other edges with invalid_at
        other_invalid_count = sum(
            1 for i, c in enumerate(cls)
            if c == "OTHER" and edges[i].get("invalid_at")
        )

        zep_pred = z.get("pred", "")
        zep_em = z["exact_match"]
        out.append({
            "query_id": qid,
            "conflict_type": ct,
            "gt_answer": entry.get("gt_answer", ""),
            "old_answer": entry.get("old_answer", ""),
            "gt_fact_text": gt_fact,
            "old_fact_text": old_fact,
            "zep_em": zep_em,
            "zep_pred": zep_pred,
            "error_type": classify_zep_error(zep_pred, entry.get("gt_answer", ""), entry.get("old_answer", ""), zep_em),
            "n_edges": len(edges),

            # GT (new) — across three retrieval scopes
            "gt_in_edges": len(gt_idx) > 0,
            "gt_in_nodes": gt_in_nodes,
            "gt_in_episodes": gt_in_episodes,
            "gt_in_any": (len(gt_idx) > 0) or gt_in_nodes or gt_in_episodes,
            "gt_edge_idx": gt_idx,
            "gt_node_idx": gt_node_idx,
            "gt_episode_idx": gt_ep_idx,
            "gt_edge_invalid_at": [v for v in gt_invalid_set if v],
            "gt_marked_invalid": any(gt_invalid_set),  # ANY GT edge marked invalid (incorrect for has_pair / no_conflict_pair)

            # Old (conflicting) — across three retrieval scopes
            "old_in_edges": len(old_idx) > 0,
            "old_in_nodes": old_in_nodes,
            "old_in_episodes": old_in_episodes,
            "old_in_any": (len(old_idx) > 0) or old_in_nodes or old_in_episodes,
            "old_edge_idx": old_idx,
            "old_node_idx": old_node_idx,
            "old_episode_idx": old_ep_idx,
            "old_edge_invalid_at": [v for v in old_invalid_set if v],
            "old_marked_invalid": any(old_invalid_set),  # supersession success signal

            # Other edges with invalid_at (false positives — Zep marked unrelated facts as invalid)
            "n_other_edges_invalid": other_invalid_count,

            # Total invalid_at edges in top-10
            "n_invalid_edges": sum(1 for ed in edges if ed.get("invalid_at")),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# MH analysis: 1 question = N hops, each with (gt, old?) pair
# ─────────────────────────────────────────────────────────────────────────────
def analyze_mh():
    mh = json.load(open(MH_ANALYSIS))
    zep_by_q = load_zep("mh")

    out = []
    for entry in mh:
        qid = entry["query_id"]
        z = zep_by_q.get(qid)
        if not z:
            continue
        edges = z["edges"]
        zep_pred = z.get("pred", "")
        zep_em = z["exact_match"]
        rec = {
            "query_id": qid,
            "num_hops": entry.get("num_hops"),
            "zep_em": zep_em,
            "zep_pred": zep_pred,
            "gt_answer": entry.get("gt_answer", ""),
            "old_final_answer": entry.get("old_final_answer", ""),
            "error_type": classify_zep_error(zep_pred, entry.get("gt_answer", ""), entry.get("old_final_answer", ""), zep_em),
            "n_edges": len(edges),
            "n_invalid_edges": sum(1 for ed in edges if ed.get("invalid_at")),
            "hops": [],
        }
        nodes = z.get("nodes", [])
        episodes = z.get("episodes", [])
        for hop in entry["hops"]:
            ct = hop["conflict_type"]
            gt_fact = hop.get("gt_fact_text", "") or ""
            old_fact = hop.get("old_fact_text", "") or ""
            gt_idx, old_idx, _ = find_edges_for_facts(edges, gt_fact, old_fact)
            gt_in_n, gt_node_i = fact_in_nodes(nodes, gt_fact)
            old_in_n, old_node_i = fact_in_nodes(nodes, old_fact)
            gt_in_e, gt_ep_i = fact_in_episodes(episodes, gt_fact)
            old_in_e, old_ep_i = fact_in_episodes(episodes, old_fact)
            gt_inv = [edges[i].get("invalid_at") for i in gt_idx]
            old_inv = [edges[i].get("invalid_at") for i in old_idx]
            rec["hops"].append({
                "hop_idx": hop["hop_idx"],
                "conflict_type": ct,
                "gt_fact_text": gt_fact,
                "old_fact_text": old_fact,
                # multi-scope retrieval
                "gt_in_edges": len(gt_idx) > 0,
                "gt_in_nodes": gt_in_n,
                "gt_in_episodes": gt_in_e,
                "gt_in_any": (len(gt_idx) > 0) or gt_in_n or gt_in_e,
                "old_in_edges": len(old_idx) > 0,
                "old_in_nodes": old_in_n,
                "old_in_episodes": old_in_e,
                "old_in_any": (len(old_idx) > 0) or old_in_n or old_in_e,
                "gt_marked_invalid": any(gt_inv),
                "old_marked_invalid": any(old_inv),
                "gt_edge_idx": gt_idx,
                "old_edge_idx": old_idx,
                "gt_edge_invalid_at": [v for v in gt_inv if v],
                "old_edge_invalid_at": [v for v in old_inv if v],
            })
        out.append(rec)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Summarize
# ─────────────────────────────────────────────────────────────────────────────
def summarize_sh(sh_recs):
    lines = []
    lines.append("=" * 70)
    lines.append("FC-SH (100 questions) — Zep mechanism summary")
    lines.append("=" * 70)

    # Group by conflict_type
    has_pair = [r for r in sh_recs if r["conflict_type"] == "has_pair"]
    nocp = [r for r in sh_recs if r["conflict_type"] == "no_conflict_pair"]
    other_ct = [r for r in sh_recs if r["conflict_type"] not in ("has_pair", "no_conflict_pair")]

    lines.append(f"\nTotal: {len(sh_recs)}  has_pair: {len(has_pair)}  no_conflict_pair: {len(nocp)}  other: {len(other_ct)}")
    lines.append(f"Zep overall EM: {sum(1 for r in sh_recs if r['zep_em'])}/{len(sh_recs)}")

    # has_pair stats
    lines.append("\n" + "─" * 70)
    lines.append(f"[has_pair, n={len(has_pair)}]   ideal: GT retrieved (valid), Old retrieved AND marked invalid")
    lines.append("─" * 70)
    def pct(n, d): return f"{n}/{d} = {n/d*100:.1f}%" if d else "0/0 = -"
    lines.append(f"  retrieval recall (3 scopes — top-10 each):")
    lines.append(f"  {'scope':<14} {'GT in':>14} {'Old in':>14} {'both':>14}")
    for scope in ("edges", "nodes", "episodes", "any"):
        gt_key = f"gt_in_{scope}"
        old_key = f"old_in_{scope}"
        ng = sum(1 for r in has_pair if r[gt_key])
        no = sum(1 for r in has_pair if r[old_key])
        nb = sum(1 for r in has_pair if r[gt_key] and r[old_key])
        lines.append(f"  {scope:<14} {pct(ng, len(has_pair)):>14} {pct(no, len(has_pair)):>14} {pct(nb, len(has_pair)):>14}")
    n_gt_in   = sum(1 for r in has_pair if r["gt_in_edges"])
    n_old_in  = sum(1 for r in has_pair if r["old_in_edges"])
    n_both_in = sum(1 for r in has_pair if r["gt_in_edges"] and r["old_in_edges"])
    n_only_gt   = sum(1 for r in has_pair if r["gt_in_edges"] and not r["old_in_edges"])
    n_only_old  = sum(1 for r in has_pair if not r["gt_in_edges"] and r["old_in_edges"])
    n_neither   = sum(1 for r in has_pair if not r["gt_in_edges"] and not r["old_in_edges"])
    lines.append(f"\n  edges-only breakdown (for supersession analysis below):")
    lines.append(f"    only GT in edges:   {n_only_gt}")
    lines.append(f"    only Old in edges:  {n_only_old}")
    lines.append(f"    neither in edges:   {n_neither}")

    # supersession on the both-retrieved subset
    both = [r for r in has_pair if r["gt_in_edges"] and r["old_in_edges"]]
    if both:
        n_old_inv      = sum(1 for r in both if r["old_marked_invalid"])
        n_gt_active    = sum(1 for r in both if not r["gt_marked_invalid"])
        n_perfect      = sum(1 for r in both if r["old_marked_invalid"] and not r["gt_marked_invalid"])
        n_gt_falsely_inv = sum(1 for r in both if r["gt_marked_invalid"])
        lines.append(f"\n  supersession outcome on both-retrieved subset (n={len(both)}):")
        lines.append(f"    Old marked invalid (correct):           {n_old_inv}/{len(both)} = {n_old_inv/len(both)*100:.1f}%")
        lines.append(f"    GT NOT marked invalid (correct):        {n_gt_active}/{len(both)} = {n_gt_active/len(both)*100:.1f}%")
        lines.append(f"    Perfect: Old invalid AND GT active:     {n_perfect}/{len(both)} = {n_perfect/len(both)*100:.1f}%")
        lines.append(f"    GT falsely marked invalid (error):      {n_gt_falsely_inv}")

        # accuracy conditional on perfect supersession
        n_em_perfect = sum(1 for r in both if r["old_marked_invalid"] and not r["gt_marked_invalid"] and r["zep_em"])
        n_em_old_active = sum(1 for r in both if not r["old_marked_invalid"] and r["zep_em"])
        lines.append(f"\n  Zep EM conditional on supersession:")
        if n_perfect:
            lines.append(f"    when Old invalid+GT active (perfect):    EM={n_em_perfect}/{n_perfect} = {n_em_perfect/n_perfect*100:.1f}%")
        n_old_active = len(both) - n_old_inv
        if n_old_active:
            lines.append(f"    when Old still active (no supersession): EM={n_em_old_active}/{n_old_active} = {n_em_old_active/n_old_active*100:.1f}%")

    # failure-mode breakdown on has_pair
    lines.append("\n  failure-mode breakdown (has_pair):")
    et = Counter(r["error_type"] for r in has_pair)
    for k, v in et.most_common():
        lines.append(f"    {k:<22} {v}")

    # no_conflict_pair stats
    lines.append("\n" + "─" * 70)
    lines.append(f"[no_conflict_pair, n={len(nocp)}]   ideal: GT retrieved (valid), no false invalidations")
    lines.append("─" * 70)
    if nocp:
        for scope in ("edges", "nodes", "episodes", "any"):
            n = sum(1 for r in nocp if r[f"gt_in_{scope}"])
            lines.append(f"  GT in {scope:<8}: {n}/{len(nocp)} = {n/len(nocp)*100:.1f}%")
        n_gt_inv  = sum(1 for r in nocp if r["gt_marked_invalid"])
        n_other_inv = sum(r["n_other_edges_invalid"] for r in nocp)
        n_any_inv = sum(1 for r in nocp if r["n_invalid_edges"] > 0)
        lines.append(f"  GT marked invalid (wrong):   {n_gt_inv}/{len(nocp)}")
        lines.append(f"  any edge marked invalid in top-10: {n_any_inv}/{len(nocp)}")
        lines.append(f"  total OTHER edges marked invalid (false positives, summed): {n_other_inv}")
        lines.append(f"  Zep EM: {sum(1 for r in nocp if r['zep_em'])}/{len(nocp)}")

    return "\n".join(lines)


def summarize_mh(mh_recs):
    lines = []
    lines.append("\n" + "=" * 70)
    lines.append("FC-MH (100 questions, hop-level mechanism) — Zep mechanism summary")
    lines.append("=" * 70)

    all_hops = []
    for r in mh_recs:
        for h in r["hops"]:
            all_hops.append((r, h))

    n_hops = len(all_hops)
    has_pair_hops = [(r, h) for r, h in all_hops if h["conflict_type"] == "has_pair"]
    nocp_hops = [(r, h) for r, h in all_hops if h["conflict_type"] == "no_conflict_pair"]

    lines.append(f"\nQuestions: {len(mh_recs)}, total hops: {n_hops}")
    lines.append(f"  has_pair hops: {len(has_pair_hops)}")
    lines.append(f"  no_conflict_pair hops: {len(nocp_hops)}")
    lines.append(f"Zep overall EM: {sum(1 for r in mh_recs if r['zep_em'])}/{len(mh_recs)}")

    lines.append("\n" + "─" * 70)
    lines.append(f"[has_pair hops, n={len(has_pair_hops)}]")
    lines.append("─" * 70)
    def pct(n, d): return f"{n}/{d} = {n/d*100:.1f}%" if d else "0/0 = -"
    lines.append(f"  retrieval recall (3 scopes, hop-level):")
    lines.append(f"  {'scope':<14} {'GT in':>16} {'Old in':>16} {'both':>16}")
    for scope in ("edges", "nodes", "episodes", "any"):
        gt_key = f"gt_in_{scope}"
        old_key = f"old_in_{scope}"
        ng = sum(1 for _, h in has_pair_hops if h[gt_key])
        no = sum(1 for _, h in has_pair_hops if h[old_key])
        nb = sum(1 for _, h in has_pair_hops if h[gt_key] and h[old_key])
        lines.append(f"  {scope:<14} {pct(ng, len(has_pair_hops)):>16} {pct(no, len(has_pair_hops)):>16} {pct(nb, len(has_pair_hops)):>16}")
    n_only_gt = sum(1 for _, h in has_pair_hops if h["gt_in_edges"] and not h["old_in_edges"])
    n_only_old = sum(1 for _, h in has_pair_hops if not h["gt_in_edges"] and h["old_in_edges"])
    n_neither = sum(1 for _, h in has_pair_hops if not h["gt_in_edges"] and not h["old_in_edges"])
    lines.append(f"\n  edges-only breakdown:")
    lines.append(f"    only GT:   {n_only_gt}")
    lines.append(f"    only Old:  {n_only_old}")
    lines.append(f"    neither:   {n_neither}")

    both = [(r, h) for r, h in has_pair_hops if h["gt_in_edges"] and h["old_in_edges"]]
    if both:
        n_old_inv = sum(1 for _, h in both if h["old_marked_invalid"])
        n_gt_active = sum(1 for _, h in both if not h["gt_marked_invalid"])
        n_perfect = sum(1 for _, h in both if h["old_marked_invalid"] and not h["gt_marked_invalid"])
        n_gt_falsely_inv = sum(1 for _, h in both if h["gt_marked_invalid"])
        lines.append(f"\n  supersession outcome on both-retrieved hops (n={len(both)}):")
        lines.append(f"    Old marked invalid (correct):       {n_old_inv}/{len(both)} = {n_old_inv/len(both)*100:.1f}%")
        lines.append(f"    GT NOT marked invalid (correct):    {n_gt_active}/{len(both)} = {n_gt_active/len(both)*100:.1f}%")
        lines.append(f"    Perfect (Old invalid AND GT active):{n_perfect}/{len(both)} = {n_perfect/len(both)*100:.1f}%")
        lines.append(f"    GT falsely marked invalid (error):  {n_gt_falsely_inv}")

    # question-level: all has_pair hops perfectly superseded → ideal scenario
    lines.append("\n" + "─" * 70)
    lines.append("[per-question rollup: all has_pair hops perfectly superseded?]")
    lines.append("─" * 70)
    perfect_q = []
    partial_q = []
    none_q = []
    for r in mh_recs:
        hp = [h for h in r["hops"] if h["conflict_type"] == "has_pair"]
        if not hp:
            continue
        all_perfect = all(h["gt_in_edges"] and h["old_in_edges"] and h["old_marked_invalid"] and not h["gt_marked_invalid"] for h in hp)
        any_perfect = any(h["gt_in_edges"] and h["old_in_edges"] and h["old_marked_invalid"] and not h["gt_marked_invalid"] for h in hp)
        if all_perfect:
            perfect_q.append(r)
        elif any_perfect:
            partial_q.append(r)
        else:
            none_q.append(r)
    n_q_with_hp = len(perfect_q) + len(partial_q) + len(none_q)
    lines.append(f"  Questions with has_pair hops:    {n_q_with_hp}")
    lines.append(f"    all hops perfectly superseded: {len(perfect_q)} (EM={sum(1 for r in perfect_q if r['zep_em'])}/{len(perfect_q)})")
    lines.append(f"    some hops perfectly superseded:{len(partial_q)} (EM={sum(1 for r in partial_q if r['zep_em'])}/{len(partial_q)})")
    lines.append(f"    no hops perfectly superseded:  {len(none_q)} (EM={sum(1 for r in none_q if r['zep_em'])}/{len(none_q)})")

    # failure-mode breakdown for MH question-level
    lines.append("\n  failure-mode breakdown (question-level):")
    et = Counter(r["error_type"] for r in mh_recs)
    for k, v in et.most_common():
        lines.append(f"    {k:<22} {v}")

    # no_conflict_pair hops
    lines.append("\n" + "─" * 70)
    lines.append(f"[no_conflict_pair hops, n={len(nocp_hops)}]")
    lines.append("─" * 70)
    if nocp_hops:
        for scope in ("edges", "nodes", "episodes", "any"):
            n = sum(1 for _, h in nocp_hops if h[f"gt_in_{scope}"])
            lines.append(f"  GT in {scope:<8}: {n}/{len(nocp_hops)} = {n/len(nocp_hops)*100:.1f}%")
        n_gt_inv = sum(1 for _, h in nocp_hops if h["gt_marked_invalid"])
        lines.append(f"  GT marked invalid (wrong):    {n_gt_inv}/{len(nocp_hops)}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Analyzing SH...")
    sh = analyze_sh()
    json.dump(sh, open(OUT_DIR / "sh_zep_mechanism.json", "w"), ensure_ascii=False, indent=2)
    print(f"  → {OUT_DIR / 'sh_zep_mechanism.json'}")

    print("Analyzing MH...")
    mh = analyze_mh()
    json.dump(mh, open(OUT_DIR / "mh_zep_mechanism.json", "w"), ensure_ascii=False, indent=2)
    print(f"  → {OUT_DIR / 'mh_zep_mechanism.json'}")

    text = summarize_sh(sh) + "\n" + summarize_mh(mh)
    (OUT_DIR / "zep_mechanism_summary.txt").write_text(text, encoding="utf-8")
    print(f"  → {OUT_DIR / 'zep_mechanism_summary.txt'}")
    print()
    print(text)
