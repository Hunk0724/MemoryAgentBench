"""
FC-MH 100 題的 dataset characterization:

(1) Hop count distribution (num_hops 分布)
(2) has_pair (chain_old) 在 chain 中的位置分布
    - 絕對 hop_idx 分布
    - 相對位置 (hop_idx / num_hops) 分布
    - 是否偏向 chain 開頭/中間/結尾
(3) Conflict triple surface variation
    - chain_new vs chain_old 字串的:
      - char-level Levenshtein 距離
      - token-level Jaccard / F1
      - shared prefix / shared suffix 長度
      - 是否只 swap object (S P O 結構保持)
    - update_gap (gt_seq - old_seq) 分布

Output: analysis/results/fc_mh_dataset_characterization.json + console summary
"""

import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
GT_PATH = BASE / 'analysis/results/mh_512_mquake_analysis.json'
OUT_PATH = BASE / 'analysis/results/fc_mh_dataset_characterization.json'

mh = json.load(open(GT_PATH))


# ---------- Helpers ----------

def levenshtein(a, b):
    if len(a) < len(b):
        return levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def tokenize(s):
    return re.findall(r"[\w']+", s.lower())


def jaccard(a, b):
    sa, sb = set(tokenize(a)), set(tokenize(b))
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def token_f1(a, b):
    sa, sb = tokenize(a), tokenize(b)
    if not sa or not sb:
        return 0.0
    common = Counter(sa) & Counter(sb)
    n_common = sum(common.values())
    if n_common == 0:
        return 0.0
    p = n_common / len(sa)
    r = n_common / len(sb)
    return 2 * p * r / (p + r)


def shared_prefix_chars(a, b):
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def shared_suffix_chars(a, b):
    return shared_prefix_chars(a[::-1], b[::-1])


def percentiles(values, ps=(25, 50, 75, 90, 95)):
    if not values:
        return {f'p{p}': None for p in ps}
    s = sorted(values)
    out = {}
    for p in ps:
        idx = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
        out[f'p{p}'] = s[idx]
    return out


# ---------- (1) Hop distribution ----------
hop_counter = Counter()
for q in mh:
    hop_counter[q['num_hops']] += 1
hop_dist = dict(sorted(hop_counter.items()))

n_has_pair_per_q = []
for q in mh:
    pairs = sum(1 for h in q['hops'] if h.get('conflict_type') == 'has_pair')
    n_has_pair_per_q.append(pairs)
n_has_pair_per_q_dist = Counter(n_has_pair_per_q)

# has_pair count vs num_hops cross-tab
crosstab = defaultdict(lambda: Counter())
for q in mh:
    pairs = sum(1 for h in q['hops'] if h.get('conflict_type') == 'has_pair')
    crosstab[q['num_hops']][pairs] += 1


# ---------- (2) has_pair position distribution ----------
abs_pos = []
rel_pos = []
position_buckets = {'first_only': 0, 'last_only': 0, 'middle_only': 0,
                    'mixed': 0, 'all_in_chain': 0}

for q in mh:
    n = q['num_hops']
    has_pair_idx = [h['hop_idx'] for h in q['hops'] if h.get('conflict_type') == 'has_pair']
    if not has_pair_idx:
        continue
    abs_pos.extend(has_pair_idx)
    rel_pos.extend([i / max(n - 1, 1) for i in has_pair_idx])

    # bucket
    if len(has_pair_idx) == n:
        position_buckets['all_in_chain'] += 1
    elif has_pair_idx == [0]:
        position_buckets['first_only'] += 1
    elif has_pair_idx == [n - 1]:
        position_buckets['last_only'] += 1
    elif all(0 < i < n - 1 for i in has_pair_idx):
        position_buckets['middle_only'] += 1
    else:
        position_buckets['mixed'] += 1

abs_pos_counter = Counter(abs_pos)


