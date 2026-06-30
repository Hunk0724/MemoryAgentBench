#!/usr/bin/env bash
# LCA × gpt-4o-mini on FC-{SH,MH} × {6k,32k}.
# Expects OPENAI_API_KEY in .env. No Vertex env needed.

set -u
cd /home/yhchiang/MemoryAgentBench

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/hf
# Explicitly unset Vertex so the OpenAI branch is taken
unset GOOGLE_GENAI_USE_VERTEXAI
unset GOOGLE_CLOUD_PROJECT
unset GOOGLE_CLOUD_LOCATION

started=$(date +%s)
for data in \
  Factconsolidation_sh_6k.yaml \
  Factconsolidation_mh_6k.yaml \
  Factconsolidation_sh_32k.yaml \
  Factconsolidation_mh_32k.yaml; do
  echo ""
  echo "=============================================================="
  echo "[$(date +%H:%M:%S)] gpt-4o-mini × $data"
  echo "=============================================================="
  conda run -n MABench --no-capture-output python main.py \
    --agent_config  configs/agent_conf/Long_Context_Agents/Long_context_agent_gpt-4o-mini.yaml \
    --dataset_config configs/data_conf/Conflict_Resolution/"$data" 2>&1 \
    | tail -30
done

echo ""
echo "=== ALL 4 RUNS DONE at $(date), total $(($(date +%s)-started))s ==="
