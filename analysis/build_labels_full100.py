"""Build hop-level prop_id labels for ALL 100 FC-MH 6k queries.

Extension of build_mini_eval_w14.py:
  - Same strict s+o extractor + extended _PREDICATE_PATTERNS
  - Input: ALL 100 queries (vs 16 in W1.4)
  - Output: analysis/results/full100_eval/labels.json
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# Reuse extractor from W1.4 mini-eval (DRY: import functions directly)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_mini_eval_w14 import (
    extract_so, fact_match, _norm, _PREDICATE_PATTERNS,
)

BASE = Path('/home/yhchiang/MemoryAgentBench')
GT = BASE / 'analysis/results/mh_512_mquake_analysis.json'
PROP_INDEX = BASE / ('outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/'
                     'chunksize_512/context_id_0/'
                     'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/'
                     'proposition_index.json')
OUT = BASE / 'analysis/results/full100_eval/labels.json'


def main():
    gt = json.load(open(GT))
    prop_index = json.load(open(PROP_INDEX))
    props = prop_index['propositions']
    print(f"[build] N queries: {len(gt)}, N propositions: {len(props)}")

    # Cache extractions
    prop_so = {p['id']: (extract_so(p['text']), p) for p in props}

    def find_prop_id(fact_text: str):
        return [
            {
                'prop_id': p['id'],
                'prop_text': p['text'],
                'timestamp': p['timestamp'],
                'source_chunk_id': p['source_chunk_id'],
            }
            for pid, ((s, o), p) in prop_so.items()
            if fact_match(fact_text, p['text'])
        ]

    labels = []
    match_stats = Counter()
    for q in gt:
        entry = {
            'qa_pair_id': q['qa_pair_id'],
            'query_id': q['query_id'],
            'question': q['question'],
            'gt_answer': q['gt_answer'],
            'num_hops': q['num_hops'],
            'w1_3_exact_match': q.get('exact_match'),
            'hops': [],
        }
        for hop in q['hops']:
            hop_entry = {
                'hop_idx': hop['hop_idx'],
                'hop_question': hop['hop_question'],
                'conflict_type': hop['conflict_type'],
                'gt_fact_text': hop['gt_fact_text'],
                'old_fact_text': hop.get('old_fact_text'),
                'gt_seq': hop.get('gt_seq'),
                'old_seq': hop.get('old_seq'),
                'gt_answer': hop.get('gt_answer'),
                'old_answer': hop.get('old_answer'),
                'chain_new_matches': find_prop_id(hop['gt_fact_text']),
            }
            if hop['conflict_type'] == 'has_pair' and hop.get('old_fact_text'):
                hop_entry['chain_old_matches'] = find_prop_id(hop['old_fact_text'])
                new_n = len(hop_entry['chain_new_matches'])
                old_n = len(hop_entry['chain_old_matches'])
                if new_n == 1 and old_n == 1:
                    match_stats['perfect_1_1'] += 1
                elif new_n >= 1 and old_n >= 1:
                    match_stats['multi_match'] += 1
                elif new_n == 0 and old_n == 0:
                    match_stats['both_missing'] += 1
                elif new_n == 0:
                    match_stats['new_missing'] += 1
                else:
                    match_stats['old_missing'] += 1
            else:
                hop_entry['chain_old_matches'] = []
                new_n = len(hop_entry['chain_new_matches'])
                if new_n == 1:
                    match_stats['no_pair_perfect'] += 1
                elif new_n >= 1:
                    match_stats['no_pair_multi'] += 1
                else:
                    match_stats['no_pair_missing'] += 1
            entry['hops'].append(hop_entry)
        labels.append(entry)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)

    print(f"\n=== Match statistics ({sum(match_stats.values())} total hops) ===")
    for k, n in match_stats.most_common():
        print(f"  {k}: {n}")
    total_hp = sum(v for k, v in match_stats.items() if not k.startswith('no_pair'))
    total_np = sum(v for k, v in match_stats.items() if k.startswith('no_pair'))
    perfect_hp = match_stats['perfect_1_1']
    perfect_np = match_stats['no_pair_perfect']
    print(f"\nhas_pair: {perfect_hp}/{total_hp} ({100*perfect_hp/max(total_hp,1):.0f}%) perfect 1:1")
    print(f"no_pair:  {perfect_np}/{total_np} ({100*perfect_np/max(total_np,1):.0f}%) perfect 1:1")

    # List problematic hops for review
    problematic = []
    for entry in labels:
        for h in entry['hops']:
            new_n = len(h['chain_new_matches'])
            old_n = len(h['chain_old_matches'])
            if h['conflict_type'] == 'has_pair':
                if new_n != 1 or old_n != 1:
                    problematic.append((entry['qa_pair_id'], h['hop_idx'],
                                        new_n, old_n, h['gt_fact_text'], h.get('old_fact_text')))
            else:
                if new_n != 1:
                    problematic.append((entry['qa_pair_id'], h['hop_idx'],
                                        new_n, '-', h['gt_fact_text'], None))
    print(f"\nproblematic hops (NEW != 1 OR OLD != 1): {len(problematic)}")
    for p in problematic[:10]:
        print(f"  {p[0]} h{p[1]}: NEW={p[2]} OLD={p[3]} | gt={p[4][:60]}")

    print(f"\n[wrote] {OUT}")


if __name__ == '__main__':
    main()