# ---------- (3) Surface variation of conflict triples ----------
surface_metrics = []
for q in mh:
    for h in q['hops']:
        if h.get('conflict_type') != 'has_pair':
            continue
        new_t = h.get('gt_fact_text', '')
        old_t = h.get('old_fact_text', '')
        if not new_t or not old_t:
            continue
        d = {
            'qid': q['query_id'],
            'hop_idx': h['hop_idx'],
            'new_text': new_t,
            'old_text': old_t,
            'new_len_chars': len(new_t),
            'old_len_chars': len(old_t),
            'new_len_tokens': len(tokenize(new_t)),
            'old_len_tokens': len(tokenize(old_t)),
            'levenshtein': levenshtein(new_t, old_t),
            'jaccard': round(jaccard(new_t, old_t), 4),
            'token_f1': round(token_f1(new_t, old_t), 4),
            'shared_prefix_chars': shared_prefix_chars(new_t, old_t),
            'shared_suffix_chars': shared_suffix_chars(new_t, old_t),
            'update_gap': h.get('update_gap'),
            'gt_seq': h.get('gt_seq'),
            'old_seq': h.get('old_seq'),
        }
        # 判斷是否「只 object 不同」: 共享 prefix 涵蓋大部分句子
        max_len = max(d['new_len_chars'], d['old_len_chars'])
        d['shared_prefix_ratio'] = round(d['shared_prefix_chars'] / max_len, 3)
        # 「object swap only」heuristic: prefix+suffix 涵蓋 ≥75% 較長句
        prefix_plus_suffix = d['shared_prefix_chars'] + d['shared_suffix_chars']
        # 避免重疊計算 (e.g., 兩字串相同時)
        prefix_plus_suffix = min(prefix_plus_suffix, max_len)
        d['prefix_plus_suffix_ratio'] = round(prefix_plus_suffix / max_len, 3)
        d['is_object_swap_only'] = bool(prefix_plus_suffix / max_len >= 0.75)
        surface_metrics.append(d)


# ---------- Aggregate stats ----------
agg = {}
if surface_metrics:
    for k in ['levenshtein', 'jaccard', 'token_f1', 'shared_prefix_ratio',
              'prefix_plus_suffix_ratio']:
        vals = [m[k] for m in surface_metrics]
        agg[k] = {
            'n': len(vals),
            'mean': round(st.mean(vals), 3),
            'median': round(st.median(vals), 3),
            'stdev': round(st.stdev(vals), 3) if len(vals) > 1 else 0,
            'min': min(vals),
            'max': max(vals),
            **{p: round(v, 3) if isinstance(v, float) else v
               for p, v in percentiles(vals).items()}
        }

    # update_gap stats
    gap_vals = [m['update_gap'] for m in surface_metrics if m['update_gap'] is not None]
    if gap_vals:
        agg['update_gap'] = {
            'n': len(gap_vals),
            'mean': round(st.mean(gap_vals), 1),
            'median': st.median(gap_vals),
            'stdev': round(st.stdev(gap_vals), 1) if len(gap_vals) > 1 else 0,
            'min': min(gap_vals),
            'max': max(gap_vals),
            **percentiles(gap_vals),
        }

    # length stats
    n_object_swap = sum(1 for m in surface_metrics if m['is_object_swap_only'])
    agg['object_swap_only_rate'] = {
        'count': n_object_swap,
        'total': len(surface_metrics),
        'pct': round(n_object_swap / len(surface_metrics) * 100, 1),
    }


result = {
    'meta': {
        'source': str(GT_PATH.relative_to(BASE)),
        'n_questions': len(mh),
        'n_has_pair_hops': len(surface_metrics),
        'methodology': {
            'levenshtein': 'character-level Levenshtein distance between gt_fact_text and old_fact_text',
            'jaccard': 'token-level Jaccard similarity (regex \\w+, lowercase)',
            'token_f1': 'token-level F1 (multiset)',
            'shared_prefix_ratio': 'longest common prefix length / max(len(new), len(old))',
            'prefix_plus_suffix_ratio': '(prefix + suffix) chars / max length, capped at 1.0',
            'is_object_swap_only': 'prefix+suffix ratio >= 0.75 (heuristic for SPO swap)',
            'update_gap': 'gt_seq - old_seq (序號距離,越大代表 update 越晚)',
        },
    },
    'hop_count_distribution': hop_dist,
    'n_has_pair_per_question': dict(sorted(n_has_pair_per_q_dist.items())),
    'crosstab_num_hops_x_n_has_pair': {
        f'{nh}-hop': dict(sorted(c.items()))
        for nh, c in sorted(crosstab.items())
    },
    'has_pair_position': {
        'absolute_hop_idx_distribution': dict(sorted(abs_pos_counter.items())),
        'relative_position_buckets': position_buckets,
        'rel_pos_mean': round(st.mean(rel_pos), 3) if rel_pos else None,
        'rel_pos_median': round(st.median(rel_pos), 3) if rel_pos else None,
    },
    'surface_variation_aggregate': agg,
    # detail 太長, 只存前 5 跟低/高 jaccard 各 5 例
    'surface_examples_low_jaccard': sorted(surface_metrics, key=lambda x: x['jaccard'])[:5],
    'surface_examples_high_jaccard': sorted(surface_metrics, key=lambda x: -x['jaccard'])[:5],
}

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
json.dump(result, open(OUT_PATH, 'w'), ensure_ascii=False, indent=2)
print(f'Saved: {OUT_PATH}\n')


