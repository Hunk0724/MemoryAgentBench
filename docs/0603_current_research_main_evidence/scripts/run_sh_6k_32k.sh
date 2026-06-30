#!/bin/bash
# Run FC-SH query pipeline at 6k then 32k, sequentially.
# Reuses the MH factaware agent yamls (SH/MH is decided by the DATASET config;
# outputs are isolated by sub_dataset path + mem0 user_id, so no collision).
# Write-time instrumentation ON (sh-specific dirs) — also a determinism check:
# SH ingestion of the shared context should match MH's.
# Launch ONLY after the MH 32k run finishes (avoid Vertex rate contention).
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="/home/yhchiang/MemoryAgentBench/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=/home/yhchiang/MemoryAgentBench/docs/0603_current_research_main_evidence/logs

run_one () {
  local tag=$1 agent=$2 data=$3
  export MEM0_CAND_LOG_DIR="$LOGROOT/$tag"
  rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
  echo "================ $tag ================"
  python main.py --agent_config "$agent" --dataset_config "$data" \
    > "$LOGROOT/run_${tag}.log" 2>&1
  echo "[$tag] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_${tag}.log" | grep -v substring | tail -1)"
}

AG6=configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware.yaml
AG32=configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_32k.yaml

run_one sh_6k  "$AG6"  configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml
run_one sh_32k "$AG32" configs/data_conf/Conflict_Resolution/Factconsolidation_sh_32k.yaml

echo "================ SH runs DONE ================"
