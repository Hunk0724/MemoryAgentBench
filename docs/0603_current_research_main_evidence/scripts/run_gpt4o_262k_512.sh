#!/bin/bash
# mem0 gpt-4o-mini 262k @512、OpenAI embed、L2、temp 0。
# 先建 extraction_cache_262k(gemini L2,與 6k/32k/64k 同 extraction);再 ingest+query。
# ⚠️ 由 chain waiter 在 6k/32k/64k 完成後啟動,避免與 OpenAI pipeline 並跑。
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="$PWD/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=docs/0603_current_research_main_evidence/logs
CACHE=$PWD/analysis/results/extraction_cache_262k.json
AG=configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0_l2_512_openai.yaml
STORE=/home/yhchiang/MemoryAgentBench/analysis/results/expanded/stores/qdrant_gpt4o_512_openai

# 1. build 262k extraction cache (gemini L2) if missing
if [[ ! -f "$CACHE" ]]; then
  echo "[262k] building extraction cache (gemini L2) ..."
  python docs/0603_current_research_main_evidence/scripts/build_extraction_cache.py \
    --ctx analysis/contexts/factconsolidation_262k_context.txt \
    --out "$CACHE" --chunk-size 512 --model gemini-3.1-flash-lite \
    > "$LOGROOT/build_cache_262k.log" 2>&1
  echo "[262k] cache build exit=$?"
fi

# 2. ingest + query 262k (gpt-4o-mini OpenAI)
export MEM0_EXTRACTION_CACHE="$CACHE"
export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_262k_gpt4o_512_openai"
rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
rm -rf "${STORE}__factconsolidation_sh_262k"
echo "[262k] ingesting (SLOW ~500 chunks) ..."
python main.py --agent_config "$AG" \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_262k.yaml \
  > "$LOGROOT/run_gpt4o_262k_512_openai.log" 2>&1
echo "[262k] exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_gpt4o_262k_512_openai.log" | grep -v substring | tail -1)"
echo "================ 262k DONE ================"
