"""Verify the MECHANISM behind vanilla's `neither` failures (esp. D1):
was the OLD version removed by a DELETE event (i.e., LLM chose DELETE
instead of UPDATE when the conflicting new fact arrived), or overwritten
by an UPDATE to unrelated text?

For each conflict-pair query whose vanilla FINAL store is `neither`:
  D0: neither old nor new ever entered the store (pure omission)
  D1: old entered, later removed; new never entered
  D2: new entered, later destroyed
For D1/D2, trace the removal event type (DELETE vs UPDATE-overwrite).

Usage: python neither_mechanism.py <L>
"""
import json, re, sys
from collections import Counter

L = sys.argv[1] if len(sys.argv) > 1 else "6k"
ROOT = "/home/yhchiang/MemoryAgentBench"
AGENT = "Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun"

def norm(s):
    s = (s or "").lower().strip()
    s = re.sub(r'^\s*\d+\.\s*', '', s)
    s = re.sub(r'\s+', ' ', s).rstrip('.').strip()
    return s
def match(a, b):
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a == b or a in b or b in a)

gt = {r["query_id"]: r for r in json.load(open(f"{ROOT}/analysis/results/sh_{L}_RUN_gt.json"))}
CP = [q for q, g in gt.items() if g["conflict_type"] == "has_pair"]

# Replay events keeping full per-id history
retdir = f"{ROOT}/outputs/rag_retrieved/{AGENT}/k_100/factconsolidation_sh_{L}/chunksize_512"
events = []   # (chunk_idx, event, id, text)
for ci, line in enumerate(open(f"{retdir}/ingestion_context_0.jsonl")):
    for ev in json.loads(line).get("vector_results", {}).get("results", []):
        events.append((ci, ev.get("event"), ev.get("id"), ev.get("memory")))

# final store
store = {}
for ci, e, i, t in events:
    if e in ("ADD", "UPDATE") and t is not None: store[i] = t
    elif e == "DELETE": store.pop(i, None)
final_texts = {norm(t) for t in store.values()}

def fate(fact):
    """Did `fact` ever enter the store, and if removed, how?"""
    # ids whose ADD or UPDATE text matched the fact
    holder = {}
    removal = []
    for ci, e, i, t in events:
        if e in ("ADD", "UPDATE") and t is not None and match(t, fact):
            holder[i] = (ci, e)
        elif i in holder:
            if e == "DELETE":
                removal.append((ci, "DELETE")); holder.pop(i)
            elif e == "UPDATE" and t is not None and not match(t, fact):
                removal.append((ci, "UPDATE_overwrite")); holder.pop(i)
    entered = bool(holder) or bool(removal)
    in_final = any(match(t, fact) for t in store.values())
    return entered, in_final, removal

rows = []
cnt = Counter(); rem = Counter()
for q in CP:
    g = gt[q]
    new_in = any(match(t, g["gt_fact_text"]) for t in store.values())
    old_in = any(match(t, g["old_fact_text"]) for t in store.values())
    if new_in or old_in: continue   # only `neither`
    ne, _, nrem = fate(g["gt_fact_text"])
    oe, _, orem = fate(g["old_fact_text"])
    if ne: sub = "D2_new_destroyed"; how = nrem
    elif oe: sub = "D1_old_removed_new_never"; how = orem
    else: sub = "D0_omission"; how = []
    cnt[sub] += 1
    for _, h in how: rem[(sub, h)] += 1
    rows.append((q, sub, [h for _, h in how], g["old_answer"], g["gt_answer"]))

n = sum(cnt.values())
print(f"\nFC-SH {L} vanilla — conflict pairs with FINAL store = neither: n={n}")
for s in ["D0_omission", "D1_old_removed_new_never", "D2_new_destroyed"]:
    print(f"  {s:<26} {cnt[s]}")
print("\nRemoval mechanism (how the entered version left the store):")
for (s, h), c in sorted(rem.items()):
    print(f"  {s:<26} via {h:<18} {c}")
print("\nper-case:")
for q, s, how, oa, ga in sorted(rows, key=lambda x: x[1]):
    print(f"  qid {q:>3} {s:<26} {','.join(how) or '-':<28} old='{oa}' new='{ga}'")
