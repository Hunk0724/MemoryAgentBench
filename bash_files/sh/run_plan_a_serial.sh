#!/bin/bash
# Plan A Serial Launcher
# ──────────────────────
# Runs all 4 methods × SH/MH × {6k, 32k} = 16 cells, strictly serial.
# All temp=0 (top + mem0 internal). Single trial each. Deterministic.
#
# Order (fast → slow for quick early signal):
#   1. LCA      (no ingestion → fastest)
#   2. Mem0     (vector L1/L2 → medium)
#   3. HippoRAG-v2 vanilla (OpenIE + PPR → medium)
#   4. Mem0g-promptaware (graph extraction → slowest)
#
# Per cell:
#   - Wipe qdrant + sqlite + rag_retrieved/ingestion (prevents cross-cell leak)
#   - Run main.py
#   - Append {method, task, ctx, em, latency_sec} to _plan_a_run_log.csv
#
# Skip if result file already exists (idempotent — safe to re-run).
# CTX_GROUPS env var controls scope: "6k", "32k", or "6k 32k" (default).

set -u  # ← do NOT set -e; we want one cell failure to not abort the whole batch
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

# ───────────────── Configuration ─────────────────
CTX_GROUPS="${CTX_GROUPS:-6k 32k}"   # override with: CTX_GROUPS="6k" bash ...
LOG_CSV="_plan_a_run_log.csv"

# Cell-key → (method_label, agent_cfg, agent_dir_for_outputs, qdrant_base_path, sqlite_agent_fp)
# Use bash arrays via colon-delimited strings to keep one source-of-truth per method
# Order matters: process by speed.
# Default skips HippoRAG-v2 (requires GPU torch + NV-Embed-v2 model — see RESULTS_MASTER.md).
# To include: METHOD_ORDER_OVERRIDE="LCA Mem0 HippoRAG-v2-vanilla Mem0g-promptaware" bash ...
if [[ -n "${METHOD_ORDER_OVERRIDE:-}" ]]; then
    read -ra METHOD_ORDER <<< "$METHOD_ORDER_OVERRIDE"
else
    METHOD_ORDER=(
        "LCA"
        "Mem0"
        "Mem0g-promptaware"
    )
fi

method_agent_cfg () {
    case "$1" in
      LCA)
        echo "configs/agent_conf/Long_Context_Agents/Long_context_agent_gemini-3.1-flash-lite_temp0.yaml"
        ;;
      Mem0)
        echo "configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0.yaml"
        ;;
      HippoRAG-v2-vanilla)
        echo "configs/agent_conf/RAG_Agents/Gemini/Structure_rag_hippo_rag_v2_nv_gemini-3.1-flash-lite_temp0.yaml"
        ;;
      Mem0g-promptaware)
        echo "configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0g_promptaware_gemini-3.1-flash-lite_chunk512_temp0.yaml"
        ;;
    esac
}

method_output_dir () {
    case "$1" in
      LCA)                  echo "outputs/gemini-3.1-flash-lite-temp0";;
      Mem0)                 echo "outputs/gemini-3.1-flash-lite-mem0-chunk512-temp0";;
      HippoRAG-v2-vanilla)  echo "outputs/gemini-3.1-flash-lite-hippo_rag_v2_nv-vanilla-temp0";;
      Mem0g-promptaware)    echo "outputs/gemini-3.1-flash-lite-mem0g-promptaware-chunk512-temp0";;
    esac
}

method_agent_name () {
    case "$1" in
      LCA)                  echo "Long_context_agent_gemini-3.1-flash-lite";;
      Mem0)                 echo "Structure_rag_mem0_gemini-3.1-flash-lite_chunk512";;
      HippoRAG-v2-vanilla)  echo "Structure_rag_hippo_rag_v2_nv";;
      Mem0g-promptaware)    echo "Structure_rag_mem0g_promptaware_gemini-3.1-flash-lite_chunk512_temp0";;
    esac
}

method_chunk () {
    case "$1" in
      LCA)                  echo "4096";;  # LCA uses dataset default chunk_size
      Mem0)                 echo "512";;
      HippoRAG-v2-vanilla)  echo "512";;
      Mem0g-promptaware)    echo "512";;
    esac
}

method_retrieve () {
    case "$1" in
      LCA)                  echo "";;
      Mem0)                 echo "100";;
      HippoRAG-v2-vanilla)  echo "10";;
      Mem0g-promptaware)    echo "100";;
    esac
}

# Wipe per-cell state for mem0/mem0g (no-op for LCA / HippoRAG-v2)
wipe_state_mem0 () {
    local sd=$1
    rm -rf "/tmp/qdrant_mem0_vertex_t4__${sd}" || true
    rm -f  "$HOME/.mem0/history__${sd}.db" || true                                # pre-P8 layout
    rm -f  "$HOME/.mem0/history__${sd}__Structure_rag_mem0_"*.db || true          # post-P8 mem0 layout
}

