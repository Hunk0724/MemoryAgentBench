#!/bin/bash
# Mem0g-prompt-aware × FC-{SH,MH} × 6k × temp=0.7 × 1 trial
# Smoke + initial pilot:
#   - 1 trial (not 3) to verify the prompt-aware verbalize logic before scaling
#   - serial SH then MH (Neo4j namespace is by user_id so different sub_dataset
#     uses different namespace; but we stay serial to keep Vertex API load low
#     while b9nad0ox1 mem0 temp=0.7 is also running)
#   - independent qdrant/sqlite/neo4j paths from b9nad0ox1 (see yaml)
#
# After SH 6k completes, peek at first query json to confirm
# system_prompt contains "Relationships:" — that's the smoke-pass signal.

set -e
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench

export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench

export HF_HOME="/home/yhchiang/MemoryAgentBench/.cache/huggingface"
export HF_DATASETS_CACHE="/home/yhchiang/MemoryAgentBench/.cache/huggingface/datasets"
export HUGGINGFACE_HUB_CACHE="/home/yhchiang/MemoryAgentBench/.cache/huggingface/hub"

set -a
[[ -f /home/yhchiang/MemoryAgentBench/.env ]] && . /home/yhchiang/MemoryAgentBench/.env
set +a

AGENT_CFG="configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0g_promptaware_gemini-3.1-flash-lite_chunk512_temp07.yaml"

# Wipe-state helper (prevents bleed if rerun)
wipe_state () {
    local sd=$1
    local fp="Structure_rag_mem0g_promptaware_gemini_3_1_flash"  # P8 agent_name fp (re.sub then [:48].strip('_'))
    rm -rf "/tmp/qdrant_mem0g_promptaware_t4__${sd}"
    rm -f  "$HOME/.mem0/history__${sd}__${fp}.db"
    echo "[wipe] qdrant + sqlite state for ${sd} / ${fp}"
}

for TASK in sh_6k mh_6k; do
    SD="factconsolidation_${TASK}"
    DATA_CFG="configs/data_conf/Conflict_Resolution/Factconsolidation_${TASK}.yaml"

    echo "================ Mem0g-promptaware :: ${SD} ================"
    wipe_state "${SD}"

    python main.py \
        --agent_config   "${AGENT_CFG}" \
        --dataset_config "${DATA_CFG}"

    echo "================ ${SD} DONE ================"

    if [[ "$TASK" == "sh_6k" ]]; then
        # Smoke check: SH 6k must save retrieval json with "Relationships:" in system_prompt
        RR_DIR="outputs/rag_retrieved/Structure_rag_mem0g_promptaware_gemini-3.1-flash-lite_chunk512_temp07/k_100/${SD}/chunksize_512"
        FIRST_Q=$(ls -t ${RR_DIR}/query_*.json 2>/dev/null | head -1)
        if [[ -n "$FIRST_Q" ]]; then
            if grep -q "Relationships:" "$FIRST_Q"; then
                echo "[SMOKE PASS] $FIRST_Q contains 'Relationships:' in system_prompt"
            else
                echo "[SMOKE FAIL] $FIRST_Q does NOT contain 'Relationships:' — prompt_aware flag may not be wiring"
                head -20 "$FIRST_Q" || true
                exit 2
            fi
        else
            echo "[SMOKE WARN] no per-query json found at ${RR_DIR}"
        fi
    fi
done

echo "================ ALL DONE ================"
