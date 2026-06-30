#!/bin/bash
# FC-SH 262k: phase0 + phase2 (ours) + vanilla, through the real benchmark.
# ours ingestion completes the partial triple_cache_262k (live calls for the
# ~12k uncached facts on the FIRST ours run, then frozen). vanilla does live
# destructive update (~531 LLM calls). Long run (~1-2h); ours first.
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
L=262k
export MEM0_EXTRACTION_CACHE="$PWD/analysis/results/extraction_cache_${L}.json"
export MEM0_TRIPLE_CACHE="$PWD/analysis/results/triple_cache_${L}.json"
export MEM0_SUBJECT_CACHE="$PWD/analysis/results/subject_cache_${L}.json"
export MEM0_TRIPLE_MODEL=gpt-4o-mini

run () {
  local TAG=$1 AG=$2 PREFIX=$3 ADD=$4 QMODE=$5
  if [[ -n "$ADD" ]]; then export MEM0_ADD_MODE=$ADD; else unset MEM0_ADD_MODE; fi
  if [[ -n "$QMODE" ]]; then export MEM0_QUERY_MODE=$QMODE; else unset MEM0_QUERY_MODE; fi
  export MEM0_SP_INDEX_PATH="$PWD/analysis/results/phase0/sp_index_${TAG}_sh_${L}.json"
  export MEM0_GROUPING_CACHE="$PWD/analysis/results/phase0/grouping_cache_${TAG}_sh_${L}.json"
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_${TAG}"
  local OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-${TAG}"
  rm -rf "$MEM0_CAND_LOG_DIR" "$MEM0_SP_INDEX_PATH" "$MEM0_GROUPING_CACHE" \
         "$STOREBASE/qdrant_gpt4o_512_openai_${PREFIX}__factconsolidation_sh_${L}" \
         "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
  mkdir -p "$MEM0_CAND_LOG_DIR"
  echo "================ $TAG sh_${L} (add=${ADD:-none} query=${QMODE:-none}) ================"
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

run phase0  Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase0.yaml phase0 phase0_structural structural
run phase2  Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase2.yaml phase2 phase0_structural phase2
run vanilla Structure_rag_gpt-4o-mini-mem0_l2_512_openai_rerun.yaml  rerun  "" ""
echo "================ DONE FC-SH 262k ================"
