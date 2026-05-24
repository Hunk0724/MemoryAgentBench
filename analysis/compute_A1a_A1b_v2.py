"""A1a / A1b detection F1 v2 — 修正 v1 兩個 bug:
  1. v1 從 audit JSON 抽 events 但 JSON 只存 20 樣本 → 改從 raw source(history.db / verdict_events)抽
  2. v1 A1b precision 永遠 100%(構造上只 match has_pair) → v2 改用「chain prop 文字 → chain hop」全集 lookup,允許 flag 到 no_pair hop = FP

定義:
  A1a — 所有 invalidation events 為單位
    Precision = correct_events / total_events
    Recall = unique_GT_has_pair_hops_caught / total_GT_has_pair_hops
  A1b — per-query, 限定 chain hops
    對每 query Q 的每個 chain hop h:
      truth = (h is has_pair)
      pred  = (有 event 認為 h 上的某個 prop 被取代)
    TP = truth ∧ pred,FP = ¬truth ∧ pred,FN = truth ∧ ¬pred
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
OUT = BASE / 'analysis/results/paper_narrative'
HISTORY_DB = Path('/home/yhchiang/.mem0/history.db')


def norm(s: str) -> str:
    s = (s or '').strip().lower().rstrip('.,;:!?\"\'').strip()
    for art in ('the ', 'a ', 'an '):
        if s.startswith(art):
            s = s[len(art):]
    s = re.sub(r'\s+', ' ', s)
    return s


def text_match(a: str, b: str) -> bool:
    """Loose: one is substring of the other (after normalization)."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


# ─── 1. labels.json → build chain-hop GT lookup ─────────────────────────
labels = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))
# For each query: list of (hop_idx, conflict_type, canonical_prop_text, chain_old_text, chain_new_text, pids)
chain_hops = defaultdict(list)
# text → list of (qid, hop_idx, role) where role in {'old', 'new', 'canonical'}
text_to_chain_hop = defaultdict(list)
# has_pair hop count
has_pair_total = 0
for q in labels:
    qid_num = int(q['qa_pair_id'].split('_no')[-1])
    for hop in q['hops']:
        h_idx = hop['hop_idx']
        ct = hop['conflict_type']
        old_m = (hop.get('chain_old_matches') or [None])[0]
        new_m = (hop.get('chain_new_matches') or [None])[0]
        if ct == 'has_pair' and old_m and new_m:
            has_pair_total += 1
            ot = norm(old_m['prop_text']); nt = norm(new_m['prop_text'])
            chain_hops[qid_num].append({
                'hop_idx': h_idx, 'conflict_type': 'has_pair',
                'old_text': ot, 'new_text': nt,
                'old_pid': old_m['prop_id'], 'new_pid': new_m['prop_id'],
            })
            text_to_chain_hop[ot].append((qid_num, h_idx, 'old'))
            text_to_chain_hop[nt].append((qid_num, h_idx, 'new'))
        elif new_m:
            canon = norm(new_m['prop_text'])
            chain_hops[qid_num].append({
                'hop_idx': h_idx, 'conflict_type': ct,
                'old_text': None, 'new_text': canon,
                'old_pid': None, 'new_pid': new_m['prop_id'],
            })
            text_to_chain_hop[canon].append((qid_num, h_idx, 'canonical'))

print(f"GT: has_pair hops (labels.json) = {has_pair_total}")
print(f"All chain hops: {sum(len(v) for v in chain_hops.values())}")
print(f"Distinct chain prop texts: {len(text_to_chain_hop)}")


