"""Pick 30 diverse FC-MH targets for expanded smoke test, including the
existing 6 targets for continuity.

Stratify by n_conflict and Zep/HippoRAG EM outcome.
"""
import json
from pathlib import Path
import random
random.seed(42)

BASE = Path('/home/yhchiang/MemoryAgentBench')

zep = {r['query_id']: r for r in
       json.load(open(BASE / 'analysis/results/zep/mh_zep_mechanism.json'))}
ana = {e['query_id']: e for e in
       json.load(open(BASE / 'analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json'))}
hippo = json.load(open(BASE / 'outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
hippo_em = {e['query_id']: bool(e.get('exact_match', False)) for e in hippo['data']}

candidates = []
for qid, z in zep.items():
    a = ana[qid]
    hp = [h for h in a['hops'] if h['conflict_type'] == 'has_pair']
    z_hp = [h for h in z['hops'] if h['conflict_type'] == 'has_pair']
    if not hp:
        continue
    n_conflict = len(hp)
    all_zep_in_union = all(h['gt_in_any'] for h in z_hp)
    all_hippo_retrieved = all(h.get('gt_retrieved', False) for h in hp)
    if not (all_zep_in_union and all_hippo_retrieved):
        continue  # require fair-condition
    candidates.append({
        'qid': qid,
        'n_hops': a['num_hops'],
        'n_conflict': n_conflict,
        'zep_em': z['zep_em'],
        'hippo_em': hippo_em[qid],
        'question': a['question'][:80],
        'gt': a['gt_answer'],
    })

print(f"Fair-condition candidates: {len(candidates)}")

# Existing 6 — keep as-is for continuity
existing = json.load(open(BASE / 'analysis/results/zep/smoke_test_targets.json'))
existing_qids = {t['qid'] for t in existing}

# Stratified sample 24 more from the rest, ~proportional to n_conflict population
rest = [c for c in candidates if c['qid'] not in existing_qids]
groups = {}
for c in rest:
    groups.setdefault(c['n_conflict'], []).append(c)

# Quotas: matched to dataset distribution but capped
quotas = {1: 6, 2: 12, 3: 5, 4: 1}  # adds to 24
new_targets = []
for nc, q in quotas.items():
    pool = groups.get(nc, [])
    if not pool:
        continue
    random.shuffle(pool)
    new_targets.extend(pool[:q])

# Combine
expanded = list(existing) + new_targets
print(f"Expanded targets: {len(expanded)} (6 existing + {len(new_targets)} new)")

# Distribution
from collections import Counter
print("\nDistribution by n_conflict:")
for nc, cnt in sorted(Counter(t['n_conflict'] for t in expanded).items()):
    print(f"  {nc}-conflict: {cnt}")
print("\nDistribution by (zep_em, hippo_em):")
for k, cnt in sorted(Counter((t['zep_em'], t['hippo_em']) for t in expanded).items()):
    print(f"  zep={('✓' if k[0] else '✗')} hippo={('✓' if k[1] else '✗')}: {cnt}")

json.dump(expanded, open(BASE / 'analysis/results/zep/smoke_test_targets_expanded.json', 'w'),
          ensure_ascii=False, indent=2)
print(f"\nSaved → {BASE / 'analysis/results/zep/smoke_test_targets_expanded.json'}")
