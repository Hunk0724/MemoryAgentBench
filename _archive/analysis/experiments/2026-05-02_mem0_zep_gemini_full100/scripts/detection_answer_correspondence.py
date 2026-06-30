"""
Detection × Answer correspondence — verify the claim that detection
quality drives end-to-end EM (rigor check).

For each question (across SH/MH × Mem0/Zep):
  Per-question detection score = fraction of chain has_pair hops correctly
  invalidated by the system.

Cross-tab with EM correctness:
  - Fully detected & answer correct → "happy path"
  - Fully detected & answer wrong → propagation/inference failure
  - Partially detected & answer correct → lucky / world-knowledge bias
  - Not detected & answer wrong → detection-driven failure

If our paper claim "detection F1 < 50% drives E2E failure" is correct,
we expect strong correlation:
  P(answer correct | fully detected) >> P(answer correct | not detected)
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"
OLD_RESULTS = BASE / "analysis/results/oracle_a"
HISTORY_DB = Path("/home/yhchiang/.mem0/history.db")
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"


def normalize(s):
    if s is None:
        return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def text_contains(haystack, needle):
    h = normalize(haystack); n = normalize(needle)
    if not h or not n:
        return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def load_mem0_events(since):
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT old_memory, new_memory FROM history WHERE event='UPDATE' AND created_at >= ?",
        (since,)
    ).fetchall()
    return [{"old": r[0], "new": r[1]} for r in rows]


def get_question_pairs(task, gt):
    """Per-question chain has_pair list."""
    qpairs = {}  # qid -> [{old, new}, ...]
    if task == "SH":
        for q in gt:
            qid = q["query_id"]
            if q.get("conflict_type") == "has_pair":
                qpairs[qid] = [{
                    "old": q.get("old_fact_text", ""),
                    "new": q.get("gt_fact_text", ""),
                }]
            else:
                qpairs[qid] = []
    else:
        for q in gt:
            qid = q["query_id"]
            qpairs[qid] = []
            for h in q.get("hops", []):
                if h.get("conflict_type") == "has_pair":
                    qpairs[qid].append({
                        "old": h.get("old_fact_text", ""),
                        "new": h.get("gt_fact_text", ""),
                        "hop_idx": h.get("hop_idx"),
                    })
    return qpairs


def mem0_detection_per_question(events, qpairs):
    """For each (qid, pair), check if Mem0 had a correct UPDATE event."""
    per_q = {}
    for qid, pairs in qpairs.items():
        if not pairs:
            per_q[qid] = {"n_has_pair": 0, "n_correct": 0, "all_correct": True, "any_correct": False}
            continue
        n_correct = 0
        for p in pairs:
            if not p["old"] or not p["new"]:
                continue
            for e in events:
                if text_contains(e["old"], p["old"]) and text_contains(e["new"], p["new"]):
                    n_correct += 1
                    break
        per_q[qid] = {
            "n_has_pair": len(pairs),
            "n_correct": n_correct,
            "all_correct": n_correct == len(pairs),
            "any_correct": n_correct > 0,
        }
    return per_q


def zep_detection_per_question(zep_audit_path, qpairs):
    """From Zep invalidation audit's correct_items, build per-question detection."""
    audit = json.load(open(zep_audit_path))
    correct_items = audit.get("correct_items", [])

    correct_pair_index = set()  # (qid, hop_idx) tuples
    correct_qids_sh = set()
    for item in correct_items:
        cqid = item.get("matched_pair_qid")
        if cqid is not None:
            correct_qids_sh.add(cqid)
            # for MH item we need hop info to be precise — but the audit doesn't store hop_idx
            # so we mark "any hop covered" rather than counting per-hop
    # The existing Zep GPT audits don't have hop_idx — we approximate:
    # if at least one event matched THIS qid, count this qid as "any detected"

    # For per-question, we need to match pair-by-pair. Re-do with text_contains:
    per_q = {}
    for qid, pairs in qpairs.items():
        if not pairs:
            per_q[qid] = {"n_has_pair": 0, "n_correct": 0, "all_correct": True, "any_correct": False}
            continue
        n_correct = 0
        for p in pairs:
            for item in correct_items:
                cgt_old = item.get("counterpart") if "counterpart" in item else item.get("gt_old")
                cgt_new = item.get("fact") if "counterpart" in item else item.get("gt_new")
                # Note: in older audit shape, item has 'fact' (= old) and 'counterpart' (= new)
                # In our new mem0/zep audits, item has 'gt_old' and 'gt_new'
                # Either way map them
                edge_old = item.get("fact") or item.get("gt_old") or ""
                edge_new = item.get("counterpart") or item.get("gt_new") or ""
                if text_contains(edge_old, p["old"]) and text_contains(edge_new, p["new"]):
                    n_correct += 1
                    break
        per_q[qid] = {
            "n_has_pair": len(pairs),
            "n_correct": n_correct,
            "all_correct": n_correct == len(pairs),
            "any_correct": n_correct > 0,
        }
    return per_q


