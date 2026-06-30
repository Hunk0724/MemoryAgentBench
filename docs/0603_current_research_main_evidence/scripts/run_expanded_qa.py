"""
Expanded-set QA harness for FC-SH (and LCA).

Faithfully reuses the benchmark's own ingestion, FC query template, agent call
(`AgentWrapper.send_message`), and scoring (`drqa_exact_match_score` etc.), so an
expanded-set run is identical in every respect to the official run EXCEPT the
query set is the expanded GT (every in-store conflict pair) instead of the 100.

Because the on-disk qdrant store is ephemeral (/tmp), we re-ingest the context
once (deterministic: frozen extraction cache + temp0 + minimal thinking), then
answer every expanded question against that store.

Validation mode (--validate-against): run ONLY the official-tagged items and
compare this harness's output to the recorded official run output, item by item.
A high agreement rate proves the harness reproduces the benchmark QA exactly.

Usage (smoke, 6k, official subset, validate):
  MEM0_EXTRACTION_CACHE=analysis/results/extraction_cache_6k.json \
  python run_expanded_qa.py \
    --agent_config configs/.../l2_min.yaml \
    --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml \
    --expanded_gt analysis/results/expanded/sh_6k_EXPANDED_gt.json \
    --limit 15 --official-only \
    --validate-against outputs/.../factconsolidation_sh_6k_*size256*results.json \
    --out docs/.../logs/expanded_smoke_6k.json
"""
import argparse, json, os, sys, time
from pathlib import Path

BASE = "/home/yhchiang/MemoryAgentBench"
sys.path.insert(0, BASE)

import yaml
from agent import AgentWrapper
from initialization import create_agent_and_fetch_data, initialize_and_memorize_agent
from main import generate_agent_save_folder
from utils.templates import get_template
from utils.eval_other_utils import (
    drqa_exact_match_score, substring_exact_match_score, normalize_answer,
)

