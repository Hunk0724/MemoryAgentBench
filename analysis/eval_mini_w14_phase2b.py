"""W1.4 mini-eval — Phase 2.b pool co-occurrence + verdict accuracy.

Joins:
  - analysis/results/mini_eval_w14/labels.json (16 queries × hop-level GT prop_ids)
  - monitoring_logs/<latest>_v2_phase2_w13/verdict_events.jsonl (K_pool + verdict result per focus)
  - monitoring_logs/<latest>_v2_phase2_w13/phase2_w13_dump.jsonl (consolidated verdicts per query)

Metrics computed (per spec §B.3.4.2 v2.0.3):
  - Per-hop K_pool co-occurrence rate (RECALL upper bound)
    = #(has_pair hops where K_pool contains BOTH chain_new + chain_old) / total has_pair hops
  - Per-hop verdict accuracy CONDITIONAL on co-occurrence
    = #(co-occurrence hops where chain_old verdict is superseded BY chain_new) / co-occurrence hops
  - Per-hop verdict accuracy UNCONDITIONAL (gross)
    = same numerator / total has_pair hops
  - Pool size stats
  - Breakdown by hop count (2/3/4)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
LABELS = BASE / 'analysis/results/mini_eval_w14/labels.json'

# RUN_DIR can be overridden via CLI arg or analysis/results/mini_eval_w14/latest_run.txt pointer
import sys as _sys
_LATEST_POINTER = BASE / 'analysis/results/mini_eval_w14/latest_run.txt'
if len(_sys.argv) > 1:
    RUN_DIR = Path(_sys.argv[1])
elif _LATEST_POINTER.exists():
    RUN_DIR = Path(_LATEST_POINTER.read_text().strip())
else:
    RUN_DIR = BASE / 'monitoring_logs/2026-05-17_144921_v2_phase2_w13'

VERDICT_EVENTS = RUN_DIR / 'verdict_events.jsonl'
PHASE2_DUMP = RUN_DIR / 'phase2_w13_dump.jsonl'
# Output named by run dir suffix for traceability
_run_tag = RUN_DIR.name
OUT = BASE / f'analysis/results/mini_eval_w14/eval_{_run_tag}.json'


def normalize_query(q: str) -> str:
    """Strip prefix/suffix wrappers so labels.question and dump.query can join."""
    prefix = 'Based on the provided Knowledge Pool, '
    if q.startswith(prefix):
        q = q[len(prefix):]
    # Strip trailing \nAnswer:, whitespace, question mark
    q = q.split('\nAnswer:')[0]
    return q.strip().rstrip('?').strip().lower()


def main():
    labels = json.load(open(LABELS))

    # Load all verdict events, index by normalized question
    events_by_q = defaultdict(list)
    for line in open(VERDICT_EVENTS):
        e = json.loads(line)
        nq = normalize_query(e['query'])
        events_by_q[nq].append(e)
    print(f"[load] verdict_events.jsonl: {sum(len(v) for v in events_by_q.values())} events "
          f"across {len(events_by_q)} unique queries")

    # Load phase2 dumps
    dumps_by_q = {}
    for line in open(PHASE2_DUMP):
        d = json.loads(line)
        nq = normalize_query(d['query'])
        dumps_by_q[nq] = d
    print(f"[load] phase2_w13_dump.jsonl: {len(dumps_by_q)} unique queries")

    # Per-query evaluation
    per_query = []
    for entry in labels:
        nq = normalize_query(entry['question'])
        events = events_by_q.get(nq, [])
        dump = dumps_by_q.get(nq)
        if not dump:
            print(f"⚠️  No dump for: {entry['qa_pair_id']}")
            continue

        # Build focus_pid → event lookup
        events_by_pid = {e['focus_pid']: e for e in events}
        verdicts = dump['verdicts']  # focus_pid → verdict dict

        hops_eval = []
        for hop in entry['hops']:
            if hop['conflict_type'] != 'has_pair':
                # No-pair hop — just record presence in active region (not evaluated for co-occurrence)
                new_pid = hop['chain_new_matches'][0]['prop_id'] if hop['chain_new_matches'] else None
                hops_eval.append({
                    'hop_idx': hop['hop_idx'],
                    'conflict_type': 'no_pair',
                    'new_pid': new_pid,
                    'new_in_any_chain': any(new_pid in c['proposition_ids']
                                            for c in dump['chains']),
                })
                continue

            new_pid = hop['chain_new_matches'][0]['prop_id']
            old_pid = hop['chain_old_matches'][0]['prop_id']

            # Chain membership
            new_in_chains = any(new_pid in c['proposition_ids'] for c in dump['chains'])
            old_in_chains = any(old_pid in c['proposition_ids'] for c in dump['chains'])
            both_in_same_chain = any(
                new_pid in c['proposition_ids'] and old_pid in c['proposition_ids']
                for c in dump['chains']
            )

            # Pool inspection — check both focus directions
            # (a) when focus=new, is old in its pool?
            # (b) when focus=old, is new in its pool?
            new_event = events_by_pid.get(new_pid)
            old_event = events_by_pid.get(old_pid)
            old_in_new_pool = (new_event is not None
                                and old_pid in new_event.get('pool_pids', []))
            new_in_old_pool = (old_event is not None
                                and new_pid in old_event.get('pool_pids', []))
            # Co-occurrence: K_pool of either focus contains the counterpart
            # (this is the LLM-can-group condition)
            pool_co_occurrence = old_in_new_pool or new_in_old_pool

            # Verdict accuracy: chain_old should be 'superseded' with superseder=new_pid
            old_verdict = verdicts.get(old_pid, {})
            verdict_correct = (
                old_verdict.get('status') == 'superseded'
                and old_verdict.get('superseder_id') == new_pid
            )
            # Verdict on new_pid should be 'current'
            new_verdict = verdicts.get(new_pid, {})
            new_verdict_correct = new_verdict.get('status') == 'current'

            # Pool sizes
            new_pool_size = new_event.get('pool_size') if new_event else None
            old_pool_size = old_event.get('pool_size') if old_event else None

            hops_eval.append({
                'hop_idx': hop['hop_idx'],
                'conflict_type': 'has_pair',
                'new_pid': new_pid,
                'old_pid': old_pid,
                'new_in_chains': new_in_chains,
                'old_in_chains': old_in_chains,
                'both_in_same_chain': both_in_same_chain,
                'new_event_exists': new_event is not None,
                'old_event_exists': old_event is not None,
                'new_pool_size': new_pool_size,
                'old_pool_size': old_pool_size,
                'old_in_new_pool': old_in_new_pool,
                'new_in_old_pool': new_in_old_pool,
                'pool_co_occurrence': pool_co_occurrence,
                'old_verdict_status': old_verdict.get('status'),
                'old_verdict_superseder': old_verdict.get('superseder_id'),
                'old_verdict_correct': verdict_correct,
                'new_verdict_status': new_verdict.get('status'),
                'new_verdict_correct': new_verdict_correct,
            })

        per_query.append({
            'qa_pair_id': entry['qa_pair_id'],
            'num_hops': entry['num_hops'],
            'all_pair': entry['all_pair'],
            'w13_correct': entry['w13_correct'],
            'question': entry['question'],
            'hops': hops_eval,
        })

    # ─── Aggregate metrics ───
    metrics = {}

    # Has_pair hops only
    has_pair_hops = [(q, h) for q in per_query for h in q['hops']
                     if h['conflict_type'] == 'has_pair']
    total_hp = len(has_pair_hops)

    chain_membership_new = sum(1 for _, h in has_pair_hops if h['new_in_chains'])
    chain_membership_old = sum(1 for _, h in has_pair_hops if h['old_in_chains'])
    chain_membership_both = sum(1 for _, h in has_pair_hops if h['both_in_same_chain'])

    pool_co = sum(1 for _, h in has_pair_hops if h['pool_co_occurrence'])
    verdict_correct = sum(1 for _, h in has_pair_hops if h['old_verdict_correct'])
    verdict_correct_given_co = sum(
        1 for _, h in has_pair_hops
        if h['pool_co_occurrence'] and h['old_verdict_correct']
    )

    metrics['has_pair_hops_total'] = total_hp
    metrics['chain_membership'] = {
        'new_in_top5_chains': chain_membership_new,
        'old_in_top5_chains': chain_membership_old,
        'both_in_SAME_chain': chain_membership_both,
        'rate_new': chain_membership_new / total_hp if total_hp else 0,
        'rate_old': chain_membership_old / total_hp if total_hp else 0,
        'rate_both_same_chain': chain_membership_both / total_hp if total_hp else 0,
    }
    metrics['pool_co_occurrence'] = {
        'count': pool_co,
        'total': total_hp,
        'rate': pool_co / total_hp if total_hp else 0,
    }
    metrics['verdict_accuracy'] = {
        'correct': verdict_correct,
        'total_has_pair': total_hp,
        'rate_unconditional': verdict_correct / total_hp if total_hp else 0,
        'rate_conditional_on_co_occurrence': (
            verdict_correct_given_co / pool_co if pool_co else 0
        ),
    }

    # Breakdown by num_hops bucket
    metrics['by_num_hops'] = {}
    for nh in [2, 3, 4]:
        bucket = [(q, h) for q, h in has_pair_hops if q['num_hops'] == nh]
        n = len(bucket)
        if n == 0:
            continue
        co = sum(1 for _, h in bucket if h['pool_co_occurrence'])
        vc = sum(1 for _, h in bucket if h['old_verdict_correct'])
        vc_given_co = sum(1 for _, h in bucket if h['pool_co_occurrence']
                          and h['old_verdict_correct'])
        metrics['by_num_hops'][f'{nh}h'] = {
            'has_pair_hops': n,
            'pool_co_occurrence_rate': co / n,
            'verdict_correct_rate_unconditional': vc / n,
            'verdict_correct_rate_conditional': vc_given_co / co if co else 0,
        }

    # Failure-mode breakdown
    failures = Counter()
    for _, h in has_pair_hops:
        if h['old_verdict_correct']:
            continue
        if not h['new_in_chains'] and not h['old_in_chains']:
            failures['F1_neither_in_any_chain'] += 1
        elif not h['new_in_chains']:
            failures['F2_new_not_in_any_chain'] += 1
        elif not h['old_in_chains']:
            failures['F3_old_not_in_any_chain'] += 1
        elif not h['pool_co_occurrence']:
            failures['F4_in_chain_but_pool_missing_counterpart'] += 1
        elif h['old_verdict_status'] is None:
            failures['F5_old_no_verdict_call'] += 1
        elif h['old_verdict_status'] != 'superseded':
            failures[f'F6_old_verdict_status_{h["old_verdict_status"]}'] += 1
        elif h['old_verdict_superseder'] != h['new_pid']:
            failures['F7_old_verdict_wrong_superseder'] += 1
        else:
            failures['F_unknown'] += 1
    metrics['failure_modes'] = dict(failures)

    # Pool size stats
    pool_sizes = [h['new_pool_size'] for _, h in has_pair_hops if h['new_pool_size']]
    pool_sizes += [h['old_pool_size'] for _, h in has_pair_hops if h['old_pool_size']]
    if pool_sizes:
        pool_sizes.sort()
        metrics['pool_size'] = {
            'n_samples': len(pool_sizes),
            'median': pool_sizes[len(pool_sizes) // 2],
            'min': min(pool_sizes), 'max': max(pool_sizes),
        }

    # Print
    print("\n" + "=" * 80)
    print("MINI-EVAL W1.4 BASELINE — Phase 2.b metrics on 16-query subset")
    print("=" * 80)
    print(f"\n[Total has_pair hops]: {total_hp}")
    print(f"\n[Chain membership — does Phase 2.a find chain_new / chain_old?]")
    print(f"  chain_new in top-5 chains:  {chain_membership_new}/{total_hp} ({metrics['chain_membership']['rate_new']*100:.0f}%)")
    print(f"  chain_old in top-5 chains:  {chain_membership_old}/{total_hp} ({metrics['chain_membership']['rate_old']*100:.0f}%)")
    print(f"  BOTH in SAME chain:         {chain_membership_both}/{total_hp} ({metrics['chain_membership']['rate_both_same_chain']*100:.0f}%)")
    print(f"\n[Pool co-occurrence — does K_pool contain BOTH new + old? (the LLM-can-group condition)]")
    print(f"  count: {pool_co}/{total_hp}  RATE = {metrics['pool_co_occurrence']['rate']*100:.0f}%")
    print(f"  (spec §B.3.4.2 target: ≥ 80%)")
    print(f"\n[Verdict accuracy (chain_old marked superseded BY chain_new)]")
    print(f"  unconditional: {verdict_correct}/{total_hp}  rate = {metrics['verdict_accuracy']['rate_unconditional']*100:.0f}%")
    print(f"  conditional on co-occurrence: {verdict_correct_given_co}/{pool_co}  rate = {metrics['verdict_accuracy']['rate_conditional_on_co_occurrence']*100:.0f}%")
    print(f"  (spec §B.3.4.2 target: ≥ 80% conditional)")
    print(f"\n[Breakdown by hop count]")
    for nh, m in metrics['by_num_hops'].items():
        print(f"  {nh}: n={m['has_pair_hops']}, pool_co={m['pool_co_occurrence_rate']*100:.0f}%, "
              f"verdict_uncond={m['verdict_correct_rate_unconditional']*100:.0f}%, "
              f"verdict_cond={m['verdict_correct_rate_conditional']*100:.0f}%")
    print(f"\n[Failure modes]")
    for k, n in sorted(failures.items(), key=lambda x: -x[1]):
        print(f"  {k}: {n}")
    if 'pool_size' in metrics:
        print(f"\n[Pool size (across both focus directions)]")
        print(f"  median={metrics['pool_size']['median']}, min={metrics['pool_size']['min']}, max={metrics['pool_size']['max']}")

    # Write detailed
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        'metrics': metrics,
        'per_query': per_query,
    }, open(OUT, 'w'), indent=2, ensure_ascii=False)
    print(f"\n[wrote] {OUT}")


if __name__ == '__main__':
    main()
