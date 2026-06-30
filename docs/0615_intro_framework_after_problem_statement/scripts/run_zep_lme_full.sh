#!/bin/bash
# Zep-on-LongMemEval FULL (78 KU) across 2 Zep accounts, then concat + judge.
#   Usage: bash run_zep_lme_full.sh "<ZEP_KEY_NAME_0> <ZEP_KEY_NAME_1>" <OAI_KEY_NAME>
#     e.g. bash run_zep_lme_full.sh "ZEP_API_KEY_A ZEP_API_KEY_B" OPENAI_API_KEY_A
#   shard i -> ZEP account i (idx%2==i questions). Each shard does ingest->poll->query.
#   Wall-clock dominated by Zep cloud processing of ~39 graphs/account (poll reveals).
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh; conda activate MABench
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a
read -r -a ZK <<< "${1:?need 2 ZEP key names, space-separated}"
OAIK="${2:?need OAI key name}"
N=${#ZK[@]}
SC=docs/0615_intro_framework_after_problem_statement/scripts
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
HYPDIR=docs/0615_intro_framework_after_problem_statement/lme_hyps
JUDGE_PY=/home/yhchiang/origin_longmemeval/LongMemEval/src/evaluation/evaluate_qa.py
DATA=/home/yhchiang/LongMemEval/data/longmemeval_s_cleaned.json
export OPENAI_API_KEY="${!OAIK}"

# cleanup: delete the 2 smoke graphs on account 0 so the full ingest is fresh
# (smoke ingested Q0+Q1 to account 0; full assigns Q1 to account 1 -> Q0's graph
# would otherwise get duplicate episodes on re-add).
echo "[zep-full] cleanup smoke graphs on ${ZK[0]} ($(date))"
ZK0="${ZK[0]}" python - <<'PY' || true
import os, json
from zep_cloud import Zep
c = Zep(api_key=os.environ[os.environ['ZK0']])
for q in [d['question_id'] for d in json.load(open('/home/yhchiang/LongMemEval/data/longmemeval_s_cleaned.json'))
          if d['question_type']=='knowledge-update'][:2]:
    g = f"lme_ku_{q.replace('-','_')}"
    try: c.graph.delete(graph_id=g); print("  deleted", g)
    except Exception as e: print("  skip", g, repr(e)[:60])
PY

echo "[zep-full] launch $N shards ($(date))"
pids=()
for i in $(seq 0 $((N-1))); do
  ZEP_API_KEY="${!ZK[$i]}" OPENAI_API_KEY="${!OAIK}" SHARD=$i NSHARD=$N \
    bash "$SC/run_zep_lme_shard.sh" > "$LOGROOT/zep_lme_s${i}n${N}.log" 2>&1 &
  pids+=($!)
  echo "  shard $i -> ${ZK[$i]} pid=$! log=$LOGROOT/zep_lme_s${i}n${N}.log"
done
fail=0; for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "[zep-full] all shards done (fail=$fail) ($(date))"

FINAL="$HYPDIR/lme_ku_zep.jsonl"
cat "$HYPDIR/lme_ku_zep_s"*"n${N}.jsonl" > "$FINAL" 2>/dev/null
echo "[zep-full] concat -> $FINAL ($(wc -l < "$FINAL" 2>/dev/null) lines)"

JUDGE_MODEL="${JUDGE_MODEL:-gpt-4o-mini}"
echo "[zep-full] judge ($JUDGE_MODEL)"
( cd "$(dirname "$JUDGE_PY")" && python "$(basename "$JUDGE_PY")" "$JUDGE_MODEL" "/home/yhchiang/MemoryAgentBench/$FINAL" "$DATA" ) || echo "[judge] failed"
echo "[zep-full] DONE ($(date))"
