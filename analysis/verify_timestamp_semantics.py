"""Verify what `timestamp = (chunk_idx, in_chunk_position)` actually means in FC-MH.

Questions:
  Q1. Is a chunk a semantic "input event", or a mechanical 512-token split?
  Q2. For has_pair hops, are chain_old/chain_new ever in the SAME chunk?
      (if yes → chunk_idx alone CANNOT order them → in_chunk_position is needed)
  Q3. Is there a consistent direction (old before/after new) in list order?
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path('/home/yhchiang/MemoryAgentBench')
prop_file = (BASE / 'outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/'
             'chunksize_512/context_id_0/'
             'gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json')
props = {p['id']: p for p in json.load(open(prop_file))['propositions']}

# ─── props per chunk ───
by_chunk = defaultdict(int)
for p in props.values():
    by_chunk[p['timestamp'][0]] += 1
print(f"total props: {len(props)}   num chunks: {len(by_chunk)}")
for c in sorted(by_chunk):
    print(f"  chunk {c}: {by_chunk[c]} props")

# ─── has_pair hop old/new timestamp comparison ───
labels = json.load(open(BASE / 'analysis/results/full100_eval/labels.json'))

same_chunk = diff_chunk = 0
old_lt_new = old_gt_new = old_eq_new = 0          # full timestamp
oc_lt = oc_gt = oc_eq = 0                          # chunk_idx only
examples = []
n_pair = 0

for q in labels:
    for hop in q['hops']:
        if hop['conflict_type'] != 'has_pair':
            continue
        if not (hop['chain_old_matches'] and hop['chain_new_matches']):
            continue
        op = props.get(hop['chain_old_matches'][0]['prop_id'])
        npp = props.get(hop['chain_new_matches'][0]['prop_id'])
        if not op or not npp:
            continue
        n_pair += 1
        ots, nts = tuple(op['timestamp']), tuple(npp['timestamp'])
        if ots[0] == nts[0]:
            same_chunk += 1
        else:
            diff_chunk += 1
        if ots < nts:
            old_lt_new += 1
        elif ots > nts:
            old_gt_new += 1
        else:
            old_eq_new += 1
        if ots[0] < nts[0]:
            oc_lt += 1
        elif ots[0] > nts[0]:
            oc_gt += 1
        else:
            oc_eq += 1
        if len(examples) < 8:
            examples.append((ots, op['text'], nts, npp['text']))

print(f"\n=== has_pair hops: {n_pair} ===")
print(f"old & new SAME chunk:      {same_chunk}")
print(f"old & new DIFFERENT chunk: {diff_chunk}")
print(f"\nFull timestamp (chunk_idx, in_chunk_pos):")
print(f"  old < new (old earlier in list): {old_lt_new}")
print(f"  old > new (old later in list):   {old_gt_new}")
print(f"  old == new:                      {old_eq_new}")
print(f"\nchunk_idx ONLY:")
print(f"  old.chunk < new.chunk: {oc_lt}")
print(f"  old.chunk > new.chunk: {oc_gt}")
print(f"  old.chunk == new.chunk (chunk_idx CANNOT order them): {oc_eq}")

print(f"\n=== sample old/new pairs ===")
for ots, otext, nts, ntext in examples:
    print(f"  OLD ts={ots}: {otext[:75]}")
    print(f"  NEW ts={nts}: {ntext[:75]}")
    print()
