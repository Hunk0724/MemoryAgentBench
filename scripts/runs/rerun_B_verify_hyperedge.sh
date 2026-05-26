#!/usr/bin/env bash
# Re-run ablation B (Phase 2 only) to verify EM unchanged after hyperedge
# call de-coupling (commit a76f4cd).
#
# Pre-snapshot already written by:
#   analysis/runtime/snapshot_run_state.py --run-dir <RUN_DIR>
#
# Expected: EM ∈ [30%, 32%] (prior B run got 31%).

set -u
cd /home/yhchiang/MemoryAgentBench

RUN_DIR="${1:?usage: $0 <run-dir-from-snapshot>}"
if [ ! -f "${RUN_DIR}/run_manifest.pre.json" ]; then
    echo "ERROR: no pre-manifest at ${RUN_DIR}/run_manifest.pre.json"
    echo "Run snapshot_run_state.py first."
    exit 1
fi

# ─── Fixed environment (mirrors scripts/run_4ablations_fc_mh_100q.sh) ───
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

# Disable legacy v1 / W1 prototypes (same as original 4-ablation script)
export HIPPORAG_ENABLE_SUPERSESSION=0
export HIPPORAG_ENABLE_PHASE2_FILTER=0
export HIPPORAG_ENABLE_V2_DETECT=0
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0

# Ablation B flags
export HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION=1   # Phase 2 chain detection ON
export HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES=1   # Phase 2 filter ON
export HIPPORAG_ENABLE_PHASE3_V2_ENRICHED=0       # W3 OFF
export HIPPORAG_ENABLE_PHASE3_V2_HINTS=0
export HIPPORAG_ENABLE_PHASE3_V2_UPDATES=0

# Hyperedge: should default to OFF after a76f4cd
unset HIPPORAG_ENABLE_PROPOSITION_HYPEREDGE      # explicit unset to confirm default

# Phase 2 hyperparameters (same as prior run)
export HIPPORAG_V2_PHASE2_REGION_TOPK=50
export HIPPORAG_V2_PHASE2_M=5
export HIPPORAG_V2_PHASE2_L=3
export HIPPORAG_V2_PHASE2_BEAM=8

# Dump paths point INTO the pre-snapshotted dir
export HIPPORAG_PHASE2_W13_DUMP_PATH="${RUN_DIR}/phase2_w13_dump.jsonl"
export HIPPORAG_PHASE2_W13_VERDICT_LOG="${RUN_DIR}/verdict_events.jsonl"

AGENT="configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml"
DATASET_CFG="configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml"
RESULTS_FILE="outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"

echo "=================================================================="
echo "[$(date +%H:%M:%S)] B re-run — verify hyperedge removal preserves EM"
echo "  run dir: ${RUN_DIR}"
echo "  commit : $(git rev-parse --short HEAD)"
echo "=================================================================="
echo ""

# Remove existing results to force fresh run
if [ -f "$RESULTS_FILE" ]; then
    rm "$RESULTS_FILE"
fi

started=$(date +%s)
conda run -n hipporag_env --no-capture-output python main.py \
    --agent_config "$AGENT" \
    --dataset_config "$DATASET_CFG" \
    --chunk_size_ablation 512 \
    --force 2>&1 | tail -50

elapsed=$(($(date +%s) - started))

if [ ! -f "$RESULTS_FILE" ]; then
    echo "[B re-run] ERROR: no results.json produced"
    exit 2
fi

cp "$RESULTS_FILE" "${RUN_DIR}/results.json"
em=$(python3 -c "import json; d=json.load(open('${RUN_DIR}/results.json'))['data']; print(sum(1 for r in d if r.get('exact_match')))")
echo ""
echo "[B re-run] EM=${em}/100, elapsed ${elapsed}s"
echo "  result : ${RUN_DIR}/results.json"

# Post-snapshot
conda run -n MABench --no-capture-output python3 analysis/runtime/snapshot_run_state.py \
    --run-dir "${RUN_DIR}" --post

# Verdict
echo ""
echo "=================================================================="
if [ "$em" -ge 30 ] && [ "$em" -le 32 ]; then
    echo "✅ PASS  EM=${em} ∈ [30, 32] → hyperedge removal preserves baseline"
else
    echo "❌ FAIL  EM=${em} outside [30, 32] → investigate (could be regression or random variance)"
fi
echo "=================================================================="
