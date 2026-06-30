#!/bin/bash
# FC-SH 6k + 32k MINIMAL-thinking re-run (2026-06-06).
# Goal: clean 6k->32k->64k trend at a SINGLE thinking setting (minimal), matching
# the minimal 64k run. generation_max_length now 256 (no truncated empty outputs).
# Parallel `_min` namespace; original High-thinking l2 / l2_32k artifacts untouched.
# Extraction cache shared with the High runs -> identical frozen facts; only the
# update-LLM + answer-LLM thinking level differs (isolates the thinking effect).
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="/home/yhchiang/MemoryAgentBench/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=/home/yhchiang/MemoryAgentBench/docs/0603_current_research_main_evidence/logs
AGDIR=configs/agent_conf/RAG_Agents/Gemini
DCONF=configs/data_conf/Conflict_Resolution
RESDIR=/home/yhchiang/MemoryAgentBench/analysis/results

run_one () {
  local tag=$1 agent=$2 data=$3 cache=$4 qpath=$5
  export MEM0_CAND_LOG_DIR="$LOGROOT/$tag"
  export MEM0_EXTRACTION_CACHE="$cache"
  rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
  rm -rf "$qpath"   # fresh qdrant store for clean ingestion
  echo "================ $tag (cache=$(basename "$cache")) ================"
  python main.py --agent_config "$agent" --dataset_config "$data" \
    > "$LOGROOT/run_${tag}.log" 2>&1
  echo "[$tag] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_${tag}.log" | grep -v substring | tail -1)"
}

run_one sh_6k_l2_min \
  "$AGDIR/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_l2_min.yaml" \
  "$DCONF/Factconsolidation_sh_6k.yaml" \
  "$RESDIR/extraction_cache_6k.json" \
  /tmp/qdrant_mem0_vertex_factaware_l2_min

run_one sh_32k_l2_min \
  "$AGDIR/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_l2_32k_min.yaml" \
  "$DCONF/Factconsolidation_sh_32k.yaml" \
  "$RESDIR/extraction_cache_32k.json" \
  /tmp/qdrant_mem0_vertex_factaware_l2_32k_min

echo "================ SH minimal re-runs DONE ================"
