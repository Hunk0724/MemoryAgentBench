#!/usr/bin/env bash
# RPT-min: minimum-modification Restructured Prompt Test
# Keeps vanilla HippoRAG prompt skeleton (Wikipedia Title + Question/Thought trailer);
# only adds INSTRUCTION paragraph + inline section labels + fact-level annotations.

set -u
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

started=$(date +%s)

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] RPT-min Inference (Gemini 3.1 Flash-Lite)"
echo "=============================================================="
conda run -n hipporag_env --no-capture-output \
  python analysis/restructured_pat_min_gemini.py

echo ""
echo "=== DONE at $(date), total $(($(date +%s)-started))s ==="
