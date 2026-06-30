#!/bin/bash
# Zep-on-LongMemEval, ONE shard end-to-end: ingest -> poll(episode-count stable)
# -> query. Each shard runs on its OWN Zep account (ZEP_API_KEY) so the free-plan
# per-account load is split. Answers use OPENAI_API_KEY (gpt-4o-mini).
#   Env: ZEP_API_KEY, OPENAI_API_KEY, SHARD, NSHARD
#   Usage: ZEP_API_KEY=.. OPENAI_API_KEY=.. SHARD=0 NSHARD=2 bash run_zep_lme_shard.sh
set -u
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
LME_DATA_DIR="${LME_DATA_DIR:-$REPO_ROOT/data/longmemeval}"
export LME_DATA="${LME_DATA:-$LME_DATA_DIR/longmemeval_s_cleaned.json}"
source "$CONDA_SH"; conda activate MABench
cd $REPO_ROOT
DATA=$LME_DATA_DIR/longmemeval_s_cleaned.json
SC=docs/0615_intro_framework_after_problem_statement/scripts
HYPDIR=docs/0615_intro_framework_after_problem_statement/lme_hyps
SHARD="${SHARD:-0}"; NSHARD="${NSHARD:-1}"
HYP="$HYPDIR/lme_ku_zep_s${SHARD}n${NSHARD}.jsonl"; rm -f "$HYP"
mkdir -p "$HYPDIR"

echo "[zep-shard $SHARD/$NSHARD] INGEST ($(date))"
python "$SC/zep_lme_ingest.py" --data "$DATA" --nshard "$NSHARD" --shard "$SHARD"

echo "[zep-shard $SHARD/$NSHARD] POLL until all graphs' episode counts stabilize ($(date))"
SHARD=$SHARD NSHARD=$NSHARD python - <<'PY'
import os, time, json
from zep_cloud import Zep
c = Zep(api_key=os.environ['ZEP_API_KEY'])
S, N = int(os.environ['SHARD']), int(os.environ['NSHARD'])
ku = [d for d in json.load(open(os.environ['LME_DATA']))
      if d['question_type'] == 'knowledge-update']
mine = [d for i, d in enumerate(ku) if i % N == S]
gids = [f"lme_ku_{d['question_id'].replace('-','_')}" for d in mine]

def ep(g):
    try:
        r = c.graph.episode.get_by_graph_id(graph_id=g, lastn=100000)
        return len(r.episodes if hasattr(r, "episodes") else r)
    except Exception:
        return -1

prev, stable = None, 0
for it in range(96):  # up to ~8 hr
    cnts = {g: ep(g) for g in gids}
    tot = sum(v for v in cnts.values() if v > 0)
    nready = sum(1 for v in cnts.values() if v > 0)
    print(f"  {time.strftime('%H:%M:%S')} graphs_with_eps={nready}/{len(gids)} total_eps={tot} stable={stable}", flush=True)
    if cnts == prev and all(v > 0 for v in cnts.values()):
        stable += 1
        if stable >= 2:
            print("  all episode counts stable -> ingestion done; +5min edge-extraction buffer", flush=True)
            time.sleep(300); break
    else:
        stable = 0
    prev = cnts
    time.sleep(300)
PY

echo "[zep-shard $SHARD/$NSHARD] QUERY ($(date))"
python "$SC/zep_lme_query.py" --data "$DATA" --out "$HYP" --nshard "$NSHARD" --shard "$SHARD"
echo "[zep-shard $SHARD/$NSHARD] DONE ($(date))"
