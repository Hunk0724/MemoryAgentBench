#!/usr/bin/env bash
# C-v2 experiments — bidirectional verdict + B2 chunk_rebuild filter
#
# Two groups (run separately):
#   B group: bidir verdict + RESCUE filter   → measures bidir's effect alone
#   C group: bidir verdict + CHUNK_REBUILD filter → measures bidir + B2 combined
#
# Usage:
#   bash scripts/runs/run_C-v2_group.sh B <run-dir-with-pre-snapshot>
#   bash scripts/runs/run_C-v2_group.sh C <run-dir-with-pre-snapshot>

set -u
cd /home/yhchiang/MemoryAgentBench

GROUP="${1:?usage: $0 <B|C> <run-dir>}"
RUN_DIR="${2:?usage: $0 <B|C> <run-dir>}"

if [ ! -f "${RUN_DIR}/run_manifest.pre.json" ]; then
    echo "ERROR: no pre-manifest at ${RUN_DIR}/run_manifest.pre.json"
    echo "Run snapshot_run_state.py --run-dir <dir> first."
    exit 1
fi

# ─── Fixed environment(同 B verify hyperedge script)───
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

# Disable legacy v1 / W1 prototypes
export HIPPORAG_ENABLE_SUPERSESSION=0
export HIPPORAG_ENABLE_PHASE2_FILTER=0
export HIPPORAG_ENABLE_V2_DETECT=0
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0

# Phase 2 ON (same as B)
export HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION=1
# Hyperedge OFF (default,但顯式 unset 保險)
unset HIPPORAG_ENABLE_PROPOSITION_HYPEREDGE
# W3 OFF (we're testing bidir + chunk_rebuild, not W3)
export HIPPORAG_ENABLE_PHASE3_V2_ENRICHED=0
export HIPPORAG_ENABLE_PHASE3_V2_HINTS=0
export HIPPORAG_ENABLE_PHASE3_V2_UPDATES=0

# Phase 2 hyperparameters(同 B)
export HIPPORAG_V2_PHASE2_REGION_TOPK=50
export HIPPORAG_V2_PHASE2_M=5
export HIPPORAG_V2_PHASE2_L=3
export HIPPORAG_V2_PHASE2_BEAM=8

# ───  Group-specific flags  ───
case "$GROUP" in
    B)
        # B group: bidir verdict ON + RESCUE filter ON + chunk_rebuild OFF
        export HIPPORAG_ENABLE_PHASE2_VERDICT_BIDIRECTIONAL=1
        export HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES=1
        export HIPPORAG_ENABLE_PHASE2_FILTER_CHUNK_REBUILD=0
        DESC="bidir verdict + rescue filter"
        ;;
    C)
        # C group: bidir verdict ON + RESCUE filter OFF + chunk_rebuild ON
        export HIPPORAG_ENABLE_PHASE2_VERDICT_BIDIRECTIONAL=1
        export HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES=0
        export HIPPORAG_ENABLE_PHASE2_FILTER_CHUNK_REBUILD=1
        DESC="bidir verdict + chunk_rebuild filter (no rescue)"
        ;;
    *)
        echo "ERROR: GROUP must be 'B' or 'C', got '$GROUP'"
        exit 2
        ;;
esac

# Dump paths into run dir
export HIPPORAG_PHASE2_W13_DUMP_PATH="${RUN_DIR}/phase2_w13_dump.jsonl"
export HIPPORAG_PHASE2_W13_VERDICT_LOG="${RUN_DIR}/verdict_events.jsonl"

AGENT="configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml"
DATASET_CFG="configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml"
RESULTS_FILE="outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"

echo "=================================================================="
echo "[$(date +%H:%M:%S)] C-v2 ${GROUP} group — ${DESC}"
echo "  run dir: ${RUN_DIR}"
echo "  commit : $(git rev-parse --short HEAD)"
echo "  bidir=${HIPPORAG_ENABLE_PHASE2_VERDICT_BIDIRECTIONAL}, rescue=${HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES}, chunk_rebuild=${HIPPORAG_ENABLE_PHASE2_FILTER_CHUNK_REBUILD}"
echo "=================================================================="
echo ""

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
    echo "[C-v2 ${GROUP}] ERROR: no results.json produced"
    exit 2
fi

cp "$RESULTS_FILE" "${RUN_DIR}/results.json"
em=$(python3 -c "import json; d=json.load(open('${RUN_DIR}/results.json'))['data']; print(sum(1 for r in d if r.get('exact_match')))")
echo ""
echo "[C-v2 ${GROUP}] EM=${em}/100, elapsed ${elapsed}s"

# Post-snapshot
conda run -n MABench --no-capture-output python3 analysis/runtime/snapshot_run_state.py \
    --run-dir "${RUN_DIR}" --post

echo ""
echo "=================================================================="
echo "C-v2 ${GROUP} group: EM=${em}/100 (prior B=31; bidir 預期 ↑ detection,EM 受 filter 影響)"
echo "=================================================================="
