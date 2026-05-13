"""For the 120 Phase 1 missed Type-1 chain_old hops, identify root cause.

Approach: for each missed (gt_fact_text, old_fact_text) pair, the differing
tails give us gt_obj and old_obj. Scan ALL OpenIE triples and ask:
  - Is there ANY triple whose object matches gt_obj? (chain_new extracted)
  - Is there ANY triple whose object matches old_obj? (chain_old extracted)
  - Among them, are there pairs sharing the SAME (s, r) that would have been
    caught by Phase 1's (S, R)≠O rule?

This decomposes the missed cases into:
  (A) OpenIE didn't extract chain_old at all (or both at all)
  (B) OpenIE extracted both but DIFFERENT subjects (e.g., "Charles" vs "Darwin")
  (C) OpenIE extracted both with SAME subject but DIFFERENT relations
      (alias on relation needed)
  (D) BOTH same (S, R) — should have been caught (Phase 1 bug? rare edge case?)
"""
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
OPENIE = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
SUPERSESSION = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/supersession_index.json"
GT = BASE / "analysis/results/mh_512_mquake_analysis.json"
OUT = BASE / "analysis/results/phase_v1/phase1_root_cause.json"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip().rstrip(".,;:!?\"'"))


def text_match(a: str, b: str) -> bool:
    """Substring either direction; both ≥ 3 chars."""
    a_n, b_n = norm(a), norm(b)
    if len(a_n) < 3 or len(b_n) < 3:
        return False
    return a_n == b_n or a_n in b_n or b_n in a_n


def get_object_diff(gt_text: str, old_text: str):
    """Extract differing tails between gt and old fact text."""
    gt_n, old_n = norm(gt_text), norm(old_text)
    # Common prefix at word boundary
    gt_w, old_w = gt_n.split(), old_n.split()
    lcp = 0
    for a, b in zip(gt_w, old_w):
        if a == b:
            lcp += 1
        else:
            break
    gt_obj = " ".join(gt_w[lcp:])
    old_obj = " ".join(old_w[lcp:])
    return gt_obj, old_obj


