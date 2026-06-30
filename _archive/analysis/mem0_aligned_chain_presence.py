"""
回答: Mem0 retrieval 中是否含 chain_old?
從 retrieved_memories_preview (top-5) 估計 chain_new / chain_old 出現比例。
"""
import json
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
mh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))}
d = json.load(open(BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/mem0_gemini_aligned_mh_results.json'))


def norm(s):
    if not s:
        return ''
    return str(s).strip().lower().rstrip('.,;:!?"\'')


def text_match(h, n):
    h = norm(h); n = norm(n)
    if not h or not n: return False
    for art in ('the ', 'a ', 'an '):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


stats = {'new_only': 0, 'old_only': 0, 'both': 0, 'neither': 0, 'total': 0}

for r in d:
    qid = r['query_id']
    q = mh_gt.get(qid)
    if not q:
        continue
    preview = r.get('retrieved_memories_preview', [])
    has_pair_hops = [h for h in q['hops'] if h.get('conflict_type') == 'has_pair']
    if not has_pair_hops:
        continue
    for h in has_pair_hops:
        new_t = h.get('gt_fact_text', '')
        old_t = h.get('old_fact_text', '')
        in_new = any(text_match(p, new_t) for p in preview)
        in_old = any(text_match(p, old_t) for p in preview)
        stats['total'] += 1
        if in_new and in_old:
            stats['both'] += 1
        elif in_new:
            stats['new_only'] += 1
        elif in_old:
            stats['old_only'] += 1
        else:
            stats['neither'] += 1

t = stats['total']
print(f'has_pair hops total: {t}')
print(f'  chain_new only in top-5: {stats["new_only"]} ({stats["new_only"] / t * 100:.0f}%)')
print(f'  chain_old only in top-5: {stats["old_only"]} ({stats["old_only"] / t * 100:.0f}%)')
print(f'  both in top-5:          {stats["both"]} ({stats["both"] / t * 100:.0f}%)')
print(f'  neither in top-5:       {stats["neither"]} ({stats["neither"] / t * 100:.0f}%)')
