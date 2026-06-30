"""A1a (event-level) + A1b (per-query per-hop) detection F1 — uniform framework
across Mem0(customized × Gemini)/ Zep(× Gemini)/ 我們的方法(ablation B verdict_events).

A1a — Per-ingestion / event-level:
  D_pred = 所有「方法宣稱有衝突」的 events
  TP = event 正向(old→new)匹配到某個 GT (chain_old, chain_new) pair
  Wrong = event 方向反錯
  FP = event 完全沒匹配到任何 GT pair
  Precision = TP / |D_pred|
  Recall = |unique GT pairs caught| / |total has_pair hops|
  F1 = 2PR/(P+R)

A1b — Query-driven / per-chain-hop:
  For each query Q with chain hops H_Q:
    D_truth_Q = chain hops that are has_pair (i.e., have a real GT pair)
    D_pred_Q  = chain hops that some invalidation event matches (correct direction or wrong)
  TP = D_pred ∩ D_truth   FN = D_truth \\ D_pred   FP = D_pred \\ D_truth
  (FP = method flagged a chain hop that is actually no_pair / wrong direction)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/results/paper_narrative'
OUT.mkdir(parents=True, exist_ok=True)


def norm_text(t: str) -> str:
    t = (t or '').strip().lower()
    t = re.sub(r'\s+', ' ', t)
    t = t.rstrip('.').strip()
    return t


# ─── 1. labels.json → build GT lookup ───────────────────────────────────
labels = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))

# (qid, hop_idx) → {chain_old_text, chain_new_text, chain_old_pid, chain_new_pid, conflict_type}
hop_meta: dict[tuple[int, int], dict] = {}
# (norm_old_text, norm_new_text) → list of (qid, hop_idx)
text_pair_to_hops: dict[tuple[str, str], list] = defaultdict(list)
# (old_pid, new_pid) → list of (qid, hop_idx)
pid_pair_to_hops: dict[tuple[str, str], list] = defaultdict(list)
# Also a single-text → list of hops (for Mem0 where event_old may match without exact new)
old_text_to_hops: dict[str, list] = defaultdict(list)

# All chain hops (including no_pair) per query — for A1b FP check
chain_hops_per_query: dict[int, list] = defaultdict(list)
chain_old_text_per_query: dict[int, set] = defaultdict(set)  # texts of chain_old props (or canonical fact)

has_pair_count = 0
no_pair_count = 0
for q in labels:
    qid = q['qa_pair_id']
    qid_num = int(qid.split('_no')[-1]) if '_no' in qid else qid  # match Mem0 audit's qid format
    for hop in q['hops']:
        h_idx = hop['hop_idx']
        ct = hop['conflict_type']
        chain_hops_per_query[qid_num].append((h_idx, ct))
        new_m = (hop.get('chain_new_matches') or [None])[0]
        old_m = (hop.get('chain_old_matches') or [None])[0]
        if ct == 'has_pair' and new_m and old_m:
            has_pair_count += 1
            ot, nt = norm_text(old_m['prop_text']), norm_text(new_m['prop_text'])
            text_pair_to_hops[(ot, nt)].append((qid_num, h_idx))
            pid_pair_to_hops[(old_m['prop_id'], new_m['prop_id'])].append((qid_num, h_idx))
            old_text_to_hops[ot].append((qid_num, h_idx))
            chain_old_text_per_query[qid_num].add(ot)
            hop_meta[(qid_num, h_idx)] = dict(
                conflict_type='has_pair', old_text=ot, new_text=nt,
                old_pid=old_m['prop_id'], new_pid=new_m['prop_id'])
        else:
            no_pair_count += 1
            if new_m:
                hop_meta[(qid_num, h_idx)] = dict(
                    conflict_type=ct, old_text=None, new_text=norm_text(new_m['prop_text']),
                    old_pid=None, new_pid=new_m['prop_id'])

print(f"GT: has_pair hops with prop matches = {has_pair_count}, no_pair = {no_pair_count}")
print(f"Distinct text pairs: {len(text_pair_to_hops)},  distinct pid pairs: {len(pid_pair_to_hops)}")


# ─── 2. 抽 invalidation events per method ───────────────────────────────

def extract_mem0_events():
    """Return list of (predicted_old_text, predicted_new_text, kind) where
    kind ∈ {'correct','wrong','fp','unknown'} (per audit's own labels)."""
    a = json.load(open(BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/mem0_mh_invalidation_audit.json'))
    events = []
    for item in a.get('correct_items', []):
        events.append((norm_text(item['event_old']), norm_text(item['event_new']), 'correct'))
    for item in a.get('wrong_items', []):
        events.append((norm_text(item['event_old']), norm_text(item['event_new']), 'wrong'))
    for item in a.get('false_positive_items', []):
        events.append((norm_text(item['event_old']), norm_text(item['event_new']), 'fp'))
    for item in a.get('unknown_items', []):
        events.append((norm_text(item['event_old']), norm_text(item['event_new']), 'unknown'))
    return events


def extract_zep_events():
    """Zep's items have edge_fact text + invalid_at. Treat edge_fact as event_old."""
    a = json.load(open(BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/zep_gemini_mh_invalidation_audit.json'))
    events = []
    for item in a.get('correct_items', []):
        events.append((norm_text(item.get('edge_fact','')), norm_text(item.get('gt_new','')), 'correct'))
    for item in a.get('wrong_items', []):
        events.append((norm_text(item.get('edge_fact','')), norm_text(item.get('gt_new','')), 'wrong'))
    for item in a.get('false_positive_items', []):
        events.append((norm_text(item.get('edge_fact','')), '', 'fp'))
    for item in a.get('unknown_items', []):
        events.append((norm_text(item.get('edge_fact','')), '', 'unknown'))
    return events


def extract_ours_events():
    """Read verdict_events.jsonl, take events where verdict.status == 'superseded'.
    Each such event = (focus_pid, superseder_id) i.e. focus was determined outdated.
    Returns list of (predicted_old_pid, predicted_new_pid, query_qid_num)."""
    events = []
    # We'll also need query→qid mapping from results.json
    r = json.load(open(BASE / 'monitoring_logs/2026-05-17_182907_ablation_B/results.json'))
    query_to_qidnum = {}
    for rec in r['data']:
        qpid = rec.get('qa_pair_id', '')
        if '_no' in qpid:
            qnum = int(qpid.split('_no')[-1])
            query_to_qidnum[rec['query'].strip()] = qnum

    with open(BASE / 'monitoring_logs/2026-05-17_182907_ablation_B/verdict_events.jsonl') as f:
        for line in f:
            e = json.loads(line)
            verdict = e.get('verdict') or {}
            if verdict.get('status') == 'superseded':
                superseder = verdict.get('superseder_id')
                if superseder:
                    qnum = query_to_qidnum.get(e['query'].strip())
                    events.append((e['focus_pid'], superseder, qnum))
    return events


# ─── 3. Match events → (qid, hop) ───────────────────────────────────────
def match_events_to_hops(events, by_pid: bool):
    """Returns:
      - hop_caught: set of (qid, hop) where event matched GT pair (correct direction)
      - hop_flagged: set of (qid, hop) where method flagged this chain hop (any direction)
      - event_tags: list of per-event tag ∈ {'correct','wrong_dir','fp','no_match'}
    """
    hop_caught = set()
    hop_flagged = set()
    event_tags = []
    for ev in events:
        if by_pid:
            old_pid, new_pid, _qnum = ev
            # check exact pid pair (correct direction)
            if (old_pid, new_pid) in pid_pair_to_hops:
                hits = pid_pair_to_hops[(old_pid, new_pid)]
                hop_caught.update(hits)
                hop_flagged.update(hits)
                event_tags.append('correct')
            # check reverse (wrong direction)
            elif (new_pid, old_pid) in pid_pair_to_hops:
                hits = pid_pair_to_hops[(new_pid, old_pid)]
                hop_flagged.update(hits)
                event_tags.append('wrong_dir')
            else:
                # check if old_pid is some chain_new (method invalidated a current fact)
                # → would be FP on that chain hop
                event_tags.append('no_match')
        else:
            old_t, new_t, _kind = ev
            # exact pair match
            if (old_t, new_t) in text_pair_to_hops:
                hits = text_pair_to_hops[(old_t, new_t)]
                hop_caught.update(hits)
                hop_flagged.update(hits)
                event_tags.append('correct')
            elif (new_t, old_t) in text_pair_to_hops:
                hits = text_pair_to_hops[(new_t, old_t)]
                hop_flagged.update(hits)
                event_tags.append('wrong_dir')
            else:
                # match only by old_text (matches some chain_old without verifying new_text)
                # → still counts as flagging that chain hop (we don't know direction reliably)
                if old_t in old_text_to_hops:
                    hits = old_text_to_hops[old_t]
                    hop_flagged.update(hits)
                    event_tags.append('partial')
                else:
                    event_tags.append('no_match')
    return hop_caught, hop_flagged, event_tags


# ─── 4. Compute A1a / A1b ───────────────────────────────────────────────
def compute_metrics(method_name, events, by_pid):
    n_events = len(events)
    hop_caught, hop_flagged, tags = match_events_to_hops(events, by_pid)
    n_correct = sum(1 for t in tags if t == 'correct')
    n_wrong = sum(1 for t in tags if t == 'wrong_dir')
    n_partial = sum(1 for t in tags if t == 'partial')
    n_no_match = sum(1 for t in tags if t == 'no_match')

    # A1a
    a1a_p = n_correct / n_events if n_events else 0.0
    a1a_r = len(hop_caught) / has_pair_count if has_pair_count else 0.0
    a1a_f1 = 2*a1a_p*a1a_r / (a1a_p+a1a_r) if (a1a_p+a1a_r) else 0.0

    # A1b: per-query, restricted to chain hops
    tp = fp = fn = 0
    for qid, chain_hops in chain_hops_per_query.items():
        truth_hops = {(qid, h) for h, ct in chain_hops if ct == 'has_pair'}
        # pred = flagged hops on THIS chain
        pred_hops = {(qid, h) for (qid_e, h) in hop_flagged if qid_e == qid and (qid, h) in {(qid, hh) for hh, _ in chain_hops}}
        tp_q = len(pred_hops & truth_hops)
        fn_q = len(truth_hops - pred_hops)
        fp_q = len(pred_hops - truth_hops)
        tp += tp_q; fn += fn_q; fp += fp_q
    a1b_p = tp / (tp+fp) if (tp+fp) else 0.0
    a1b_r = tp / (tp+fn) if (tp+fn) else 0.0
    a1b_f1 = 2*a1b_p*a1b_r / (a1b_p+a1b_r) if (a1b_p+a1b_r) else 0.0

    return {
        'method': method_name,
        'n_events': n_events,
        'n_correct_events': n_correct,
        'n_wrong_dir': n_wrong,
        'n_partial_match': n_partial,
        'n_no_match': n_no_match,
        'unique_hops_caught': len(hop_caught),
        'unique_hops_flagged': len(hop_flagged),
        'a1a_precision': a1a_p,
        'a1a_recall': a1a_r,
        'a1a_f1': a1a_f1,
        'a1b_tp': tp, 'a1b_fp': fp, 'a1b_fn': fn,
        'a1b_precision': a1b_p,
        'a1b_recall': a1b_r,
        'a1b_f1': a1b_f1,
    }


methods = {
    'Mem0 customized × Gemini': (extract_mem0_events(), False),
    'Zep × Gemini':              (extract_zep_events(), False),
    '我們 (B = Phase 2)':         (extract_ours_events(), True),
}
all_results = []
for name, (events, by_pid) in methods.items():
    r = compute_metrics(name, events, by_pid)
    all_results.append(r)


def pct(x): return f"{100*x:.1f}%"

# ─── 5. Report ──────────────────────────────────────────────────────────
print(f"\n=== Uniform A1a/A1b detection metrics (has_pair denominator = {has_pair_count}) ===\n")
print(f"{'Method':<28} {'#evt':>6} {'#corr':>6} {'#wrong':>6} {'#fp/nm':>7} "
      f"{'A1a P':>7} {'A1a R':>7} {'A1a F1':>8}  "
      f"{'A1b P':>7} {'A1b R':>7} {'A1b F1':>8}  {'Gap':>6}")
for r in all_results:
    gap = r['a1a_f1'] - r['a1b_f1']
    fp_or_nm = r['n_no_match']
    print(f"{r['method']:<28} {r['n_events']:>6} {r['n_correct_events']:>6} "
          f"{r['n_wrong_dir']:>6} {fp_or_nm:>7}  "
          f"{pct(r['a1a_precision']):>7} {pct(r['a1a_recall']):>7} {pct(r['a1a_f1']):>8}  "
          f"{pct(r['a1b_precision']):>7} {pct(r['a1b_recall']):>7} {pct(r['a1b_f1']):>8}  "
          f"{pct(gap):>6}")

# Markdown
with open(OUT / 'A1a_A1b_detection_uniform.md', 'w') as f:
    f.write("# A1a / A1b — Detection F1(統一框架)\n\n")
    f.write(f"**denominator**: has_pair hops with prop-matches = **{has_pair_count}**(labels.json)\n\n")
    f.write("**A1a**(event-level): 所有 invalidation events 為單位;Precision = 正向 correct events / 總 events;Recall = unique GT pairs caught / has_pair 總數\n\n")
    f.write("**A1b**(per-query, per-chain-hop): 對每 query 的每 chain hop, 看方法有沒有 flag 該 hop(無論方向);TP=flag 到 has_pair hop, FN=漏掉的 has_pair hop, FP=flag 到 no_pair hop\n\n")
    f.write("## Results\n\n")
    f.write("| Method | #events | A1a P | A1a R | **A1a F1** | A1b P | A1b R | **A1b F1** | **Gap (A1a−A1b)** |\n")
    f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in all_results:
        gap = r['a1a_f1'] - r['a1b_f1']
        f.write(f"| {r['method']} | {r['n_events']} | {pct(r['a1a_precision'])} | {pct(r['a1a_recall'])} | "
                f"**{pct(r['a1a_f1'])}** | {pct(r['a1b_precision'])} | {pct(r['a1b_recall'])} | "
                f"**{pct(r['a1b_f1'])}** | {pct(gap)} |\n")
    f.write("\n## Event breakdown (A1a 內部分類)\n\n")
    f.write("| Method | #events | correct(對方向 + 對 GT pair) | wrong-direction | partial(只對 old 文字) | no-match(完全 FP) |\n")
    f.write("|---|---:|---:|---:|---:|---:|\n")
    for r in all_results:
        f.write(f"| {r['method']} | {r['n_events']} | {r['n_correct_events']} | "
                f"{r['n_wrong_dir']} | {r['n_partial_match']} | {r['n_no_match']} |\n")
    f.write("\n## A1b TP/FP/FN\n\n")
    f.write("| Method | TP | FP | FN |\n|---|---:|---:|---:|\n")
    for r in all_results:
        f.write(f"| {r['method']} | {r['a1b_tp']} | {r['a1b_fp']} | {r['a1b_fn']} |\n")

json.dump(all_results, open(OUT / 'A1a_A1b_detection_uniform.json', 'w'), indent=2)
print(f"\n[wrote] {OUT}/A1a_A1b_detection_uniform.md + .json")
