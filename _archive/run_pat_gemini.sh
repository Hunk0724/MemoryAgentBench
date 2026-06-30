#!/usr/bin/env bash
# Perfect Annotation Test (PAT) for HippoRAG-v2 × Gemini 3.1 Flash-Lite
# Same usable subset as Oracle A (SH=64, MH=66) for direct three-way comparison:
#   vanilla  /  Oracle A (passage removed)  /  PAT (passage labeled, kept)

set -u
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

started=$(date +%s)

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] PAT Inference (Gemini 3.1 Flash-Lite)"
echo "=============================================================="
conda run -n hipporag_env --no-capture-output \
  python analysis/pat_gemini.py

echo ""
echo "=== DONE at $(date), total $(($(date +%s)-started))s ==="
