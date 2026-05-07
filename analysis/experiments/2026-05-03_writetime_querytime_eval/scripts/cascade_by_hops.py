"""
3-way cascade table: write-time detection × query-time retrieval × E2E answer
broken down by num_hops (2 / 3 / 4).

For each FC-MH question:
  - detect_score = # has_pair hops where Mem0/Zep correctly invalidated / total has_pair hops
  - retrieve_score (Mem0) = # has_pair hops where GT new fact in top-100 / total has_pair hops
  - retrieve_score (Zep) = # has_pair hops where GT new fact AND old has invalid_at signal / total has_pair hops
  - em = answer correctness

Cross-tab by num_hops:
  for each (num_hops, detect_bucket): count, avg retrieve, avg EM

Outputs:
  results/cascade_by_hops.json + .md
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
HISTORY_DB = Path("/home/yhchiang/.mem0/history.db")
EXP_DIR = BASE / "analysis/experiments/2026-05-03_writetime_querytime_eval"
RESULTS = EXP_DIR / "results"
PRIOR_RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"

SINCE = "2026-05-02T09:00:00"  # PT-suffixed; matches today's re-ingestion in CST


def normalize(s):
    if s is None: return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def text_contains(haystack, needle):
    h = normalize(haystack); n = normalize(needle)
    if not h or not n: return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def load_mem0_events():
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT old_memory, new_memory FROM history WHERE event='UPDATE' AND created_at >= ?",
        (SINCE,)
    ).fetchall()
    return [{"old": r[0], "new": r[1]} for r in rows]


def mem0_detect_for_pair(events, p):
    for e in events:
        if text_contains(e["old"], p["old"]) and text_contains(e["new"], p["new"]):
            return True
    return False


def zep_detect_for_pair(edges, p):
    """In retrieved edges (across all queries), is old fact present with invalid_at?"""
    for e in edges:
        if text_contains(e.get("fact", ""), p["old"]) and e.get("invalid_at"):
            return True
    return False


def main():
    mh_gt = json.load(open(MH_GT))
    mem0_events = load_mem0_events()

    mem0_retrieval = json.load(open(RESULTS / "mem0_full_retrieval_mh.json"))
    zep_retrieval = json.load(open(RESULTS / "zep_full_retrieval_mh.json"))
    mem0_em = {r["query_id"]: r["exact_match"] for r in json.load(open(PRIOR_RESULTS / "mem0_gemini_mh_results.json"))}
    zep_em = {r["query_id"]: r["exact_match"] for r in json.load(open(PRIOR_RESULTS / "zep_gemini_mh_results.json"))}

    mem0_retr_by_qid = {r["query_id"]: r for r in mem0_retrieval}
    zep_retr_by_qid = {r["query_id"]: r for r in zep_retrieval}

    # Aggregate Zep edges across all queries for write-time detection check
    zep_all_edges = {}
    for r in zep_retrieval:
        for e in r.get("edges", []):
            uid = e.get("uuid")
            if uid and uid not in zep_all_edges:
                zep_all_edges[uid] = e
    zep_edges_list = list(zep_all_edges.values())

    rows = []
    for q in mh_gt:
        qid = q["query_id"]
        nh = q.get("num_hops")
        chain = [h for h in q.get("hops", []) if h.get("conflict_type") == "has_pair"]
        n_pairs = len(chain)
        if n_pairs == 0:
            # skip questions without conflicts (they're not the detection test)
            continue

        # Mem0 detection (use history.db)
        m0_correct = sum(
            1 for h in chain
            if mem0_detect_for_pair(mem0_events, {"old": h.get("old_fact_text",""), "new": h.get("gt_fact_text","")})
        )
        # Zep detection (use aggregated edges)
        zep_correct = sum(
            1 for h in chain
            if zep_detect_for_pair(zep_edges_list, {"old": h.get("old_fact_text",""), "new": h.get("gt_fact_text","")})
        )

        # Mem0 retrieval: how many chain new facts in top-100
        mem0_r = mem0_retr_by_qid.get(qid, {})
        m0_memories = [m.get("memory","") for m in mem0_r.get("retrieved_full", [])]
        m0_retrieve_new = sum(
            1 for h in chain
            if any(text_contains(m, h.get("gt_fact_text","")) for m in m0_memories)
        )
        m0_retrieve_old = sum(
            1 for h in chain
            if any(text_contains(m, h.get("old_fact_text","")) for m in m0_memories)
        )

        # Zep retrieval: how many chain new facts in top-10 edges or episodes
        zep_r = zep_retr_by_qid.get(qid, {})
        zep_strs = [e.get("fact","") for e in zep_r.get("edges", [])] + [ep.get("content","") for ep in zep_r.get("episodes", [])]
        zep_retrieve_new = sum(
            1 for h in chain
            if any(text_contains(s, h.get("gt_fact_text","")) for s in zep_strs)
        )
        zep_retrieve_both = sum(
            1 for h in chain
            if any(text_contains(s, h.get("gt_fact_text","")) for s in zep_strs)
            and any(text_contains(s, h.get("old_fact_text","")) for s in zep_strs)
        )

        rows.append({
            "qid": qid, "num_hops": nh, "n_has_pair": n_pairs,
            "mem0_detect_correct": m0_correct,
            "mem0_detect_pct": m0_correct / n_pairs,
            "zep_detect_correct": zep_correct,
            "zep_detect_pct": zep_correct / n_pairs,
            "mem0_retrieve_new": m0_retrieve_new,
            "mem0_retrieve_new_pct": m0_retrieve_new / n_pairs,
            "mem0_retrieve_old": m0_retrieve_old,
            "mem0_retrieve_old_pct": m0_retrieve_old / n_pairs,
            "zep_retrieve_new": zep_retrieve_new,
            "zep_retrieve_new_pct": zep_retrieve_new / n_pairs,
            "zep_retrieve_both": zep_retrieve_both,
            "zep_retrieve_both_pct": zep_retrieve_both / n_pairs,
            "mem0_em": mem0_em.get(qid, False),
            "zep_em": zep_em.get(qid, False),
        })

    # Aggregate by num_hops × detect bucket
    def bucket(x):
        if x == 1.0: return "all_correct"
        if x > 0:    return "partial"
        return "none"

    md = ["# Detection × Retrieval × Answer cascade by num_hops\n"]
    md.append(f"> Only has_pair questions (n_has_pair > 0). {len(rows)} qualifying questions.\n")
    md.append("---\n")

    for system in ("mem0", "zep"):
        md.append(f"## {system.upper()}\n")
        md.append(f"| num_hops | detect bucket | n questions | avg detect % | avg retrieve_new % | EM |")
        md.append(f"|:---:|:---:|:---:|:---:|:---:|:---:|")
        agg = defaultdict(list)
        for r in rows:
            nh = r["num_hops"]
            b = bucket(r[f"{system}_detect_pct"])
            agg[(nh, b)].append(r)
        for nh in sorted({r["num_hops"] for r in rows}):
            for b in ["all_correct", "partial", "none"]:
                grp = agg.get((nh, b), [])
                if not grp:
                    continue
                n = len(grp)
                avg_d = sum(r[f"{system}_detect_pct"] for r in grp) / n
                avg_r = sum(r[f"{system}_retrieve_new_pct"] for r in grp) / n
                em = sum(r[f"{system}_em"] for r in grp)
                md.append(f"| {nh} | {b} | {n} | {avg_d*100:.0f}% | {avg_r*100:.0f}% | {em}/{n} = {em/n*100:.0f}% |")
        md.append("")

    # Overall by num_hops only
    md.append("## Aggregate by num_hops only (detection bucket merged)\n")
    md.append("| num_hops | n | Mem0 detect % | Mem0 new in retrieval % | Mem0 EM | Zep detect % | Zep new in retrieval % | Zep both visible % | Zep EM |")
    md.append("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    nh_groups = defaultdict(list)
    for r in rows:
        nh_groups[r["num_hops"]].append(r)
    for nh in sorted(nh_groups):
        grp = nh_groups[nh]
        n = len(grp)
        m0_d = sum(r["mem0_detect_pct"] for r in grp)/n
        m0_r = sum(r["mem0_retrieve_new_pct"] for r in grp)/n
        m0_em = sum(r["mem0_em"] for r in grp)
        z_d = sum(r["zep_detect_pct"] for r in grp)/n
        z_r = sum(r["zep_retrieve_new_pct"] for r in grp)/n
        z_b = sum(r["zep_retrieve_both_pct"] for r in grp)/n
        z_em = sum(r["zep_em"] for r in grp)
        md.append(f"| {nh} | {n} | {m0_d*100:.0f}% | {m0_r*100:.0f}% | {m0_em}/{n} = {m0_em/n*100:.0f}% | {z_d*100:.0f}% | {z_r*100:.0f}% | {z_b*100:.0f}% | {z_em}/{n} = {z_em/n*100:.0f}% |")

    out = {
        "rows": rows,
        "n_total_has_pair_questions": len(rows),
    }
    json_path = RESULTS / "cascade_by_hops.json"
    md_path = RESULTS / "cascade_by_hops.md"
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    md_path.write_text("\n".join(md))
    print("\n".join(md))
    print(f"\nWritten: {json_path}")
    print(f"Written: {md_path}")


if __name__ == "__main__":
    main()
