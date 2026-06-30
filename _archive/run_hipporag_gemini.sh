#!/usr/bin/env bash
# HippoRAG-v2 × Gemini 3.1 Flash-Lite preview × FC-SH/MH 6k
# Vertex global endpoint; reuses Graph index cache if present.

set -u
cd /home/yhchiang/MemoryAgentBench

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

AGENT=configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml

started=$(date +%s)
for data in \
  Factconsolidation_sh_6k.yaml \
  Factconsolidation_mh_6k.yaml; do
  echo ""
  echo "=============================================================="
  echo "[$(date +%H:%M:%S)] HippoRAG-v2 × Gemini-3.1-FL × $data"
  echo "=============================================================="
  conda run -n hipporag_env --no-capture-output python main.py \
    --agent_config "$AGENT" \
    --dataset_config configs/data_conf/Conflict_Resolution/"$data" \
    --chunk_size_ablation 512 2>&1
done

echo ""
echo "=== DONE at $(date), total $(($(date +%s)-started))s ==="
