"""Full 100Q per-hop cascade analysis.

Joins per-query dumps (phase2_w13_dump + verdict_events + results.json) against
full100 labels (chain_new + chain_old prop_ids per hop) to compute, FOR EACH HOP:

  Phase 2.a:
    - new_in_active_region   (chain_new prop_id ∈ dump.active_pids)
    - old_in_active_region
    - new_in_any_chain       (∈ any chain.proposition_ids)
    - old_in_any_chain
    - both_in_same_chain     (in same chain.proposition_ids list)
  Phase 2.b:
    - new_in_pool / old_in_pool (from verdict_events.jsonl pool_pids per focus)
    - pool_co_occurrence     (BOTH new+old in some focus's pool)
    - verdict_correct        (verdict[chain_old].status='superseded', superseder=chain_new)
  Phase 2.c (passage filter):
    - new_chunk_kept         (chain_new.source_chunk in dump.passages_kept)
    - old_chunk_dropped      (chain_old.source_chunk in dump.passages_dropped)
    - filter_effective       (old dropped AND new still kept)
  Phase 3 (W3):
    - new_text_in_enriched   (chain_new.text substring in enriched_context_text)
    - old_text_in_enriched   (chain_old.text substring in enriched_context_text)
    - update_pair_in_enriched

Aggregates:
  - by hop depth (2/3/4)
  - by phase2_status (RAN / DPR_FALLBACK)
  - cascade attrition table (active → chain → pool → verdict → enriched/filter)

Usage:
  python analysis/eval_100q_full_analysis.py [dump_dir]
  (if no arg, reads analysis/results/mini_eval_w14/latest_run.txt)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
LABELS = BASE / 'analysis/results/full100_eval/labels.json'


def normalize_query(q: str) -> str:
    p = 'Based on the provided Knowledge Pool, '
    if q.startswith(p):
        q = q[len(p):]
    q = q.split('\nAnswer:')[0]
    return q.strip().rstrip('?').strip().lower()


def main():
    if len(sys.argv) > 1:
        run_dir = Path(sys.argv[1])
    else:
        ptr = BASE / 'analysis/results/mini_eval_w14/latest_run.txt'
        run_dir = Path(ptr.read_text().strip())
    print(f"[load] run dir: {run_dir}")

    labels = json.load(open(LABELS))
    print(f"[load] full100 labels: {len(labels)} queries")

    # Index dumps by normalized query
    dumps = {}
    for line in open(run_dir / 'phase2_w13_dump.jsonl'):
        d = json.loads(line)
        dumps[normalize_query(d['query'])] = d
    print(f"[load] phase2_dump: {len(dumps)} events")

    # Index verdict_events by (query, focus_pid)
    pool_lookup: dict = defaultdict(dict)
    n_events = 0
    for line in open(run_dir / 'verdict_events.jsonl'):
        e = json.loads(line)
        pool_lookup[normalize_query(e['query'])][e['focus_pid']] = e
        n_events += 1
    print(f"[load] verdict_events: {n_events} events")

    # ─── Per-hop cascade ───
    out_rows = []
    for entry in labels:
        nq = normalize_query(entry['question'])
        dump = dumps.get(nq)
        events_for_q = pool_lookup.get(nq, {})

        for hop in entry['hops']:
            row = {
                'qa_pair_id': entry['qa_pair_id'],
                'num_hops': entry['num_hops'],
                'hop_idx': hop['hop_idx'],
                'conflict_type': hop['conflict_type'],
                'phase2_status': (dump.get('phase2_status', 'NO_DUMP')
                                  if dump else 'NO_DUMP'),
            }

            # GT prop_ids
            new_pid = (hop['chain_new_matches'][0]['prop_id']
                       if hop['chain_new_matches'] else None)
            old_pid = (hop['chain_old_matches'][0]['prop_id']
                       if hop['chain_old_matches'] else None)
            new_chunk = (hop['chain_new_matches'][0]['source_chunk_id']
                         if hop['chain_new_matches'] else None)
            old_chunk = (hop['chain_old_matches'][0]['source_chunk_id']
                         if hop['chain_old_matches'] else None)
            row['has_gt_new_pid'] = new_pid is not None
            row['has_gt_old_pid'] = old_pid is not None

            if dump and dump.get('phase2_status') == 'RAN':
                active_pids = set(dump.get('active_pids', []))
                chain_pid_lists = [set(c['proposition_ids']) for c in dump['chains']]
                all_chain_pids = set().union(*chain_pid_lists) if chain_pid_lists else set()

                row['new_in_active'] = new_pid in active_pids if new_pid else None
                row['old_in_active'] = old_pid in active_pids if old_pid else None
                row['new_in_any_chain'] = new_pid in all_chain_pids if new_pid else None
                row['old_in_any_chain'] = old_pid in all_chain_pids if old_pid else None
                row['both_in_same_chain'] = (
                    any(new_pid in s and old_pid in s for s in chain_pid_lists)
                    if (new_pid and old_pid) else None
                )

                # Phase 2.b
                pool_new = events_for_q.get(new_pid)
                pool_old = events_for_q.get(old_pid)
                row['new_focus_evaluated'] = pool_new is not None
                row['old_focus_evaluated'] = pool_old is not None
                old_in_new_pool = (pool_new and old_pid in pool_new.get('pool_pids', []))
                new_in_old_pool = (pool_old and new_pid in pool_old.get('pool_pids', []))
                row['pool_co_occurrence'] = bool(old_in_new_pool or new_in_old_pool)

                verdicts = dump.get('verdicts', {})
                old_verdict = verdicts.get(old_pid, {}) if old_pid else {}
                row['old_verdict_status'] = old_verdict.get('status')
                row['old_verdict_superseder'] = old_verdict.get('superseder_id')
                row['verdict_correct'] = (
                    old_verdict.get('status') == 'superseded'
                    and old_verdict.get('superseder_id') == new_pid
                ) if (new_pid and old_pid) else None

                # Phase 2.c (filter)
                kept = set(dump.get('passages_kept_chunk_ids', []))
                dropped = set(dump.get('passages_dropped_chunk_ids', []))
                row['new_chunk_kept'] = new_chunk in kept if new_chunk else None
                row['old_chunk_dropped'] = old_chunk in dropped if old_chunk else None
                row['filter_effective'] = (
                    row.get('new_chunk_kept') and row.get('old_chunk_dropped')
                ) if (new_chunk and old_chunk) else None

                # Phase 3 (enriched)
                enriched = dump.get('enriched_context_text', '')
                new_text = hop['chain_new_matches'][0]['prop_text'] if hop['chain_new_matches'] else ''
                old_text = hop['chain_old_matches'][0]['prop_text'] if hop['chain_old_matches'] else ''
                # Substring match (chain_new text appears in enriched body)
                # Strip trailing period because enriched format may add it.
                def _strip_p(s): return s.rstrip('.').strip()
                row['new_text_in_enriched'] = bool(
                    new_text and _strip_p(new_text) in enriched
                )
                row['old_text_in_enriched'] = bool(
                    old_text and _strip_p(old_text) in enriched
                )
                row['update_pair_in_enriched'] = (
                    row['new_text_in_enriched'] and row['old_text_in_enriched']
                ) if (new_text and old_text) else False
            else:
                # NO_DUMP or DPR_FALLBACK — all phase2 fields None
                for k in ('new_in_active', 'old_in_active', 'new_in_any_chain',
                          'old_in_any_chain', 'both_in_same_chain',
                          'new_focus_evaluated', 'old_focus_evaluated',
                          'pool_co_occurrence', 'old_verdict_status',
                          'old_verdict_superseder', 'verdict_correct',
                          'new_chunk_kept', 'old_chunk_dropped', 'filter_effective',
                          'new_text_in_enriched', 'old_text_in_enriched',
                          'update_pair_in_enriched'):
                    row[k] = None

            out_rows.append(row)

    # ─── Aggregate ───
    # Status: count queries by phase2_status
    n_ran = sum(1 for v in dumps.values() if v.get('phase2_status') == 'RAN')
    n_dpr = sum(1 for v in dumps.values() if v.get('phase2_status') == 'DPR_FALLBACK_NO_FACTS')
    n_missing = len(labels) - n_ran - n_dpr
    print(f"\n=== Query-level Phase 2 status ===")
    print(f"  RAN: {n_ran}, DPR_FALLBACK: {n_dpr}, no dump: {n_missing}")

    # Cascade aggregate over has_pair hops (where both new+old labels exist + phase2 RAN)
    hp_rows = [r for r in out_rows
               if r['conflict_type'] == 'has_pair' and r['phase2_status'] == 'RAN'
               and r['has_gt_new_pid'] and r['has_gt_old_pid']]
    print(f"\n=== Per-hop cascade (has_pair hops, phase2 RAN, both labels mapped: {len(hp_rows)}) ===")

    def pct(field, rows=hp_rows):
        n_true = sum(1 for r in rows if r.get(field))
        return f"{n_true}/{len(rows)} ({100*n_true/max(len(rows),1):.0f}%)"

    print(f"\n--- Phase 2.a (chain identification) ---")
    print(f"  chain_new in active_region : {pct('new_in_active')}")
    print(f"  chain_old in active_region : {pct('old_in_active')}")
    print(f"  chain_new in any top-5 chain: {pct('new_in_any_chain')}")
    print(f"  chain_old in any top-5 chain: {pct('old_in_any_chain')}")
    print(f"  BOTH in SAME chain         : {pct('both_in_same_chain')}")
    print(f"\n--- Phase 2.b (verdict) ---")
    print(f"  pool co-occurrence         : {pct('pool_co_occurrence')}")
    print(f"  verdict correct (old→new)  : {pct('verdict_correct')}")
    print(f"\n--- Phase 2.c (passage filter) ---")
    print(f"  chain_old chunk dropped    : {pct('old_chunk_dropped')}")
    print(f"  chain_new chunk kept       : {pct('new_chunk_kept')}")
    print(f"  filter effective (both)    : {pct('filter_effective')}")
    print(f"\n--- Phase 3 (enriched context) ---")
    print(f"  chain_new text in enriched : {pct('new_text_in_enriched')}")
    print(f"  chain_old text in enriched : {pct('old_text_in_enriched')}")
    print(f"  update pair both in enriched: {pct('update_pair_in_enriched')}")

    print(f"\n=== By hop depth ===")
    for hops in (2, 3, 4):
        bucket = [r for r in hp_rows if r['num_hops'] == hops]
        if not bucket:
            continue
        print(f"\n  {hops}-hop ({len(bucket)} has_pair hops):")
        for field in ('new_in_any_chain', 'old_in_any_chain', 'both_in_same_chain',
                      'pool_co_occurrence', 'verdict_correct',
                      'update_pair_in_enriched'):
            print(f"    {field:>30}: {pct(field, bucket)}")

    out_path = run_dir / 'cascade_per_hop.json'
    json.dump({
        'meta': {'run_dir': str(run_dir), 'n_queries': len(labels),
                 'n_phase2_ran': n_ran, 'n_dpr_fallback': n_dpr,
                 'n_has_pair_hops_evaluated': len(hp_rows)},
        'rows': out_rows,
    }, open(out_path, 'w'), indent=2, ensure_ascii=False)
    print(f"\n[wrote] {out_path}")


if __name__ == '__main__':
    main()
