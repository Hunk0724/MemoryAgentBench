"""
Unified detection bucket recomputation for Mem0 / Zep × FC-SH/MH.

Replaces older detection_answer_correspondence.json + per-system metrics files
that used inconsistent text_match logic / bucket definitions.

Mem0 detection criterion (per chain_old fact):
  Check ~/.mem0/history.db for UPDATE or DELETE events since SINCE.
  - UPDATE counts if text_match(old_memory, gt.old_fact_text) AND
                     text_match(new_memory, gt.new_fact_text)
  - DELETE counts if text_match(old_memory, gt.old_fact_text)
  Either qualifies as "detected".

Zep detection criterion (per chain_old fact):
  Check union of all edges retrieved across 100 MH queries.
  - Any edge with text_match(edge.fact, gt.old_fact_text) AND
                  edge.invalid_at is not None
  qualifies as "detected".
  Note: this is a lower bound — edges never retrieved but invalidated in graph
  are missed. Acceptable proxy.

Per-question bucket:
  has_pair_hops = [h for h in q.hops if h.conflict_type == 'has_pair']
  - len == 0 → 'no_pair'
  - all detected → 'all_detected'
  - some detected → 'partial'
  - none detected → 'no_detection'

Outputs:
  analysis/results/aligned_detection_answer_correspondence.json
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
EXPDIR = BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results'
OUT_PATH = BASE / 'analysis/results/aligned_detection_answer_correspondence.json'

mh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))}
sh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/sh_512_mquake_analysis.json'))}

# Mem0 history.db (ingestion event log)
SINCE = "2026-05-02T07:00:00"

mem0_events = []
for old, new, event in sqlite3.connect('/home/yhchiang/.mem0/history.db').execute(
    "SELECT old_memory, new_memory, event FROM history WHERE created_at >= ?", (SINCE,)).fetchall():
    mem0_events.append({"old": old or "", "new": new or "", "event": event})

mem0_event_count = defaultdict(int)
for e in mem0_events:
    mem0_event_count[e['event']] += 1

# Zep edges (union of retrieved edges across 100 MH queries — lower bound proxy)
zep_retr = json.load(open(BASE / 'analysis/experiments/2026-05-03_writetime_querytime_eval/results/zep_full_retrieval_mh.json'))
zep_all_edges = {}
for r in zep_retr:
    for e in r.get('edges', []):
        uid = e.get('uuid')
        if uid and uid not in zep_all_edges:
            zep_all_edges[uid] = e
zep_edges_list = list(zep_all_edges.values())
zep_invalidated_count = sum(1 for e in zep_edges_list if e.get('invalid_at'))


def norm(s):
    if not s:
        return ""
    return str(s).strip().lower().rstrip(".,;:!?\"'")


def text_match(haystack, needle):
    h = norm(haystack); n = norm(needle)
    if not h or not n:
        return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def mem0_detected(old_text, new_text):
    """A chain_old → chain_new pair is detected if Mem0 fired UPDATE matching
    both directions, or DELETE matching the old fact."""
    for e in mem0_events:
        if e['event'] == 'UPDATE':
            if text_match(e['old'], old_text) and text_match(e['new'], new_text):
                return True
        elif e['event'] == 'DELETE':
            if text_match(e['old'], old_text):
                return True
    return False


def zep_detected(old_text, _new_text=None):
    """Chain_old fact is detected if any edge text-matches it AND has invalid_at."""
    for edge in zep_edges_list:
        if edge.get('invalid_at') and text_match(edge.get('fact', ''), old_text):
            return True
    return False


def has_pair_hops(q):
    """Returns list of {old_fact_text, gt_fact_text} for has_pair hops.
    Works on both MH (q has 'hops' list) and SH (q is itself a single hop)."""
    if 'hops' in q:
        return [{'old_fact_text': h['old_fact_text'], 'gt_fact_text': h.get('gt_fact_text', '')}
                for h in q['hops'] if h.get('conflict_type') == 'has_pair']
    if q.get('conflict_type') == 'has_pair':
        return [{'old_fact_text': q['old_fact_text'], 'gt_fact_text': q.get('gt_fact_text', '')}]
    return []


def bucket_of_question(q, detect_fn):
    pairs = has_pair_hops(q)
    if not pairs:
        return 'no_pair', 0, 0
    detected_count = sum(1 for h in pairs
                          if detect_fn(h['old_fact_text'], h['gt_fact_text']))
    if detected_count == len(pairs):
        return 'all_detected', detected_count, len(pairs)
    if detected_count == 0:
        return 'no_detection', detected_count, len(pairs)
    return 'partial', detected_count, len(pairs)


def system_summary(name, em_path, gt, detect_fn):
    em_data = {r['query_id']: r for r in json.load(open(em_path))}
    bucket_em = defaultdict(lambda: {'correct': 0, 'wrong': 0, 'qids': []})
    per_hop_correct = 0
    per_hop_total = 0

    for qid, q in gt.items():
        if qid not in em_data:
            continue
        bk, det_n, total_n = bucket_of_question(q, detect_fn)
        per_hop_correct += det_n
        per_hop_total += total_n
        em = em_data[qid].get('exact_match', False)
        if em:
            bucket_em[bk]['correct'] += 1
        else:
            bucket_em[bk]['wrong'] += 1
        bucket_em[bk]['qids'].append([qid, bool(em)])

    out = {'label': name}
    out['per_hop_detection'] = {
        'detected': per_hop_correct,
        'total_has_pair_hops': per_hop_total,
        'recall_pct': round(per_hop_correct / per_hop_total * 100, 1) if per_hop_total else 0,
    }
    out['buckets'] = {
        bk: {
            'correct': v['correct'],
            'total': v['correct'] + v['wrong'],
            'em_pct': round(v['correct'] / max(v['correct'] + v['wrong'], 1) * 100, 1),
            'qids': v['qids'],
        } for bk, v in bucket_em.items()
    }
    out['overall_em'] = round(sum(b['correct'] for b in bucket_em.values()) / 100 * 100, 1)
    return out


# Result paths
mem0_aligned_sh = EXPDIR / 'mem0_gemini_aligned_sh_results.json'
mem0_aligned_mh = EXPDIR / 'mem0_gemini_aligned_mh_results.json'
zep_aligned_sh = EXPDIR / 'zep_gemini_aligned_sh_results.json'
zep_aligned_mh = EXPDIR / 'zep_gemini_aligned_mh_results.json'

result = {
    'meta': {
        'detection_logic': {
            'Mem0': 'UPDATE event (both old/new text match GT) OR DELETE event (old match GT). Source: ~/.mem0/history.db since 2026-05-02T07:00:00.',
            'Zep': 'Any edge with invalid_at != None AND fact text match GT old_fact_text. Source: union of edges retrieved across 100 FC-MH queries (lower-bound proxy).',
        },
        'mem0_event_counts': dict(mem0_event_count),
        'zep_unique_retrieved_edges': len(zep_edges_list),
        'zep_invalidated_among_retrieved': zep_invalidated_count,
        'text_match': 'norm = lower + strip + rstrip puncts; article stripping (the/a/an); substring either direction.',
        'bucket_definition': '0 has_pair → no_pair; all detected → all_detected; partial → partial; none → no_detection.',
        'em_source': 'aligned with MABench default (FC seq-rule wrapper + Mem0 FACT_RETRIEVAL_PROMPT modified to remove anti-knowledge few-shots).',
        'inputs': {
            'mem0_sh_em': str(mem0_aligned_sh),
            'mem0_mh_em': str(mem0_aligned_mh),
            'zep_sh_em': str(zep_aligned_sh),
            'zep_mh_em': str(zep_aligned_mh),
        },
    },
    'mem0_sh': system_summary('Mem0 customized × Gemini × FC-SH (aligned)', mem0_aligned_sh, sh_gt, mem0_detected),
    'mem0_mh': system_summary('Mem0 customized × Gemini × FC-MH (aligned)', mem0_aligned_mh, mh_gt, mem0_detected),
    'zep_sh':  system_summary('Zep × Gemini × FC-SH (aligned)', zep_aligned_sh, sh_gt, zep_detected),
    'zep_mh':  system_summary('Zep × Gemini × FC-MH (aligned)', zep_aligned_mh, mh_gt, zep_detected),
}

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
json.dump(result, open(OUT_PATH, 'w'), ensure_ascii=False, indent=2)
print(f'Saved: {OUT_PATH}')

# Print summary
print('\n' + '=' * 78)
print(f'{"":<30} | {"per-hop":<14} | {"all_det":<10} | {"partial":<10} | {"no_det":<10} | {"no_pair":<10} | overall')
print('-' * 130)
for cell in ['mem0_sh', 'mem0_mh', 'zep_sh', 'zep_mh']:
    s = result[cell]
    ph = s['per_hop_detection']
    bks = s['buckets']
    def fmt_bk(b):
        if not b: return '-'
        return f'{b["correct"]}/{b["total"]}={b["em_pct"]:.0f}%'
    print(f'{s["label"][:30]:<30} | {ph["detected"]}/{ph["total_has_pair_hops"]} ({ph["recall_pct"]}%) | '
          f'{fmt_bk(bks.get("all_detected", {})):<10} | {fmt_bk(bks.get("partial", {})):<10} | '
          f'{fmt_bk(bks.get("no_detection", {})):<10} | {fmt_bk(bks.get("no_pair", {})):<10} | '
          f'{s["overall_em"]:.0f}%')

print(f'\nMem0 events since {SINCE}: {dict(mem0_event_count)}')
print(f'Zep retrieved unique edges: {len(zep_edges_list)}, with invalid_at: {zep_invalidated_count}')
