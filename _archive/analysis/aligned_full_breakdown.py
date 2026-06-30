"""
Aligned (wrapped query) Mem0/Zep MH 更詳細 breakdown:
- by num_hops × pulled-by-old
- by detection bucket × pulled-by-old
- SH detection bucket × EM
- all_detected EM (兩 split)
"""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
EXPDIR = BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results'

mh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))}
sh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/sh_512_mquake_analysis.json'))}


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


# Mem0 detection
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


# Zep detection
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


def chain_olds(q):
    return [h.get('old_answer', '') for h in q['hops'] if h.get('conflict_type') == 'has_pair']


def pulled_by_old(pred, q):
    pred = pred or ''
    return any(ans and text_match(pred, ans) for ans in chain_olds(q))


def detect_breakdown(name, em_path, gt, bucket_fn, label):
    if not em_path.exists():
        print(f'\n[{name}] file missing'); return
    d = {r['query_id']: r for r in json.load(open(em_path))}

    # 1) by num_hops × pulled-by-old (MH only, gt has hops)
    if label == 'MH':
        print(f'\n[{name} MH] by num_hops')
        print('  hop | wrong (n) | pulled (n) | rate')
        by_hop = defaultdict(lambda: {'wrong': 0, 'pulled': 0})
        for qid, q in gt.items():
            if qid not in d: continue
            r = d[qid]
            if r.get('exact_match'): continue
            n_hops = q.get('num_hops', 2)
            by_hop[n_hops]['wrong'] += 1
            if pulled_by_old(r.get('pred_answer'), q):
                by_hop[n_hops]['pulled'] += 1
        for hop in sorted(by_hop):
            b = by_hop[hop]
            rate = b['pulled']/b['wrong']*100 if b['wrong'] else 0
            print(f'  {hop}-hop | {b["wrong"]} | {b["pulled"]} | {rate:.0f}%')

    # 2) by detection bucket × pulled-by-old (MH only)
    if label == 'MH':
        print(f'\n[{name} MH] by detection bucket × pulled-by-old')
        print('  bucket          | wrong (n) | pulled (n) | rate')
        by_bk = defaultdict(lambda: {'wrong': 0, 'pulled': 0})
        for qid, q in gt.items():
            if qid not in d: continue
            r = d[qid]
            if r.get('exact_match'): continue
            bk = bucket_fn(q)
            by_bk[bk]['wrong'] += 1
            if pulled_by_old(r.get('pred_answer'), q):
                by_bk[bk]['pulled'] += 1
        for bk in ['all_detected', 'partial', 'no_detection', 'no_pair']:
            b = by_bk.get(bk, {'wrong': 0, 'pulled': 0})
            if b['wrong'] == 0: continue
            rate = b['pulled']/b['wrong']*100
            print(f'  {bk:<14} | {b["wrong"]} | {b["pulled"]} | {rate:.0f}%')

    # 3) detection bucket × EM (both splits)
    print(f'\n[{name} {label}] detection bucket × EM')
    print('  bucket          | n  | correct | EM rate')
    by_bk_em = defaultdict(lambda: {'correct': 0, 'wrong': 0})
    for qid, q in gt.items():
        if qid not in d: continue
        r = d[qid]
        bk = bucket_fn(q) if label == 'MH' else mem0_or_zep_sh_bucket(q, name, bucket_fn)
        if r.get('exact_match'):
            by_bk_em[bk]['correct'] += 1
        else:
            by_bk_em[bk]['wrong'] += 1
    for bk in ['all_detected', 'partial', 'no_detection', 'no_pair']:
        b = by_bk_em.get(bk, {'correct': 0, 'wrong': 0})
        n = b['correct'] + b['wrong']
        if n == 0: continue
        rate = b['correct']/n*100
        print(f'  {bk:<14} | {n:<3}| {b["correct"]:<7} | {rate:.0f}%')


def mem0_or_zep_sh_bucket(q, name, bucket_fn_mh):
    """SH single-hop: bucket = whether the single has_pair detected."""
    if 'old_fact_text' not in q or 'gt_fact_text' not in q:
        # fall through to MH-style hop check
        return bucket_fn_mh(q)
    pair = {'old': q['old_fact_text'], 'new': q['gt_fact_text']}
    detect = mem0_detect if 'Mem0' in name else zep_detect
    return 'all_detected' if detect(pair) else 'no_detection'


print('=' * 70)
print('Mem0 aligned MH')
print('=' * 70)
detect_breakdown('Mem0 aligned', EXPDIR / 'mem0_gemini_aligned_mh_results.json',
                 mh_gt, mem0_bucket, 'MH')

print('\n' + '=' * 70)
print('Mem0 aligned SH')
print('=' * 70)
detect_breakdown('Mem0 aligned', EXPDIR / 'mem0_gemini_aligned_sh_results.json',
                 sh_gt, mem0_bucket, 'SH')

print('\n' + '=' * 70)
print('Zep aligned MH')
print('=' * 70)
detect_breakdown('Zep aligned', EXPDIR / 'zep_gemini_aligned_mh_results.json',
                 mh_gt, zep_bucket, 'MH')

print('\n' + '=' * 70)
print('Zep aligned SH')
print('=' * 70)
detect_breakdown('Zep aligned', EXPDIR / 'zep_gemini_aligned_sh_results.json',
                 sh_gt, zep_bucket, 'SH')
