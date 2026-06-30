#!/usr/bin/env bash
# Run Gemini Flash-Lite variants on FC 32k (SH + MH) via Vertex global endpoint.

set -u
cd /home/yhchiang/MemoryAgentBench

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/hf
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

started=$(date +%s)
for agent in \
  Long_context_agent_gemini-3.1-flash-lite.yaml \
  Long_context_agent_gemini-2.5-flash-lite.yaml; do
  for data in \
    Factconsolidation_sh_32k.yaml \
    Factconsolidation_mh_32k.yaml; do
    echo ""
    echo "=============================================================="
    echo "[$(date +%H:%M:%S)] $agent × $data (32k, location=global)"
    echo "=============================================================="
    conda run -n MABench --no-capture-output python main.py \
      --agent_config "configs/agent_conf/Long_Context_Agents/$agent" \
      --dataset_config "configs/data_conf/Conflict_Resolution/$data" 2>&1 \
      | tail -30
  done
done

echo ""
echo "=== ALL 4 RUNS DONE at $(date), total $(($(date +%s)-started))s ==="