def cross_tab(detection_per_q, results, label):
    """Cross-tabulate detection × answer for the given system."""
    em_by_qid = {r["query_id"]: r["exact_match"] for r in results}

    # Buckets
    has_pair_qids = [qid for qid, d in detection_per_q.items() if d["n_has_pair"] > 0]
    no_pair_qids = [qid for qid, d in detection_per_q.items() if d["n_has_pair"] == 0]

    # For has_pair questions: classify by "all_correct" vs "any_correct" vs "none"
    full_det_em = []
    partial_det_em = []
    no_det_em = []

    for qid in has_pair_qids:
        d = detection_per_q[qid]
        em = em_by_qid.get(qid, False)
        if d["all_correct"]:
            full_det_em.append(em)
        elif d["any_correct"]:
            partial_det_em.append(em)
        else:
            no_det_em.append(em)

    # No-pair questions (no conflict at all)
    no_pair_em = [em_by_qid.get(qid, False) for qid in no_pair_qids]

    def stat(xs):
        n = len(xs); c = sum(xs)
        return c, n, (c / n * 100 if n else 0)

    print(f"\n=== {label} ===")
    print(f"\nDetection × Answer cross-tab:")
    print(f"|  Detection group  | n correct | n total | EM% |")
    print(f"|---|:---:|:---:|:---:|")
    fa, ft, fp = stat(full_det_em)
    pa, pt, pp = stat(partial_det_em)
    na, nt, np = stat(no_det_em)
    npa, npt, npp = stat(no_pair_em)
    print(f"| All has_pair detected correctly | {fa} | {ft} | {fp:.1f}% |")
    print(f"| Partial detection (1+ correct, 1+ missed) | {pa} | {pt} | {pp:.1f}% |")
    print(f"| No detection (0 correct) | {na} | {nt} | {np:.1f}% |")
    print(f"| No has_pair (no conflict in chain) | {npa} | {npt} | {npp:.1f}% |")

    overall_correct = sum(1 for em in em_by_qid.values() if em)
    print(f"\nOverall EM: {overall_correct}/{len(em_by_qid)} = {overall_correct/len(em_by_qid)*100:.1f}%")

    return {
        "label": label,
        "buckets": {
            "all_detected": {"correct": fa, "total": ft, "em_pct": fp},
            "partial_detection": {"correct": pa, "total": pt, "em_pct": pp},
            "no_detection": {"correct": na, "total": nt, "em_pct": np},
            "no_has_pair": {"correct": npa, "total": npt, "em_pct": npp},
        },
        "overall_em": overall_correct / len(em_by_qid) * 100,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="Mem0 history.db filter")
    args = parser.parse_args()

    sh_gt = json.load(open(SH_GT))
    mh_gt = json.load(open(MH_GT))

    sh_qpairs = get_question_pairs("SH", sh_gt)
    mh_qpairs = get_question_pairs("MH", mh_gt)

    # Mem0
    events = load_mem0_events(args.since)
    print(f"[load] {len(events)} Mem0 UPDATE events since {args.since}")

    mem0_sh_det = mem0_detection_per_question(events, sh_qpairs)
    mem0_mh_det = mem0_detection_per_question(events, mh_qpairs)

    mem0_sh_results = json.load(open(RESULTS / "mem0_gemini_sh_results.json"))
    mem0_mh_results = json.load(open(RESULTS / "mem0_gemini_mh_results.json"))

    out = {}
    out["mem0_sh"] = cross_tab(mem0_sh_det, mem0_sh_results, "Mem0 customized × Gemini × FC-SH")
    out["mem0_mh"] = cross_tab(mem0_mh_det, mem0_mh_results, "Mem0 customized × Gemini × FC-MH")

    # Zep × Gemini (use new audit)
    zep_g_sh_audit = RESULTS / "zep_gemini_sh_invalidation_audit.json"
    zep_g_mh_audit = RESULTS / "zep_gemini_mh_invalidation_audit.json"

    zep_sh_det = zep_detection_per_question(zep_g_sh_audit, sh_qpairs)
    zep_mh_det = zep_detection_per_question(zep_g_mh_audit, mh_qpairs)

    zep_sh_results = json.load(open(RESULTS / "zep_gemini_sh_results.json"))
    zep_mh_results = json.load(open(RESULTS / "zep_gemini_mh_results.json"))

    out["zep_sh"] = cross_tab(zep_sh_det, zep_sh_results, "Zep × Gemini × FC-SH")
    out["zep_mh"] = cross_tab(zep_mh_det, zep_mh_results, "Zep × Gemini × FC-MH")

    # Zep × GPT (existing full audit; results from outputs/gpt-4o-mini-zep/)
    zep_gpt_sh_audit = OLD_RESULTS / "zep_sh_invalidation_audit_v2.json"
    zep_gpt_mh_audit = OLD_RESULTS / "zep_mh_invalidation_audit_v2.json"

    if zep_gpt_sh_audit.exists():
        zep_gpt_sh_det = zep_detection_per_question(zep_gpt_sh_audit, sh_qpairs)
        zep_gpt_mh_det = zep_detection_per_question(zep_gpt_mh_audit, mh_qpairs)

        gpt_sh_path = BASE / "outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_6k_FULL100_chunk512_results.json"

        if gpt_sh_path.exists():
            gpt_sh_results_data = json.load(open(gpt_sh_path))
            zep_gpt_sh_results = [{"query_id": e.get("query_id", i), "exact_match": bool(e.get("exact_match", False))} for i, e in enumerate(gpt_sh_results_data["data"])]
            out["zep_gpt_sh"] = cross_tab(zep_gpt_sh_det, zep_gpt_sh_results, "Zep × GPT × FC-SH (FULL100, existing)")

        # MH FULL100 GPT JSON missing; reported 28% in zep_mh_full100_findings.md — skip cross-tab
        print("\n[note] Zep × GPT MH FULL100 JSON not found — skipping cross-tab. See analysis/results/oracle_a/zep_mh_full100_findings.md for the 28% number.")

    out_path = RESULTS / "detection_answer_correspondence.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
