"""
Per-fact operation audit: map EVERY context fact to its ACTUAL write-time
operation, then explain the ideal-vs-actual deviation concretely (not just
counts). Specifically:
  (1) the 16 same-chunk pairs: what op did the world-fact (old) and the
      counterfactual (new) each get? (ideal: both ADD)
  (2) the NONE/dropped facts: which facts, what role, world or counterfactual?
  (3) the DELETE facts: which, what role?

Fact <-> op mapping (Layer A texts == L2 cache texts, both verbatim):
  ADD    memory          -> that fact was added
  UPDATE memory(new)      -> winner fact stored (superseding)
         previous_memory  -> loser fact superseded (it WAS add'd earlier)
  DELETE memory          -> that fact deleted
  (a fact whose text appears in NONE of the above = NONE/dropped = not stored)
"""
import argparse
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--cache", required=True)          # extraction_cache_6k.json
ap.add_argument("--ctx", required=True)
ap.add_argument("--pairs", required=True)          # mh_6k_FULLPAIRS_gt.json
ap.add_argument("--layera", required=True)
ap.add_argument("--chunk-size", type=int, default=512)
args = ap.parse_args()

import sys
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line


def norm(s):
    return s.strip().rstrip(".").lower() if s else ""


# seq -> chunk, and seq -> verbatim context text
chunks = chunk_facts_by_line(Path(args.ctx).read_text(), chunk_size=args.chunk_size)
seq_chunk, seq_ctxtext = {}, {}
for cid, ch in enumerate(chunks):
    for ln in ch.split("\n"):
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", ln.strip())
        if m:
            seq_chunk[int(m.group(1))] = cid
            seq_ctxtext[int(m.group(1))] = m.group(2).strip().rstrip(".")
txt2seq = {norm(t): s for s, t in seq_ctxtext.items()}

# pairs -> role + same-chunk
pairs = json.load(open(args.pairs))
role = {}            # seq -> 'single'|'loser'|'winner'
partner = {}         # seq -> partner seq
samechunk = {}       # seq -> bool
for q in pairs:
    h = q["hops"][0]
    o, g = h["old_seq"], h["gt_seq"]
    lo, wi = min(o, g), max(o, g)   # loser = smaller seq (ingested first); winner = larger
    role[lo] = "loser(world/old)"; role[wi] = "winner(counterfactual/new)"
    partner[lo] = wi; partner[wi] = lo
    sc = seq_chunk.get(lo) == seq_chunk.get(wi)
    samechunk[lo] = samechunk[wi] = sc
for s in seq_ctxtext:
    role.setdefault(s, "single")

# actual op per seq from Layer A
op = {}              # seq -> set of ops touching it
layerA = [json.loads(l) for l in Path(args.layera).read_text().splitlines() if l.strip()]
for ln in layerA:
    for r in ln["vector_results"]["results"]:
        ev = r["event"]
        s = txt2seq.get(norm(r.get("memory", "")))
        if ev == "ADD" and s is not None:
            op.setdefault(s, set()).add("ADD")
        elif ev == "UPDATE":
            if s is not None:
                op.setdefault(s, set()).add("UPDATE-winner")
            ps = txt2seq.get(norm(r.get("previous_memory", "")))
            if ps is not None:
                op.setdefault(ps, set()).add("superseded")
        elif ev == "DELETE" and s is not None:
            op.setdefault(s, set()).add("DELETE")

stored_ops = {"ADD", "UPDATE-winner", "superseded"}
none_dropped = [s for s in seq_ctxtext if not (op.get(s, set()) & stored_ops | (op.get(s, set()) & {"DELETE"}))]
deleted = [s for s in seq_ctxtext if "DELETE" in op.get(s, set())]