# ---------- Console summary ----------
print('=' * 70)
print(f'  FC-MH Dataset Characterization (n={len(mh)} questions)')
print('=' * 70)

print(f'\n--- (1) Hop count distribution ---')
for nh, c in hop_dist.items():
    bar = '█' * c
    print(f'  {nh}-hop: {c:3d} ({c}%) {bar}')
print(f'  total: {sum(hop_dist.values())} questions')

print(f'\n--- has_pair per question ---')
for n, c in sorted(n_has_pair_per_q_dist.items()):
    print(f'  {n} has_pair hops: {c:3d} questions')

print(f'\n--- Crosstab num_hops × n_has_pair ---')
print(f'  {"":8s} | ' + ' | '.join(f'{n}-pair' for n in range(5)) + ' | total')
for nh in sorted(crosstab):
    row = crosstab[nh]
    cells = [str(row.get(np, 0)) for np in range(5)]
    total = sum(row.values())
    print(f'  {nh}-hop  | ' + ' | '.join(f'{c:>5s}' for c in cells) + f' | {total:>5d}')

print(f'\n--- (2) has_pair position distribution ---')
print(f'  Absolute hop_idx (where in chain has_pair appears):')
for idx, c in sorted(abs_pos_counter.items()):
    print(f'    hop_idx {idx}: {c} hops')
print(f'  Relative position (idx / (num_hops-1)):')
print(f'    mean: {result["has_pair_position"]["rel_pos_mean"]}, median: {result["has_pair_position"]["rel_pos_median"]}')
print(f'  Position bucket per question:')
for k, v in position_buckets.items():
    print(f'    {k}: {v}')

print(f'\n--- (3) Surface variation (188 has_pair hops) ---')
for k in ['levenshtein', 'jaccard', 'token_f1', 'shared_prefix_ratio',
          'prefix_plus_suffix_ratio']:
    s = agg[k]
    print(f'  {k}: mean={s["mean"]}, median={s["median"]}, p25={s["p25"]}, p75={s["p75"]}, range=[{s["min"]}, {s["max"]}]')
print(f'\n  is_object_swap_only (heuristic prefix+suffix ≥75% of max len):')
print(f'    {agg["object_swap_only_rate"]["count"]}/{agg["object_swap_only_rate"]["total"]} = {agg["object_swap_only_rate"]["pct"]}%')

if 'update_gap' in agg:
    g = agg['update_gap']
    print(f'\n  update_gap (gt_seq - old_seq):')
    print(f'    mean={g["mean"]}, median={g["median"]}, range=[{g["min"]}, {g["max"]}]')
    print(f'    p25={g["p25"]}, p50={g["p50"]}, p75={g["p75"]}, p90={g["p90"]}')

print(f'\n--- Lowest jaccard examples (most different surface) ---')
for ex in result['surface_examples_low_jaccard']:
    print(f'  qid={ex["qid"]} hop={ex["hop_idx"]} jaccard={ex["jaccard"]} levenshtein={ex["levenshtein"]}')
    print(f'    new: {ex["new_text"]}')
    print(f'    old: {ex["old_text"]}')
print(f'\n--- Highest jaccard examples (most similar surface, e.g. SPO swap) ---')
for ex in result['surface_examples_high_jaccard']:
    print(f'  qid={ex["qid"]} hop={ex["hop_idx"]} jaccard={ex["jaccard"]} levenshtein={ex["levenshtein"]} object_swap_only={ex["is_object_swap_only"]}')
    print(f'    new: {ex["new_text"]}')
    print(f'    old: {ex["old_text"]}')
