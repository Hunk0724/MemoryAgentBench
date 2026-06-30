#!/bin/bash
# Complete the FC-SH 64k row with matched settings (same as our 6k/32k reruns):
#   1) LCA gpt-4o-mini temp0 (isolated output dir)
#   2) vanilla mem0 matched rerun + ours(U5)  [via run_u5_sh.sh 64k]
# Sequential to avoid TPM contention.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=docs/0612_research_method_improve_with_evidence/logs
mkdir -p "$LOGROOT"

echo "================ LCA gpt-4o-mini temp0 sh_64k (matched rerun) ================"
python main.py \
  --agent_config configs/agent_conf/Long_Context_Agents/Long_context_agent_gpt-4o-mini_temp0_rerun.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_64k.yaml --force \
  > "$LOGROOT/run_lca_rerun_64k.log" 2>&1
echo "[LCA] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_lca_rerun_64k.log" | grep -v substring | tail -1)"

echo "================ mem0 vanilla + U5 sh_64k ================"
bash docs/0612_research_method_improve_with_evidence/scripts/run_u5_sh.sh 64k
echo "================ 64k ALL DONE ================"
