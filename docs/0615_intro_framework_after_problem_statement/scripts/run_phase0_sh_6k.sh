#!/bin/bash
# Phase 0 (0615) vs vanilla on FC-SH 6k, through the REAL benchmark (main.py).
# Same gpt-4o-mini backbone, OpenAI text-embedding-3-small, L2 frozen extraction,
# top-100 retrieval, IDENTICAL FC inference prompt + scorer. ONLY the memory-side
# differs: vanilla = mem0 default update; phase0 = conservative ADD + (S,P) triple
# index (write) + group/temporal-resolve (query), gated by MEM0_ADD_MODE.
set -u
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
LME_DATA_DIR="${LME_DATA_DIR:-$REPO_ROOT/data/longmemeval}"
export LME_DATA="${LME_DATA:-$LME_DATA_DIR/longmemeval_s_cleaned.json}"
source "$CONDA_SH"
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd $REPO_ROOT
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
DCONF=configs/data_conf/Conflict_Resolution
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
STOREBASE=$REPO_ROOT/analysis/results/expanded/stores
mkdir -p "$LOGROOT"
L=6k
export MEM0_EXTRACTION_CACHE="$PWD/analysis/results/extraction_cache_${L}.json"
export MEM0_TRIPLE_CACHE="$PWD/analysis/results/triple_cache_${L}.json"
export MEM0_TRIPLE_MODEL=gpt-4o-mini

run () {
  local TAG=$1 AG=$2 MODE=$3 STORE=$4
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_${TAG}"
  rm -rf "$MEM0_CAND_LOG_DIR"; mkdir -p "$MEM0_CAND_LOG_DIR"
  rm -rf "${STORE}__factconsolidation_sh_${L}"
  if [[ "$MODE" == "phase0" ]]; then
    export MEM0_ADD_MODE=phase0_structural
    export MEM0_QUERY_MODE=structural
    export MEM0_SP_INDEX_PATH="$PWD/analysis/results/phase0/sp_index_bench_sh_${L}.json"
    rm -f "$MEM0_SP_INDEX_PATH"
  else
    unset MEM0_ADD_MODE; unset MEM0_QUERY_MODE; unset MEM0_SP_INDEX_PATH || true
  fi
  echo "================ $TAG (mode=$MODE) sh_${L} ================"
  python main.py --agent_config "$AGDIR/$AG" \
    --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
    > "$LOGROOT/run_${TAG}_${L}.log" 2>&1
  echo "[$TAG] exit=$? | $(grep -iE 'exact_match|accuracy|EM' "$LOGROOT/run_${TAG}_${L}.log" | tail -2)"
}

run phase0        Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase0.yaml phase0  "$STOREBASE/qdrant_gpt4o_512_openai_phase0"
run vanilla_rerun Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun.yaml vanilla "$STOREBASE/qdrant_gpt4o_512_openai_rerun_p0cmp"
echo "================ DONE FC-SH 6k ================"