wipe_state_mem0g_pa () {
    local sd=$1
    rm -rf "/tmp/qdrant_mem0g_promptaware_t4__${sd}" || true
    rm -f  "$HOME/.mem0/history__${sd}__Structure_rag_mem0g_promptaware_"*.db || true
    # Optionally wipe Neo4j namespace for this user_id
    cypher_user="context_0_${sd}"
    docker exec neo4j-mem0g cypher-shell -u neo4j -p mem0gpassword \
        "MATCH (n {user_id: '${cypher_user}'}) DETACH DELETE n" \
        2>/dev/null || true
}

# Wipe rag_retrieved ingestion log (prevents 24-chunk contamination bug)
wipe_rag_retrieved () {
    local agent_name=$1
    local sd=$2
    local chunk=$3
    local k=$4
    if [[ -n "$k" ]]; then
        rm -rf "outputs/rag_retrieved/${agent_name}/k_${k}/${sd}/chunksize_${chunk}/" || true
    fi
}

# CSV header (create if missing)
if [[ ! -f "$LOG_CSV" ]]; then
    echo "timestamp,method,task,ctx,em,latency_sec,status,result_path" > "$LOG_CSV"
fi

run_cell () {
    local method=$1
    local task_ctx=$2   # e.g. sh_6k, mh_32k
    local agent_cfg=$(method_agent_cfg "$method")
    local agent_name=$(method_agent_name "$method")
    local output_dir=$(method_output_dir "$method")
    local chunk=$(method_chunk "$method")
    local k=$(method_retrieve "$method")
    local sd="factconsolidation_${task_ctx}"
    local task="${task_ctx%_*}"   # sh / mh
    local ctx="${task_ctx#*_}"    # 6k / 32k

    # Glob for the result file (filename pattern differs per method —
    # LCA omits _chunk and _k; mem0/mem0g include _k100_chunk512;
    # hippo includes _k10_chunk512). Also: max_test_samples differs
    # across data_conf yamls (null → "unknown", 1 → "1"), so use a wildcard.
    local result_glob="${output_dir}/Conflict_Resolution/${sd}_unknown_in*_size10_shots0_max_samples*_results.json"

    echo
    echo "================ ${method} :: ${sd} ================"

    # Find existing result (latest match)
    local existing=$(ls -t $result_glob 2>/dev/null | head -1)
    if [[ -n "$existing" && -f "$existing" ]]; then
        em=$(python3 -c "import json; d=json.load(open('$existing')); print(f\"{d['averaged_metrics']['exact_match']:.1f}\")" 2>/dev/null || echo "n/a")
        echo "[SKIP] result exists (EM=${em}%): $existing"
        echo "$(date -Iseconds),${method},${task},${ctx},${em},0,skipped,${existing}" >> "$LOG_CSV"
        return 0
    fi

    # Wipe state per method
    case "$method" in
      Mem0)                wipe_state_mem0 "$sd";;
      Mem0g-promptaware)   wipe_state_mem0g_pa "$sd";;
      LCA|HippoRAG-v2-vanilla) ;;   # no per-cell qdrant/sqlite state
    esac
    wipe_rag_retrieved "$agent_name" "$sd" "$chunk" "$k"
    echo "[wipe] done"

    local data_cfg="configs/data_conf/Conflict_Resolution/Factconsolidation_${task_ctx}.yaml"
    local start_ts=$(date +%s)

    # Do NOT toggle set -e here: re-enabling it inside a function leaks back to
    # the caller and aborts the whole batch if any later cell fails.
    # The script intentionally avoids set -e globally so per-cell FAIL just logs.
    python main.py \
        --agent_config "$agent_cfg" \
        --dataset_config "$data_cfg"
    local exit_code=$?

    local end_ts=$(date +%s)
    local latency=$((end_ts - start_ts))

    # Glob again after main.py finishes
    local found=$(ls -t $result_glob 2>/dev/null | head -1)

    if [[ "$exit_code" -ne 0 || -z "$found" ]]; then
        echo "[FAIL] exit=${exit_code}, result missing (glob: $result_glob)"
        echo "$(date -Iseconds),${method},${task},${ctx},,${latency},FAIL_exit${exit_code},$result_glob" >> "$LOG_CSV"
        return $exit_code
    fi

    em=$(python3 -c "import json; d=json.load(open('$found')); print(f\"{d['averaged_metrics']['exact_match']:.1f}\")" 2>/dev/null || echo "?")
    echo "[OK] EM=${em}% latency=${latency}s → $found"
    echo "$(date -Iseconds),${method},${task},${ctx},${em},${latency},OK,$found" >> "$LOG_CSV"
}

# ───────────────── Main loop ─────────────────
for CTX in $CTX_GROUPS; do
    echo
    echo "########################################"
    echo "#  CTX group: ${CTX}                       "
    echo "########################################"
    for METHOD in "${METHOD_ORDER[@]}"; do
        for TASK in sh mh; do
            run_cell "$METHOD" "${TASK}_${CTX}"
        done
    done
done

echo
echo "================ Plan A serial DONE ================"
echo "Log: $LOG_CSV"
cat "$LOG_CSV" | column -t -s,
