#!/usr/bin/env bash
# Phase 1: Zep + Mem0 at chunk=512 on FC-SH 6k + FC-MH 6k.
# Uses MAB default settings (gpt-4o-mini backbone, agent yaml as-is)
# only override chunk_size_ablation=512 to align with HippoRAG-v2 comparison.
#
# Outputs:
#   outputs/gpt-4o-mini-{mem0,zep}/Conflict_Resolution/factconsolidation_*_chunk512_results.json
# Inspection (per-query):
#   outputs/rag_retrieved/Structure_rag_{mem0,zep}/k_*/.../query_*.json
#   outputs/rag_retrieved/Structure_rag_mem0/.../ingestion_*.jsonl

set -u
cd /home/yhchiang/MemoryAgentBench

# Environment from .env (must have ZEP_API_KEY + OPENAI_API_KEY)
unset GOOGLE_GENAI_USE_VERTEXAI GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION

# HF cache: /home/yhchiang/.cache/huggingface is root-owned, must redirect to a writable
# location. Same fix as LCA/HippoRAG run scripts.
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/hf

started=$(date +%s)

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] [1/4] Mem0 × FC-SH 6k × chunk=512"
echo "=============================================================="
conda run -n MABench --no-capture-output python main.py \
  --agent_config  configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml \
  --chunk_size_ablation 512 2>&1

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] [2/4] Mem0 × FC-MH 6k × chunk=512"
echo "=============================================================="
conda run -n MABench --no-capture-output python main.py \
  --agent_config  configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml \
  --chunk_size_ablation 512 2>&1

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] [3/4] Zep × FC-MH 6k warm-up (1 query) + 60s wait"
echo "=============================================================="
conda run -n MABench --no-capture-output python main.py \
  --agent_config  configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-zep.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml \
  --chunk_size_ablation 512 \
  --max_test_queries_ablation 1 2>&1
echo "[$(date +%H:%M:%S)] Sleeping 60s for Zep async indexing..."
sleep 60

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] [4/4] Zep × FC-MH 6k full 100"
echo "=============================================================="
conda run -n MABench --no-capture-output python run_zep_mh_full100.py 2>&1

echo ""
echo "=== Phase 1 DONE at $(date), total $(($(date +%s)-started))s ==="