def find_flagged_hops(event_old_text: str, event_new_text: str | None):
    """Given an event(old→new),find chain hops that this event flags.
    A hop is flagged if event_old matches any chain prop text on that hop
    (the event is trying to invalidate something on that hop)。
    Returns dict: (qid, hop_idx) → 'correct' | 'wrong_dir' | 'fp_no_pair' | 'fp_misdir'
    """
    flags = {}
    eo = norm(event_old_text or '')
    en = norm(event_new_text or '')
    if not eo:
        return flags
    # which chain hops does eo touch?
    candidates = set()
    for text, hits in text_to_chain_hop.items():
        if eo in text or text in eo:
            candidates.update(hits)
    for qid, h_idx, role in candidates:
        # find this hop's metadata
        hop = next(h for h in chain_hops[qid] if h['hop_idx'] == h_idx)
        if hop['conflict_type'] == 'has_pair':
            # event_old should match chain_old; check event_new
            if role == 'old' and en:
                # correct direction: event_new should match chain_new
                if (en in hop['new_text']) or (hop['new_text'] in en):
                    flags[(qid, h_idx)] = 'correct'
                    continue
                # wrong direction means event invalidating new instead — but we already match old=eo,
                # so en that doesn't match new is just unmatched
                flags[(qid, h_idx)] = 'partial'  # we know it touched chain_old but new not verified
            elif role == 'new' and en:
                # event_old==chain_new → reverse direction. event_new should match chain_old
                if (en in hop['old_text']) or (hop['old_text'] in en):
                    flags[(qid, h_idx)] = 'wrong_dir'
                    continue
                flags[(qid, h_idx)] = 'partial'
            else:
                flags[(qid, h_idx)] = 'partial'
        else:
            # no_pair hop: event old matches the canonical prop → method falsely thinks it's outdated
            flags[(qid, h_idx)] = 'fp_no_pair'
    return flags


# ─── 2. 抽 events: full from raw source ─────────────────────────────────

def extract_mem0_events_from_db():
    """Pull ALL UPDATE events from history.db in the run window."""
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT old_memory, new_memory, created_at FROM history "
        "WHERE event='UPDATE' AND created_at >= ? ORDER BY created_at",
        ('2026-05-02T07:00:00',)
    ).fetchall()
    return [{'old': r[0], 'new': r[1], 'at': r[2]} for r in rows]


