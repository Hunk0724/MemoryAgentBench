#!/bin/bash
# Long-Context Agent (LCA) baseline on FC-SH: feed the WHOLE serial-numbered
# knowledge pool + question into the model (no memory module, no retrieval).
# 32k/64k fit gpt-4o-mini's 128k window (no truncation); 262k truncates.
#   Usage: RUN_OAI_KEY_NAME=OPENAI_API_KEY_B bash run_lca_fc.sh <L> [model_cfg]
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a

if [[ -n "${RUN_OAI_KEY_NAME:-}" ]]; then
  export OPENAI_API_KEY="${!RUN_OAI_KEY_NAME}"; echo "[key] \$$RUN_OAI_KEY_NAME ...${OPENAI_API_KEY: -6}"
elif [[ -n "${RUN_OAI_KEY:-}" ]]; then export OPENAI_API_KEY="$RUN_OAI_KEY"; fi
[[ -z "${OPENAI_API_KEY:-}" ]] && { echo "[key] ERROR none"; exit 1; }

L="${1:?need L}"
AG="${2:-Long_context_agent_gpt-4o-mini_temp0.yaml}"
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
DCONF=configs/data_conf/Conflict_Resolution
OUTDIR="outputs/gpt-4o-mini-temp0"
rm -f "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
mkdir -p "$LOGROOT"

echo "================ LCA gpt-4o-mini FC-SH ${L} ================"; date
python main.py --agent_config "configs/agent_conf/Long_Context_Agents/$AG" \
  --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
  > "$LOGROOT/run_lca_${L}.log" 2>&1
echo "[lca ${L}] exit=$?"; date
python3 -c "
import json, glob
fs=glob.glob('$OUTDIR/**/*sh_${L}*results*.json',recursive=True)
if fs:
    rows=json.load(open(fs[0]))['data']; em=sum(1 for x in rows if x.get('exact_match'))
    print(f'LCA gpt-4o-mini FC-SH ${L}: EM {em}/{len(rows)} = {em/len(rows)*100:.1f}%')
else: print('no result json -- see $LOGROOT/run_lca_${L}.log')
"
echo "================ DONE LCA ${L} ================"
