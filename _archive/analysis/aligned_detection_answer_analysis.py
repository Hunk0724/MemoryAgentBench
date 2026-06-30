"""
After re-running Mem0/Zep with WRAPPED query (aligned with MABench default):
recompute detection × answer cross-tab + pulled-by-old failure mode stats.

Reads:
  Existing detection bucket assignments (from prior cascade analysis)
  New aligned EM results
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
EXPDIR = BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results'

mh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))}

def norm(s):
    if not s: return ""
    return str(s).strip().lower().rstrip(".,;:!?\"'")

def text_match(h, n):
    h = norm(h); n = norm(n)
    if not h or not n: return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n

# -------- Mem0 detection bucket --------
SINCE = "2026-05-02T07:00:00"
events = [{"old": r[0], "new": r[1], "event": r[2]} for r in
          sqlite3.connect('/home/yhchiang/.mem0/history.db').execute(
              "SELECT old_memory, new_memory, event FROM history WHERE created_at >= ?", (SINCE,)).fetchall()]

def mem0_detect(p):
    return any(e['event'] == 'UPDATE'
               and text_match(e['old'], p['old'])
               and text_match(e['new'], p['new'])
               for e in events)

def mem0_bucket(q):
    chain = [h for h in q['hops'] if h.get('conflict_type') == 'has_pair']
    if not chain: return 'no_pair'
    correct = sum(1 for h in chain if mem0_detect({'old': h['old_fact_text'], 'new': h['gt_fact_text']}))
    if correct == len(chain): return 'all_detected'
    if correct == 0: return 'no_detection'
    return 'partial'

# -------- Zep detection bucket --------
zep_retr = json.load(open(BASE / 'analysis/experiments/2026-05-03_writetime_querytime_eval/results/zep_full_retrieval_mh.json'))
zep_all_edges = {}
for r in zep_retr:
    for e in r.get('edges', []):
        uid = e.get('uuid')
        if uid and uid not in zep_all_edges: zep_all_edges[uid] = e
zep_edges_list = list(zep_all_edges.values())

def zep_detect(p):
    return any(text_match(e.get('fact', ''), p['old']) and e.get('invalid_at') for e in zep_edges_list)

def zep_bucket(q):
    chain = [h for h in q['hops'] if h.get('conflict_type') == 'has_pair']
    if not chain: return 'no_pair'
    correct = sum(1 for h in chain if zep_detect({'old': h['old_fact_text'], 'new': h['gt_fact_text']}))
    if correct == len(chain): return 'all_detected'
    if correct == 0: return 'no_detection'
    return 'partial'


def analyze_system(name, em_path, bucket_fn):
    if not em_path.exists():
        print(f'\n=== {name} === SKIPPED (file not found: {em_path.name})')
        return
    d = {r['query_id']: r for r in json.load(open(em_path))}
    bucket_groups = defaultdict(lambda: {'correct': 0, 'wrong': 0, 'qids': []})
    pulled_count = 0; wrong_total = 0

    for qid, q in mh_gt.items():
        if qid not in d: continue
        r = d[qid]
        em = r.get('exact_match', False)
        bk = bucket_fn(q)
        bucket_groups[bk]['correct' if em else 'wrong'] += 1
        bucket_groups[bk]['qids'].append((qid, em))

        if not em:
            wrong_total += 1
            pred = r.get('pred_answer', '') or ''
            chain_old_ans = [h.get('old_answer', '') for h in q['hops']
                             if h.get('conflict_type') == 'has_pair']
            if any(ans and text_match(pred, ans) for ans in chain_old_ans):
                pulled_count += 1

    total = sum(b['correct'] + b['wrong'] for b in bucket_groups.values())
    overall_em = sum(b['correct'] for b in bucket_groups.values())
    print(f'\n=== {name} (n={total}) ===')
    print(f'Overall EM: {overall_em}/{total} = {overall_em/total*100:.0f}%')
    print(f'Wrong: {wrong_total}, Pulled-by-old: {pulled_count} = {pulled_count/wrong_total*100:.0f}%' if wrong_total else 'No wrong')
    print(f'\n  bucket          | n  | correct | EM rate')
    print(f'  ---------------+----+---------+--------')
    for bk in ['all_detected', 'partial', 'no_detection', 'no_pair']:
        b = bucket_groups.get(bk, {'correct': 0, 'wrong': 0})
        n = b['correct'] + b['wrong']
        if n == 0: continue
        em_rate = b['correct'] / n * 100
        print(f'  {bk:<14} | {n:<3}| {b["correct"]:<7} | {em_rate:.0f}%')


print('=' * 70)
print('ALIGNED (wrapped query) — supports MABench-default comparison')
print('=' * 70)
analyze_system('Mem0 aligned MH', EXPDIR / 'mem0_gemini_aligned_mh_results.json', mem0_bucket)
analyze_system('Zep aligned MH', EXPDIR / 'zep_gemini_aligned_mh_results.json', zep_bucket)

print('\n' + '=' * 70)
print('ORIGINAL (bare question) — for reference')
print('=' * 70)
analyze_system('Mem0 bare MH', EXPDIR / 'mem0_gemini_mh_results.json', mem0_bucket)
analyze_system('Zep bare MH', EXPDIR / 'zep_gemini_mh_results.json', zep_bucket)
