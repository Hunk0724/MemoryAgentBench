#!/bin/bash
# LCA (Long-Context Agent) baseline for FC-SH at 6k/32k/64k/262k (2026-06-06).
# Model gemini-3.1-flash-lite, temp=0, thinking_level=minimal (agent.py:719),
# generation_max_length=256 (dataset yaml; -> fresh size256 result files, the old
# stale size10 LCA results are left untouched). FULLY matches the mem0 minimal
# answer setting (same model/temp/thinking/budget) => fair method comparison.
# Run AFTER the mem0 minimal re-runs to avoid Vertex rate contention.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="/home/yhchiang/MemoryAgentBench/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=/home/yhchiang/MemoryAgentBench/docs/0603_current_research_main_evidence/logs
AG=configs/agent_conf/Long_Context_Agents/Long_context_agent_gemini-3.1-flash-lite_temp0.yaml
DCONF=configs/data_conf/Conflict_Resolution

run_one () {
  local tag=$1 data=$2
  echo "================ LCA $tag ================"
  python main.py --agent_config "$AG" --dataset_config "$DCONF/$data" \
    > "$LOGROOT/run_lca_${tag}.log" 2>&1
  echo "[lca_$tag] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_lca_${tag}.log" | grep -v substring | tail -1)"
}

run_one sh_6k   Factconsolidation_sh_6k.yaml
run_one sh_32k  Factconsolidation_sh_32k.yaml
run_one sh_64k  Factconsolidation_sh_64k.yaml
run_one sh_262k Factconsolidation_sh_262k.yaml

echo "================ LCA SH baselines DONE ================"
