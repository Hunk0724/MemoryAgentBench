#!/usr/bin/env bash
# Oracle A for HippoRAG-v2 × Gemini 3.1 Flash-Lite (Vertex global)
#
# Phase 1: validate retrieval passage ranks, decide which to remove,
#          output analysis/results/oracle_a_gemini/corrected_ranks.json
# Phase 2: for each usable question, rebuild prompt without old passages,
#          call Gemini, compute Oracle A Acc vs baseline
#
# Usable counts (pre-computed): SH=59, MH=66. Cost on Vertex <= $0.10.

set -u
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

started=$(date +%s)

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] Phase 1: validate passage ranks"
echo "=============================================================="
conda run -n hipporag_env --no-capture-output \
  python analysis/oracle_a_phase1_validate_gemini.py

echo ""
echo "=============================================================="
echo "[$(date +%H:%M:%S)] Phase 2: run Gemini inference on usable questions"
echo "=============================================================="
conda run -n hipporag_env --no-capture-output \
  python analysis/oracle_a_phase2_inference_gemini.py

echo ""
echo "=== DONE at $(date), total $(($(date +%s)-started))s ==="
