"""Offline attribution: for FC-SH 6k has_pair, per backbone, decide for each
query whether the OLD and NEW extracted triples get merged into the same
(S,P) group, and — if merged — which normalization layer did it:
  L0 (P2-exact) : raw (subj.lower.strip, pred.lower.strip) already identical
  L1            : identical only after L1 (hyphen/underscore->space, ws-collapse)
  L2            : identical only after full normalize (drop articles the/a/an/of,
                  copula is/was/..->be)
  NOT-MERGED    : still differ after full normalize -> old survives beside new
                  -> pool NOT isolated (reader must rescue, or it's wrong).
Cross-referenced with the reader EM (results.json) -> rescue (not-merged & EM ok)
vs drag (not-merged & EM wrong). No embeddings / no store / no GPU / no .env.
  python3 analysis/attribute_sp_merge_6k.py [sizes...]
"""
import json, glob, re, sys, unicodedata

SIZES = sys.argv[1:] or ["12b"]
gt = {r["query_id"]: r for r in json.load(open("analysis/results/sh_6k_RUN_gt.json"))}
HP = [q for q, r in gt.items() if r["conflict_type"] == "has_pair"]

# --- normalize (mirrors methods/phase0_triple_extractor.py, verified) ---
_PRED_ARTICLES = {"the", "a", "an", "of"}
_PRED_COPULA = {"is", "was", "are", "were", "be", "been", "being"}


def n_subj(t):
    s = (t or "").lower().strip()
    s = re.sub(r"[-‐-―]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+", "_", s)


def pred_L1(t):  # L1 only: hyphen/underscore->space + ws-collapse
    s = (t or "").lower().strip()
    s = re.sub(r"[-_‐-―]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pred_full(t):  # L1 + L2 (drop articles, copula->be)
    toks = pred_L1(t).split()
    out = [("be" if w in _PRED_COPULA else w) for w in toks if w not in _PRED_ARTICLES]
    return " ".join(out) or " ".join(toks)


def subj_L1(t):
    s = (t or "").lower().strip()
    s = re.sub(r"[-‐-―]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_val(v):
    v = unicodedata.normalize("NFKC", str(v)).lower().strip().strip("[]'\" .")
    return re.sub(r"\s+", " ", v)


def obj_match(triple_obj, gt_val):
    a, b = norm_val(triple_obj), norm_val(gt_val)
    return a == b or (len(b) > 2 and (b in a or a in b))


def em_map(tag, size):
    fs = glob.glob(f"outputs/*unified_{tag}__gemma3-{size}/Conflict_Resolution/*sh_6k*results*.json")
    return {r["query_id"]: bool(r["exact_match"]) for r in json.load(open(fs[0]))["data"]} if fs else {}


for size in SIZES:
    triples = list(json.load(open(f"analysis/results/p1_caches__gemma3-{size}/triple_cache_p1_6k.json")).values())
    em = em_map("struct", size)
    print(f"\n================ gemma3-{size}  (has_pair N={len(HP)}) ================")
    lvl = {"L0_p2exact": 0, "L1": 0, "L2": 0, "not_merged": 0, "new_missing": 0, "old_missing": 0}
    notiso = []
    bylevel_examples = {"L0_p2exact": [], "L1": [], "L2": []}
    for q in HP:
        r = gt[q]
        new_c = [t for t in triples if obj_match(t.get("object", ""), r["gt_answer"])]
        old_c = [t for t in triples if obj_match(t.get("object", ""), r["old_answer"])]
        if not new_c:
            lvl["new_missing"] += 1
            notiso.append((q, "NEW_MISSING", None, None, em.get(q)))
            continue
        if not old_c:
            lvl["old_missing"] += 1  # old absent -> trivially isolated (nothing to drop)
            continue
        # pick the (new,old) pair sharing a subject (normalized)
        pair = None
        for nt in new_c:
            for ot in old_c:
                if n_subj(nt.get("subject", "")) == n_subj(ot.get("subject", "")):
                    pair = (nt, ot); break
            if pair: break
        if pair is None:  # fall back: closest by subject token overlap
            nt = new_c[0]; ot = min(old_c, key=lambda o: -len(set(n_subj(o.get("subject","")).split("_")) & set(n_subj(nt.get("subject","")).split("_"))))
            pair = (nt, ot)
        nt, ot = pair
        ns, os_ = nt.get("subject", ""), ot.get("subject", "")
        npd, opd = nt.get("predicate", ""), ot.get("predicate", "")
        raw_eq = (ns.lower().strip() == os_.lower().strip()) and (npd.lower().strip() == opd.lower().strip())
        l1_eq = (subj_L1(ns) == subj_L1(os_)) and (pred_L1(npd) == pred_L1(opd))
        full_eq = (n_subj(ns) == n_subj(os_)) and (pred_full(npd) == pred_full(opd))
        if raw_eq:
            lvl["L0_p2exact"] += 1
            if len(bylevel_examples["L0_p2exact"]) < 2: bylevel_examples["L0_p2exact"].append((q, ns, npd))
        elif l1_eq:
            lvl["L1"] += 1; bylevel_examples["L1"].append((q, (ns, npd), (os_, opd)))
        elif full_eq:
            lvl["L2"] += 1; bylevel_examples["L2"].append((q, (ns, npd), (os_, opd)))
        else:
            lvl["not_merged"] += 1
            notiso.append((q, "NOT_MERGED", (ns, npd, nt.get("object")), (os_, opd, ot.get("object")), em.get(q)))
    merged = lvl["L0_p2exact"] + lvl["L1"] + lvl["L2"]
    print(f"MERGED (old dropped, pool isolated): {merged}  = P2-exact {lvl['L0_p2exact']} + L1 {lvl['L1']} + L2 {lvl['L2']}")
    print(f"old_missing (trivially isolated)   : {lvl['old_missing']}")
    print(f"NOT-MERGED (old survives, not iso) : {lvl['not_merged']}   new_missing: {lvl['new_missing']}")
    print(f"  -> structural-isolated total = {merged + lvl['old_missing']}  (compare compute_resolution res)")
    for L in ["L1", "L2"]:
        if bylevel_examples[L]:
            print(f"  [{L} rescued these (S,P) merges]:")
            for q, new, old in bylevel_examples[L][:4]:
                print(f"    q{q}: NEW subj={new[0]!r} pred={new[1]!r}  |  OLD subj={old[0]!r} pred={old[1]!r}")
    print("  [NOT-MERGED / new_missing cases -> reader rescue or wrong]:")
    for q, kind, new, old, e in notiso:
        tag = "RESCUE(reader saved)" if e else "WRONG"
        if kind == "NEW_MISSING":
            print(f"    q{q}: {kind}  EM={e} [{tag}]  Qgt_new={gt[q]['gt_answer']!r} old={gt[q]['old_answer']!r}")
        else:
            print(f"    q{q}: {kind}  EM={e} [{tag}]")
            print(f"        NEW (S,P,O)={new}")
            print(f"        OLD (S,P,O)={old}")
