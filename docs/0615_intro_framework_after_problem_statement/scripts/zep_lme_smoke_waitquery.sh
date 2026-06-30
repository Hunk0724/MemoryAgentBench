#!/bin/bash
# Zep-on-LongMemEval SMOKE phase 2+3: wait for the 2 ingested graphs to finish
# Zep cloud processing (poll edges), then query + official judge (gpt-4o-mini).
# Uses ZEP_API_KEY_A (the account that ingested) + OPENAI_API_KEY_A for answers.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh; conda activate MABench
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a
export ZEP_API_KEY="${ZEP_API_KEY_A:?need ZEP_API_KEY_A}"
export OPENAI_API_KEY="${OPENAI_API_KEY_A:?need OPENAI_API_KEY_A}"
DATA=/home/yhchiang/LongMemEval/data/longmemeval_s_cleaned.json
HYP=docs/0615_intro_framework_after_problem_statement/lme_hyps/lme_ku_zep_smoke2.jsonl
JUDGE_PY=/home/yhchiang/origin_longmemeval/LongMemEval/src/evaluation/evaluate_qa.py
rm -f "$HYP"

echo "[zep-smoke] polling 2 graphs until EPISODE count stabilizes (ingestion done) ($(date))"
python - <<'PY'
import os, time, json
from zep_cloud import Zep
c = Zep(api_key=os.environ['ZEP_API_KEY'])
ku = [d for d in json.load(open('/home/yhchiang/LongMemEval/data/longmemeval_s_cleaned.json'))
      if d['question_type'] == 'knowledge-update'][:2]
gids = [f"lme_ku_{d['question_id'].replace('-','_')}" for d in ku]

def ep_count(g):
    try:
        r = c.graph.episode.get_by_graph_id(graph_id=g, lastn=100000)
        return len(r.episodes if hasattr(r, "episodes") else r)
    except Exception:
        return -1

prev, stable = None, 0
for it in range(36):  # up to ~3 hr
    cnts = {g: ep_count(g) for g in gids}
    print(f"  {time.strftime('%H:%M:%S')} episodes={list(cnts.values())} stable={stable}", flush=True)
    if cnts == prev and all(v > 0 for v in cnts.values()):
        stable += 1
        if stable >= 2:  # unchanged for 2 consecutive checks (~10 min) -> ingestion done
            print("  episode count stable -> ingestion done; +5min buffer for edge extraction", flush=True)
            time.sleep(300)
            break
    else:
        stable = 0
    prev = cnts
    time.sleep(300)
PY

echo "[zep-smoke] querying 2 questions ($(date))"
python docs/0615_intro_framework_after_problem_statement/scripts/zep_lme_query.py \
  --data "$DATA" --out "$HYP" --nshard 1 --shard 0 --limit 2

echo "[zep-smoke] official judge (gpt-4o-mini)"
HYP_ABS="/home/yhchiang/MemoryAgentBench/$HYP"
( cd "$(dirname "$JUDGE_PY")" && python "$(basename "$JUDGE_PY")" gpt-4o-mini "$HYP_ABS" "$DATA" )
echo "[zep-smoke] DONE ($(date))"
