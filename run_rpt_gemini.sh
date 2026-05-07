#!/usr/bin/env bash
# Restructured Prompt Test (RPT) — section partition + fact-level annotation + strong instructions

set -u
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

started=$(date +%s)

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] RPT Inference (Gemini 3.1 Flash-Lite)"
echo "=============================================================="
conda run -n hipporag_env --no-capture-output \
  python analysis/restructured_pat_gemini.py

echo ""
echo "=== DONE at $(date), total $(($(date +%s)-started))s ==="
