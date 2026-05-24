"""W1.4 mini-eval builder.

Build hop-level GT labels for 16 selected FC-MH 6k queries.

For each query × hop with conflict_type='has_pair':
  - Find prop_id in proposition_index.json that matches gt_fact_text (chain_new)
  - Find prop_id matching old_fact_text (chain_old)
  - Strict s+o matching (reuses analyze_w1_2_hop_coverage logic)

Output:
  analysis/results/mini_eval_w14/labels.json
  + console summary of match coverage
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
SELECTION = BASE / 'analysis/results/mini_eval_w14/selection.json'
PROP_INDEX = BASE / ('outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/'
                     'chunksize_512/context_id_0/'
                     'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/'
                     'proposition_index.json')
OUT = BASE / 'analysis/results/mini_eval_w14/labels.json'


# ─── strict s+o extractor (ported from analyze_w1_2_hop_coverage.py) ───

def _norm(s: str) -> str:
    s = s.lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_PREDICATE_PATTERNS = [
    r"\bis a citizen of\b", r"\bcitizen of\b",
    r"\bis married to\b", r"\bwas married to\b", r"\bmarried to\b",
    r"\bis associated with\b", r"\bwas associated with\b", r"\bassociated with\b",
    r"\bplays the position of\b", r"\bplays position\b", r"\bposition of\b",
    r"\bis the chairperson of\b", r"\bwas the chairperson of\b", r"\bchairperson of\b",
    r"\bwas born in\b", r"\bis born in\b", r"\bborn in\b",
    r"\bdied in\b", r"\bwas employed by\b", r"\bis employed by\b", r"\bemployed by\b",
    r"\bwas founded by\b", r"\bis founded by\b", r"\bfounded by\b", r"\bfounded\b",
    r"\bwas created by\b", r"\bis created by\b", r"\bcreated by\b",
    r"\bwas authored by\b", r"\bis authored by\b", r"\bauthored by\b",
    r"\bis the author of\b", r"\bwas the author of\b", r"\bauthor of\b",
    r"\bis the director of\b", r"\bwas the director of\b", r"\bdirector of\b",
    r"\bis the performer of\b", r"\bwas the performer of\b", r"\bperformer of\b",
    r"\bwas performed by\b", r"\bperformed by\b", r"\bperformed\b",
    r"\bwas educated at\b", r"\bis educated at\b", r"\beducated at\b",
    r"\bholds the title of\b", r"\bhas the title of\b",
    r"\bis the child of\b", r"\bwas the child of\b",
    r"'s child is\b", r"'s spouse is\b", r"'s parent is\b",
    r"\bis located in the continent of\b", r"\bis located in\b", r"\blocated in\b",
    r"\bis the capital of\b", r"\bcapital of\b",
    r"\bis the founder of\b", r"\bfounder of\b",
    r"\bcreated in the country of\b", r"\bcreated in\b",
    r"\bwritten in the language of\b", r"\bwritten in\b",
    r"\bspeaks\b", r"\bwrote\b", r"\bcomposed\b",
    r"\bis owned by\b", r"\bowned by\b",
    r"\bworks for\b", r"\bworked for\b",
    r"\bworks in the field of\b", r"\bworks in field of\b",
    r"\bworked in the city of\b", r"\bworks in the city of\b",
    r"\bwas developed by\b", r"\bis developed by\b", r"\bdeveloped by\b",
    r"\bis affiliated with the religion of\b",
    r"\bwas affiliated with the religion of\b",
    r"\baffiliated with the religion of\b",
    r"\bis the name of the current head of state in\b",
    r"\bcurrent head of state in\b",
    r"\bhead of state in\b",
    r"\bis the head of state of\b", r"\bhead of state of\b",
    r"\bis the operating system of\b", r"\boperating system of\b",
    r"\bwas designed by\b", r"\bdesigned by\b",
    r"\bworks as a\b", r"\bworks as\b",
    r"\bplace of death\b", r"\bdied\b",
    r"\bceo of\b", r"\bchief executive officer of\b",
    r"\bis famous for\b", r"\bfamous for\b",
    r"\bis the sport of\b", r"\bsport of\b",
    r"\bis the country of citizenship of\b",
    # Fallback (broad)
    r"\bis the\b", r"\bwas the\b", r"\bis\b", r"\bwas\b",
]


def extract_so(fact_text: str):
    text = _norm(fact_text)
    best = None
    best_span_len = 0
    for pat in _PREDICATE_PATTERNS:
        m = re.search(pat, text)
        if not m:
            continue
        s_phrase = text[:m.start()].strip()
        o_phrase = text[m.end():].strip()
        # Strip leading articles + trailing pre-article (handle both "the X" and bare "the")
        s_phrase = re.sub(r"^(the|a|an)\b\s*", "", s_phrase).strip()
        o_phrase = re.sub(r"^(the|a|an)\b\s*", "", o_phrase).strip()
        if len(s_phrase) < 3 or len(o_phrase) < 3:
            continue
        # Reject phrases that are still empty after article-strip
        if not s_phrase or not o_phrase:
            continue
        span_len = m.end() - m.start()
        if span_len > best_span_len:
            best = (s_phrase, o_phrase)
            best_span_len = span_len
    return best if best else (None, None)


def fact_match(a: str, b: str) -> bool:
    sa, oa = extract_so(a)
    sb, ob = extract_so(b)
    if sa is None or sb is None:
        return False

    def overlap(x, y):
        if len(x) < 3 or len(y) < 3:
            return False
        return x in y or y in x

    forward = overlap(sa, sb) and overlap(oa, ob)
    flipped = overlap(sa, ob) and overlap(oa, sb)
    return forward or flipped


# ─── Main ───

def main():
    selection = json.load(open(SELECTION))
    prop_index = json.load(open(PROP_INDEX))
    props = prop_index['propositions']

    gt = {q['query_id']: q for q in
          json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))}

    # Pre-extract s+o for all 450 props (cache)
    prop_so = {}
    for p in props:
        prop_so[p['id']] = (extract_so(p['text']), p)

    def find_prop_id(fact_text: str):
        """Return list of (prop_id, prop_text, ts) matching fact_text."""
        matches = []
        for pid, ((s, o), p) in prop_so.items():
            if fact_match(fact_text, p['text']):
                matches.append({
                    'prop_id': pid,
                    'prop_text': p['text'],
                    'timestamp': p['timestamp'],
                    'source_chunk_id': p['source_chunk_id'],
                })
        return matches

    labels = []
    match_stats = Counter()
    for sel in selection:
        qid = sel['query_id']
        q = gt[qid]
        entry = {
            'qa_pair_id': sel['qa_pair_id'],
            'query_id': qid,
            'question': sel['question'],
            'gt_answer': sel['gt_answer'],
            'num_hops': sel['num_hops'],
            'all_pair': sel['all_pair'],
            'w13_correct': sel['w13_correct'],
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
                'chain_new_matches': [],
                'chain_old_matches': [],
            }
            new_matches = find_prop_id(hop['gt_fact_text'])
            hop_entry['chain_new_matches'] = new_matches
            if hop['conflict_type'] == 'has_pair' and hop.get('old_fact_text'):
                old_matches = find_prop_id(hop['old_fact_text'])
                hop_entry['chain_old_matches'] = old_matches
                # stats
                if len(new_matches) == 1 and len(old_matches) == 1:
                    match_stats['perfect_1_1'] += 1
                elif len(new_matches) >= 1 and len(old_matches) >= 1:
                    match_stats['multi_match'] += 1
                elif len(new_matches) == 0 and len(old_matches) == 0:
                    match_stats['both_missing'] += 1
                elif len(new_matches) == 0:
                    match_stats['new_missing'] += 1
                else:
                    match_stats['old_missing'] += 1
            else:
                if len(new_matches) == 1:
                    match_stats['no_pair_perfect'] += 1
                elif len(new_matches) >= 1:
                    match_stats['no_pair_multi'] += 1
                else:
                    match_stats['no_pair_missing'] += 1
            entry['hops'].append(hop_entry)
        labels.append(entry)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)

    print(f"=== Mini-eval labels written: {OUT}")
    print(f"N queries: {len(labels)}")
    print(f"\n=== Hop match statistics ===")
    for k, n in match_stats.most_common():
        print(f"  {k}: {n}")
    total_has_pair = sum(v for k, v in match_stats.items() if not k.startswith('no_pair'))
    total_no_pair = sum(v for k, v in match_stats.items() if k.startswith('no_pair'))
    print(f"\nTotal has_pair hops: {total_has_pair}")
    print(f"Total no_pair hops: {total_no_pair}")

    # List problematic hops for review
    print(f"\n=== Hops needing review (multi-match or missing) ===")
    for entry in labels:
        for hop in entry['hops']:
            issue = None
            new_n = len(hop['chain_new_matches'])
            old_n = len(hop['chain_old_matches'])
            if hop['conflict_type'] == 'has_pair':
                if new_n != 1 or old_n != 1:
                    issue = f"NEW={new_n} OLD={old_n}"
            else:
                if new_n != 1:
                    issue = f"NEW={new_n} (no_pair)"
            if issue:
                print(f"  [{entry['qa_pair_id']} h{hop['hop_idx']}] {issue}")
                print(f"    gt: {hop['gt_fact_text']}")
                if hop['conflict_type'] == 'has_pair':
                    print(f"    old: {hop['old_fact_text']}")
                if new_n > 1:
                    for m in hop['chain_new_matches']:
                        print(f"      new candidate: ({m['timestamp']}) {m['prop_text']}")
                if old_n > 1:
                    for m in hop['chain_old_matches']:
                        print(f"      old candidate: ({m['timestamp']}) {m['prop_text']}")


if __name__ == '__main__':
    main()