def main():
    oie = json.load(open(OPENIE))
    sup = json.load(open(SUPERSESSION))["superseded_facts"]
    gt = json.load(open(GT))

    # Collect ALL OpenIE triples (across all chunks)
    triples = []  # list of (s_norm, r_orig, r_norm, o_norm, chunk_idx, s_orig, o_orig)
    for chunk_idx, doc in enumerate(oie["docs"]):
        for tri in doc.get("extracted_triples", []):
            if not (isinstance(tri, (list, tuple)) and len(tri) == 3):
                continue
            s, r, o = [str(x).strip() for x in tri]
            triples.append((norm(s), r, norm(r), norm(o), chunk_idx, s, o))

    # Iterate missed
    detected_count = 0
    missed = []
    for q in gt:
        qid = q.get("query_id")
        for hop_idx, hop in enumerate(q.get("hops", [])):
            if hop.get("conflict_type") != "has_pair":
                continue
            gt_text = hop.get("gt_fact_text", "")
            old_text = hop.get("old_fact_text", "")
            if not gt_text or not old_text:
                continue

            # detected check (same as before)
            detected = False
            for fk, info in sup.items():
                s, o = norm(info["s"]), norm(info["o_old"])
                tn = norm(old_text)
                if s in tn and o in tn and len(s) >= 3 and len(o) >= 3:
                    detected = True
                    break

            if detected:
                detected_count += 1
                continue

            # Missed — diagnose
            gt_obj, old_obj = get_object_diff(gt_text, old_text)

            # Find OpenIE triples matching gt_obj (chain_new) and old_obj (chain_old)
            new_triples = [t for t in triples if text_match(t[3], gt_obj)]   # match on object
            old_triples = [t for t in triples if text_match(t[3], old_obj)]

            # Now check if any new/old pair shares same S and same R
            new_subjects = {t[0] for t in new_triples}
            old_subjects = {t[0] for t in old_triples}
            shared_subjects = new_subjects & old_subjects

            has_new = len(new_triples) > 0
            has_old = len(old_triples) > 0
            same_S = len(shared_subjects) > 0

            if has_new and has_old and same_S:
                # Check if any shared_subj has same R between new and old
                same_S_same_R_pairs = []
                for s in shared_subjects:
                    new_rels = {t[2] for t in new_triples if t[0] == s}
                    old_rels = {t[2] for t in old_triples if t[0] == s}
                    if new_rels & old_rels:
                        same_S_same_R_pairs.append({"s": s, "shared_rels": list(new_rels & old_rels)})
                if same_S_same_R_pairs:
                    root = "(D) Same S same R but Phase1 didn't catch — investigate"
                    extra = same_S_same_R_pairs
                else:
                    root = "(C) Both extracted, SAME S, DIFFERENT R surfaces — alias R needed"
                    extra = {"shared_subjects": list(shared_subjects)[:3]}
            elif has_new and has_old:
                root = "(B) Both extracted, DIFFERENT S surfaces — alias S (entity canonicalize) needed"
                extra = {
                    "new_subjects": list(new_subjects)[:3],
                    "old_subjects": list(old_subjects)[:3],
                }
            elif has_old and not has_new:
                root = "(A1) Only chain_old extracted (not chain_new) — corpus / OpenIE coverage"
                extra = {"old_subjects": list(old_subjects)[:3]}
            elif has_new and not has_old:
                root = "(A2) Only chain_new extracted (not chain_old) — corpus / OpenIE coverage"
                extra = {"new_subjects": list(new_subjects)[:3]}
            else:
                root = "(A3) NEITHER extracted — OpenIE missed both"
                extra = {}

            missed.append({
                "qid": qid, "hop_idx": hop_idx,
                "gt_text": gt_text, "old_text": old_text,
                "gt_obj": gt_obj, "old_obj": old_obj,
                "n_chain_new_triples": len(new_triples),
                "n_chain_old_triples": len(old_triples),
                "root_cause": root,
                "extra": extra,
            })

    # Aggregate
    root_counts = defaultdict(int)
    for m in missed:
        root_counts[m["root_cause"]] += 1

    print("=" * 75)
    print(f"Phase 1 Root Cause Analysis (n_missed={len(missed)} of 188 GT has_pair hops)")
    print("=" * 75)
    print(f"\nDetected by Phase 1:    {detected_count} / 188 = {detected_count*100/188:.1f}%")
    print(f"Missed:                  {len(missed)} / 188")

    print(f"\n--- Root cause distribution (missed only) ---")
    for root, count in sorted(root_counts.items(), key=lambda x: -x[1]):
        pct = count * 100 / len(missed) if missed else 0
        print(f"  {count:3d} ({pct:5.1f}%)  {root}")

    print(f"\n--- Sample by root cause ---")
    seen_roots = set()
    for m in missed:
        if m["root_cause"] in seen_roots:
            continue
        seen_roots.add(m["root_cause"])
        print(f"\n  [{m['root_cause']}]")
        print(f"    qid={m['qid']} hop={m['hop_idx']}")
        print(f"    GT new: {m['gt_text']!r}")
        print(f"    GT old: {m['old_text']!r}")
        print(f"    gt_obj={m['gt_obj']!r}, old_obj={m['old_obj']!r}")
        print(f"    OpenIE: {m['n_chain_new_triples']} chain_new + {m['n_chain_old_triples']} chain_old triples found")
        if m["extra"]:
            print(f"    extra: {m['extra']}")

    # v2 direction implications
    cat_A = root_counts["(A1) Only chain_old extracted (not chain_new) — corpus / OpenIE coverage"] \
            + root_counts["(A2) Only chain_new extracted (not chain_old) — corpus / OpenIE coverage"] \
            + root_counts["(A3) NEITHER extracted — OpenIE missed both"]
    cat_B = root_counts["(B) Both extracted, DIFFERENT S surfaces — alias S (entity canonicalize) needed"]
    cat_C = root_counts["(C) Both extracted, SAME S, DIFFERENT R surfaces — alias R needed"]
    cat_D = root_counts.get("(D) Same S same R but Phase1 didn't catch — investigate", 0)

    print(f"\n--- v2 implications ---")
    print(f"  (A) OpenIE coverage issue:  {cat_A:3d} ({cat_A*100/len(missed):.1f}%) — needs OpenIE prompt improvement / LLM-based detection")
    print(f"  (B) Entity surface alias:   {cat_B:3d} ({cat_B*100/len(missed):.1f}%) — needs alias normalization on entities")
    print(f"  (C) Relation surface alias: {cat_C:3d} ({cat_C*100/len(missed):.1f}%) — needs alias normalization on relations")
    print(f"  (D) Edge case bugs:         {cat_D:3d} ({cat_D*100/len(missed):.1f}%) — investigate Phase 1 logic")

    json.dump({
        "n_detected": detected_count, "n_missed": len(missed),
        "root_cause_distribution": dict(root_counts),
        "v2_implications": {"A_openie_coverage": cat_A, "B_entity_alias": cat_B, "C_relation_alias": cat_C, "D_bug": cat_D},
        "missed_examples": missed[:40],
    }, open(OUT, "w"), indent=2)
    print(f"\n[wrote] {OUT}")


if __name__ == "__main__":
    main()
