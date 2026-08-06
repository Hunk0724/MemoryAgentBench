#!/usr/bin/env python3
"""FC-SH 5.3 bottom-layer error mode: L0 extraction recall + Don't Ask L1 world-prior
candidate-drop across backbones. FC-SH 6k, has_pair (N=74), committed data only.

MATCHER (stated): a store fact matches gt_new/gt_old via compute_m1_m2_m3.match_pair
(v4: L0 full-fact-substring + triple-based fallback). For NL stores the fact string is
matched directly; for TRIPLE stores each triple is reconstructed as "<subject> <predicate>
<object>" and matched. gt_new/gt_old objects are distinctive (counterfactual vs real), so
false positives are low, but match_pair can OVER-MATCH on generic (S,P) stems shared across
entities -> L0 recall is an UPPER BOUND (flagged). gemma3-1b/4b pool axis is unreliable
(tiny / anomalous stores) -> treat their absolute numbers as coarse.

STORE per backbone (coordinator-specified):
  NL extraction_cache : gpt-4o-mini, llama3.1-8b, qwen2.5-7b, gemma2-9b, mistral-7b
  TRIPLE cache        : gemma3-1b (extraction_cache anomalous=132 -> use triples 375),
                        gemma3-4b (379), gemma3-12b (456), gemma3-27b (455)

TASK 2 banks (from bank_cache field):
  oursP1 files  = PER-BACKBONE P1  (bank_cache = p1_caches__<bb>/extraction_cache_p1_6k.json) [case b]
  vector100 files = held-fixed gpt-4o-mini P1 bank (bank_cache=None/default)                  [case a]
  -> case (a) held-fixed isolates the LLM: gt_new-in-bank ~constant, drops ~pure L1 world-prior.
"""
import json, glob, re, sys, unicodedata
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "analysis"))
from compute_m1_m2_m3 import match_pair                         # noqa: E402
from rescore_canonical import official_subem                    # noqa: E402

RUN_GT = json.load(open(REPO / "analysis/results/sh_6k_RUN_gt.json"))
HP = [r for r in RUN_GT if r.get("conflict_type") == "has_pair"]

# backbone -> (store_path, store_type)
STORES = {
    "gpt-4o-mini":  ("analysis/results/p1_caches/extraction_cache_p1_6k.json", "nl"),
    "gemma3-1b":    ("analysis/results/p1_caches__gemma3-1b/triple_cache_p1_6k.json", "triple"),
    "gemma3-4b":    ("analysis/results/p1_caches__gemma3-4b/triple_cache_p1_6k.json", "triple"),
    "gemma3-12b":   ("analysis/results/p1_caches__gemma3-12b/triple_cache_p1_6k.json", "triple"),
    "gemma3-27b":   ("analysis/results/p1_caches__gemma3-27b/triple_cache_p1_6k.json", "triple"),
    "llama3.1-8b":  ("analysis/results/p1_caches__llama3.1-8b/extraction_cache_p1_6k.json", "nl"),
    "qwen2.5-7b":   ("analysis/results/p1_caches__qwen2.5-7b/extraction_cache_p1_6k.json", "nl"),
    "gemma2-9b":    ("analysis/results/p1_caches__gemma2-9b/extraction_cache_p1_6k.json", "nl"),
    "mistral-7b":   ("analysis/results/p1_caches__mistral-7b/extraction_cache_p1_6k.json", "nl"),
}
ORDER = ["gpt-4o-mini","gemma3-1b","gemma3-4b","gemma3-12b","gemma3-27b",
         "llama3.1-8b","qwen2.5-7b","gemma2-9b","mistral-7b"]

def load_store_texts(path, typ):
    d = json.load(open(REPO / path))
    if typ == "nl":
        facts = []
        for v in d.values():
            facts.extend(v if isinstance(v, list) else [v])
        return [f for f in facts if isinstance(f, str)], len(facts)
    # triple: {hash: {subject,predicate,object}}
    texts = []
    for v in d.values():
        for t in (v if isinstance(v, list) else [v]):
            texts.append(f"{t.get('subject','')} {t.get('predicate','')} {t.get('object','')}".strip())
    return texts, len(texts)

def in_store(texts, gt_ff, old_ff, target):
    return any(match_pair(t, gt_ff, old_ff, target) for t in texts)

# ---------------- TASK 1 ----------------
print("="*92)
print("TASK 1 — L0 extraction recall (FC-SH 6k, has_pair N=74): is gt_new in the per-backbone store")
print("="*92)
print(f"{'backbone':<14}{'store':<9}{'#facts':>7}{'gt_new-in':>12}{'gt_old-in':>12}{'both-in':>10}")
t1 = {}
for bb in ORDER:
    path, typ = STORES[bb]
    texts, nfacts = load_store_texts(path, typ)
    nnew=nold=nboth=0
    for r in HP:
        gt_ff, old_ff = r["gt_fact_text"], r["old_fact_text"]
        hasn = in_store(texts, gt_ff, old_ff, "new")
        haso = in_store(texts, gt_ff, old_ff, "old")
        nnew += hasn; nold += haso; nboth += (hasn and haso)
    N=len(HP); t1[bb]=texts
    print(f"{bb:<14}{typ:<9}{nfacts:>7}{f'{nnew}/{N} ({100*nnew/N:.0f}%)':>12}"
          f"{f'{nold}/{N} ({100*nold/N:.0f}%)':>12}{f'{nboth}/{N} ({100*nboth/N:.0f}%)':>10}")

