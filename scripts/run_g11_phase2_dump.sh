#!/usr/bin/env bash
# G.11 — Phase 2 filter event dump (P/Q/R-P1/R-P2/S diagnostic).
# Runs FC-SH+MH 6k with Phase 1+2-99 enabled + per-passage state dump per query.
# Output: monitoring_logs/<ts>_g11_phase2_dump/{sh,mh}_phase2_dump.jsonl

set -u
cd /home/yhchiang/MemoryAgentBench

export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# v1 Phase 1+2-99 lock config (matches §10 entry "Phase 1+2 v0.1 pct=99")
export HIPPORAG_ENABLE_SUPERSESSION=1
export HIPPORAG_ENABLE_PHASE2_FILTER=1
export HIPPORAG_PHASE2_PERCENTILE=99
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0   # G.11 isolates P2; keep P3 off
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

TS=$(date +%Y-%m-%d_%H%M%S)
OUT_DIR="monitoring_logs/${TS}_g11_phase2_dump"
mkdir -p "$OUT_DIR"

AGENT=configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml

started=$(date +%s)
for data in sh mh; do
  cfg="Factconsolidation_${data}_6k.yaml"
  dump_path="${OUT_DIR}/${data}_phase2_dump.jsonl"
  export HIPPORAG_PHASE2_DUMP_PATH="$dump_path"

  echo ""
  echo "=============================================================="
  echo "[$(date +%H:%M:%S)] G.11 dump: ${data}_6k → $dump_path"
  echo "=============================================================="
  conda run -n hipporag_env --no-capture-output python main.py \
    --agent_config "$AGENT" \
    --dataset_config configs/data_conf/Conflict_Resolution/"$cfg" \
    --chunk_size_ablation 512 \
    --force 2>&1
done

echo ""
echo "=== G.11 dump done at $(date), total $(($(date +%s)-started))s ==="
echo "=== Output dir: $OUT_DIR ==="
ls -la "$OUT_DIR"
