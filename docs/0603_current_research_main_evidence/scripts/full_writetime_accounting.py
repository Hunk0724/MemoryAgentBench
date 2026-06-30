"""
Complete write-time accounting for the FC-MH 6k run.

Partitions the ENTIRE 455-fact context by fate, so no claim rests on the
queried-pairs subset alone. Answers:
  - context composition: conflict-pair facts vs non-pair (single) facts
  - extraction: how many of 455 reached the store (missing) / paraphrase 1:1
  - operations (Layer A, applied): ADD / UPDATE / DELETE / (NONE-or-dropped)
  - operation CORRECTNESS:
      * UPDATE that supersedes a conflict-loser  -> correct
      * UPDATE on a non-pair (single) fact       -> over-fire (wrong)
      * UPDATE prev==new                          -> no-op (wasted)
      * single facts that got only ADD            -> correct
  - conflict-pair resolution (links to A-WT)

Authoritative conflict pairs = union of sh+mh MQuAKE analysis (sh ⊆ mh here).
seq<->memory-text bridge = extraction 1:1 in-order position (validated:
per-chunk fact count == chunk seq-range size, and A-WT matched 165 pairs with
0 unmatched). mem0 paraphrases text but uses that text consistently in
candidate/update/Layer-A logs, so text is a stable key within mem0's space.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line

BASE = Path("/home/yhchiang/MemoryAgentBench")

_ap = argparse.ArgumentParser()
_ap.add_argument("--ctx", default=str(BASE / "analysis/contexts/factconsolidation_6k_context.txt"))
_ap.add_argument("--logdir", default=str(BASE / "docs/0603_current_research_main_evidence/logs/mh_6k"))
_ap.add_argument("--layera", default=str(BASE / (
    "outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_factaware"
    "/k_100/factconsolidation_mh_6k/chunksize_512/ingestion_context_0.jsonl")))
_ap.add_argument("--mh", default=str(BASE / "analysis/results/mh_512_mquake_analysis.json"))
_ap.add_argument("--sh", default=str(BASE / "analysis/results/sh_512_mquake_analysis.json"))
_ap.add_argument("--chunk-size", type=int, default=512)
_args = _ap.parse_args()

CTX = Path(_args.ctx)
LOGDIR = Path(_args.logdir)
LAYERA = Path(_args.layera)
MH = Path(_args.mh)
SH = Path(_args.sh)
CHUNK_SIZE = _args.chunk_size


def parse_context():
    facts = {}
    for ln in CTX.read_text().split("\n"):
        m = re.match(r"^(\d+)\.\s+(.*)$", ln.strip())
        if m:
            facts[int(m.group(1))] = m.group(2).strip().rstrip(".")
    return facts


def auth_pairs():
    pairs = set()
    for q in json.load(open(MH)):
        for h in q.get("hops", []):
            if h.get("conflict_type") == "has_pair" and h.get("old_seq") is not None:
                pairs.add((h["old_seq"], h["gt_seq"]))
    if SH.exists():  # sh is 6k-specific and ⊆ mh; skip gracefully for 32k
        try:
            for q in json.load(open(SH)):
                if q.get("conflict_type") == "has_pair" and q.get("old_seq") is not None:
                    pairs.add((q["old_seq"], q["gt_seq"]))
        except Exception:
            pass
    return pairs


def seq_to_extracted(extraction):
    """seq -> mem0 extracted (paraphrased) text, by 1:1 in-order chunk position."""
    chunks = chunk_facts_by_line(CTX.read_text(), chunk_size=CHUNK_SIZE)
    seq2text, mism = {}, []
    for cid, chunk in enumerate(chunks):
        seqs = [int(m.group(1)) for ln in chunk.split("\n")
                if (m := re.match(r"^(\d+)\.", ln.strip()))]
        ex = extraction[cid]["facts"]
        if len(seqs) != len(ex):
            mism.append((cid, len(seqs), len(ex)))
        for i, s in enumerate(seqs):
            if i < len(ex):
                seq2text[s] = ex[i]
    return seq2text, mism


def main():
    facts = parse_context()
    pairs = auth_pairs()
    extraction = [json.loads(l) for l in (LOGDIR / "extraction.jsonl").read_text().splitlines() if l.strip()]
    layerA = [json.loads(l) for l in LAYERA.read_text().splitlines() if l.strip()]

    seq2text, mism = seq_to_extracted(extraction)
    text2seq = {t: s for s, t in seq2text.items()}

    # roles
    conflict_seqs = set(x for p in pairs for x in p)
    loser_seqs = set(min(p) for p in pairs)
    winner_seqs = set(max(p) for p in pairs)
    single_seqs = set(facts) - conflict_seqs
    # winner->loser map (a winner may supersede multiple losers across chains)
    win2los = defaultdict(set)
    for o, g in pairs:
        win2los[max(o, g)].add(min(o, g))

    print("=" * 60)
    print("1) CONTEXT COMPOSITION")
    print(f"  total facts            : {len(facts)}")
    print(f"  authoritative pairs    : {len(pairs)}  (sh⊆mh)")
    print(f"  conflict-involved seqs : {len(conflict_seqs)}")
    print(f"    - distinct losers     : {len(loser_seqs)}")
    print(f"    - distinct winners    : {len(winner_seqs)}")
    print(f"  non-pair (single) seqs : {len(single_seqs)}")

    print("\n2) EXTRACTION (write-time recall)")
    n_ext = sum(e["n_facts"] for e in extraction)
    print(f"  total extracted facts  : {n_ext}")
    print(f"  per-chunk count mismatch vs seq-range: {mism if mism else 'none (1:1)'}")
    print(f"  seqs with an extracted text: {len(seq2text)}/{len(facts)}"
          f"  (missing: {len(facts)-len(seq2text)})")

    print("\n3) OPERATIONS (Layer A, applied)")
    ev = Counter()
    updates = []  # (prev, new)
    for ln in layerA:
        for r in ln["vector_results"]["results"]:
            ev[r["event"]] += 1
            if r["event"] == "UPDATE":
                updates.append((r.get("previous_memory"), r.get("memory")))
    print(f"  applied events: {dict(ev)}")
    applied = ev["ADD"] + ev["UPDATE"] + ev.get("DELETE", 0)
    print(f"  extracted {n_ext} -> applied {applied}  (NONE/dropped: {n_ext-applied})")

    print("\n4) UPDATE CORRECTNESS  (n={})".format(len(updates)))
    cat = Counter()
    over_fire = []
    for prev, new in updates:
        if prev == new:
            cat["no-op (prev==new)"] += 1; continue
        ps = text2seq.get(prev)            # superseded fact's seq
        ns = text2seq.get(new)             # new content's seq
        if ps is None:
            cat["prev_unmatched"] += 1; continue
        if ps in single_seqs:
            cat["OVER-FIRE on single"] += 1
            over_fire.append((ps, prev, new)); continue
        # correct iff superseding a loser with its winner partner's content
        if ps in loser_seqs and (ns is None or ns in [w for w, ls in win2los.items() if ps in ls] or ns in winner_seqs):
            cat["correct supersession"] += 1
        elif ps in loser_seqs:
            cat["loser superseded (content seq odd)"] += 1
        elif ps in winner_seqs:
            cat["WRONG-DIR (superseded a winner)"] += 1
        else:
            cat["other"] += 1
    for k, v in cat.most_common():
        print(f"    {k:35s}: {v}")
    for ps, prev, new in over_fire[:6]:
        print(f"      [over-fire] single seq{ps}: {prev!r} -> {new!r}")

    print("\n5) SINGLE-FACT FATE  (should be pure ADD)")
    # which single seqs were touched by an UPDATE as the superseded prev?
    touched = set()
    for prev, new in updates:
        s = text2seq.get(prev)
        if s in single_seqs and prev != new:
            touched.add(s)
    print(f"  single seqs superseded by an UPDATE (over-fire): {len(touched)}")
    print(f"  single seqs left intact (expected ADD path)    : {len(single_seqs)-len(touched)}")

    print("\n6) CONFLICT-PAIR RESOLUTION (from A-WT)")
    awt = json.load(open(LOGDIR / "awt_result.json"))
    print(f"  {awt['counts']}  | detectable={awt['n_detectable']}")


if __name__ == "__main__":
    main()
