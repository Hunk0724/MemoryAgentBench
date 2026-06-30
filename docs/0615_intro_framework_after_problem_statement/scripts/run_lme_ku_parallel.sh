#!/bin/bash
# Orchestrate a SHARDED LongMemEval-KU full run (78 KU) across N OpenAI keys,
# then concat shard hyps and judge once.
#   Usage: bash run_lme_ku_parallel.sh <method> "<KEY_NAME_1 KEY_NAME_2 ...>"
#     e.g. bash run_lme_ku_parallel.sh ours "OPENAI_API_KEY_A OPENAI_API_KEY_B"
#   NSHARD = number of keys given. Each shard runs as its own process with its own
#   key + isolated store/caches/hyp (see run_lme_ku.sh). Wall-clock ~= 9.5hr / N.
set -u
cd /home/yhchiang/MemoryAgentBench
METHOD="${1:?need method (ours|b|vanilla)}"
read -r -a KEYS <<< "${2:?need space-separated key names}"
N=${#KEYS[@]}
SCRIPTS=docs/0615_intro_framework_after_problem_statement/scripts
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
HYPDIR=docs/0615_intro_framework_after_problem_statement/lme_hyps
mkdir -p "$LOGROOT" "$HYPDIR"

echo "[orch] $METHOD over $N shards: ${KEYS[*]}  ($(date))"
pids=()
for i in $(seq 0 $((N-1))); do
  SHARD=$i NSHARD=$N RUN_OAI_KEY_NAME="${KEYS[$i]}" \
    bash "$SCRIPTS/run_lme_ku.sh" "$METHOD" 0 0 \
    > "$LOGROOT/lme_${METHOD}_s${i}n${N}.log" 2>&1 &
  pids+=($!)
  echo "[orch] launched shard $i/$N key=${KEYS[$i]} pid=$! log=$LOGROOT/lme_${METHOD}_s${i}n${N}.log"
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "[orch] all shards done (fail=$fail)  ($(date))"

# concat shard hyps -> final
FINAL="$HYPDIR/lme_ku_${METHOD}.jsonl"
cat "$HYPDIR/lme_ku_${METHOD}"_s*n${N}.jsonl > "$FINAL" 2>/dev/null
echo "[orch] concatenated -> $FINAL ($(wc -l < "$FINAL" 2>/dev/null) lines)"

# judge once (gpt-4o-mini for validation; set JUDGE_MODEL=gpt-4o for paper-final)
JUDGE_MODEL="${JUDGE_MODEL:-gpt-4o-mini}"
JUDGE_PY=/home/yhchiang/origin_longmemeval/LongMemEval/src/evaluation/evaluate_qa.py
DATA=/home/yhchiang/LongMemEval/data/longmemeval_s_cleaned.json
FINAL_ABS="$PWD/$FINAL"
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh; conda activate MABench
set -a; [[ -f .env ]] && . .env; set +a
kn="${KEYS[0]}"; export OPENAI_API_KEY="${!kn}"
echo "---- judge ($JUDGE_MODEL; paper-final=gpt-4o) on $FINAL ----"
( cd "$(dirname "$JUDGE_PY")" && python "$(basename "$JUDGE_PY")" "$JUDGE_MODEL" "$FINAL_ABS" "$DATA" ) \
  2>&1 || echo "[judge] failed (run separately)"
echo "[orch] DONE $METHOD  ($(date))"
