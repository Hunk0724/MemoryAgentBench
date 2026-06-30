"""5 Priority analyses from 4-ablation dumps + labels.json.

  1. C2.14 — Filter rescue breakdown (hard drop / rescue, rescue purity)
  2. C2.6  — Pool sources contribution (entity overlap / cosine / γ)
  3. C2.8  — LLM identify accuracy (conditional on pool co-occurrence)
  4. Tier3 — Failure root-cause cascade (F0-F8 per wrong query)
  5. V1    — Cascade attrition by hop bar chart

Outputs:
  analysis/results/priority5/<analysis>_table.md
  analysis/results/priority5/<analysis>_chart.png
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/results/priority5'
OUT.mkdir(parents=True, exist_ok=True)

# ─── Load resources ───
labels_list = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))
labels_by_qid = {q['qa_pair_id']: q for q in labels_list}

# Load propositions (for source_chunk_id lookups)
prop_index = json.load(open(BASE / 'outputs/rag_retrieved/NV-Embed-v2/'
                            'factconsolidation_mh_6k/chunksize_512/context_id_0/'
                            'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/'
                            'proposition_index.json'))
props_by_id = {p['id']: p for p in prop_index['propositions']}


def load_run(name):
    dirs = sorted((BASE / 'monitoring_logs').glob(f'*_ablation_{name}'))
    if not dirs:
        return None
    d = dirs[-1]
    out = {'dir': d}
    if (d / 'results.json').exists():
        out['results'] = {r['qa_pair_id']: r for r in
                          json.load(open(d / 'results.json'))['data']}
    out['dump'] = {}
    if (d / 'phase2_w13_dump.jsonl').exists():
        for line in open(d / 'phase2_w13_dump.jsonl'):
            e = json.loads(line)
            out['dump'][normalize_query(e['query'])] = e
    out['verdicts'] = defaultdict(dict)
    if (d / 'verdict_events.jsonl').exists():
        for line in open(d / 'verdict_events.jsonl'):
            e = json.loads(line)
            out['verdicts'][normalize_query(e['query'])][e['focus_pid']] = e
    return out


def normalize_query(q):
    p = 'Based on the provided Knowledge Pool, '
    if q.startswith(p):
        q = q[len(p):]
    q = q.split('\nAnswer:')[0]
    return q.strip().rstrip('?').strip().lower()


print("[load] runs...")
runs = {n: load_run(n) for n in 'ABCD'}
print(f"  A results: {len(runs['A']['results']) if runs['A'] else 0}")
print(f"  B dumps:   {len(runs['B']['dump'])}, verdicts: {sum(len(v) for v in runs['B']['verdicts'].values())}")
print(f"  C dumps:   {len(runs['C']['dump'])}")
print(f"  D dumps:   {len(runs['D']['dump'])}")


# Helper: get GT mapping for a query
def gt_for(qid):
    q = labels_by_qid.get(qid)
    if not q:
        return None
    pairs = []
    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair':
            continue
        if hop['chain_new_matches'] and hop['chain_old_matches']:
            pairs.append({
                'hop_idx': hop['hop_idx'],
                'new_pid': hop['chain_new_matches'][0]['prop_id'],
                'old_pid': hop['chain_old_matches'][0]['prop_id'],
                'new_chunk': hop['chain_new_matches'][0]['source_chunk_id'],
                'old_chunk': hop['chain_old_matches'][0]['source_chunk_id'],
                'new_text': hop['chain_new_matches'][0]['prop_text'],
                'old_text': hop['chain_old_matches'][0]['prop_text'],
            })
    return {'num_hops': q['num_hops'], 'pairs': pairs, 'question': q['question']}


# ============================================================
# Analysis 1: C2.14 — Filter rescue breakdown
# ============================================================
print("\n=== Analysis 1: Filter rescue breakdown (B,C — D has no filter) ===")

def analyze_rescue(run, run_name):
    """Categorize each top-20 passage into:
       - hard_drop: had chain_old, no rescuing chain_current → dropped
       - rescue (containing chain_new): rescue justified (passage has chain_new of some hop)
       - rescue (containing unrelated current): rescue questionable
       - no_chain_old: passage didn't contain chain_old (kept normally)
    """
    cats = Counter()
    per_q_rescue_purity = []  # for each query: (rescue_kept_count, rescue_with_chain_new, rescue_unrelated)

    for nq, dump in run['dump'].items():
        if dump.get('phase2_status') != 'RAN':
            continue
        chain_old_pids = set(dump.get('chain_old_pids', []))
        verdicts = dump.get('verdicts', {})
        pre_filter = dump.get('passages_pre_filter_chunk_ids', [])
        kept = set(dump.get('passages_kept_chunk_ids', []))
        dropped = set(dump.get('passages_dropped_chunk_ids', []))

        # Build chunk → prop_ids mapping for this query's relevant chunks
        # Use props_by_id to map chunk_id → list of prop_ids in that chunk
        chunk_to_props = defaultdict(list)
        for pid, p in props_by_id.items():
            chunk_to_props[p['source_chunk_id']].append(pid)

        # Need labels.json to know which chain_new pids exist (for rescue purity)
        # Get qa_pair_id from question
        qid = None
        for q in labels_list:
            if normalize_query(q['question']) == nq:
                qid = q['qa_pair_id']
                break
        if not qid:
            continue
        gt = gt_for(qid)
        if not gt:
            continue
        true_chain_new_pids = {p['new_pid'] for p in gt['pairs']}

        rescue_kept = 0
        rescue_with_new = 0
        rescue_unrelated = 0

        for ck in pre_filter:
            psg_pids = chunk_to_props.get(ck, [])
            has_chain_old = any(pid in chain_old_pids for pid in psg_pids)
            if not has_chain_old:
                cats['no_chain_old'] += 1
                continue
            # Has chain_old. Check filter outcome
            if ck in dropped:
                cats['hard_drop'] += 1
            elif ck in kept:
                # rescue happened
                cats['rescue'] += 1
                rescue_kept += 1
                has_true_chain_new = any(pid in true_chain_new_pids for pid in psg_pids)
                if has_true_chain_new:
                    cats['rescue_with_chain_new'] += 1
                    rescue_with_new += 1
                else:
                    cats['rescue_unrelated_current'] += 1
                    rescue_unrelated += 1

        per_q_rescue_purity.append({
            'qid': qid,
            'num_hops': gt['num_hops'],
            'rescue_kept': rescue_kept,
            'rescue_with_new': rescue_with_new,
            'rescue_unrelated': rescue_unrelated,
        })
    return cats, per_q_rescue_purity

rescue_b, purity_b = analyze_rescue(runs['B'], 'B')
rescue_c, purity_c = analyze_rescue(runs['C'], 'C')

print(f"\nAblation B rescue breakdown (across all top-20 passages):")
for k, v in rescue_b.most_common():
    print(f"  {k}: {v}")
total_drop_candidates = rescue_b['hard_drop'] + rescue_b['rescue']
print(f"\nFor passages WITH chain_old (drop candidates: {total_drop_candidates}):")
print(f"  hard_drop:                 {rescue_b['hard_drop']}/{total_drop_candidates} = {100*rescue_b['hard_drop']/max(total_drop_candidates,1):.0f}%")
print(f"  rescue (any chain_current): {rescue_b['rescue']}/{total_drop_candidates} = {100*rescue_b['rescue']/max(total_drop_candidates,1):.0f}%")
print(f"    └─ rescue with real chain_new in passage:  {rescue_b['rescue_with_chain_new']}/{rescue_b['rescue']} = {100*rescue_b['rescue_with_chain_new']/max(rescue_b['rescue'],1):.0f}% (justified)")
print(f"    └─ rescue with unrelated current only:    {rescue_b['rescue_unrelated_current']}/{rescue_b['rescue']} = {100*rescue_b['rescue_unrelated_current']/max(rescue_b['rescue'],1):.0f}% (questionable)")

# Write markdown table
with open(OUT / 'A1_rescue_breakdown.md', 'w') as f:
    f.write("# A1 — Filter Rescue Breakdown\n\n")
    f.write("Categorize top-20 passages containing chain_old props:\n\n")
    f.write("| Category | Count B | % B | Count C | % C |\n|---|---|---|---|---|\n")
    total_b = rescue_b['hard_drop'] + rescue_b['rescue']
    total_c = rescue_c['hard_drop'] + rescue_c['rescue']
    f.write(f"| Hard drop (no chain_current rescue) | {rescue_b['hard_drop']} | {100*rescue_b['hard_drop']/max(total_b,1):.0f}% | {rescue_c['hard_drop']} | {100*rescue_c['hard_drop']/max(total_c,1):.0f}% |\n")
    f.write(f"| Rescued | {rescue_b['rescue']} | {100*rescue_b['rescue']/max(total_b,1):.0f}% | {rescue_c['rescue']} | {100*rescue_c['rescue']/max(total_c,1):.0f}% |\n")
    f.write(f"| └ rescue with chain_new (justified) | {rescue_b['rescue_with_chain_new']} | {100*rescue_b['rescue_with_chain_new']/max(rescue_b['rescue'],1):.0f}% | {rescue_c['rescue_with_chain_new']} | — |\n")
    f.write(f"| └ rescue unrelated current (questionable) | {rescue_b['rescue_unrelated_current']} | {100*rescue_b['rescue_unrelated_current']/max(rescue_b['rescue'],1):.0f}% | {rescue_c['rescue_unrelated_current']} | — |\n")
    f.write(f"\n**Takeaway**: rescue 內有 {100*rescue_b['rescue_unrelated_current']/max(rescue_b['rescue'],1):.0f}% 是「無關 current 觸發」, 這是可以收緊的部分 → P1 候選\n")

# Chart 1
fig, ax = plt.subplots(figsize=(8, 5))
cats_show = ['Hard drop\n(filter works)', 'Rescue\n(w/ chain_new)\njustified', 'Rescue\n(unrelated current)\nquestionable']
vals_b = [rescue_b['hard_drop'], rescue_b['rescue_with_chain_new'], rescue_b['rescue_unrelated_current']]
colors = ['#66bb6a', '#42a5f5', '#ef5350']
bars = ax.bar(cats_show, vals_b, color=colors)
for bar, val in zip(bars, vals_b):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
            f' {val} ({100*val/sum(vals_b):.0f}%)',
            ha='center', va='bottom')
ax.set_ylabel('Top-20 passages containing chain_old')
ax.set_title(f'A1: Filter rescue breakdown (B run, total {sum(vals_b)} drop candidates)')
plt.tight_layout()
plt.savefig(OUT / 'A1_rescue_breakdown.png', dpi=150)
plt.close()

# ============================================================
# Analysis 2: C2.6 — Pool sources contribution
# ============================================================
print("\n=== Analysis 2: Pool sources contribution ===")

# verdict_events.jsonl has 'sources' field listing 'phase1_cache' / 'dynamic_any' / 'gamma' for each focus
source_counter = Counter()
sources_per_event = []
for nq, focus_dict in runs['B']['verdicts'].items():
    for fpid, ev in focus_dict.items():
        sources = ev.get('sources', [])
        sources_per_event.append(sources)
        for s in sources:
            source_counter[s] += 1
        if not sources:
            source_counter['(none)'] += 1

# Each event's source COMBINATION
from collections import Counter as Cnt
combo_counter = Cnt()
for srcs in sources_per_event:
    combo_counter[tuple(sorted(srcs))] += 1

print(f"\nTotal verdict events: {len(sources_per_event)}")
print(f"\nSource appearance per event:")
for s, n in source_counter.most_common():
    print(f"  '{s}': {n} / {len(sources_per_event)} = {100*n/len(sources_per_event):.0f}% events used this source")
print(f"\nSource combinations:")
for combo, n in combo_counter.most_common():
    print(f"  {combo}: {n}")

# Write table
with open(OUT / 'A2_pool_sources.md', 'w') as f:
    f.write("# A2 — Pool Sources Contribution\n\n")
    f.write(f"Total verdict events: {len(sources_per_event)} (across {sum(1 for _ in runs['B']['verdicts'])} queries)\n\n")
    f.write("## Source appearance rate (% events using each source)\n\n")
    f.write("| Source | Events using it | % |\n|---|---|---|\n")
    for s, n in source_counter.most_common():
        f.write(f"| `{s}` | {n} | {100*n/max(len(sources_per_event),1):.0f}% |\n")
    f.write("\n## Source combinations\n\n")
    f.write("| Combination | Events | % |\n|---|---|---|\n")
    for combo, n in combo_counter.most_common():
        combo_str = ' + '.join(combo) if combo else '(empty)'
        f.write(f"| {combo_str} | {n} | {100*n/max(len(sources_per_event),1):.0f}% |\n")

# Chart 2: source appearance bar
fig, ax = plt.subplots(figsize=(8, 5))
src_names = list(source_counter.keys())
src_vals = list(source_counter.values())
src_pct = [100*v/max(len(sources_per_event),1) for v in src_vals]
bars = ax.bar(src_names, src_pct, color=['#42a5f5','#66bb6a','#ffa726','#9e9e9e'][:len(src_names)])
for bar, v, p in zip(bars, src_vals, src_pct):
    ax.text(bar.get_x() + bar.get_width()/2, p, f' {v}\n({p:.0f}%)',
            ha='center', va='bottom')
ax.set_ylabel('% of verdict events using this source')
ax.set_title(f'A2: Pool sources contribution (B run, {len(sources_per_event)} events)')
ax.set_ylim(0, max(src_pct) * 1.15)
plt.tight_layout()
plt.savefig(OUT / 'A2_pool_sources.png', dpi=150)
plt.close()


# ============================================================
# Analysis 3: C2.8 — LLM identify accuracy (conditional on pool co-occurrence)
# ============================================================
print("\n=== Analysis 3: LLM identify conditional accuracy ===")

# For each has_pair hop with pool co-occurrence (both new/old in some focus's pool):
#   Did LLM identify them as contradicting?
# Joint: parse verdict_events.llm_contradicting_pids vs GT pair

llm_stats = Counter()
per_hop_llm_stats = defaultdict(Counter)
for q in labels_list:
    qid = q['qa_pair_id']
    nq = normalize_query(q['question'])
    if nq not in runs['B']['dump'] or runs['B']['dump'][nq].get('phase2_status') != 'RAN':
        continue
    focus_to_event = runs['B']['verdicts'].get(nq, {})

    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair':
            continue
        if not (hop['chain_new_matches'] and hop['chain_old_matches']):
            continue
        new_pid = hop['chain_new_matches'][0]['prop_id']
        old_pid = hop['chain_old_matches'][0]['prop_id']
        n_hop = q['num_hops']

        # Check: focus=new_pid event has old_pid in llm_contradicting_pids?
        # OR focus=old_pid event has new_pid in llm_contradicting_pids?
        ev_new = focus_to_event.get(new_pid)
        ev_old = focus_to_event.get(old_pid)

        # Pool co-occurrence first (precondition for evaluation)
        old_in_new_pool = ev_new and old_pid in ev_new.get('pool_pids', [])
        new_in_old_pool = ev_old and new_pid in ev_old.get('pool_pids', [])
        pool_co = old_in_new_pool or new_in_old_pool

        if not pool_co:
            continue  # condition not met

        # LLM identify: did LLM say "the counterpart is contradicting"?
        old_in_new_llm = ev_new and old_pid in ev_new.get('llm_contradicting_pids', [])
        new_in_old_llm = ev_old and new_pid in ev_old.get('llm_contradicting_pids', [])

        if old_in_new_llm or new_in_old_llm:
            llm_stats['identified_correct'] += 1
            per_hop_llm_stats[n_hop]['identified_correct'] += 1
        else:
            llm_stats['missed'] += 1
            per_hop_llm_stats[n_hop]['missed'] += 1

print(f"\nLLM identify (conditional on pool co-occurrence):")
total = sum(llm_stats.values())
print(f"  identified_correct: {llm_stats['identified_correct']}/{total} = {100*llm_stats['identified_correct']/max(total,1):.0f}%")
print(f"  missed:             {llm_stats['missed']}/{total} = {100*llm_stats['missed']/max(total,1):.0f}%")
print(f"\nBy hop depth:")
for h in sorted(per_hop_llm_stats):
    s = per_hop_llm_stats[h]
    tot = sum(s.values())
    print(f"  {h}-hop: {s['identified_correct']}/{tot} = {100*s['identified_correct']/max(tot,1):.0f}% identified correctly")

# Table
with open(OUT / 'A3_llm_identify_accuracy.md', 'w') as f:
    f.write("# A3 — LLM Identify Accuracy (conditional on pool co-occurrence)\n\n")
    f.write("Among has_pair hops where pool contains BOTH chain_new + chain_old:\n\n")
    f.write("| Bucket | identified | missed | accuracy |\n|---|---|---|---|\n")
    f.write(f"| All hop depths | {llm_stats['identified_correct']} | {llm_stats['missed']} | **{100*llm_stats['identified_correct']/max(total,1):.0f}%** |\n")
    for h in sorted(per_hop_llm_stats):
        s = per_hop_llm_stats[h]
        tot = sum(s.values())
        f.write(f"| {h}-hop | {s['identified_correct']} | {s['missed']} | {100*s['identified_correct']/max(tot,1):.0f}% |\n")

# Chart 3
fig, ax = plt.subplots(figsize=(8, 5))
hops_x = sorted(per_hop_llm_stats)
acc = [100*per_hop_llm_stats[h]['identified_correct']/max(sum(per_hop_llm_stats[h].values()),1)
       for h in hops_x]
counts = [sum(per_hop_llm_stats[h].values()) for h in hops_x]
bars = ax.bar([f'{h}-hop\n(n={n})' for h,n in zip(hops_x, counts)], acc, color='#66bb6a')
for bar, a in zip(bars, acc):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f' {a:.0f}%',
            ha='center', va='bottom')
ax.set_ylabel('LLM identify accuracy (%)')
ax.set_ylim(0, 110)
ax.set_title(f'A3: LLM identify accuracy by hop (conditional on pool co-occurrence)')
ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5)
plt.tight_layout()
plt.savefig(OUT / 'A3_llm_identify_accuracy.png', dpi=150)
plt.close()


# ============================================================
# Analysis 4: Tier 3 Failure root-cause cascade
# ============================================================
print("\n=== Analysis 4: Failure root-cause cascade ===")

# For each wrong query in B, walk cascade F0 → F8
# Use B as canonical (Phase 2 ran). For each query, find first failure stage.

failure_per_q = []
for qid, q in labels_by_qid.items():
    nq = normalize_query(q['question'])
    result = runs['B']['results'].get(qid)
    if not result:
        continue
    is_wrong = not result.get('exact_match', False)
    if not is_wrong:
        continue  # we only analyze wrong ones

    n_hops = q['num_hops']
    dump = runs['B']['dump'].get(nq)
    if not dump or dump.get('phase2_status') != 'RAN':
        # F0: DPR fallback or no Phase 2 run
        failure_per_q.append({'qid': qid, 'num_hops': n_hops, 'stage': 'F0_no_phase2'})
        continue

    # Check has_pair hops
    has_pair_hops = [h for h in q['hops'] if h['conflict_type'] == 'has_pair'
                     and h['chain_new_matches'] and h['chain_old_matches']]
    if not has_pair_hops:
        # No conflict hop — failure is in LLM answering (F7)
        failure_per_q.append({'qid': qid, 'num_hops': n_hops, 'stage': 'F7_llm_answer'})
        continue

    # Walk cascade for each has_pair hop, find first failure
    active_pids = set(dump.get('active_pids', []))
    all_chain_pids = set().union(*[set(c['proposition_ids']) for c in dump['chains']]) if dump['chains'] else set()
    chain_old_pids = set(dump.get('chain_old_pids', []))
    dropped_chunks = set(dump.get('passages_dropped_chunk_ids', []))
    verdicts_q = runs['B']['verdicts'].get(nq, {})

    stage_for_this_q = None
    for hop in has_pair_hops:
        new_pid = hop['chain_new_matches'][0]['prop_id']
        old_pid = hop['chain_old_matches'][0]['prop_id']
        old_chunk = hop['chain_old_matches'][0]['source_chunk_id']

        # F1: neither in active region (use union, not "both same chain")
        if new_pid not in active_pids and old_pid not in active_pids:
            stage_for_this_q = 'F1_neither_in_active'
            break
        # F2: not both in any chain (relaxed: either one missing from union of all chains)
        if new_pid not in all_chain_pids or old_pid not in all_chain_pids:
            stage_for_this_q = 'F2_not_both_in_chains'
            break
        # F3: pool co-occurrence check
        ev_new = verdicts_q.get(new_pid)
        ev_old = verdicts_q.get(old_pid)
        old_in_new_pool = ev_new and old_pid in ev_new.get('pool_pids', [])
        new_in_old_pool = ev_old and new_pid in ev_old.get('pool_pids', [])
        if not (old_in_new_pool or new_in_old_pool):
            stage_for_this_q = 'F3_pool_missing_counterpart'
            break
        # F4: LLM identify
        old_in_new_llm = ev_new and old_pid in ev_new.get('llm_contradicting_pids', [])
        new_in_old_llm = ev_old and new_pid in ev_old.get('llm_contradicting_pids', [])
        if not (old_in_new_llm or new_in_old_llm):
            stage_for_this_q = 'F4_llm_missed_identify'
            break
        # F5: verdict status — chain_old should be 'superseded'
        if old_pid not in chain_old_pids:
            stage_for_this_q = 'F5_verdict_wrong_status'
            break
        # F6: chain_old chunk not dropped
        if old_chunk not in dropped_chunks:
            stage_for_this_q = 'F6_filter_no_drop'
            break

    if stage_for_this_q is None:
        # All hops passed cascade — LLM still answered wrong (F7)
        stage_for_this_q = 'F7_llm_answer_despite_clean_context'

    failure_per_q.append({'qid': qid, 'num_hops': n_hops, 'stage': stage_for_this_q})

# Aggregate
stage_counter = Counter(f['stage'] for f in failure_per_q)
print(f"\nFailure cascade (Ablation B, {len(failure_per_q)} wrong queries):")
for stage, n in stage_counter.most_common():
    print(f"  {stage}: {n}")

# Per hop
per_hop_stage = defaultdict(Counter)
for f in failure_per_q:
    per_hop_stage[f['num_hops']][f['stage']] += 1
print(f"\nFailure cascade by hop:")
for h in sorted(per_hop_stage):
    print(f"  {h}-hop:")
    for stage, n in per_hop_stage[h].most_common():
        print(f"    {stage}: {n}")

with open(OUT / 'A4_failure_cascade.md', 'w') as f:
    f.write("# A4 — Failure Root-Cause Cascade (Ablation B)\n\n")
    f.write(f"Of {len(failure_per_q)} wrong queries, classify each by FIRST cascade stage that fails:\n\n")
    f.write("| Stage | Description | Count | % |\n|---|---|---|---|\n")
    stage_desc = {
        'F0_no_phase2': 'DPR fallback, Phase 2 not run',
        'F1_neither_in_active': 'Both chain_new/old missing from active region',
        'F2_not_both_in_chains': 'One/both not in any top-5 chain',
        'F3_pool_missing_counterpart': 'In chain, but counterpart not in pool',
        'F4_llm_missed_identify': 'In pool, but LLM didn\'t mark contradicting',
        'F5_verdict_wrong_status': 'Identified but verdict didn\'t mark chain_old as superseded',
        'F6_filter_no_drop': 'Verdict correct, but filter didn\'t drop chain_old chunk',
        'F7_llm_answer': 'No conflict hop, LLM answer wrong (other reasons)',
        'F7_llm_answer_despite_clean_context': 'Cascade clean but LLM still answered wrong',
    }
    for stage, n in stage_counter.most_common():
        f.write(f"| `{stage}` | {stage_desc.get(stage,'?')} | {n} | {100*n/max(len(failure_per_q),1):.0f}% |\n")
    f.write("\n## By hop depth\n\n")
    f.write("| Hop | F1 | F2 | F3 | F4 | F5 | F6 | F7 |\n|---|---|---|---|---|---|---|---|\n")
    for h in sorted(per_hop_stage):
        c = per_hop_stage[h]
        f.write(f"| {h}-hop | {c['F1_neither_in_active']} | {c['F2_not_both_in_chains']} | {c['F3_pool_missing_counterpart']} | {c['F4_llm_missed_identify']} | {c['F5_verdict_wrong_status']} | {c['F6_filter_no_drop']} | {c['F7_llm_answer']+c['F7_llm_answer_despite_clean_context']} |\n")

# Chart 4: stacked bar by hop
fig, ax = plt.subplots(figsize=(10, 6))
stages_show = ['F1_neither_in_active', 'F2_not_both_in_chains', 'F3_pool_missing_counterpart',
               'F4_llm_missed_identify', 'F5_verdict_wrong_status', 'F6_filter_no_drop',
               'F7_llm_answer', 'F7_llm_answer_despite_clean_context']
stage_labels = ['F1 not in active', 'F2 not in chains', 'F3 pool missing', 'F4 LLM missed',
                'F5 verdict status', 'F6 no drop', 'F7 LLM wrong', 'F7 clean+wrong']
colors_s = ['#d32f2f', '#f57c00', '#fbc02d', '#7cb342', '#0288d1', '#5e35b1', '#8d6e63', '#616161']
hops_y = sorted(per_hop_stage)
bottom = np.zeros(len(hops_y))
for stage, label, col in zip(stages_show, stage_labels, colors_s):
    vals = [per_hop_stage[h][stage] for h in hops_y]
    ax.bar([f'{h}-hop' for h in hops_y], vals, bottom=bottom, label=label, color=col)
    bottom += np.array(vals)
ax.set_ylabel('Wrong queries')
ax.set_title('A4: Failure cascade stage by hop depth (Ablation B wrong queries)')
ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
plt.tight_layout()
plt.savefig(OUT / 'A4_failure_cascade.png', dpi=150, bbox_inches='tight')
plt.close()


# ============================================================
# Analysis 5: V1 — Cascade attrition by hop bar chart
# ============================================================
print("\n=== Analysis 5: Cascade attrition by hop ===")

# Reuse logic: for B, compute cascade per hop
# Per hop: % active / % in chain / % BOTH-union / % pool co / % verdict correct / % filter dropped
cascade_per_hop = defaultdict(lambda: defaultdict(int))
cascade_total_per_hop = defaultdict(int)

for q in labels_list:
    nq = normalize_query(q['question'])
    if nq not in runs['B']['dump']:
        continue
    dump = runs['B']['dump'][nq]
    if dump.get('phase2_status') != 'RAN':
        continue
    verdicts_q = runs['B']['verdicts'].get(nq, {})
    active_pids = set(dump.get('active_pids', []))
    all_chain_pids = set().union(*[set(c['proposition_ids']) for c in dump['chains']]) if dump['chains'] else set()
    chain_old_pids_dump = set(dump.get('chain_old_pids', []))
    dropped_chunks = set(dump.get('passages_dropped_chunk_ids', []))

    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair':
            continue
        if not (hop['chain_new_matches'] and hop['chain_old_matches']):
            continue
        new_pid = hop['chain_new_matches'][0]['prop_id']
        old_pid = hop['chain_old_matches'][0]['prop_id']
        n_hops = q['num_hops']
        cascade_total_per_hop[n_hops] += 1

        # Both in active region
        if new_pid in active_pids and old_pid in active_pids:
            cascade_per_hop[n_hops]['both_in_active'] += 1
        # Both in some chain (union, NOT same)
        if new_pid in all_chain_pids and old_pid in all_chain_pids:
            cascade_per_hop[n_hops]['both_in_chain_union'] += 1
        # Pool co-occurrence
        ev_new = verdicts_q.get(new_pid)
        ev_old = verdicts_q.get(old_pid)
        if (ev_new and old_pid in ev_new.get('pool_pids', [])) or \
           (ev_old and new_pid in ev_old.get('pool_pids', [])):
            cascade_per_hop[n_hops]['pool_co'] += 1
        # Verdict correct
        if old_pid in chain_old_pids_dump:
            cascade_per_hop[n_hops]['verdict_correct'] += 1
        # Filter dropped chain_old chunk
        old_chunk = hop['chain_old_matches'][0]['source_chunk_id']
        if old_chunk in dropped_chunks:
            cascade_per_hop[n_hops]['filter_dropped'] += 1

print(f"\nCascade attrition (Ablation B, B = filter on; D would be same except filter_dropped=0):")
for h in sorted(cascade_total_per_hop):
    tot = cascade_total_per_hop[h]
    print(f"\n  {h}-hop ({tot} has_pair hops):")
    for stage in ['both_in_active', 'both_in_chain_union', 'pool_co', 'verdict_correct', 'filter_dropped']:
        v = cascade_per_hop[h][stage]
        print(f"    {stage:>25}: {v}/{tot} = {100*v/max(tot,1):.0f}%")

with open(OUT / 'A5_cascade_attrition.md', 'w') as f:
    f.write("# A5 — Cascade Attrition by Hop (Ablation B)\n\n")
    f.write("For each has_pair hop, track how many survive each pipeline stage:\n\n")
    f.write("| Hop | n | Active (both in) | Chain (union) | Pool co | Verdict correct | Filter dropped |\n")
    f.write("|---|---|---|---|---|---|---|\n")
    for h in sorted(cascade_total_per_hop):
        tot = cascade_total_per_hop[h]
        c = cascade_per_hop[h]
        f.write(f"| {h}-hop | {tot} | "
                f"{c['both_in_active']} ({100*c['both_in_active']/max(tot,1):.0f}%) | "
                f"{c['both_in_chain_union']} ({100*c['both_in_chain_union']/max(tot,1):.0f}%) | "
                f"{c['pool_co']} ({100*c['pool_co']/max(tot,1):.0f}%) | "
                f"{c['verdict_correct']} ({100*c['verdict_correct']/max(tot,1):.0f}%) | "
                f"{c['filter_dropped']} ({100*c['filter_dropped']/max(tot,1):.0f}%) |\n")

# Chart 5: Cascade attrition lines per hop
fig, ax = plt.subplots(figsize=(10, 6))
stages_show = ['both_in_active', 'both_in_chain_union', 'pool_co', 'verdict_correct', 'filter_dropped']
stage_labels = ['Both in\nActive Region', 'Both in\nChain Union', 'Pool\nCo-occurrence', 'Verdict\nCorrect', 'Filter\nDropped chain_old']
colors_h = {2: '#42a5f5', 3: '#fb8c00', 4: '#d32f2f'}
x_pos = np.arange(len(stages_show))
width = 0.25
for i, h in enumerate(sorted(cascade_total_per_hop)):
    tot = cascade_total_per_hop[h]
    vals = [100*cascade_per_hop[h][s]/max(tot,1) for s in stages_show]
    bars = ax.bar(x_pos + (i-1)*width, vals, width, label=f'{h}-hop (n={tot})',
                  color=colors_h.get(h, 'gray'))
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f'{v:.0f}',
                ha='center', va='bottom', fontsize=8)
ax.set_xticks(x_pos)
ax.set_xticklabels(stage_labels)
ax.set_ylabel('% of has_pair hops surviving stage')
ax.set_title('A5: Pipeline Cascade Attrition by Hop Depth (Ablation B)')
ax.legend()
ax.set_ylim(0, 110)
plt.tight_layout()
plt.savefig(OUT / 'A5_cascade_attrition.png', dpi=150)
plt.close()


# ─── Summary ───
print(f"\n[done] outputs written to {OUT}/")
print(f"  Tables: A1_rescue_breakdown.md / A2_pool_sources.md / A3_llm_identify_accuracy.md / A4_failure_cascade.md / A5_cascade_attrition.md")
print(f"  Charts: A1_*.png / A2_*.png / A3_*.png / A4_*.png / A5_*.png")
