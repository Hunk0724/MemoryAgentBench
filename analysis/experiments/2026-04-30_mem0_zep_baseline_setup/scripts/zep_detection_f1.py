"""
Zep detection F1 from existing invalidation audit (no new LLM calls).

Reads:
  analysis/results/oracle_a/zep_{sh,mh}_invalidation_audit_v2.json
  analysis/results/{sh,mh}_512_mquake_analysis.json     (for has_pair denominator)

Writes (stdout + json):
  analysis/results/diagnostic/zep_detection_metrics.json

Definitions:
  - TP = correct (Zep invalidate the OLD fact, in the right direction)
  - FP = wrong (invalidate the NEW fact instead) + false_positive (no GT counterpart)
  - FN = has_pair counts in dataset that Zep did NOT invalidate at all
  - Precision = TP / (TP + FP)
  - Recall    = TP / (TP + FN)
  - F1        = 2PR / (P + R)
"""

import json
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")


def compute(label, audit, has_pair_count):
    correct = audit.get("correct", 0)
    wrong = audit.get("wrong", 0)
    fp_no_counterpart = audit.get("false_positive", audit.get("false_positive_no_counterpart", 0))
    unknown = audit.get("unknown", 0)
    total_invalidations = audit.get("total", audit.get("total_invalidated", correct + wrong + fp_no_counterpart + unknown))

    tp = correct
    fp = wrong + fp_no_counterpart
    fn = has_pair_count - tp  # has_pair entries Zep failed to invalidate correctly

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    out = {
        "label": label,
        "has_pair_in_dataset": has_pair_count,
        "total_invalidations_made_by_zep": total_invalidations,
        "TP_correct": tp,
        "FP_wrong_direction": wrong,
        "FP_no_counterpart": fp_no_counterpart,
        "unknown": unknown,
        "FN_has_pair_not_invalidated": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }
    print(f"\n=== {label} ===")
    for k, v in out.items():
        print(f"  {k}: {v}")
    return out


def main():
    sh_audit = json.load(open(BASE / "analysis/results/oracle_a/zep_sh_invalidation_audit_v2.json"))
    mh_audit = json.load(open(BASE / "analysis/results/oracle_a/zep_mh_invalidation_audit_v2.json"))

    sh_gt = json.load(open(BASE / "analysis/results/sh_512_mquake_analysis.json"))
    mh_gt = json.load(open(BASE / "analysis/results/mh_512_mquake_analysis.json"))

    sh_has_pair = sum(1 for q in sh_gt if q.get("conflict_type") == "has_pair")
    mh_has_pair_hops = sum(
        1 for q in mh_gt for h in q.get("hops", [])
        if h.get("conflict_type") == "has_pair"
    )

    sh_metrics = compute("Zep FC-SH (gpt-4o-mini)", sh_audit, sh_has_pair)
    mh_metrics = compute("Zep FC-MH (gpt-4o-mini, hop-level)", mh_audit, mh_has_pair_hops)

    out_path = BASE / "analysis/experiments/2026-04-30_mem0_zep_baseline_setup/results/zep_detection_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "fc_sh": sh_metrics,
            "fc_mh": mh_metrics,
            "notes": [
                "Zep internal LLM = whatever Zep cloud uses (closed; not changeable to Gemini).",
                "Inference-side LLM in our existing run = gpt-4o-mini.",
                "TP / FP / FN are at the (s, r, OLD fact) level for SH and the hop level for MH.",
                "Wrong direction (invalidate NEW instead of OLD) counted as FP — production system error mode.",
            ],
        }, f, indent=2)
    print(f"\nWritten to: {out_path}")


if __name__ == "__main__":
    main()
