#!/usr/bin/env bash
# v2 LLM-judge runner — FC-SH+MH 6k with query-time semantic detection.
#
# Usage:
#   bash scripts/run_v2_llm_judge.sh filter      # filter mode only
#   bash scripts/run_v2_llm_judge.sh annotate    # annotate mode only
#   bash scripts/run_v2_llm_judge.sh both        # filter + annotate
#   bash scripts/run_v2_llm_judge.sh off         # detect-only (no EM impact, dump for diagnostic)

set -u
cd /home/yhchiang/MemoryAgentBench

MODE=${1:-filter}
if [[ ! "$MODE" =~ ^(filter|annotate|both|off)$ ]]; then
  echo "Usage: $0 {filter|annotate|both|off}"
  exit 1
fi

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# v2 detection config
export HIPPORAG_ENABLE_V2_DETECT=1
export HIPPORAG_V2_MODE="$MODE"
export HIPPORAG_V2_TOP_N_PASSAGES=20

# Embedding config (match v1 lock)
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

# v1 P1/P2/P3 OFF for v2 head-to-head clean test
export HIPPORAG_ENABLE_SUPERSESSION=0
export HIPPORAG_ENABLE_PHASE2_FILTER=0
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0

TS=$(date +%Y-%m-%d_%H%M%S)
RUN_LABEL="v2_${MODE}"
OUT_DIR="monitoring_logs/${TS}_${RUN_LABEL}"
mkdir -p "$OUT_DIR"
export HIPPORAG_V2_DUMP_PATH="${OUT_DIR}/v2_detection_dump.jsonl"

AGENT=configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml

# Back up existing result jsons to force fresh run
BACKUP_DIR=".baseline_backup_v2_${MODE}_pre"
mkdir -p "$BACKUP_DIR"
for split in sh mh; do
  src="outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_${split}_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
  if [ -f "$src" ]; then
    mv "$src" "$BACKUP_DIR/$(basename $src)"
    echo "[backup] moved $src → $BACKUP_DIR/"
  fi
done

started=$(date +%s)
for data in sh mh; do
  cfg="Factconsolidation_${data}_6k.yaml"
  echo ""
  echo "=============================================================="
  echo "[$(date +%H:%M:%S)] v2 ${MODE} mode: ${data}_6k → ${OUT_DIR}"
  echo "=============================================================="
  conda run -n hipporag_env --no-capture-output python main.py \
    --agent_config "$AGENT" \
    --dataset_config configs/data_conf/Conflict_Resolution/"$cfg" \
    --chunk_size_ablation 512 \
    --force 2>&1
done

echo ""
echo "=== v2 ${MODE} done at $(date), total $(($(date +%s)-started))s ==="
echo "=== Output dir: $OUT_DIR ==="
echo "=== EM ==="
python3 -c "
import json
for split in ['sh', 'mh']:
    p = f'outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_{split}_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'
    d = json.load(open(p))
    em = sum(1 for r in d['data'] if r.get('exact_match'))
    print(f'{split.upper()}: exact_match={em}/100')
"
echo "=== Dump line count ==="
wc -l "$OUT_DIR/v2_detection_dump.jsonl" 2>/dev/null || echo "(no dump file)"