ap = argparse.ArgumentParser()
ap.add_argument("--agent_config", required=True)
ap.add_argument("--dataset_config", required=True)
ap.add_argument("--expanded_gt", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--limit", type=int, default=0, help="0 = all items")
ap.add_argument("--official-only", action="store_true",
                help="only run items tagged is_official (for validation)")
ap.add_argument("--validate-against", default=None,
                help="official run results.json; compare per-item output (official items)")
ap.add_argument("--store-path", default=None,
                help="persistent qdrant path (overrides the yaml /tmp path so the store "
                     "survives between harness runs). Default: <repo>/analysis/results/"
                     "expanded/stores/<sub_dataset>")
ap.add_argument("--skip-ingest", action="store_true",
                help="reuse an already-ingested persistent store (no re-ingestion)")
args = ap.parse_args()


def load_yaml(p):
    with open(p) as f:
        return yaml.safe_load(f)


agent_config = load_yaml(args.agent_config)
dataset_config = load_yaml(args.dataset_config)

# --- persist qdrant off /tmp so the store survives between harness runs ---
sub = dataset_config["sub_dataset"]
store_path = args.store_path or os.path.join(
    BASE, "analysis/results/expanded/stores", sub)
vs = agent_config.setdefault("mem0_config", {}).setdefault("vector_store", {}).setdefault("config", {})
vs["path"] = store_path
# CRITICAL: mem0's Qdrant.__init__ does shutil.rmtree(path) when on_disk=False
# (the default) — wiping the store on every init. on_disk=True skips that wipe and
# persists vectors to disk so --skip-ingest can reuse the store. Search results are
# identical (on_disk only controls disk-mmap vs RAM, not similarity).
vs["on_disk"] = True
# agent.py appends "__{sub_dataset}" to the qdrant path/collection (per-context isolation)
actual_store = f"{store_path}__{sub.replace('-', '_')}"
print(f"[harness] qdrant store path = {store_path} (actual: {actual_store})", flush=True)

# --- build agent; ingest once unless reusing a persistent store ---
print(f"[harness] cache={os.environ.get('MEM0_EXTRACTION_CACHE')!r}", flush=True)
if args.skip_ingest:
    if not os.path.isdir(actual_store):
        sys.exit(f"[harness] --skip-ingest but store missing: {actual_store}")
    print("[harness] reusing persistent store (no ingestion)", flush=True)
    agent = AgentWrapper(agent_config, dataset_config, load_agent_from="__noexist__")
else:
    _, all_chunks, _ = create_agent_and_fetch_data(agent_config, dataset_config)
    save_folder = generate_agent_save_folder(agent_config, dataset_config, 0)
    if os.path.isdir(save_folder):
        import shutil
        shutil.rmtree(save_folder)
    if os.path.isdir(actual_store):
        import shutil
        shutil.rmtree(actual_store)  # fresh deterministic ingest
    print(f"[harness] ingesting context 0 ({len(all_chunks[0])} chunks)...", flush=True)
    agent = initialize_and_memorize_agent(agent_config, dataset_config, save_folder,
                                          all_chunks[0], 0, len(all_chunks))
print("[harness] ready; answering expanded questions...", flush=True)


def send_with_retry(query, qid, max_retries=8):
    """Wrap send_message with backoff on 429/503 (answer path has no built-in retry)."""
    from google.genai.errors import ClientError, ServerError
    for attempt in range(max_retries):
        try:
            return agent.send_message(query, memorizing=False, query_id=qid, context_id=0)
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            if code not in (429, 503) or attempt == max_retries - 1:
                raise
            delay = min(2 ** attempt * 10, 120)
            print(f"  [retry] {code} on qid={qid} attempt {attempt+1}, sleeping {delay}s", flush=True)
            time.sleep(delay)

# --- FC query template for this agent ---
query_template = get_template(dataset_config["sub_dataset"], "query", agent_config["agent_name"])

# --- optional: official recorded outputs, keyed by normalized question ---
off_by_q = {}
if args.validate_against:
    vfiles = sorted(Path().glob(args.validate_against)) if any(c in args.validate_against for c in "*?[") \
             else [Path(args.validate_against)]
    vd = json.load(open(vfiles[-1]))
    for rec in vd["data"]:
        # rec['query'] is the full templated query; recover the raw question is hard,
        # so key on the templated query text directly.
        off_by_q[rec["query"]] = rec.get("output", "")

items = json.load(open(args.expanded_gt))
if args.official_only:
    items = [it for it in items if it.get("is_official")]
if args.limit:
    items = items[: args.limit]
print(f"[harness] {len(items)} items to answer", flush=True)

rows = []
n_em = n_sub = n_leak = 0
n_val = n_val_match = 0
for i, it in enumerate(items):
    raw_q = it["question"]
    query = query_template.format(question=raw_q)
    out = send_with_retry(query, i)
    output = out["output"] if isinstance(out, dict) else str(out)

    gts = [it["gt_answer"]] + [a for a in it.get("gt_answer_aliases", []) if a]
    em = any(drqa_exact_match_score(output, g) for g in gts)
    sub = any(substring_exact_match_score(output, g) for g in gts)
    em = em or sub  # benchmark sets EM=True on substring match
    leak = substring_exact_match_score(output, it["old_answer"]) if it.get("old_answer") else False
    n_em += em; n_sub += sub; n_leak += leak

    val_match = None
    if args.validate_against and query in off_by_q:
        n_val += 1
        val_match = normalize_answer(output) == normalize_answer(off_by_q[query])
        n_val_match += bool(val_match)

    rows.append({
        "qa_id": it["qa_id"], "question": raw_q, "gt_answer": it["gt_answer"],
        "output": output, "exact_match": em, "substring": sub, "stale_leak": leak,
        "write_time_fate": it.get("write_time_fate"),
        "is_official": it.get("is_official"), "official_recorded": off_by_q.get(query),
        "validate_match": val_match,
    })
    if (i + 1) % 10 == 0:
        print(f"  [{i+1}/{len(items)}] EM={n_em} leak={n_leak}"
              + (f" valMatch={n_val_match}/{n_val}" if args.validate_against else ""), flush=True)

n = len(items)
# break EM / stale-leak down by vanilla-mem0 write-time fate
by_fate = {}
for r in rows:
    f = r.get("write_time_fate") or "n/a"
    b = by_fate.setdefault(f, {"n": 0, "em": 0, "leak": 0})
    b["n"] += 1; b["em"] += bool(r["exact_match"]); b["leak"] += bool(r["stale_leak"])
for f, b in by_fate.items():
    b["EM"] = round(100 * b["em"] / b["n"], 1)
    b["stale_leak_pct"] = round(100 * b["leak"] / b["n"], 1)
summary = {
    "n": n, "EM": round(100 * n_em / n, 1) if n else 0,
    "substring": round(100 * n_sub / n, 1) if n else 0,
    "stale_leak_pct": round(100 * n_leak / n, 1) if n else 0,
    "validate_n": n_val, "validate_agreement": (round(100 * n_val_match / n_val, 1) if n_val else None),
    "by_write_time_fate": by_fate,
}
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
json.dump({"summary": summary, "rows": rows}, open(args.out, "w"), ensure_ascii=False, indent=1)
print("\n=== EXPANDED QA SUMMARY ===")
print(json.dumps(summary, ensure_ascii=False, indent=1))
print(f"written: {args.out}")
