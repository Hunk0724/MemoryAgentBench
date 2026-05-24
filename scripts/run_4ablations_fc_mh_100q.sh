#!/usr/bin/env bash
# Stage 2: Run 4 cumulative ablations × FC-MH 100Q.
#   A. vanilla                 (no Phase 2)
#   B. + Phase 2 only          (chain detection + verdict + filter)
#   C. + W3 full               (Hints + Updates + filter)
#   D. W3 minimal              (no filter + Updates only)
#
# After each run: copy results.json + dump to monitoring_logs/<ts>_ablation_<name>
# then run analysis/eval_100q_full_analysis.py to get cascade table.

set -u
cd /home/yhchiang/MemoryAgentBench

# ─── Fixed environment ───
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global
export HIPPORAG_EMBED_FP16=1
export HIPPORAG_EMBED_BATCH_SIZE=8

# Disable legacy v1 and W1 LLM-judge prototypes
export HIPPORAG_ENABLE_SUPERSESSION=0
export HIPPORAG_ENABLE_PHASE2_FILTER=0
export HIPPORAG_ENABLE_V2_DETECT=0
export HIPPORAG_ENABLE_PHASE3_SCAFFOLD=0

# Phase 2 hyperparameters (used when chain detection is ON)
export HIPPORAG_V2_PHASE2_REGION_TOPK=50
export HIPPORAG_V2_PHASE2_M=5
export HIPPORAG_V2_PHASE2_L=3
export HIPPORAG_V2_PHASE2_BEAM=8

AGENT="configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml"
DATASET_CFG="configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml"
RESULTS_FILE="outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"

BACKUP_DIR=".baseline_backup_4ablation_pre_$(date +%s)"
mkdir -p "$BACKUP_DIR"
if [ -f "$RESULTS_FILE" ]; then
    cp "$RESULTS_FILE" "$BACKUP_DIR/initial_results.json"
    echo "[setup] backed up initial results to $BACKUP_DIR/"
fi

run_ablation() {
    local name="$1"
    local p2cd="$2"      # enable_phase2_chain_detection
    local filter="$3"    # enable_phase2_filter_passages
    local enriched="$4"  # enable_phase3_v2_enriched
    local hints="$5"     # enable_phase3_v2_reasoning_hints
    local updates="$6"   # enable_phase3_v2_recent_updates
    local desc="$7"

    local ts
    ts=$(date +%Y-%m-%d_%H%M%S)
    local out_dir="monitoring_logs/${ts}_ablation_${name}"
    mkdir -p "$out_dir"

    export HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION="$p2cd"
    export HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES="$filter"
    export HIPPORAG_ENABLE_PHASE3_V2_ENRICHED="$enriched"
    export HIPPORAG_ENABLE_PHASE3_V2_HINTS="$hints"
    export HIPPORAG_ENABLE_PHASE3_V2_UPDATES="$updates"
    export HIPPORAG_PHASE2_W13_DUMP_PATH="${out_dir}/phase2_w13_dump.jsonl"
    export HIPPORAG_PHASE2_W13_VERDICT_LOG="${out_dir}/verdict_events.jsonl"

    echo ""
    echo "=================================================================="
    echo "[$(date +%H:%M:%S)] Ablation ${name}: ${desc}"
    echo "   p2cd=${p2cd} filter=${filter} enriched=${enriched} hints=${hints} updates=${updates}"
    echo "=================================================================="

    # Remove existing results to force fresh run (main.py --force ignores existing).
    if [ -f "$RESULTS_FILE" ]; then
        rm "$RESULTS_FILE"
    fi

    local started
    started=$(date +%s)
    conda run -n hipporag_env --no-capture-output python main.py \
        --agent_config "$AGENT" \
        --dataset_config "$DATASET_CFG" \
        --chunk_size_ablation 512 \
        --force 2>&1 | tail -50

    local elapsed=$(($(date +%s) - started))

    # Save results + run cascade eval
    if [ -f "$RESULTS_FILE" ]; then
        cp "$RESULTS_FILE" "${out_dir}/results.json"
        # EM tally
        local em
        em=$(python3 -c "import json; d=json.load(open('${out_dir}/results.json'))['data']; print(sum(1 for r in d if r.get('exact_match')))")
        echo ""
        echo "[ablation ${name}] EM=${em}/100, elapsed ${elapsed}s, out=${out_dir}"

        # Cascade eval (best-effort)
        python3 analysis/eval_100q_full_analysis.py "${out_dir}" 2>&1 \
            | tee "${out_dir}/cascade_eval.log" | tail -20
    else
        echo "[ablation ${name}] WARNING: no results.json produced"
    fi
}

# ─── 4 cumulative ablations ───
# A. vanilla (no Phase 2)
run_ablation A 0 0 0 0 0 "vanilla HippoRAG-v2 (no Phase 2)"

# B. + Phase 2 only (chain detect + filter passages, no W3)
run_ablation B 1 1 0 0 0 "+ Phase 2 chain detect + verdict + filter"

# C. + W3 full (Hints + Updates + filter)
run_ablation C 1 1 1 1 1 "+ W3 full (Hints+Updates+filter)"

# D. W3 minimal (no filter + Updates only)
run_ablation D 1 0 1 0 1 "W3 minimal (no filter, Updates only)"

echo ""
echo "=================================================================="
echo "[$(date +%H:%M:%S)] ALL 4 ablations done"
echo "=================================================================="
echo ""
echo "=== EM summary ==="
for name in A B C D; do
    dir=$(ls -td monitoring_logs/*_ablation_${name} 2>/dev/null | head -1)
    if [ -n "$dir" ] && [ -f "$dir/results.json" ]; then
        em=$(python3 -c "import json; d=json.load(open('$dir/results.json'))['data']; print(sum(1 for r in d if r.get('exact_match')))")
        echo "  $name (FC-MH 100Q): EM=${em}/100"
    else
        echo "  $name: NO RESULTS"
    fi
done
