#!/bin/bash
# mem0 gpt-4o-mini scale 分析:6k/32k/64k @ chunk 512、OpenAI embed、L2 凍結 cache、temp 0。
# 觀察失敗模式分布隨長度轉移(final-store new_only/old_only/neither/both + same-chunk,不預排除）。
# 262k 另跑(需先建 extraction cache)。
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="$PWD/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=docs/0603_current_research_main_evidence/logs
AG=configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0_l2_512_openai.yaml
DCONF=configs/data_conf/Conflict_Resolution
STORE=/home/yhchiang/MemoryAgentBench/analysis/results/expanded/stores/qdrant_gpt4o_512_openai

run_one () {
  local L=$1
  export MEM0_EXTRACTION_CACHE="$PWD/analysis/results/extraction_cache_${L}.json"
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_gpt4o_512_openai"
  rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
  rm -rf "${STORE}__factconsolidation_sh_${L}"
  echo "================ gpt-4o-mini sh_${L} @512 OpenAI ================"
  python main.py --agent_config "$AG" \
    --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" \
    > "$LOGROOT/run_gpt4o_${L}_512_openai.log" 2>&1
  echo "[${L}] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_gpt4o_${L}_512_openai.log" | grep -v substring | tail -1)"
}

run_one 6k
run_one 32k
run_one 64k
echo "================ 6k/32k/64k DONE ================"
