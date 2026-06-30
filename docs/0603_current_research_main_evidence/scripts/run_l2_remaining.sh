#!/bin/bash
# L2 + frozen-cache runs for the remaining 3 cells: SH 6k, MH 32k, SH 32k.
# (MH 6k L2 is the validation run, already done separately.)
# Each reads the matching frozen extraction cache so SH/MH ingest identical facts.
# Launch after both the MH-6k-L2 validation and the 32k cache build finish.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="/home/yhchiang/MemoryAgentBench/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=/home/yhchiang/MemoryAgentBench/docs/0603_current_research_main_evidence/logs
AG6=configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_l2.yaml
AG32=configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_l2_32k.yaml

run_one () {
  local tag=$1 agent=$2 data=$3 cache=$4
  export MEM0_CAND_LOG_DIR="$LOGROOT/$tag"
  export MEM0_EXTRACTION_CACHE="$cache"
  rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
  echo "================ $tag (cache=$(basename $cache)) ================"
  python main.py --agent_config "$agent" --dataset_config "$data" \
    > "$LOGROOT/run_${tag}.log" 2>&1
  echo "[$tag] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_${tag}.log" | grep -v substring | tail -1)"
}

C6=/home/yhchiang/MemoryAgentBench/analysis/results/extraction_cache_6k.json
C32=/home/yhchiang/MemoryAgentBench/analysis/results/extraction_cache_32k.json
DCONF=configs/data_conf/Conflict_Resolution

run_one sh_6k_l2  "$AG6"  "$DCONF/Factconsolidation_sh_6k.yaml"  "$C6"
run_one mh_32k_l2 "$AG32" "$DCONF/Factconsolidation_mh_32k.yaml" "$C32"
run_one sh_32k_l2 "$AG32" "$DCONF/Factconsolidation_sh_32k.yaml" "$C32"

echo "================ L2 remaining runs DONE ================"