# ---------------- TASK 2 ----------------
def dflag(r): return r.get("gt_seq") is not None and r.get("old_seq") is not None and r["gt_seq"] < r["old_seq"]

def analyze_dontask(fname, store_texts):
    path = REPO / f"outputs/maxserial_theircode/{fname}"
    if not path.exists(): return None
    d = json.load(open(path))
    rows = {r["query_id"]: r for r in d["rows"]}
    nf=nc1=nc1old=L0=L1=0; nc1old_df=0; nf_df=0
    for r in HP:
        row = rows.get(r["query_id"])
        if row is None: continue
        ans = row.get("answer")
        if official_subem(ans, [r["gt_answer"]]): continue   # correct
        nf += 1
        ncand1 = (row.get("n_candidates") == 1)
        fell_old = official_subem(ans, [r["old_answer"]])
        if ncand1: nc1 += 1
        if ncand1 and fell_old: nc1old += 1
        if not dflag(r):
            nf_df += 1
            if ncand1 and fell_old: nc1old_df += 1
        # L0 vs L1: gt_new in store?
        if in_store(store_texts, r["gt_fact_text"], r["old_fact_text"], "new"): L1 += 1
        else: L0 += 1
    return dict(nf=nf, nc1=nc1, nc1old=nc1old, L0=L0, L1=L1, nc1old_df=nc1old_df, nf_df=nf_df, bank_cache=d.get("bank_cache"))

def gpt4omini_store():
    texts,_ = load_store_texts(*STORES["gpt-4o-mini"]); return texts

print("\n"+"="*92)
print("TASK 2a — Don't Ask oursP1 (PER-BACKBONE P1 bank, case b): has_pair failures, L0/L1 split")
print("="*92)
print(f"{'backbone':<14}{'fail':>5}{'n_cand==1':>12}{'answered-old(nc1)':>18}{'L0(no extract)':>16}{'L1(refusal)':>13}")
for bb in ORDER:
    if bb == "gpt-4o-mini":
        # committed vector100 uses gpt-4o-mini bank; its own store
        res = analyze_dontask("6k_gpt-4o-mini_vector100.json", t1[bb])
    else:
        res = analyze_dontask(f"6k_{bb}_oursP1_vector100.json", t1[bb])
    if not res: print(f"{bb:<14} (no file)"); continue
    nf=res["nf"]
    c_nc1 = f'{res["nc1"]}/{nf} ({100*res["nc1"]/nf:.0f}%)'
    c_old = f'{res["nc1old"]}/{nf} ({100*res["nc1old"]/nf:.0f}%)'
    c_l0 = f'{res["L0"]} ({100*res["L0"]/nf:.0f}%)'
    c_l1 = f'{res["L1"]} ({100*res["L1"]/nf:.0f}%)'
    print(f"{bb:<14}{nf:>5}{c_nc1:>12}{c_old:>18}{c_l0:>16}{c_l1:>13}")

print("\n"+"="*92)
print("TASK 2b — Don't Ask vector100 (HELD-FIXED gpt-4o-mini bank, case a): clean L1 world-prior test")
print("  (bank held fixed -> gt_new-in-bank ~constant near-full -> drops ~= pure L1 refusal)")
print("="*92)
print(f"{'backbone':<14}{'fail':>5}{'n_cand==1':>12}{'answered-old(nc1) raw':>22}{'D-flag-adj':>12}{'L0':>7}{'L1':>7}")
gstore = gpt4omini_store()
for bb in ORDER:
    fn = "6k_gpt-4o-mini_vector100.json" if bb=="gpt-4o-mini" else f"6k_{bb}_vector100.json"
    res = analyze_dontask(fn, gstore)   # held-fixed bank = gpt-4o-mini store for ALL
    if not res: print(f"{bb:<14} (no held-fixed vector100 file)"); continue
    nf=res["nf"]
    c_nc1 = f'{res["nc1"]}/{nf} ({100*res["nc1"]/nf:.0f}%)'
    raw = f'{res["nc1old"]}/{nf} ({100*res["nc1old"]/nf:.0f}%)'
    dfa = f'{res["nc1old_df"]}/{res["nf_df"]} ({100*res["nc1old_df"]/res["nf_df"]:.0f}%)' if res["nf_df"] else "—"
    print(f"{bb:<14}{nf:>5}{c_nc1:>12}{raw:>22}{dfa:>12}{res['L0']:>7}{res['L1']:>7}  bank={res['bank_cache']}")

if __name__ == "__main__":
    pass
