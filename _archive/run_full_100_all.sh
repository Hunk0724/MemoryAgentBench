#!/usr/bin/env bash
# Run PAT / RPT / RPT-min on FULL 100 questions for both SH and MH.
# Each row of results carries `group` ∈ {different_passage, same_passage, retrieval_missing,
# no_conflict_pair (SH only)} so post-hoc grouped analysis is straightforward.

set -u
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

started=$(date +%s)
for method in pat rpt rpt_min; do
  for task in sh mh; do
    echo ""
    echo "=============================================================="
    echo "[$(date +%H:%M:%S)] $method × $task — full 100"
    echo "=============================================================="
    conda run -n hipporag_env --no-capture-output \
      python analysis/run_full_100.py --method "$method" --task "$task"
  done
done

echo ""
echo "=== ALL 6 RUNS DONE at $(date), total $(($(date +%s)-started))s ==="
