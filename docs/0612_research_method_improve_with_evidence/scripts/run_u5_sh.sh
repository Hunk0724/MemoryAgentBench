#!/bin/bash
# U5 Phase-1 vs vanilla matched baseline on FC-SH at a given length ($1).
# Only the update component differs. Isolated stores/outputs/logs.
# Usage: run_u5_sh.sh 6k | 32k | 64k
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a

L=${1:?usage: run_u5_sh.sh <6k|32k|64k>}
LOGROOT=docs/0612_research_method_improve_with_evidence/logs
DCONF=configs/data_conf/Conflict_Resolution
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
STOREBASE=/home/yhchiang/MemoryAgentBench/analysis/results/expanded/stores
mkdir -p "$LOGROOT"
export MEM0_EXTRACTION_CACHE="$PWD/analysis/results/extraction_cache_${L}.json"

run () {
  local TAG=$1 AG=$2 MODE=$3 STORE=$4
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_${TAG}"
  rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
  rm -rf "${STORE}__factconsolidation_sh_${L}"
  if [[ "$MODE" == "u5" ]]; then export MEM0_UPDATE_MODE=u5_classification; else unset MEM0_UPDATE_MODE; fi
  echo "================ $TAG (mode=$MODE) sh_${L} ================"
  python main.py --agent_config "$AGDIR/$AG" \
    --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
    > "$LOGROOT/run_${TAG}_${L}.log" 2>&1
  echo "[$TAG] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_${TAG}_${L}.log" | grep -v substring | tail -1)"
}

run vanilla_rerun Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun.yaml vanilla "$STOREBASE/qdrant_gpt4o_512_openai_rerun"
run u5           Structure_rag_gpt-4o-mini-mem0_l2_512_openai_u5.yaml    u5      "$STOREBASE/qdrant_gpt4o_512_openai_u5"
echo "================ DONE ${L} ================"
