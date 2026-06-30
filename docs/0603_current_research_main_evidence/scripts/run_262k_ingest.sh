#!/bin/bash
# 262k FC-SH mem0 ingestion (run before bed — SLOW: ~500 chunks, each update has a
# huge candidate pool). Builds the frozen extraction cache first (for completeness),
# then ingests with write-time logging + a PERSISTENT on_disk qdrant store so we can
# reconstruct/QA the battlefield afterwards without re-ingesting.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
export HF_HOME="$PWD/.cache/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=/home/yhchiang/MemoryAgentBench/docs/0603_current_research_main_evidence/logs
CACHE=/home/yhchiang/MemoryAgentBench/analysis/results/extraction_cache_262k.json
S=docs/0603_current_research_main_evidence/scripts

# 1. build frozen extraction cache if missing
if [[ ! -f "$CACHE" ]]; then
  echo "[262k] building extraction cache ..."
  python $S/build_extraction_cache.py \
    --ctx analysis/contexts/factconsolidation_262k_context.txt \
    --out "$CACHE" --chunk-size 512 --model gemini-3.1-flash-lite \
    > "$LOGROOT/build_cache_262k.log" 2>&1
  echo "[262k] cache build exit=$? ($(wc -l < "$CACHE" 2>/dev/null) bytes-ish)"
fi

# 2. ingest (writes vector_results + write-time logs + persistent on_disk store)
export MEM0_EXTRACTION_CACHE="$CACHE"
export MEM0_CAND_LOG_DIR="$LOGROOT/sh_262k_l2"
rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
echo "[262k] ingesting (this is the slow part) ..."
python main.py \
  --agent_config configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_l2_262k.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_262k.yaml \
  > "$LOGROOT/run_sh_262k_l2.log" 2>&1
echo "[262k] ingest exit=$? EM=$(grep -E 'exact_match:' "$LOGROOT/run_sh_262k_l2.log" | grep -v substring | tail -1)"
echo "================ 262k DONE ================"
