#!/usr/bin/env bash
# T1 — path scoring variant ablation
#
# Usage:
#   bash scripts/runs/run_T1_scoring_variant.sh <variant> <bidir> <run-dir>
# Examples:
#   bash scripts/runs/run_T1_scoring_variant.sh pure_relevance 0 monitoring_logs/<TS>_T1_pure_rel_bidir-off
#   bash scripts/runs/run_T1_scoring_variant.sh proprag_strict 0 monitoring_logs/<TS>_T1_proprag_bidir-off

set -u
cd /home/yhchiang/MemoryAgentBench

VARIANT="${1:?usage: $0 <pure_relevance|proprag_strict|adhoc> <0|1 bidir> <run-dir>}"
BIDIR="${2:?usage: $0 <variant> <0|1 bidir> <run-dir>}"
RUN_DIR="${3:?usage: $0 <variant> <bidir> <run-dir>}"

if [ ! -f "${RUN_DIR}/run_manifest.pre.json" ]; then
    echo "ERROR: no pre-manifest at ${RUN_DIR}/run_manifest.pre.json. Run snapshot first."
    exit 1
fi

# Fixed env
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

# Disable legacy paths
export HIPPORAG_ENABLE_SUPERSESSION=0
export HIPPORAG_ENABLE_PHASE2_FILTER=0
export HIPPORAG_ENABLE_V2_DETECT=0
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0
unset HIPPORAG_ENABLE_PROPOSITION_HYPEREDGE

# Phase 2 ON,rescue ON,chunk_rebuild OFF(我們在這次只測 scoring variant 的影響)
export HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION=1
export HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES=1
export HIPPORAG_ENABLE_PHASE2_FILTER_CHUNK_REBUILD=0
export HIPPORAG_ENABLE_PHASE3_V2_ENRICHED=0
export HIPPORAG_ENABLE_PHASE3_V2_HINTS=0
export HIPPORAG_ENABLE_PHASE3_V2_UPDATES=0

# Bidir verdict — by arg
export HIPPORAG_ENABLE_PHASE2_VERDICT_BIDIRECTIONAL="$BIDIR"

# Scoring variant — by arg
export HIPPORAG_PHASE2A_SCORING_VARIANT="$VARIANT"

# Phase 2 hyperparams (same as prior runs)
export HIPPORAG_V2_PHASE2_REGION_TOPK=50
export HIPPORAG_V2_PHASE2_M=5
export HIPPORAG_V2_PHASE2_L=3
export HIPPORAG_V2_PHASE2_BEAM=8

# Dumps into run dir
export HIPPORAG_PHASE2_W13_DUMP_PATH="${RUN_DIR}/phase2_w13_dump.jsonl"
export HIPPORAG_PHASE2_W13_VERDICT_LOG="${RUN_DIR}/verdict_events.jsonl"

AGENT="configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml"
DATASET_CFG="configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml"
RESULTS_FILE="outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"

echo "=================================================================="
echo "[$(date +%H:%M:%S)] T1 scoring variant — ${VARIANT}, bidir=${BIDIR}"
echo "  run dir: ${RUN_DIR}"
echo "  commit : $(git rev-parse --short HEAD)"
echo "=================================================================="
echo ""

[ -f "$RESULTS_FILE" ] && rm "$RESULTS_FILE"

started=$(date +%s)
conda run -n hipporag_env --no-capture-output python main.py \
    --agent_config "$AGENT" \
    --dataset_config "$DATASET_CFG" \
    --chunk_size_ablation 512 \
    --force 2>&1 | tail -50
elapsed=$(($(date +%s) - started))

[ ! -f "$RESULTS_FILE" ] && { echo "ERROR: no results.json"; exit 2; }

cp "$RESULTS_FILE" "${RUN_DIR}/results.json"
em=$(python3 -c "import json; d=json.load(open('${RUN_DIR}/results.json'))['data']; print(sum(1 for r in d if r.get('exact_match')))")
echo ""
echo "[T1 ${VARIANT} bidir=${BIDIR}] EM=${em}/100, elapsed ${elapsed}s"

conda run -n MABench --no-capture-output python3 analysis/runtime/snapshot_run_state.py \
    --run-dir "${RUN_DIR}" --post

echo ""
echo "=================================================================="
echo "T1 ${VARIANT} bidir=${BIDIR}: EM=${em}/100"
echo "Compare: vanilla=17, prior B (adhoc, bidir=0)=31, C-v2 B (adhoc, bidir=1)=29"
echo "=================================================================="
