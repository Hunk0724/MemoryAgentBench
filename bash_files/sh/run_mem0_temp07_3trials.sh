#!/bin/bash
# Mem0 × FC-{SH,MH} × 6k × temp=0.7 × 3 trials
# - temp=0.7 aligns with benchmark default (Structure_rag_gpt-4o-mini-mem0.yaml)
# - 3 trials needed because temp>0 introduces variance
# - serial execution because P7/P8 isolate by sub_dataset, NOT by trial,
#   so we wipe qdrant/sqlite between every trial to prevent state bleed
#
# Output:
#   outputs/gemini-3.1-flash-lite-mem0-chunk512-temp07-trial${T}/Conflict_Resolution/factconsolidation_{sh,mh}_6k_*_results.json
#
# Doc: docs/baseline_methods/CRITICAL_FINDINGS_2026-05-29_evening.md F3

set -e
# bashrc is interactive-guarded — source conda init directly
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench

export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench

# Project-local HF cache (the default ~/.cache/huggingface/ is root-owned;
# the project keeps its own cache populated from prior dataset downloads)
export HF_HOME="/home/yhchiang/MemoryAgentBench/.cache/huggingface"
export HF_DATASETS_CACHE="/home/yhchiang/MemoryAgentBench/.cache/huggingface/datasets"
export HUGGINGFACE_HUB_CACHE="/home/yhchiang/MemoryAgentBench/.cache/huggingface/hub"

# Source .env for any other vars (GOOGLE_CLOUD_PROJECT, etc.) — silently
set -a
[[ -f /home/yhchiang/MemoryAgentBench/.env ]] && . /home/yhchiang/MemoryAgentBench/.env
set +a

AGENT_CFG="configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp07.yaml"
BASE_OUTPUT_DIR="./outputs/gemini-3.1-flash-lite-mem0-chunk512-temp07"

# Wipe-state helper for a given sub_dataset (sh_6k or mh_6k)
wipe_state () {
    local sd=$1
    rm -rf "/tmp/qdrant_mem0_vertex_t4__${sd}"
    rm -f  "$HOME/.mem0/history__${sd}.db"
    echo "[wipe] qdrant + sqlite state for ${sd}"
}

# Move result + retrieval log to trial-specific dir
archive_trial () {
    local sd=$1   # factconsolidation_sh_6k
    local task_short=$2  # sh_6k or mh_6k
    local trial=$3
    local trial_dir="${BASE_OUTPUT_DIR}-trial${trial}/Conflict_Resolution"
    mkdir -p "$trial_dir"
    # Result json
    local src="${BASE_OUTPUT_DIR}/Conflict_Resolution/${sd}_unknown_in*_size10_shots0_max_samplesunknown_k100_chunk512_results.json"
    # use shell glob
    for f in $src; do
        if [[ -f "$f" ]]; then
            mv "$f" "${trial_dir}/$(basename "$f")"
            echo "[archive] $f → $trial_dir/"
        fi
    done
    # rag_retrieved (per-query json + ingestion log)
    local rr_src="./outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512/k_100/${sd}"
    if [[ -d "$rr_src" ]]; then
        local rr_dst="./outputs/rag_retrieved/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512-trial${trial}/k_100"
        mkdir -p "$rr_dst"
        mv "$rr_src" "$rr_dst/${sd}"
        echo "[archive] rag_retrieved/${sd} → trial${trial}"
    fi
}

for TRIAL in 1 2 3; do
    echo "================ TRIAL ${TRIAL} ================"

    for TASK in sh_6k mh_6k; do
        SD="factconsolidation_${TASK}"
        DATA_CFG="configs/data_conf/Conflict_Resolution/Factconsolidation_${TASK}.yaml"

        echo "---- Trial ${TRIAL} :: ${SD} ----"
        wipe_state "${SD}"

        python main.py \
            --agent_config   "${AGENT_CFG}" \
            --dataset_config "${DATA_CFG}"

        archive_trial "${SD}" "${TASK}" "${TRIAL}"
        echo "---- Trial ${TRIAL} :: ${SD} DONE ----"
    done
done

echo "================ ALL DONE ================"
echo "Output dirs:"
ls -d ${BASE_OUTPUT_DIR}-trial*/ 2>/dev/null
