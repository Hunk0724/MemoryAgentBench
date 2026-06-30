#!/bin/bash
# Phase 0 (structural) + Phase 2 (v2: improved prompt + subject guard) on FC-SH
# 32k through the REAL benchmark. Reuses yesterday's frozen triple_cache_32k.
# vanilla mem0 32k baseline (documented) = n/a.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a

LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
DCONF=configs/data_conf/Conflict_Resolution
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
STOREBASE=/home/yhchiang/MemoryAgentBench/analysis/results/expanded/stores
mkdir -p "$LOGROOT"
L=64k
export MEM0_EXTRACTION_CACHE="$PWD/analysis/results/extraction_cache_${L}.json"
export MEM0_TRIPLE_CACHE="$PWD/analysis/results/triple_cache_${L}.json"
export MEM0_SUBJECT_CACHE="$PWD/analysis/results/subject_cache_${L}.json"
export MEM0_TRIPLE_MODEL=gpt-4o-mini

run () {
  local TAG=$1 QMODE=$2 AG=$3
  export MEM0_ADD_MODE=phase0_structural
  export MEM0_QUERY_MODE=$QMODE
  export MEM0_SP_INDEX_PATH="$PWD/analysis/results/phase0/sp_index_bench_${TAG}_sh_${L}.json"
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_${TAG}"
  export MEM0_GROUPING_CACHE="$PWD/analysis/results/phase0/grouping_cache_${TAG}_sh_${L}.json"
  local OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-${TAG}"
  # fresh: store, sp_index, grouping cache (content-keyed; prompt may have changed),
  # cand log, and the result JSON (avoid the benchmark resume-skip).
  rm -rf "$MEM0_CAND_LOG_DIR" "$MEM0_SP_INDEX_PATH" "$MEM0_GROUPING_CACHE" \
         "$STOREBASE/qdrant_gpt4o_512_openai_${TAG}__factconsolidation_sh_${L}" \
         "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
  mkdir -p "$MEM0_CAND_LOG_DIR"
  echo "================ $TAG (query=$QMODE) sh_${L} ================"
  python main.py --agent_config "$AGDIR/$AG" \
    --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
    > "$LOGROOT/run_${TAG}_${L}.log" 2>&1
  echo "[$TAG] exit=$?"
  python3 -c "
import json,glob
fs=glob.glob('$OUTDIR/**/*sh_${L}*results*.json',recursive=True)
if fs:
    rows=json.load(open(fs[0])).get('data')
    em=sum(1 for x in rows if x.get('exact_match')); print(f'$TAG EM {em}/{len(rows)} = {em/len(rows)*100:.1f}%')
"
}

run phase0 structural Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase0.yaml
run phase2 phase2     Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase2.yaml
echo "================ DONE FC-SH 32k (vanilla baseline = n/a) ================"