def extract_zep_events_from_audit():
    """Zep events: best we can do offline = audit's 33 saved items
    (20 correct + 7 wrong + 6 FP).Note caveat: full data needs Zep cloud re-pull."""
    a = json.load(open(BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/zep_gemini_mh_invalidation_audit.json'))
    events = []
    for item in a.get('correct_items', []):
        events.append({'old': item.get('edge_fact',''), 'new': item.get('gt_new',''), 'audit_tag': 'correct'})
    for item in a.get('wrong_items', []):
        events.append({'old': item.get('edge_fact',''), 'new': item.get('gt_old',''), 'audit_tag': 'wrong'})
    for item in a.get('false_positive_items', []):
        events.append({'old': item.get('edge_fact',''), 'new': '', 'audit_tag': 'fp'})
    return events, a  # also return the full audit (for A1a published numbers)


def extract_ours_events():
    """從 verdict_events.jsonl 抽 verdict.status == 'superseded' 的事件,
    用 proposition_index 把 pid 轉成文字。"""
    prop_file = (BASE / 'outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/'
                 'chunksize_512/context_id_0/'
                 'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json')
    prop_idx = {p['id']: p for p in json.load(open(prop_file))['propositions']}
    events = []
    with open(BASE / 'monitoring_logs/2026-05-17_182907_ablation_B/verdict_events.jsonl') as f:
        for line in f:
            e = json.loads(line)
            v = e.get('verdict') or {}
            if v.get('status') == 'superseded':
                focus = e['focus_pid']; sup = v.get('superseder_id')
                if sup and focus in prop_idx and sup in prop_idx:
                    events.append({
                        'old': prop_idx[focus]['text'],
                        'new': prop_idx[sup]['text'],
                        'focus_pid': focus, 'superseder_id': sup,
                    })
    return events


# ─── 3. Compute A1a / A1b ───────────────────────────────────────────────
def compute(method, events):
    n_events = len(events)
    # A1a accumulators
    n_correct = 0; n_wrong_dir = 0; n_partial = 0; n_fp_no_pair = 0; n_no_match = 0
    hops_caught = set()      # (qid, h_idx) with correct direction match
    # A1b: per chain hop, was it flagged?
    flagged_hop_status = {}  # (qid, h) → best status among 'correct','wrong_dir','partial','fp_no_pair'

    for ev in events:
        flags = find_flagged_hops(ev['old'], ev['new'])
        if not flags:
            n_no_match += 1
            continue
        # event-level classification: take strongest signal
        statuses = list(flags.values())
        if 'correct' in statuses:
            n_correct += 1
            for k, v in flags.items():
                if v == 'correct': hops_caught.add(k)
        elif 'wrong_dir' in statuses:
            n_wrong_dir += 1
        elif 'fp_no_pair' in statuses:
            n_fp_no_pair += 1
        else:
            n_partial += 1
        # A1b: every chain hop touched by this event gets flagged
        for k, v in flags.items():
            prev = flagged_hop_status.get(k)
            # prefer correct > wrong_dir > partial > fp_no_pair
            order = {'correct': 3, 'wrong_dir': 2, 'partial': 1, 'fp_no_pair': 1}
            if prev is None or order.get(v, 0) > order.get(prev, 0):
                flagged_hop_status[k] = v

    # A1a
    a1a_p = n_correct / n_events if n_events else 0.0
    a1a_r = len(hops_caught) / has_pair_total if has_pair_total else 0.0
    a1a_f1 = 2*a1a_p*a1a_r / (a1a_p+a1a_r) if (a1a_p+a1a_r) else 0.0

    # A1b — per chain hop classification
    tp = fp = fn = tn = 0
    for qid, hops in chain_hops.items():
        for hop in hops:
            key = (qid, hop['hop_idx'])
            is_has_pair = (hop['conflict_type'] == 'has_pair')
            status = flagged_hop_status.get(key)
            flagged = status in ('correct', 'wrong_dir', 'partial')  # touched chain prop
            no_pair_flag = status == 'fp_no_pair'
            if is_has_pair and flagged:
                tp += 1
            elif is_has_pair and not flagged:
                fn += 1
            elif (not is_has_pair) and (flagged or no_pair_flag):
                fp += 1
            else:
                tn += 1
    a1b_p = tp / (tp+fp) if (tp+fp) else 0.0
    a1b_r = tp / (tp+fn) if (tp+fn) else 0.0
    a1b_f1 = 2*a1b_p*a1b_r / (a1b_p+a1b_r) if (a1b_p+a1b_r) else 0.0

    return {
        'method': method,
        'n_events': n_events,
        'n_correct': n_correct, 'n_wrong_dir': n_wrong_dir,
        'n_partial': n_partial, 'n_fp_no_pair': n_fp_no_pair, 'n_no_match': n_no_match,
        'unique_hops_caught': len(hops_caught),
        'a1a_p': a1a_p, 'a1a_r': a1a_r, 'a1a_f1': a1a_f1,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'a1b_p': a1b_p, 'a1b_r': a1b_r, 'a1b_f1': a1b_f1,
        'gap': a1a_f1 - a1b_f1,
    }


# ─── 4. Run all three methods ───────────────────────────────────────────
mem0_events = extract_mem0_events_from_db()
print(f"\nMem0: pulled {len(mem0_events)} UPDATE events from history.db")
zep_events, zep_audit = extract_zep_events_from_audit()
print(f"Zep: audit-saved {len(zep_events)} events (PARTIAL — full set requires cloud re-pull)")
ours_events = extract_ours_events()
print(f"Ours: {len(ours_events)} superseded verdicts")

results = [
    compute('Mem0 customized × Gemini', mem0_events),
    compute('Zep × Gemini (audit-saved partial)', zep_events),
    compute('我們 (B = Phase 2)', ours_events),
]


def pct(x): return f"{100*x:.1f}%"

print(f"\n=== A1a / A1b uniform framework (has_pair denominator = {has_pair_total}) ===\n")
print(f"{'Method':<38} {'#evt':>5} {'A1a-P':>6} {'A1a-R':>6} {'A1a-F1':>7}  "
      f"{'A1b-P':>6} {'A1b-R':>6} {'A1b-F1':>7}  {'Gap':>6}")
for r in results:
    print(f"{r['method']:<38} {r['n_events']:>5} "
          f"{pct(r['a1a_p']):>6} {pct(r['a1a_r']):>6} {pct(r['a1a_f1']):>7}  "
          f"{pct(r['a1b_p']):>6} {pct(r['a1b_r']):>6} {pct(r['a1b_f1']):>7}  "
          f"{pct(r['gap']):>6}")

print(f"\n=== Event-level breakdown ===")
print(f"{'Method':<38} {'#evt':>5} {'correct':>8} {'wrong':>6} {'partial':>8} {'fp_no_pair':>11} {'no_match':>9}")
for r in results:
    print(f"{r['method']:<38} {r['n_events']:>5} "
          f"{r['n_correct']:>8} {r['n_wrong_dir']:>6} {r['n_partial']:>8} "
          f"{r['n_fp_no_pair']:>11} {r['n_no_match']:>9}")

print(f"\n=== A1b TP/FP/FN/TN ===")
print(f"{'Method':<38} {'TP':>5} {'FP':>5} {'FN':>5} {'TN':>5}")
for r in results:
    print(f"{r['method']:<38} {r['tp']:>5} {r['fp']:>5} {r['fn']:>5} {r['tn']:>5}")

# Reference: Zep's full audit (event-level, published)
print(f"\n=== Zep full audit (reference, NOT recomputed) ===")
print(f"  total_invalidations: {zep_audit['total_invalidations_made_by_zep']}, "
      f"correct: {zep_audit['correct']}, wrong: {zep_audit['wrong']}, fp: {zep_audit['false_positive']}")
print(f"  Published P={zep_audit['precision_event_level']:.4f}, "
      f"R={zep_audit['recall_pair_level']:.4f}, F1={zep_audit['f1']:.4f}")

# Markdown
with open(OUT / 'A1a_A1b_detection_v2.md', 'w') as f:
    f.write("# A1a / A1b — Detection F1 v2(統一框架,full raw source)\n\n")
    f.write(f"**Denominator(has_pair)**: {has_pair_total}(labels.json prop-matched)\n\n")
    f.write("**Sources**:\n")
    f.write(f"- Mem0: 從 `~/.mem0/history.db` 抽完整 UPDATE events(since 2026-05-02T07:00:00)\n")
    f.write(f"- Zep: **僅** audit JSON 內存 33 個樣本(20 correct + 7 wrong + 6 FP);**完整 78 events 要重打 Zep API 才能拿**\n")
    f.write(f"- 我們: `monitoring_logs/2026-05-17_182907_ablation_B/verdict_events.jsonl`\n\n")
    f.write("## Results\n\n")
    f.write("| Method | #events | A1a P | A1a R | **A1a F1** | A1b P | A1b R | **A1b F1** | **Gap** |\n")
    f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results:
        f.write(f"| {r['method']} | {r['n_events']} | "
                f"{pct(r['a1a_p'])} | {pct(r['a1a_r'])} | **{pct(r['a1a_f1'])}** | "
                f"{pct(r['a1b_p'])} | {pct(r['a1b_r'])} | **{pct(r['a1b_f1'])}** | "
                f"{pct(r['gap'])} |\n")
    f.write("\n## Event-level breakdown(A1a 分類)\n\n")
    f.write("| Method | #events | correct(對方向 + 對 GT) | wrong-direction | partial(部分對) | fp_no_pair(flag 到 no_pair hop) | no_match(完全 FP) |\n")
    f.write("|---|---:|---:|---:|---:|---:|---:|\n")
    for r in results:
        f.write(f"| {r['method']} | {r['n_events']} | {r['n_correct']} | "
                f"{r['n_wrong_dir']} | {r['n_partial']} | {r['n_fp_no_pair']} | {r['n_no_match']} |\n")
    f.write("\n## A1b TP/FP/FN/TN(per chain hop)\n\n")
    f.write("| Method | TP | FP | FN | TN |\n|---|---:|---:|---:|---:|\n")
    for r in results:
        f.write(f"| {r['method']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['tn']} |\n")
    f.write("\n## Reference — Zep audit 已發表完整數字(non-recomputed)\n\n")
    f.write(f"- Total invalidations: {zep_audit['total_invalidations_made_by_zep']}\n")
    f.write(f"- correct: {zep_audit['correct']}, wrong: {zep_audit['wrong']}, fp: {zep_audit['false_positive']}\n")
    f.write(f"- **Published P={zep_audit['precision_event_level']*100:.1f}%, R={zep_audit['recall_pair_level']*100:.1f}%, F1={zep_audit['f1']*100:.1f}%**\n")
    f.write("- Caveat: 上面 partial 數字嚴重 underestimate(只 33/78 events),真實 Zep A1a F1 ≈ 48.9% 為準\n")

json.dump(results, open(OUT / 'A1a_A1b_detection_v2.json', 'w'), indent=2, default=str)
print(f"\n[wrote] {OUT}/A1a_A1b_detection_v2.md + .json")
