#!/usr/bin/env bash
# v2.0.2 W1.3 runner — Phase 2 chain-restricted detection on FC-SH+MH 6k.
#
# Prerequisite: proposition_index.json must exist at:
#   outputs/.../gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/proposition_index.json
# Build via: conda run -n hipporag_env python analysis/build_proposition_index_w1.py

set -u
cd /home/yhchiang/MemoryAgentBench

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# v2.0.2 Phase 2 chain detection
export HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION=1
export HIPPORAG_V2_PHASE2_REGION_TOPK=50
export HIPPORAG_V2_PHASE2_M=5
export HIPPORAG_V2_PHASE2_L=3
export HIPPORAG_V2_PHASE2_BEAM=8

# Embedding config
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

# Disable v1 + earlier v2 prototypes (clean head-to-head)
export HIPPORAG_ENABLE_SUPERSESSION=0
export HIPPORAG_ENABLE_PHASE2_FILTER=0
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0
export HIPPORAG_ENABLE_V2_DETECT=0

TS=$(date +%Y-%m-%d_%H%M%S)
OUT_DIR="monitoring_logs/${TS}_v2_phase2_w13"
mkdir -p "$OUT_DIR"
export HIPPORAG_PHASE2_W13_DUMP_PATH="${OUT_DIR}/phase2_w13_dump.jsonl"
export HIPPORAG_PHASE2_W13_VERDICT_LOG="${OUT_DIR}/verdict_events.jsonl"

AGENT=configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml

# Backup any prior result jsons to force fresh run
BACKUP_DIR=".baseline_backup_v2_phase2_w13_pre"
mkdir -p "$BACKUP_DIR"
for split in sh mh; do
  src="outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_${split}_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
  if [ -f "$src" ]; then
    mv "$src" "$BACKUP_DIR/$(basename $src)"
    echo "[backup] $src → $BACKUP_DIR/"
  fi
done

started=$(date +%s)
for data in sh mh; do
  cfg="Factconsolidation_${data}_6k.yaml"
  echo ""
  echo "=============================================================="
  echo "[$(date +%H:%M:%S)] v2.0.2 W1.3: ${data}_6k"
  echo "=============================================================="
  conda run -n hipporag_env --no-capture-output python main.py \
    --agent_config "$AGENT" \
    --dataset_config configs/data_conf/Conflict_Resolution/"$cfg" \
    --chunk_size_ablation 512 \
    --force 2>&1
done

echo ""
echo "=== v2.0.2 W1.3 done at $(date), total $(($(date +%s)-started))s ==="
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
echo "=== Dump line counts ==="
wc -l "$OUT_DIR"/*.jsonl 2>/dev/null || echo "(no dump files)"
