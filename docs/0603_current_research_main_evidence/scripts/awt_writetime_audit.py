"""
A-WT — Write-time conflict-resolution audit (query-independent).

Answers: at memory-construction time, where does mem0's conflict handling fail?
For each GT conflict pair (old_seq -> gt_seq, gt_seq > old_seq), classify into:

  same-chunk    chunk(old) == chunk(new)  -> old not yet in store when new ingested
                (structural blind spot, excluded from H1/H2 denominator)
  H1-miss       old NOT in new_fact's top-5 candidate pool
                -> LLM never saw the old version -> can only ADD  (hypothesis 1)
  H2-refuse     old IS in candidates but update LLM did NOT UPDATE/DELETE it
                -> saw the conflict, refused to overwrite             (hypothesis 2)
  resolved      old in candidates AND UPDATE/DELETE'd

Alignment (clean thanks to fact-aware chunker):
  - chunk K holds a contiguous seq range; extraction is 1:1 in-order with it,
    so seq -> extracted_text is by position.
  - candidate top5 `text` == stored memory text == extracted text -> EXACT match.
  - update_decision: integer index <-> uuid via id_to_uuid; referenced_ids lists
    the UPDATE/DELETE indices.

Counting: unique context pairs (old_seq, gt_seq), deduped across queries/hops.

Inputs (all already produced by the T5 run):
  --logdir   dir with extraction.jsonl / candidate_pool.jsonl / update_decision.jsonl
  --context  analysis/contexts/factconsolidation_6k_context.txt
  --gt       analysis/results/mh_512_mquake_analysis.json
  --chunk-size  (default 512, must match the run)
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
from utils.eval_other_utils import chunk_facts_by_line


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def build_seq_maps(context_path, chunk_size, extraction):
    """Return seq->chunk_id, seq->extracted_text, and per-chunk seq order."""
    text = Path(context_path).read_text()
    chunks = chunk_facts_by_line(text, chunk_size=chunk_size)
    seq_to_chunk, seq_to_text = {}, {}
    align_warnings = []
    for cid, chunk in enumerate(chunks):
        seqs = [int(m.group(1)) for ln in chunk.split("\n")
                if (m := re.match(r"^(\d+)\.", ln.strip()))]
        ex_facts = extraction[cid]["facts"] if cid < len(extraction) else []
        if len(seqs) != len(ex_facts):
            align_warnings.append(f"chunk{cid}: {len(seqs)} seqs vs {len(ex_facts)} extracted")
        for i, s in enumerate(seqs):
            seq_to_chunk[s] = cid
            if i < len(ex_facts):
                seq_to_text[s] = ex_facts[i]
    return seq_to_chunk, seq_to_text, align_warnings


def collect_pairs(gt):
    """Unique (old_seq, gt_seq) conflict pairs from has_pair hops."""
    pairs = {}
    for q in gt:
        for hop in q.get("hops", []):
            if hop.get("conflict_type") == "has_pair" and hop.get("old_seq") is not None:
                key = (hop["old_seq"], hop["gt_seq"])
                pairs.setdefault(key, {
                    "old_seq": hop["old_seq"], "gt_seq": hop["gt_seq"],
                    "old_fact_text": hop.get("old_fact_text"),
                    "gt_fact_text": hop.get("gt_fact_text"),
                })
    return list(pairs.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logdir", default="docs/0603_current_research_main_evidence/logs/mh_6k")
    ap.add_argument("--context", default="analysis/contexts/factconsolidation_6k_context.txt")
    ap.add_argument("--gt", default="analysis/results/mh_512_mquake_analysis.json")
    ap.add_argument("--chunk-size", type=int, default=512)
    ap.add_argument("--out", default="docs/0603_current_research_main_evidence/logs/mh_6k/awt_result.json")
    args = ap.parse_args()

    extraction = load_jsonl(Path(args.logdir) / "extraction.jsonl")
    candidates = load_jsonl(Path(args.logdir) / "candidate_pool.jsonl")
    updates = load_jsonl(Path(args.logdir) / "update_decision.jsonl")
    gt = json.load(open(args.gt))

    seq_to_chunk, seq_to_text, warns = build_seq_maps(args.context, args.chunk_size, extraction)
    for w in warns:
        print(f"[align WARN] {w}")

    pairs = collect_pairs(gt)
    print(f"[pairs] {len(pairs)} unique GT conflict pairs (has_pair)")

    rows = []
    for p in pairs:
        # Write-time supersession is by INGESTION ORDER, not the MQuAKE gt/old
        # label: facts ingest in seq order, so the larger-seq fact (winner) is
        # ingested later and should supersede the smaller-seq fact (loser).
        winner_seq = max(p["old_seq"], p["gt_seq"])
        loser_seq = min(p["old_seq"], p["gt_seq"])
        c_win, c_lose = seq_to_chunk.get(winner_seq), seq_to_chunk.get(loser_seq)
        row = {**p, "winner_seq": winner_seq, "loser_seq": loser_seq,
               "chunk_winner": c_win, "chunk_loser": c_lose,
               "gt_is_winner": p["gt_seq"] == winner_seq}  # is MQuAKE gt the larger seq?

        if c_win is None or c_lose is None:
            row["bucket"] = "unmapped_seq"
            rows.append(row); continue
        if c_win == c_lose:
            row["bucket"] = "same-chunk"
            rows.append(row); continue

        win_text = seq_to_text.get(winner_seq)
        lose_text = seq_to_text.get(loser_seq)
        # winner is the incoming new fact at its own chunk's add()
        pf = next((x for x in candidates[c_win]["per_fact_candidates"] if x["new_fact"] == win_text), None)
        if pf is None:
            row["bucket"] = "winner_unmatched"  # alignment gap, flag
            rows.append(row); continue

        # H1: is the loser (earlier-ingested) among the winner's top5?
        hit = next((c for c in pf["top5"] if c["text"] == lose_text), None)
        if hit is None:
            row["bucket"] = "H1-miss"
            row["loser_in_top5"] = False
            rows.append(row); continue

        row["loser_in_top5"] = True
        row["loser_rank_in_winner_top5"] = hit["rank"]
        row["loser_score"] = hit["score"]

        # H2: was the loser candidate UPDATE/DELETE'd in winner's update decision?
        upd = updates[c_win]
        uuid2idx = {v: k for k, v in upd["id_to_uuid"].items()}
        idx = uuid2idx.get(hit["id"])
        acted = idx is not None and idx in set(upd["referenced_ids"])
        row["update_idx"] = idx
        row["bucket"] = "resolved" if acted else "H2-refuse"
        rows.append(row)

    # aggregate
    counts = Counter(r["bucket"] for r in rows)
    detectable = [r for r in rows if r["bucket"] in ("H1-miss", "H2-refuse", "resolved")]
    n_det = len(detectable)
    print("\n=== A-WT write-time conflict-resolution audit ===")
    print(f"total pairs: {len(rows)}")
    for b in ["resolved", "H1-miss", "H2-refuse", "same-chunk",
              "unmapped_seq", "winner_unmatched"]:
        n = counts.get(b, 0)
        extra = f"  ({n/n_det*100:.1f}% of detectable)" if b in ("H1-miss", "H2-refuse", "resolved") and n_det else ""
        print(f"  {b:20s}: {n}{extra}")
    print(f"\ndetectable (cross-chunk) denominator: {n_det}")
    if n_det:
        print(f"  write-time conflict resolved rate: {counts.get('resolved',0)/n_det*100:.1f}%")
        print(f"  H1 (candidate-miss) share        : {counts.get('H1-miss',0)/n_det*100:.1f}%")
        print(f"  H2 (update-refuse) share         : {counts.get('H2-refuse',0)/n_det*100:.1f}%")

    # Diagnostic: does MQuAKE's gt answer == the larger-seq (benchmark "newer") fact?
    n_gt_win = sum(1 for r in rows if r.get("gt_is_winner"))
    print(f"\n[diag] pairs where MQuAKE gt == larger seq (benchmark 'newer'): "
          f"{n_gt_win}/{len(rows)} ; gt == smaller seq: {len(rows)-n_gt_win}")
    print("  → if many gt==smaller, mem0's ingestion-order supersession (keep larger seq) "
          "would yield the benchmark-correct answer only for gt==larger pairs.")

    Path(args.out).write_text(json.dumps(
        {"counts": dict(counts), "n_detectable": n_det, "rows": rows},
        ensure_ascii=False, indent=1))
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