print("=== (1) SAME-CHUNK PAIRS (ideal: both ADD) ===")
sc_pairs = sorted({tuple(sorted((s, partner[s]))) for s in samechunk if samechunk[s]})
print(f"  {len(sc_pairs)} same-chunk pairs")
for lo, wi in sc_pairs:
    print(f"  chunk{seq_chunk[lo]}: world(old seq{lo}) op={sorted(op.get(lo,{'NONE'}))}"
          f" | counterfactual(new seq{wi}) op={sorted(op.get(wi,{'NONE'}))}")

print("\n=== (2) NONE/DROPPED facts (not stored) ===")
print(f"  {len(none_dropped)} facts")
for s in sorted(none_dropped):
    print(f"  seq{s} [{role[s]}{' SAME-CHUNK' if samechunk.get(s) else ''}]: {seq_ctxtext[s]!r}")

print("\n=== (3) DELETE facts ===")
print(f"  {len(deleted)} facts")
for s in sorted(deleted):
    print(f"  seq{s} [{role[s]}{' SAME-CHUNK' if samechunk.get(s) else ''}]: {seq_ctxtext[s]!r}")

# --- CLEAN per-fact FINAL FATE partition (mutually exclusive, sums to 455) ---
from collections import Counter
fate = {}
for s in seq_ctxtext:
    ops = op.get(s, set())
    if "DELETE" in ops:
        fate[s] = "DELETED"
    elif "superseded" in ops:
        fate[s] = "SUPERSEDED (loser, slot now holds winner)"
    elif ops & {"ADD", "UPDATE-winner"}:
        fate[s] = "STORED"
    else:
        fate[s] = "DROPPED/NONE (never stored)"
fc = Counter(fate.values())
print("\n=== per-fact FINAL FATE (mutually exclusive, must sum to 455) ===")
tot = 0
for k, v in fc.most_common():
    print(f"  {k:45s}: {v}"); tot += v
print(f"  {'TOTAL':45s}: {tot}")

# deviation = facts NOT in their ideal terminal state (DROPPED + DELETED)
dev = [s for s in seq_ctxtext if fate[s] in ("DROPPED/NONE (never stored)", "DELETED")]
sc_dev = sum(1 for s in dev if samechunk.get(s))
print(f"\n=== deviation (DROPPED + DELETED) ===")
print(f"  total: {len(dev)} = DROPPED {fc['DROPPED/NONE (never stored)']} + DELETED {fc['DELETED']}")
print(f"  same-chunk-involved: {sc_dev} | non-same-chunk: {len(dev)-sc_dev}")

# --- ROLE x FATE cross-tab (the ideal->actual reconciliation) ---
def fine_role(s):
    if role[s] == "single":
        return "single"
    sc = "same" if samechunk.get(s) else "cross"
    return ("loser" if "loser" in role[s] else "winner") + "-" + sc

short = {"STORED": "STORED", "SUPERSEDED (loser, slot now holds winner)": "SUPERSEDED",
         "DROPPED/NONE (never stored)": "DROPPED", "DELETED": "DELETED"}
ideal_fate = {  # ideal terminal fate per fine role
    "single": "STORED", "loser-cross": "SUPERSEDED", "winner-cross": "STORED",
    "loser-same": "STORED", "winner-same": "STORED"}
order = ["single", "loser-cross", "winner-cross", "loser-same", "winner-same"]
cols = ["STORED", "SUPERSEDED", "DROPPED", "DELETED"]
tab = {r: Counter() for r in order}
for s in seq_ctxtext:
    tab[fine_role(s)][short[fate[s]]] += 1
print("\n=== ROLE x FATE (ideal->actual reconciliation) ===")
print(f"  {'role':14s} {'n':>4} | " + " ".join(f"{c:>10}" for c in cols) + "   ideal")
for r in order:
    n = sum(tab[r].values())
    row = " ".join(f"{tab[r][c]:>10}" for c in cols)
    dev_mark = "" if all(tab[r][c] == (n if c == ideal_fate[r] else 0) for c in cols) else "  <-- deviates"
    print(f"  {r:14s} {n:>4} | {row}   {ideal_fate[r]}{dev_mark}")
