#!/usr/bin/env bash
# Retry the 3 gpt-4o-mini runs that hit Tier-1 TPM (SH 6k is complete, skipped).
# agent.py now creates OpenAI client with max_retries=20, so 429s auto-backoff.

set -u
cd /home/yhchiang/MemoryAgentBench

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/hf
unset GOOGLE_GENAI_USE_VERTEXAI
unset GOOGLE_CLOUD_PROJECT
unset GOOGLE_CLOUD_LOCATION

started=$(date +%s)
for data in \
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
echo "=== ALL 3 RETRIES DONE at $(date), total $(($(date +%s)-started))s ==="
