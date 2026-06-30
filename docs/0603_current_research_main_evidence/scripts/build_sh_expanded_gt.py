"""
Build the EXPANDED FC-SH evaluation set for a context length.

Motivation: the official benchmark only queries 100 of the conflict pairs that
are actually in the store (6k=161, 32k=837, 64k=1691, 262k=7236 in-store pairs).
A strong backbone can hide a memory method's conflict-resolution behaviour on
just 100 items. EVERY in-store conflict pair maps 1:1 to a MQuAKE-CF
`requested_rewrite`, which carries a natural-language `question` (verified
identical to the official FC-SH question text, 66/66 at 64k). So we can turn
every in-store pair into a valid single-hop QA item.

Answer convention = LARGEST SERIAL (the benchmark's own stated rule: "newer =
larger serial number"). This is defect-free: it agrees with the official answer
key on all non-defective items and CORRECTS the answer-key defects (e.g. 64k
qid18/20, 32k qid8/9) where the benchmark key contradicts its own rule.

Output schema (list of items), QA-runnable and A-WT-compatible:
  {
    "qa_id", "question", "gt_answer", "gt_answer_aliases",
    "gt_seq", "gt_fact_text", "old_answer", "old_seq", "old_fact_text",
    "conflict_type": "has_pair", "case_id", "is_official", "official_answer",
    "answer_key_defect"   # True when official key != largest-serial
  }
"""
import argparse, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--ctx", required=True)
ap.add_argument("--mquake", default="/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")
ap.add_argument("--official", default=None,
                help="optional run GT (sh_<L>_RUN_gt.json) to tag which items are the official 100")
ap.add_argument("--out", required=True)
args = ap.parse_args()


def norm(s):
    return s.strip().rstrip(".").lower()


# --- context: norm(fact) -> seq ---
ctx = {}
for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", Path(args.ctx).read_text(), re.MULTILINE):
    ctx[norm(m.group(2))] = (int(m.group(1)), m.group(2).strip().rstrip("."))

# --- MQuAKE: enumerate every edit; collect per-fact question + aliases ---
mq = json.load(open(args.mquake))


def alias_lookup(case, cloze, ans_str):
    """Answer aliases that ACTUALLY belong to ans_str.

    Match strictly on answer equality (NOT cloze): a conflicting (subject,relation)
    cloze is shared by the world hop and the edited hop, so a cloze match would
    attach the world-fact aliases to a counterfactual answer (and vice versa) —
    wrongly marking a stale answer as correct. Counterfactual edits usually have
    no single-hop alias entry, so they get just the answer string itself.
    """
    out = {ans_str}
    for key in ("new_single_hops", "single_hops"):
        for h in case.get(key, []):
            if norm(h.get("answer", "")) == norm(ans_str):
                out.update(h.get("answer_alias", []) or [])
    return sorted(out)


seen = {}
for c in mq:
    for rw in c.get("requested_rewrite", []):
        subj, prompt = rw.get("subject", ""), rw.get("prompt", "")
        tn = rw.get("target_new", {}).get("str", "")
        tt = rw.get("target_true", {}).get("str", "")
        q = rw.get("question", "")
        if "{}" not in prompt or not tn or not tt:
            continue
        stem = prompt.format(subj)
        nt, ot = norm(f"{stem} {tn}"), norm(f"{stem} {tt}")
        if nt not in ctx or ot not in ctx:
            continue
        new_seq, new_text = ctx[nt]
        old_seq, old_text = ctx[ot]
        key = (old_seq, new_seq)
        if key in seen:
            continue
        # largest serial wins
        if new_seq > old_seq:
            gt_seq, gt_text, gt_ans = new_seq, new_text, tn
            lo_seq, lo_text, lo_ans = old_seq, old_text, tt
        else:
            gt_seq, gt_text, gt_ans = old_seq, old_text, tt
            lo_seq, lo_text, lo_ans = new_seq, new_text, tn
        cloze = stem
        seen[key] = {
            "qa_id": f"sh_pair_{old_seq}_{new_seq}",
            "question": q,
            "gt_answer": gt_ans,
            "gt_answer_aliases": alias_lookup(c, cloze, gt_ans),
            "gt_seq": gt_seq, "gt_fact_text": gt_text,
            "old_answer": lo_ans, "old_seq": lo_seq, "old_fact_text": lo_text,
            "conflict_type": "has_pair",
            "case_id": c.get("case_id"),
            "target_new": tn, "target_true": tt,
            "is_official": None,             # filled below if --official given
            "official_hf_answer": None,      # the benchmark's HF answer key (official items only)
            "disagrees_with_official": None, # largest-serial != HF key -> reproduces answer-key defects
        }

items = list(seen.values())

# --- tag official-100 membership + cross-check HF answer key (optional) ---
if args.official and Path(args.official).exists():
    off = json.load(open(args.official))
    # map unordered pair -> official HF answer
    off_map = {}
    for g in off:
        if g.get("conflict_type") != "has_pair":
            continue
        if g.get("old_seq") is not None and g.get("gt_seq") is not None:
            off_map[frozenset((g["old_seq"], g["gt_seq"]))] = g.get("gt_answer")
    for it in items:
        k = frozenset((it["old_seq"], it["gt_seq"]))
        if k in off_map:
            it["is_official"] = True
            it["official_hf_answer"] = off_map[k]
            it["disagrees_with_official"] = norm(off_map[k]) != norm(it["gt_answer"])
        else:
            it["is_official"] = False

json.dump(items, open(args.out, "w"), ensure_ascii=False, indent=1)
n_off = sum(1 for it in items if it["is_official"])
n_def = sum(1 for it in items if it.get("disagrees_with_official"))
n_alias = sum(1 for it in items if len(it["gt_answer_aliases"]) > 1)
print(f"context facts={len(ctx)} | expanded SH items={len(items)} | "
      f"official-tagged={n_off} | official HF-key defects reproduced={n_def} | "
      f"with real aliases={n_alias} | written: {args.out}")
