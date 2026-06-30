"""Compare gpt-4o-mini vs gemini-3.1-flash-lite on the same 30 expanded
HippoRAG-only smoke test. Reuses parse_a_trace / fact_in_candidates /
detect_bailout from analyze_smoke_traces.py.
"""
import json, sys, re, unicodedata
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/home/yhchiang/MemoryAgentBench/analysis')
from analyze_smoke_traces import parse_a_trace, fact_in_candidates, detect_bailout, norm

BASE = Path('/home/yhchiang/MemoryAgentBench')

mh_ana = {e['query_id']: e for e in
          json.load(open(BASE / 'analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json'))}

gpt_traces = json.load(open(BASE / 'analysis/results/zep/smoke_test_expanded_traces.json'))
gem_traces = json.load(open(BASE / 'analysis/results/zep/smoke_test_gemini_traces.json'))


def evaluate(traces, label):
    """Compute metrics for HippoRAG-only on a trace set."""
    h_hops_all = []  # (qid, hop_idx, listed_gt, listed_old)
    bailed = 0
    em_C = 0
    em_A = 0
    for r in traces:
        qid = r['qid']
        ana = mh_ana[qid]
        hp_hops = [h for h in ana['hops'] if h['conflict_type'] == 'has_pair']
        h_A_hops = parse_a_trace(r['hippo']['A_trace_first']['response'])
        h_C_resp = r['hippo']['C_original']['response']
        h_bailed, _ = detect_bailout(h_C_resp)
        if h_bailed:
            bailed += 1
        # EM
        if r['hippo']['C_original']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,'):
            em_C += 1
        if r['hippo']['A_trace_first']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,'):
            em_A += 1
        # per-hop coverage
        for hop in hp_hops:
            hop_idx = hop['hop_idx']
            block = next((b for b in h_A_hops if b['hop_idx'] == hop_idx + 1), None)
            if not block:
                h_hops_all.append({'qid': qid, 'hop': hop_idx,
                                    'listed_gt': False, 'listed_old': False,
                                    'block_missing': True})
                continue
            cands = block['candidates']
            h_hops_all.append({
                'qid': qid, 'hop': hop_idx,
                'listed_gt': fact_in_candidates(hop['gt_fact_text'], cands),
                'listed_old': fact_in_candidates(hop['old_fact_text'], cands),
                'conflict': block['conflict'],
                'signal': block['signal'].lower(),
                'block_missing': False,
            })

    n_hops = len(h_hops_all)
    n_block_missing = sum(1 for h in h_hops_all if h['block_missing'])
    listed_gt = sum(1 for h in h_hops_all if h['listed_gt'])
    listed_old = sum(1 for h in h_hops_all if h['listed_old'])
    listed_both = sum(1 for h in h_hops_all if h['listed_gt'] and h['listed_old'])
    listed_neither = sum(1 for h in h_hops_all if not h['listed_gt'] and not h['listed_old'] and not h['block_missing'])
    conflict_yes = sum(1 for h in h_hops_all if h.get('conflict'))

    sigs = Counter()
    for h in h_hops_all:
        s = h.get('signal', '')
        for kw in ['serial', 'date', 'none', 'fallback', 'world', 'first']:
            if kw in s:
                sigs[kw] += 1
                break
        else:
            if not h['block_missing']:
                sigs['other'] += 1

    return {
        'label': label,
        'n_queries': len(traces),
        'n_hops': n_hops,
        'em_C': em_C,
        'em_A': em_A,
        'bailed': bailed,
        'block_missing': n_block_missing,
        'listed_gt': listed_gt,
        'listed_old': listed_old,
        'listed_both': listed_both,
        'listed_neither': listed_neither,
        'conflict_yes': conflict_yes,
        'signal_distribution': dict(sigs),
    }


gpt = evaluate(gpt_traces, 'gpt-4o-mini')
gem = evaluate(gem_traces, 'gemini-3.1-flash-lite')

