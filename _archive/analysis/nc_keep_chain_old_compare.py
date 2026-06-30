"""
Compare NC + keep-chain-old vs all baselines on FC-MH.

Reads:
  results/diagnostic/nc_keep_chain_old_origprompt_mh_results.json
  + multiple existing baseline JSONs

Prints comparison table with rule-clean 96 + stratification.
"""

import json
from pathlib import Path
from collections import defaultdict

BASE = Path('/home/yhchiang/MemoryAgentBench')
DIAG = BASE / 'analysis/results/diagnostic'

mh_gt = json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))
violated = set()
for q in mh_gt:
    for h in q.get('hops', []):
        if h.get('conflict_type') == 'has_pair' and h['gt_seq'] < h['old_seq']:
            violated.add(q['query_id']); break

def acc(rows, qid_filter=None):
    if qid_filter is not None:
        rows = [r for r in rows if r.get('query_id') in qid_filter]
    if not rows: return None
    ok = sum(1 for r in rows if r['exact_match'])
    return f'{ok}/{len(rows)} = {ok/len(rows)*100:.0f}%'

clean_qids = {q['query_id'] for q in mh_gt if q['query_id'] not in violated}

# Load all baselines
files = {
    'NC orig (all olds removed globally)': DIAG / 'non_counterfactual_baseline_origprompt_mh_results.json',
    'NC + keep chain_old (NEW)': DIAG / 'nc_keep_chain_old_origprompt_mh_results.json',
    'OA2 fact-level orig (this Q chain_old removed)': DIAG / 'oracle_a_fact_level_origprompt_mh_results.json',
    'Sim-OB chain-only orig (chain_new only)': DIAG / 'sim_ob_chain_only_origprompt_results.json',
    'Mode A: chain_new + chain_old, 0 noise': DIAG / 'sim_ob_grad_v2_chain_only_olds_results.json',
    'Mode C n=1: chain_new + sat noise + 1 chain_old': DIAG / 'sim_ob_grad_v2_grad_injection_results.json',
}

print('='*92)
print(f'{"Setup":<55} | {"All 100":<14} | {"Rule-clean 96":<14}')
print('='*92)

for name, path in files.items():
    if not path.exists():
        print(f'{name:<55} | {"NOT RUN":<14} | {"":<14}')
        continue
    d = json.load(open(path))
    if 'grad_injection' in str(path):
        d = [r for r in d if r.get('n_old_injected') == 1]
    a_all = acc(d)
    a_clean = acc(d, qid_filter=clean_qids)
    print(f'{name:<55} | {(a_all or "—"):<14} | {(a_clean or "—"):<14}')

# Vanilla HippoRAG-v2 from outputs
mh_results = json.load(open(BASE / 'outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
vanilla_data = [{'query_id': r['query_id'], 'exact_match': r['exact_match']} for r in mh_results['data']]
print(f'{"HippoRAG-v2 vanilla orig":<55} | {acc(vanilla_data):<14} | {acc(vanilla_data, qid_filter=clean_qids):<14}')

# Stratify NC + keep chain_old by num_hops
nc_keep_path = DIAG / 'nc_keep_chain_old_origprompt_mh_results.json'
if nc_keep_path.exists():
    print()
    print('=== NC + keep chain_old stratification (rule-clean 96) ===')
    d = [r for r in json.load(open(nc_keep_path)) if r['query_id'] in clean_qids]
    g = defaultdict(list)
    for r in d: g[r['num_hops']].append(r)
    for k in sorted(g):
        rs = g[k]; ok = sum(1 for r in rs if r['exact_match'])
        print(f'  {k}-hop: {ok}/{len(rs)} = {ok/len(rs)*100:.0f}%')

    print()
    print('=== NC + keep chain_old by n_conflict (rule-clean) ===')
    g = defaultdict(list)
    for r in d: g[r['n_conflict']].append(r)
    for k in sorted(g):
        rs = g[k]; ok = sum(1 for r in rs if r['exact_match'])
        print(f'  n_conflict={k}: {ok}/{len(rs)} = {ok/len(rs)*100:.0f}%')

    # Also: how many chain_olds actually appeared in retrieval?
    print()
    print('=== chain_olds_kept_in_top10 distribution ===')
    g = defaultdict(list)
    for r in d:
        n_pair = r['n_conflict']
        n_kept = r['chain_olds_kept_in_top10']
        g[(n_pair, n_kept)].append(r)
    for k in sorted(g):
        rs = g[k]; ok = sum(1 for r in rs if r['exact_match'])
        print(f'  n_conflict={k[0]}, chain_olds_kept={k[1]}: {ok}/{len(rs)} = {ok/len(rs)*100:.0f}%')
