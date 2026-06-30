"""Parse smoke_test_expanded_traces.json (A) traces:
  • per-hop LLM-listed candidates → check coverage of GT/Old fact text
  • per-hop conflict-detected / signal-cited
  • aggregate LLM-side candidate-recall

Also scan (C) HippoRAG Thought blocks for bail-out language patterns.

Output: analysis/results/zep/smoke_traces_quantified.json + .txt summary
"""
import json
import re
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict

BASE = Path('/home/yhchiang/MemoryAgentBench')


def norm(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFKC', s).lower().strip()
    s = re.sub(r'\s+', ' ', s)
    return s.rstrip(' .,;:!?\"\'')


def parse_a_trace(text):
    """Extract per-hop blocks from condition A response.

    Returns list of dicts:
      {hop_idx, candidates: [str], conflict: bool|None, selected: str,
       signal: str, criterion: str}
    """
    if not text:
        return []
    # Split on "Hop N (" boundaries inside Evidence section
    # Find Evidence section
    ev_match = re.search(r'Evidence:?\s*\n', text)
    chain_match = re.search(r'Reasoning chain:|Reasoning Chain:|Final Answer:|^Answer:', text, re.MULTILINE)
    ev_start = ev_match.end() if ev_match else 0
    ev_end = chain_match.start() if chain_match else len(text)
    evidence = text[ev_start:ev_end]

    # Find hop boundaries
    hop_re = re.compile(r'^\s*(?:##\s*)?Hop\s*(\d+)', re.MULTILINE)
    matches = list(hop_re.finditer(evidence))
    hops = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(evidence)
        block = evidence[start:end]
        hop_idx = int(m.group(1))

        # Candidates: lines starting with " - " or "  - "
        cand_lines = re.findall(r'^\s*-\s+(.+?)(?:\n|$)', block, re.MULTILINE)
        # Filter out bullet lines that are just labels (very short or contain placeholder text)
        candidates = [c.strip() for c in cand_lines if len(c.strip()) > 10 and '<' not in c[:5]]

        # Conflict
        conflict_m = re.search(r'Conflict[^:\n]*:\s*(yes|no|none|None|N/A)', block, re.IGNORECASE)
        conflict = None
        if conflict_m:
            v = conflict_m.group(1).lower()
            conflict = (v == 'yes')

        # Selected / Signal / Criterion
        selected_m = re.search(r'Selected\s*:\s*(.+?)(?:\n|$)', block)
        signal_m = re.search(r'Signal\s*used\s*:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)
        criterion_m = re.search(r'Criterion\s*:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)

        hops.append({
            'hop_idx': hop_idx,
            'candidates': candidates,
            'conflict': conflict,
            'selected': selected_m.group(1).strip() if selected_m else '',
            'signal': signal_m.group(1).strip() if signal_m else '',
            'criterion': criterion_m.group(1).strip() if criterion_m else '',
            'block_text': block.strip()[:600],
        })
    return hops


def fact_in_candidates(fact_text, candidates):
    """Check if fact_text appears (substring) in any candidate string."""
    f = norm(fact_text)
    if not f:
        return False
    # Try exact substring or core relation match
    for c in candidates:
        cn = norm(c)
        if f in cn or cn in f:
            return True
        # Strict containment of subject + object word together
        # Heuristic: check if the last 2 words of fact appear in candidate
        f_words = f.split()
        if len(f_words) >= 2:
            tail = ' '.join(f_words[-2:])
            head = ' '.join(f_words[:2])
            if tail in cn and head in cn:
                return True
    return False


def detect_bailout(thought_text):
    """Look for LLM bail-out patterns in HippoRAG (C) Thought block."""
    if not thought_text:
        return False, []
    flags = []
    patterns = [
        r'no specific mention',
        r'no information about',
        r'not mentioned',
        r'not found in',
        r'fall back',
        r'refer to the (earlier|previous|older) fact',
        r'since.*not (mentioned|found|specified)',
        r'I will (refer to|use) the (earlier|previous|older)',
    ]
    for pat in patterns:
        if re.search(pat, thought_text, re.IGNORECASE):
            flags.append(pat)
    return bool(flags), flags


def main():
    traces = json.load(open(BASE / 'analysis/results/zep/smoke_test_expanded_traces.json'))
    mh_ana = {e['query_id']: e for e in
              json.load(open(BASE / 'analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json'))}
    zep_mech = {r['query_id']: r for r in
                json.load(open(BASE / 'analysis/results/zep/mh_zep_mechanism.json'))}

    # ─── Per-trace analysis ────────────────────────────────────────────────
    structured = []
    for r in traces:
        qid = r['qid']
        ana = mh_ana[qid]
        z = zep_mech[qid]
        hp_hops = [h for h in ana['hops'] if h['conflict_type'] == 'has_pair']

        # Parse A traces for both methods
        h_A_hops = parse_a_trace(r['hippo']['A_trace_first']['response'])
        z_A_hops = parse_a_trace(r['zep']['A_trace_first']['response'])

        # Bail-out detection in HippoRAG C Thought
        h_C_resp = r['hippo']['C_original']['response']
        h_bailed, h_bail_flags = detect_bailout(h_C_resp)

        # Per-hop check: did LLM list GT and Old in its candidates?
        # has_pair hops only
        per_hop_metrics = []
        for hop in hp_hops:
            hop_idx = hop['hop_idx']
            gt_text = hop['gt_fact_text']
            old_text = hop['old_fact_text']
            # find LLM's hop block by index
            hippo_a_block = next((b for b in h_A_hops if b['hop_idx'] == hop_idx + 1), None)
            zep_a_block = next((b for b in z_A_hops if b['hop_idx'] == hop_idx + 1), None)

            entry = {
                'hop_idx': hop_idx,
                'gt': gt_text,
                'old': old_text,
                'gt_retrieved_hippo': hop.get('gt_retrieved', False),
                'old_retrieved_hippo': hop.get('old_retrieved', False),
            }
            # Hippo
            if hippo_a_block:
                entry['hippo_listed_gt'] = fact_in_candidates(gt_text, hippo_a_block['candidates'])
                entry['hippo_listed_old'] = fact_in_candidates(old_text, hippo_a_block['candidates'])
                entry['hippo_n_candidates'] = len(hippo_a_block['candidates'])
                entry['hippo_conflict'] = hippo_a_block['conflict']
                entry['hippo_signal'] = hippo_a_block['signal']
            # Zep
            if zep_a_block:
                entry['zep_listed_gt'] = fact_in_candidates(gt_text, zep_a_block['candidates'])
                entry['zep_listed_old'] = fact_in_candidates(old_text, zep_a_block['candidates'])
                entry['zep_n_candidates'] = len(zep_a_block['candidates'])
                entry['zep_conflict'] = zep_a_block['conflict']
                entry['zep_signal'] = zep_a_block['signal']
            per_hop_metrics.append(entry)

        structured.append({
            'qid': qid,
            'gt': r['gt'],
            'n_conflict': r['n_conflict'],
            'orig_zep_em': r['zep_em'],
            'orig_hippo_em': r['hippo_em'],
            'rerun_hippo_C_correct': r['hippo']['C_original']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,'),
            'rerun_hippo_A_correct': r['hippo']['A_trace_first']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,'),
            'rerun_zep_C_correct': r['zep']['C_original']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,'),
            'rerun_zep_A_correct': r['zep']['A_trace_first']['parsed_answer'].lower().strip().rstrip('.,') == r['gt'].lower().strip().rstrip('.,'),
            'hippo_C_bailed_out': h_bailed,
            'hippo_C_bail_flags': h_bail_flags,
            'per_hop_metrics': per_hop_metrics,
            'h_A_hops_count': len(h_A_hops),
            'z_A_hops_count': len(z_A_hops),
        })

    json.dump(structured, open(BASE / 'analysis/results/zep/smoke_traces_quantified.json', 'w'),
              ensure_ascii=False, indent=2)

    # ─── Aggregate metrics ─────────────────────────────────────────────────
    lines = []
    lines.append("=" * 70)
    lines.append(f"Smoke test expanded — {len(structured)} queries")
    lines.append("=" * 70)

    # Hop-level coverage
    h_hops_all = [hop for s in structured for hop in s['per_hop_metrics'] if 'hippo_listed_gt' in hop]
    z_hops_all = [hop for s in structured for hop in s['per_hop_metrics'] if 'zep_listed_gt' in hop]
    n_h = len(h_hops_all)
    n_z = len(z_hops_all)

    lines.append(f"\n=== H1 验证 — LLM-side candidate-recall ===")
    lines.append(f"\nHippoRAG (n={n_h} has_pair hops, all GT retrieved by filter):")
    if n_h:
        h_listed_gt = sum(1 for h in h_hops_all if h['hippo_listed_gt'])
        h_listed_old = sum(1 for h in h_hops_all if h['hippo_listed_old'])
        h_listed_both = sum(1 for h in h_hops_all if h['hippo_listed_gt'] and h['hippo_listed_old'])
        h_listed_neither = sum(1 for h in h_hops_all if not h['hippo_listed_gt'] and not h['hippo_listed_old'])
        h_listed_only_gt = sum(1 for h in h_hops_all if h['hippo_listed_gt'] and not h['hippo_listed_old'])
        h_listed_only_old = sum(1 for h in h_hops_all if not h['hippo_listed_gt'] and h['hippo_listed_old'])
        lines.append(f"  GT listed in candidates:   {h_listed_gt}/{n_h} = {h_listed_gt/n_h*100:.1f}%")
        lines.append(f"  Old listed in candidates:  {h_listed_old}/{n_h} = {h_listed_old/n_h*100:.1f}%")
        lines.append(f"  Both listed:               {h_listed_both}/{n_h} = {h_listed_both/n_h*100:.1f}%")
        lines.append(f"  Only GT:                   {h_listed_only_gt}")
        lines.append(f"  Only Old:                  {h_listed_only_old}")
        lines.append(f"  Neither:                   {h_listed_neither}")
        lines.append(f"  → Retrieval-side: GT 100% (filter); LLM-side: GT only {h_listed_gt/n_h*100:.1f}%")

    lines.append(f"\nZep (n={n_z}):")
    if n_z:
        z_hops_with_old_in_any = [h for h in z_hops_all if zep_mech.get(qid) and any(zh.get('old_in_any') for zh in zep_mech.get(qid, {}).get('hops', []))]
        z_listed_gt = sum(1 for h in z_hops_all if h['zep_listed_gt'])
        z_listed_old = sum(1 for h in z_hops_all if h['zep_listed_old'])
        z_listed_both = sum(1 for h in z_hops_all if h['zep_listed_gt'] and h['zep_listed_old'])
        z_listed_neither = sum(1 for h in z_hops_all if not h['zep_listed_gt'] and not h['zep_listed_old'])
        lines.append(f"  GT listed:    {z_listed_gt}/{n_z} = {z_listed_gt/n_z*100:.1f}%")
        lines.append(f"  Old listed:   {z_listed_old}/{n_z} = {z_listed_old/n_z*100:.1f}%")
        lines.append(f"  Both listed:  {z_listed_both}/{n_z} = {z_listed_both/n_z*100:.1f}%")
        lines.append(f"  Neither:      {z_listed_neither}")

    # Conflict-detected rate
    lines.append(f"\n=== Conflict detection rate (LLM self-report) ===")
    h_conflict_detected = sum(1 for h in h_hops_all if h.get('hippo_conflict'))
    z_conflict_detected = sum(1 for h in z_hops_all if h.get('zep_conflict'))
    lines.append(f"  HippoRAG: {h_conflict_detected}/{n_h} hops self-reported conflict")
    lines.append(f"  Zep:      {z_conflict_detected}/{n_z} hops self-reported conflict")

    # Signal cited distribution
    lines.append(f"\n=== Signal-cited distribution (LLM self-report) ===")
    for label, hops_all, key in [('HippoRAG', h_hops_all, 'hippo_signal'), ('Zep', z_hops_all, 'zep_signal')]:
        sigs = Counter()
        for h in hops_all:
            sig = (h.get(key) or '').lower().strip()
            for keyword in ['serial', 'date', 'none', 'fallback', 'world', 'first', 'newest']:
                if keyword in sig:
                    sigs[keyword] += 1
                    break
            else:
                sigs['other'] += 1
        lines.append(f"  {label}:")
        for k, v in sigs.most_common():
            lines.append(f"    {k}: {v}")

    # H3: bail-out
    lines.append(f"\n=== H3 验证 — HippoRAG (C) Thought 中的 bail-out 語言 ===")
    bailed = sum(1 for s in structured if s['hippo_C_bailed_out'])
    lines.append(f"  Hippo (C) responses with bail-out language: {bailed}/{len(structured)}")
    # cross-tab with EM
    bailed_wrong = sum(1 for s in structured if s['hippo_C_bailed_out'] and not s['rerun_hippo_C_correct'])
    bailed_right = sum(1 for s in structured if s['hippo_C_bailed_out'] and s['rerun_hippo_C_correct'])
    nobail_wrong = sum(1 for s in structured if not s['hippo_C_bailed_out'] and not s['rerun_hippo_C_correct'])
    nobail_right = sum(1 for s in structured if not s['hippo_C_bailed_out'] and s['rerun_hippo_C_correct'])
    lines.append(f"  bailed × wrong:    {bailed_wrong}")
    lines.append(f"  bailed × correct:  {bailed_right}")
    lines.append(f"  no-bail × wrong:   {nobail_wrong}")
    lines.append(f"  no-bail × correct: {nobail_right}")

    # H2: counterfactual GT skipped (qualitative — list cases where GT listed but LLM selects Old)
    lines.append(f"\n=== H2 检查 — LLM listed GT but selected something else (per-hop) ===")
    h2_cases = []
    for s in structured:
        for hop in s['per_hop_metrics']:
            if hop.get('hippo_listed_gt') and hop.get('hippo_listed_old'):
                # We need to check if selected matches GT or Old via the trace; simplification:
                # check if signal indicates use of serial / date for HippoRAG
                pass
    # For simplicity emit count of "LLM listed GT but final answer wrong"
    for label, key in [('Hippo', 'hippo_listed_gt'), ('Zep', 'zep_listed_gt')]:
        listed_but_wrong = 0
        for s in structured:
            correct_key = f'rerun_{label.lower()}_A_correct'
            if not s.get(correct_key):  # answer wrong
                for hop in s['per_hop_metrics']:
                    if hop.get(key):
                        listed_but_wrong += 1
                        break
        lines.append(f"  {label}: 答錯題目中 listed GT in any hop's candidates → {listed_but_wrong}")

    # EM perturbation check
    lines.append(f"\n=== EM perturbation: original vs (C) rerun vs (A) trace-first ===")
    h_orig = sum(1 for s in structured if s['orig_hippo_em'])
    h_C = sum(1 for s in structured if s['rerun_hippo_C_correct'])
    h_A = sum(1 for s in structured if s['rerun_hippo_A_correct'])
    z_orig = sum(1 for s in structured if s['orig_zep_em'])
    z_C = sum(1 for s in structured if s['rerun_zep_C_correct'])
    z_A = sum(1 for s in structured if s['rerun_zep_A_correct'])
    n = len(structured)
    lines.append(f"  HippoRAG: original {h_orig}/{n}, rerun-C {h_C}/{n}, rerun-A {h_A}/{n}")
    lines.append(f"  Zep:      original {z_orig}/{n}, rerun-C {z_C}/{n}, rerun-A {z_A}/{n}")

    out_text = '\n'.join(lines)
    (BASE / 'analysis/results/zep/smoke_traces_quantified.txt').write_text(out_text, encoding='utf-8')
    print(out_text)


if __name__ == '__main__':
    main()
