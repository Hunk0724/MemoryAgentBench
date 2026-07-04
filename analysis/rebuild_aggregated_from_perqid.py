"""Rebuild aggregated Conflict_Resolution/*.json from per-qid `response`.

Per rigor_audit.py, several (method, length) cells have stale/broken aggregated
files whose `output`/`exact_match` fields do NOT match the per-qid `response`
they were supposedly summarizing. This script:

  1. For each requested (method, length):
     - Locate the canonical aggregated file (same picker as compute_pool_acc_crosstab)
     - Locate the per-qid dir
  2. Backup the OLD aggregated JSON to
       outputs/_deprecated/2026-07-04-cleanup/<agent>/<Conflict_Resolution>/<basename>
     (preserves the historical file — nothing is deleted)
  3. Rebuild the aggregated file:
     - For each qid in old aggregated's `data` list:
       - Read matching per-qid file's `response`
       - Overwrite: output, parsed_output, exact_match, f1, substring_exact_match,
         rougeL_f1, rougeL_recall, rougeLsum_f1, rougeLsum_recall
       - Preserve everything else (input_len, memory_construction_time,
         query_time_len, answer, query, query_id, qa_pair_id)
     - Recompute `averaged_metrics` from the rebuilt data list
     - Add `_rebuilt` provenance block with date + source-of-truth per-qid dir
  4. Write rebuilt file to the ORIGINAL aggregated path
  5. Print a per-cell before/after EM summary

Cost: 0 API. ~30 seconds for 4 problematic cells.

Reversibility: OLD aggregated is at _deprecated/2026-07-04-cleanup/... — moving
that back and re-running rigor_audit.py restores prior state.

Usage:
    # Rebuild only the 4 audit-flagged cells:
    python analysis/rebuild_aggregated_from_perqid.py

    # Or specify explicitly:
    python analysis/rebuild_aggregated_from_perqid.py \\
        --cell "(b) mem0+P1:64k" --cell "Zep (k=10):32k"
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from utils.eval_other_utils import default_post_process  # noqa: E402
from analysis.rigor_audit import METHODS, pick_agg_file, load_gt  # noqa: E402

DEPRECATED_ROOT = REPO / "outputs/_deprecated/2026-07-04-cleanup"


def rebuild_cell(label: str, per_qid_root: str, results_dir: str, L: str,
                 dry_run: bool = False) -> dict:
    """Rebuild aggregated for one (method, length). Returns summary dict."""
    agg_file = pick_agg_file(results_dir, L)
    if agg_file is None:
        return {"method": label, "length": L, "status": "no-aggregated"}
    agg_path = Path(agg_file)
    per_qid_dir = REPO / per_qid_root / f"factconsolidation_sh_{L}" / "chunksize_512"
    if not per_qid_dir.exists():
        return {"method": label, "length": L, "status": "no-perqid-dir"}

    old_agg = json.load(open(agg_path))
    if "data" not in old_agg:
        return {"method": label, "length": L, "status": "no-data-field"}

    # Rebuild data by walking old data + patching from per-qid
    new_data = []
    old_em, new_em = 0, 0
    old_sem, new_sem = 0, 0
    n_patched = 0
    n_missing = 0
    dataset_config = old_agg.get("dataset_config", {})

    for row in old_agg["data"]:
        qid = row.get("query_id")
        answer = row.get("answer")
        pqf = per_qid_dir / f"query_{qid}_context_0.json"
        old_em += 1 if row.get("exact_match") else 0
        old_sem += 1 if row.get("substring_exact_match") else 0

        if not pqf.exists():
            n_missing += 1
            new_data.append(row)
            new_em += 1 if row.get("exact_match") else 0
            new_sem += 1 if row.get("substring_exact_match") else 0
            continue

        try:
            pq = json.load(open(pqf))
        except Exception:
            n_missing += 1
            new_data.append(row)
            new_em += 1 if row.get("exact_match") else 0
            new_sem += 1 if row.get("substring_exact_match") else 0
            continue

        response = pq.get("response") or ""
        # Apply MAB default_post_process semantics
        metrics, extras = default_post_process({"output": response}, answer)
        parsed_out = extras.get("parsed_output")

        new_row = dict(row)  # preserve query_id, input_len, ..., answer, query, qa_pair_id
        new_row["output"] = response
        new_row["parsed_output"] = parsed_out
        for k in ("exact_match", "f1", "substring_exact_match",
                  "rougeL_f1", "rougeL_recall", "rougeLsum_f1", "rougeLsum_recall"):
            if k in metrics:
                new_row[k] = metrics[k]
        new_data.append(new_row)
        new_em += 1 if new_row.get("exact_match") else 0
        new_sem += 1 if new_row.get("substring_exact_match") else 0
        n_patched += 1

    # Recompute averaged_metrics
    def _avg(rows, key):
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        if not vals: return None
        return sum(float(v) for v in vals) / len(vals)
    averaged = {
        k: _avg(new_data, k)
        for k in ("exact_match", "f1", "substring_exact_match",
                  "rougeL_f1", "rougeL_recall", "rougeLsum_f1", "rougeLsum_recall",
                  "input_len", "output_len",
                  "memory_construction_time", "query_time_len")
    }
    # Scale exact_match/substring/etc. to percentage if they came in as 0/1
    for k in ("exact_match", "f1", "substring_exact_match",
              "rougeL_f1", "rougeL_recall", "rougeLsum_f1", "rougeLsum_recall"):
        if averaged.get(k) is not None and averaged[k] <= 1.0:
            averaged[k] = averaged[k] * 100

    new_agg = dict(old_agg)  # preserve agent_config, dataset_config, time_cost, etc.
    new_agg["data"] = new_data
    new_agg["averaged_metrics"] = averaged
    new_agg["_rebuilt"] = {
        "date": str(date(2026, 7, 4)),
        "source_of_truth": f"per-qid {per_qid_dir.relative_to(REPO)}",
        "n_patched_from_perqid": n_patched,
        "n_perqid_missing": n_missing,
        "backup": str((DEPRECATED_ROOT / agg_path.relative_to(REPO / "outputs")).relative_to(REPO)) if not dry_run else "(dry-run)",
        "reason": "aggregated `output`/`exact_match` was stale/broken vs per-qid `response`; see rigor_audit.md",
    }

    summary = {
        "method": label,
        "length": L,
        "agg_file": str(agg_path.relative_to(REPO)),
        "old_em": f"{old_em}/{len(old_agg['data'])}",
        "new_em": f"{new_em}/{len(new_data)}",
        "old_sem": f"{old_sem}/{len(old_agg['data'])}",
        "new_sem": f"{new_sem}/{len(new_data)}",
        "n_patched": n_patched,
        "n_missing": n_missing,
        "status": "rebuilt" if not dry_run else "dry-run",
    }

    if dry_run:
        return summary

    # Backup and write
    backup_path = DEPRECATED_ROOT / agg_path.relative_to(REPO / "outputs")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(agg_path, backup_path)
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(new_agg, f, ensure_ascii=False, indent=2)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    p.add_argument("--cell", action="append", default=None,
                   help='Specific cell: "label:length" e.g. "(b) mem0+P1:64k". Repeatable.')
    p.add_argument("--audit-flagged-only", action="store_true", default=True,
                   help="Only rebuild cells flagged by rigor_audit.py (stale or broken). Default TRUE.")
    args = p.parse_args()

    FLAGGED = {
        ("(b) mem0+P1", "6k"),
        ("(b) mem0+P1", "32k"),
        ("(b) mem0+P1", "64k"),
        ("Zep (k=10)", "32k"),
    }

    if args.cell:
        want = {tuple(c.rsplit(":", 1)) for c in args.cell}
    elif args.audit_flagged_only:
        want = FLAGGED
    else:
        want = {(m[0], L) for m in METHODS for L in ("6k", "32k", "64k")}

    print(f"Rebuild target cells: {sorted(want)}")
    print()

    rows = []
    for label, per_qid_root, results_dir in METHODS:
        for L in ("6k", "32k", "64k"):
            if (label, L) not in want:
                continue
            r = rebuild_cell(label, per_qid_root, results_dir, L, dry_run=args.dry_run)
            rows.append(r)
            if r.get("status") in ("rebuilt", "dry-run"):
                print(f"[{r['status']:7s}] {label:24s} × {L:3s}  "
                      f"EM {r['old_em']} → {r['new_em']}  "
                      f"sEM {r['old_sem']} → {r['new_sem']}  "
                      f"(patched {r['n_patched']}, missing {r['n_missing']})")
            else:
                print(f"[{r['status']:7s}] {label:24s} × {L:3s}  (skipped)")

    print()
    if args.dry_run:
        print("DRY-RUN complete. Re-run without --dry-run to apply.")
    else:
        print(f"Rebuild complete. Backups in {DEPRECATED_ROOT.relative_to(REPO)}/")
        print("Verify: python analysis/rigor_audit.py")


if __name__ == "__main__":
    main()
