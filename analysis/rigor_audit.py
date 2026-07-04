"""Rigor audit — scan all (method, length) for aggregated vs per-qid consistency.

For each canonical (method, length) cell used by paper_current, this script:
  1. Locate the aggregated Conflict_Resolution/*.json (canonical picker: same
     pattern as compute_pool_acc_crosstab.load_em).
  2. Locate the per-qid `outputs/rag_retrieved/.../query_*.json` files.
  3. For every has_pair qid, compare:
     - aggregated `output` vs per-qid `response`      (raw string equality)
     - aggregated `exact_match` (as reported by MAB)  vs
     - EM recomputed from per-qid `response` via MAB official
       `default_post_process` semantics: max(EM(raw), EM(parse_output(raw)))
  4. Report per (method, length):
     - has_pair N, aggregated n_data, per-qid n_files
     - mismatch count (agg.output ≠ perqid.response)
     - AGG EM, PER-Q EM, and per-qid derived EM
     - status: OK / stale-aggregated / broken-aggregated
  5. Emit a markdown report → paper_current/results/rigor_audit.md

Usage:
    python analysis/rigor_audit.py [--out PATH]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from utils.eval_other_utils import (  # noqa: E402
    parse_output, drqa_exact_match_score, drqa_metric_max_over_ground_truths,
)

GT_PATHS = {
    "6k": "analysis/results/sh_512_mquake_analysis.json",
    "32k": "analysis/results/sh_32k_mquake_analysis.json",
    "64k": "analysis/results/sh_64k_mquake_analysis.json",
}

# Canonical (method, length) cells used by paper_current/results/pool_acc_crosstab.md.
# Each row: (label, per_qid_dir_root, results_dir_glob)
#
# Naming (2026-07-05 update per user directive):
#   - MAIN method = `ours` = struct + P3 + argmax (formerly labeled "no_p5")
#   - Ablations: `ours (no P3)` = struct only; `ours (no struct)` = P3 only
#   - Appendix: `ours (+P5)` = with P5 conflict-type classifier (formerly "full")
#     kept because run_fc_sh.sh requires ours variant to run first to build
#     P1 extraction cache; the +P5 result itself is appendix-only material.
METHODS = [
    # ==================== gpt-4o-mini (canonical main analyses) ====================
    ("ours",
     "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5/k_100",
     "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_no_p5/Conflict_Resolution"),
    ("ours (no P3)",
     "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_struct/k_100",
     "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct/Conflict_Resolution"),
    ("ours (no struct)",
     "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_p3_only_no_struct/k_100",
     "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_p3_only_no_struct/Conflict_Resolution"),
    ("(b) mem0+P1",
     "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100",
     "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution"),
    ("Zep (k=10)",
     "outputs/rag_retrieved/Structure_rag_zep/k_10",
     "gpt-4o-mini-zep/Conflict_Resolution"),
    ("ours (+P5) [appendix]",
     "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified/k_100",
     "gpt-4o-mini-mem0-chunk512-temp0-openai-unified/Conflict_Resolution"),
    # ==================== gpt-4.1-mini (Plan A backbone extension @ 64k) ====================
    ("[4.1-mini] ours",
     "outputs/rag_retrieved/Structure_rag_gpt-4.1-mini-mem0_512_openai_unified_no_p5/k_100",
     "gpt-4.1-mini-mem0-chunk512-temp0-openai-unified_no_p5/Conflict_Resolution"),
    ("[4.1-mini] ours (no P3)",
     "outputs/rag_retrieved/Structure_rag_gpt-4.1-mini-mem0_512_openai_unified_struct/k_100",
     "gpt-4.1-mini-mem0-chunk512-temp0-openai-unified_struct/Conflict_Resolution"),
    ("[4.1-mini] ours (no struct)",
     "outputs/rag_retrieved/Structure_rag_gpt-4.1-mini-mem0_512_openai_unified_p3_only_no_struct/k_100",
     "gpt-4.1-mini-mem0-chunk512-temp0-openai-unified_p3_only_no_struct/Conflict_Resolution"),
    ("[4.1-mini] (b) mem0+P1",
     "outputs/rag_retrieved/Structure_rag_gpt-4.1-mini-mem0_512_openai_unified_dest/k_100",
     "gpt-4.1-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution"),
    ("[4.1-mini] Zep (k=10)",
     "outputs/rag_retrieved/Structure_rag_gpt-4.1-mini-zep/k_10",
     "gpt-4.1-mini-zep/Conflict_Resolution"),
    ("[4.1-mini] ours (+P5) [appendix]",
     "outputs/rag_retrieved/Structure_rag_gpt-4.1-mini-mem0_512_openai_unified/k_100",
     "gpt-4.1-mini-mem0-chunk512-temp0-openai-unified/Conflict_Resolution"),
]

STANDARD_PATTERN = "size256_shots0_max_samplesunknown"
FALLBACK_PATTERN = "size256_shots0_max_samples1"  # 64k mem0 uses this


def load_gt(L: str) -> dict:
    return {e["query_id"]: e for e in json.load(open(REPO / GT_PATHS[L]))}


def pick_agg_file(results_dir: str, L: str) -> Optional[str]:
    root = REPO / f"outputs/{results_dir}"
    files = sorted(glob.glob(str(root / f"factconsolidation_sh_{L}_*results*.json")))
    for pattern in (STANDARD_PATTERN, FALLBACK_PATTERN):
        for f in files:
            if pattern in f:
                try:
                    d = json.load(open(f))
                    if len(d.get("data", [])) >= 50:
                        return f
                except Exception:
                    continue
    # Fallback: file with max n_data
    best_file, best_n = None, 0
    for f in files:
        try:
            d = json.load(open(f))
            n = len(d.get("data", []))
            if n > best_n:
                best_n = n
                best_file = f
        except Exception:
            continue
    return best_file if best_n >= 50 else None


def official_em(response: str, gt_answer) -> bool:
    """MAB official EM: max(EM(raw), EM(parse_output(raw)))."""
    if response is None or gt_answer is None:
        return False
    if bool(drqa_metric_max_over_ground_truths(
            drqa_exact_match_score, str(response), gt_answer)):
        return True
    parsed = parse_output(str(response))
    if parsed is None:
        return False
    return bool(drqa_metric_max_over_ground_truths(
        drqa_exact_match_score, parsed, gt_answer))


def audit_cell(label: str, per_qid_root: str, results_dir: str, L: str) -> dict:
    gt = load_gt(L)
    hp_qids = {q for q, e in gt.items() if e.get("conflict_type") == "has_pair"}
    per_qid_dir = REPO / per_qid_root / f"factconsolidation_sh_{L}" / "chunksize_512"

    agg_file = pick_agg_file(results_dir, L)
    result = {
        "method": label,
        "length": L,
        "n_hp": len(hp_qids),
        "agg_file": os.path.relpath(agg_file, REPO) if agg_file else None,
        "per_qid_dir": os.path.relpath(per_qid_dir, REPO) if per_qid_dir.exists() else None,
        "per_qid_missing": [],
        "n_agg_data": None,
        "agg_em_hp": 0,
        "perqid_em_hp": 0,
        "n_perqid_present": 0,
        "mismatches_output_vs_response": 0,
        "mismatch_sample": [],
        "empty_response_perqid": 0,
        "empty_output_agg": 0,
        "status": "unknown",
    }

    if agg_file is None:
        result["status"] = "no-aggregated"
        return result
    if not per_qid_dir.exists():
        result["status"] = "no-perqid-dir"
        return result

    agg = json.load(open(agg_file))
    result["n_agg_data"] = len(agg.get("data", []))
    agg_map = {d["query_id"]: d for d in agg["data"]}

    for qid in sorted(hp_qids):
        pqf = per_qid_dir / f"query_{qid}_context_0.json"
        if not pqf.exists():
            result["per_qid_missing"].append(qid)
            continue
        try:
            pq = json.load(open(pqf))
        except Exception:
            result["per_qid_missing"].append(qid)
            continue
        result["n_perqid_present"] += 1

        # Response strings
        resp_pq = (pq.get("response") or "").strip()
        if not resp_pq or resp_pq.lower() in ("answer:", "answer"):
            result["empty_response_perqid"] += 1

        if qid not in agg_map:
            continue
        agg_row = agg_map[qid]
        agg_out = (agg_row.get("output") or "").strip()
        if not agg_out or agg_out.lower() in ("answer:", "answer"):
            result["empty_output_agg"] += 1

        # Mismatch (raw string equality — case-sensitive to catch overwrites)
        if resp_pq != agg_out:
            result["mismatches_output_vs_response"] += 1
            if len(result["mismatch_sample"]) < 3:
                result["mismatch_sample"].append({
                    "qid": qid,
                    "per_qid": resp_pq[:80],
                    "agg": agg_out[:80],
                    "gt_answer": agg_row.get("answer"),
                })

        # EM
        if agg_row.get("exact_match"):
            result["agg_em_hp"] += 1
        gt_ans = agg_row.get("answer") or gt.get(qid, {}).get("gt_answer")
        if official_em(resp_pq, gt_ans):
            result["perqid_em_hp"] += 1

    # Status heuristic
    if result["mismatches_output_vs_response"] == 0:
        result["status"] = "OK"
    elif result["empty_output_agg"] > 5:
        result["status"] = "broken-aggregated"
    else:
        result["status"] = "stale-aggregated"

    return result


def emit_report(rows: list[dict], out_path: Path) -> None:
    lines = []
    lines.append("# Rigor Audit — aggregated ↔ per-qid consistency (all method × length)")
    lines.append("")
    lines.append("> **When to re-run**:每次 baseline / method 有新 run 之後,commit 前必跑一次。")
    lines.append("> **Command**: `python analysis/rigor_audit.py`")
    lines.append("> **Source of truth**:per-qid `response`(內部 consistent with pool);aggregated 只是 batch summary,可能 stale。")
    lines.append("> **EM 定義**:MAB 官方 `default_post_process` = max(EM(raw), EM(parse_output(raw))) 用 `drqa_exact_match_score`。")
    lines.append("> **Matcher**:pool state 判定用 [`matcher_specification.md`](matcher_specification.md) v4;此 audit 只查 EM/response consistency,不查 matcher。")
    lines.append("")
    lines.append("## 1. 摘要 status 表")
    lines.append("")
    lines.append("| Method | Length | N | AGG EM | Per-qid EM | Mismatch (out ≠ resp) | Empty AGG output | Empty per-qid resp | Status |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
    for r in rows:
        n_hp = r["n_hp"]
        agg_em = r["agg_em_hp"]
        pq_em = r["perqid_em_hp"]
        mism = r["mismatches_output_vs_response"]
        emp_a = r["empty_output_agg"]
        emp_p = r["empty_response_perqid"]
        status = r["status"]
        status_icon = {
            "OK": "✅ OK",
            "stale-aggregated": "⚠️ stale-agg",
            "broken-aggregated": "🚨 broken-agg",
            "no-aggregated": "❌ no-agg",
            "no-perqid-dir": "❌ no-perqid",
            "unknown": "❓",
        }.get(status, status)
        lines.append(f"| {r['method']} | {r['length']} | {n_hp} | {agg_em}/{n_hp} | {pq_em}/{n_hp} | {mism} | {emp_a} | {emp_p} | {status_icon} |")
    lines.append("")

    lines.append("## 2. 詳細:mismatch 樣本")
    lines.append("")
    for r in rows:
        if r["mismatches_output_vs_response"] == 0:
            continue
        lines.append(f"### {r['method']} × {r['length']} ({r['mismatches_output_vs_response']} mismatches)")
        lines.append(f"- Aggregated: `{r['agg_file']}`")
        lines.append(f"- Per-qid   : `{r['per_qid_dir']}/query_*_context_0.json`")
        lines.append("")
        lines.append("| qid | per-qid response | aggregated output | gt_answer |")
        lines.append("| :---: | :--- | :--- | :--- |")
        for s in r["mismatch_sample"]:
            pq = s["per_qid"].replace("|", "\\|")
            ag = s["agg"].replace("|", "\\|")
            lines.append(f"| {s['qid']} | `{pq}` | `{ag}` | `{s['gt_answer']}` |")
        lines.append("")

    lines.append("## 3. Canonical file registry(以 per-qid 為 source of truth)")
    lines.append("")
    lines.append("| Method × Length | Aggregated file | Per-qid dir |")
    lines.append("| :--- | :--- | :--- |")
    for r in rows:
        lines.append(f"| {r['method']} × {r['length']} | `{r['agg_file']}` | `{r['per_qid_dir']}` |")
    lines.append("")

    lines.append("## 4. Interpretation & action recommended per status")
    lines.append("")
    lines.append("- **✅ OK** — aggregated ↔ per-qid consistent;可安全引用 aggregated 的 `exact_match` 欄")
    lines.append("- **⚠️ stale-aggregated** — mismatch 存在但 aggregated `output` 非空;通常代表**部分 re-run 覆蓋 per-qid 但沒重生 aggregated**。**應該從 per-qid 重生 aggregated**;此處 crosstab 已 fallback 用 per-qid,結果不受影響")
    lines.append("- **🚨 broken-aggregated** — aggregated `output` 大量為 `Answer:` 空 stub;需要:(a) 用 per-qid 重生 aggregated,或 (b) 明確標記此 aggregated 檔為 corrupted 並移到 `_deprecated/`")
    lines.append("- **❌ no-aggregated / no-perqid** — canonical 路徑找不到檔;需檢查 method × length 是否真的跑過 / 檔案路徑是否對")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(REPO / "docs/0615_intro_framework_after_problem_statement/paper_current/results/rigor_audit.md"))
    p.add_argument("--length", choices=["6k", "32k", "64k"], nargs="*", default=["6k", "32k", "64k"])
    args = p.parse_args()

    rows = []
    for label, per_qid_root, results_dir in METHODS:
        for L in args.length:
            r = audit_cell(label, per_qid_root, results_dir, L)
            rows.append(r)
            print(f"{label:24s} × {L}: status={r['status']}  agg_em={r['agg_em_hp']}/{r['n_hp']}  pq_em={r['perqid_em_hp']}/{r['n_hp']}  mism={r['mismatches_output_vs_response']}")

    emit_report(rows, Path(args.out))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
