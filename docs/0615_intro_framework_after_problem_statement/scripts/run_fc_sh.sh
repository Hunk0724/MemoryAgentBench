#!/bin/bash
# Parametrized FC-SH runner (one script for all lengths/methods; parallel-safe).
#   Usage:  RUN_OAI_KEY="$OPENAI_API_KEY_B" bash run_fc_sh.sh <L> <method>
#     L      = 6k | 32k | 64k | 262k
#     method = ours | vanilla
#   - ours    : P1 unified extractor + phase0 conservative write + phase2 query
#               resolution + raw-q retrieval + batch embedding (the defined method)
#   - vanilla : stock mem0 (native extraction, destructive update) + raw-q (ungated)
# Per-run isolated store/caches/cost-log keyed by <method>_<L> -> safe to run many
# in parallel, each with its own OpenAI key (RUN_OAI_KEY) so rate limits don't collide.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a

# per-run API key (override so parallel runs don't share quota). Two ways:
#   RUN_OAI_KEY_NAME=OPENAI_API_KEY_A  -> resolved from .env here (robust; preferred)
#   RUN_OAI_KEY=sk-...                 -> literal key
if [[ -n "${RUN_OAI_KEY_NAME:-}" ]]; then
  export OPENAI_API_KEY="${!RUN_OAI_KEY_NAME}"
  echo "[key] using \$$RUN_OAI_KEY_NAME ...${OPENAI_API_KEY: -6}"
elif [[ -n "${RUN_OAI_KEY:-}" ]]; then
  export OPENAI_API_KEY="$RUN_OAI_KEY"
  echo "[key] using literal key ...${RUN_OAI_KEY: -6}"
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then echo "[key] ERROR: no OPENAI_API_KEY resolved"; exit 1; fi

L="${1:?need L (6k|32k|64k|262k)}"
METHOD="${2:?need method (ours|vanilla)}"
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
DCONF=configs/data_conf/Conflict_Resolution
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
STOREBASE=/home/yhchiang/MemoryAgentBench/analysis/results/expanded/stores
PC=$PWD/analysis/results/p1_caches
mkdir -p "$LOGROOT" "$PC" "$PWD/analysis/results/phase0"

# cost/latency log (env-gated instrumentation; fresh per run)
export MEM0_COST_LOG="$LOGROOT/cost_${METHOD}_${L}.jsonl"
: > "$MEM0_COST_LOG"

if [[ "$METHOD" == "ours" ]]; then
  TAG=unified
  AG=Structure_rag_gpt-4o-mini-mem0_512_openai_unified.yaml
  STORE="qdrant_gpt4o_512_openai_unified__factconsolidation_sh_${L}"
  export MEM0_TRIPLE_MODEL=gpt-4o-mini
  export MEM0_EXTRACTION_CACHE="$PC/extraction_cache_p1_${L}.json"
  export MEM0_TRIPLE_CACHE="$PC/triple_cache_p1_${L}.json"
  export MEM0_SUBJECT_CACHE="$PC/subject_cache_p1_${L}.json"
  export MEM0_GROUPING_CACHE="$PC/grouping_cache_p1_${L}.json"
  export MEM0_CONFLICT_CACHE="$PC/conflict_cache_p1_${L}.json"
  export MEM0_SP_INDEX_PATH="$PWD/analysis/results/phase0/sp_index_p1_sh_${L}.json"
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_p1"
  export MEM0_ADD_MODE=phase0_structural
  export MEM0_QUERY_MODE=phase2
  OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified"
  rm -rf "$MEM0_CAND_LOG_DIR" "$MEM0_SP_INDEX_PATH" "$MEM0_GROUPING_CACHE" \
         "$MEM0_CONFLICT_CACHE" "$STOREBASE/$STORE" \
         "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
  ANSDIR="outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified/k_100/factconsolidation_sh_${L}/chunksize_512"
elif [[ "$METHOD" == "b" ]]; then
  # mem0(b): P1 extraction HELD FIXED (reuse ours' p1 extraction cache, read-only)
  # + mem0 DESTRUCTIVE update (no phase env). Isolates write-time-update loss.
  TAG=unified_dest
  AG=Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest.yaml
  STORE="qdrant_gpt4o_512_openai_unified_dest__factconsolidation_sh_${L}"
  export MEM0_EXTRACTION_CACHE="$PC/extraction_cache_p1_${L}.json"   # held-fixed P1
  unset MEM0_ADD_MODE MEM0_QUERY_MODE MEM0_TRIPLE_CACHE             # destructive update
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_b"
  OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest"
  rm -rf "$MEM0_CAND_LOG_DIR" "$STOREBASE/$STORE" \
         "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
  ANSDIR="outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/factconsolidation_sh_${L}/chunksize_512"
else
  TAG=native
  AG=Structure_rag_gpt-4o-mini-mem0_512_openai_native.yaml
  STORE="qdrant_gpt4o_512_openai_native__factconsolidation_sh_${L}"
  # vanilla: native extraction + destructive update; NO phase env, NO p1 caches.
  unset MEM0_ADD_MODE MEM0_QUERY_MODE MEM0_EXTRACTION_CACHE MEM0_TRIPLE_CACHE
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_native"
  OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-native"
  rm -rf "$MEM0_CAND_LOG_DIR" "$STOREBASE/$STORE" \
         "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
  ANSDIR="outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_native/k_100/factconsolidation_sh_${L}/chunksize_512"
fi
mkdir -p "$MEM0_CAND_LOG_DIR"

echo "================ $METHOD FC-SH ${L} ================"; date
python main.py --agent_config "$AGDIR/$AG" \
  --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
  > "$LOGROOT/run_${METHOD}_${L}.log" 2>&1
echo "[$METHOD ${L}] exit=$?"; date

echo "---- EM ----"
python3 -c "
import json, glob
fs = glob.glob('$OUTDIR/**/*sh_${L}*results*.json', recursive=True)
if fs:
    rows = json.load(open(fs[0]))['data']; em = sum(1 for x in rows if x.get('exact_match'))
    print(f'$METHOD FC-SH ${L}: EM {em}/{len(rows)} = {em/len(rows)*100:.1f}%')
"
echo "---- cost ----"
python3 docs/0615_intro_framework_after_problem_statement/scripts/summarize_cost.py "$MEM0_COST_LOG" "$ANSDIR"
echo "================ DONE $METHOD ${L} ================"