# Print comparison
def pct(num, den):
    return f"{num}/{den} = {num/den*100:.1f}%" if den else "—"

print("=" * 78)
print(f"HippoRAG-v2 backbone comparison on 30 expanded targets")
print("=" * 78)
print(f"\n{'Metric':<48} {'gpt-4o-mini':>15} {'gemini-FL':>15}")
print("-" * 78)
print(f"{'EM (C original)':<48} {pct(gpt['em_C'], gpt['n_queries']):>15} {pct(gem['em_C'], gem['n_queries']):>15}")
print(f"{'EM (A trace-first)':<48} {pct(gpt['em_A'], gpt['n_queries']):>15} {pct(gem['em_A'], gem['n_queries']):>15}")
print()
print(f"{'has_pair hops total':<48} {gpt['n_hops']:>15} {gem['n_hops']:>15}")
print(f"{'(A) trace failed to parse hop block':<48} {pct(gpt['block_missing'], gpt['n_hops']):>15} {pct(gem['block_missing'], gem['n_hops']):>15}")
print(f"{'GT listed in candidates':<48} {pct(gpt['listed_gt'], gpt['n_hops']):>15} {pct(gem['listed_gt'], gem['n_hops']):>15}")
print(f"{'Old listed in candidates':<48} {pct(gpt['listed_old'], gpt['n_hops']):>15} {pct(gem['listed_old'], gem['n_hops']):>15}")
print(f"{'Both listed':<48} {pct(gpt['listed_both'], gpt['n_hops']):>15} {pct(gem['listed_both'], gem['n_hops']):>15}")
print(f"{'Neither listed':<48} {pct(gpt['listed_neither'], gpt['n_hops']):>15} {pct(gem['listed_neither'], gem['n_hops']):>15}")
print(f"{'Conflict self-reported (yes)':<48} {pct(gpt['conflict_yes'], gpt['n_hops']):>15} {pct(gem['conflict_yes'], gem['n_hops']):>15}")
print(f"{'(C) Bail-out language':<48} {pct(gpt['bailed'], gpt['n_queries']):>15} {pct(gem['bailed'], gem['n_queries']):>15}")
print()
print("Signal-cited distribution:")
all_keys = sorted(set(list(gpt['signal_distribution'].keys()) + list(gem['signal_distribution'].keys())))
for k in all_keys:
    g = gpt['signal_distribution'].get(k, 0)
    m = gem['signal_distribution'].get(k, 0)
    print(f"  {k:<46} {g:>15} {m:>15}")

# Also show per-conflict-bucket EM
print()
print("=" * 78)
print("EM by n_conflict-hops")
print("=" * 78)
print(f"{'n_conflict':<10} {'n':>4} {'gpt-C':>8} {'gpt-A':>8} {'gem-C':>8} {'gem-A':>8}")
print("-" * 50)
gpt_by_nc = {}
gem_by_nc = {}
for r in gpt_traces:
    nc = r['n_conflict']
    em_C = r['hippo']['C_original']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,')
    em_A = r['hippo']['A_trace_first']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,')
    gpt_by_nc.setdefault(nc, []).append((em_C, em_A))
for r in gem_traces:
    nc = r['n_conflict']
    em_C = r['hippo']['C_original']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,')
    em_A = r['hippo']['A_trace_first']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,')
    gem_by_nc.setdefault(nc, []).append((em_C, em_A))
for nc in sorted(gpt_by_nc.keys()):
    g_list = gpt_by_nc[nc]
    m_list = gem_by_nc[nc]
    n = len(g_list)
    g_C = sum(1 for x, _ in g_list if x)
    g_A = sum(1 for _, x in g_list if x)
    m_C = sum(1 for x, _ in m_list if x)
    m_A = sum(1 for _, x in m_list if x)
    print(f"{nc:<10} {n:>4} {g_C:>4}/{n:<3} {g_A:>4}/{n:<3} {m_C:>4}/{n:<3} {m_A:>4}/{n:<3}")
