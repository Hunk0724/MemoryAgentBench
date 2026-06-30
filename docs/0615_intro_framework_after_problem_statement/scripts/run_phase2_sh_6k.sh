#!/bin/bash
# Phase 2 (0615) on FC-SH 6k through the REAL benchmark (main.py).
# Same write-time as Phase 0 (conservative ADD + (S,P) triple); query-time adds
# conditional routing + LLM dynamic grouping. Same backbone/embedder/retrieval/
# inference prompt/scorer as vanilla — only memory selection differs.
#
# Mode matrix (reproducibility):
#   vanilla     : MEM0_ADD_MODE unset            , MEM0_QUERY_MODE unset
#   ablation A1 : MEM0_ADD_MODE=phase0_structural, MEM0_QUERY_MODE unset   (conservative store, raw retrieval)
#   phase0      : MEM0_ADD_MODE=phase0_structural, MEM0_QUERY_MODE=structural
#   phase2      : MEM0_ADD_MODE=phase0_structural, MEM0_QUERY_MODE=phase2
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

# Phase 2 flags
export MEM0_ADD_MODE=phase0_structural
export MEM0_QUERY_MODE=phase2
export MEM0_SP_INDEX_PATH="$PWD/analysis/results/phase0/sp_index_bench_p2_sh_${L}.json"
export MEM0_GROUPING_CACHE="$PWD/analysis/results/phase0/grouping_cache_sh_${L}.json"
export MEM0_SUBJECT_CACHE="$PWD/analysis/results/subject_cache_${L}.json"
export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_phase2"
# Grouping cache is content-keyed: invalidate it whenever the grouping prompt
# changes (same contents + new prompt must NOT reuse old clusters).
rm -rf "$MEM0_CAND_LOG_DIR" "$MEM0_SP_INDEX_PATH" "$MEM0_GROUPING_CACHE" \
       "$STOREBASE/qdrant_gpt4o_512_openai_phase2__factconsolidation_sh_${L}" \
       outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-phase2/Conflict_Resolution/*sh_${L}*results*.json
mkdir -p "$MEM0_CAND_LOG_DIR"

echo "================ phase2 sh_${L} ================"
python main.py --agent_config "$AGDIR/Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase2.yaml" \
  --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
  > "$LOGROOT/run_phase2_${L}.log" 2>&1
echo "[phase2] exit=$? | $(grep -iE 'exact_match|accuracy' "$LOGROOT/run_phase2_${L}.log" | tail -2)"
python3 -c "
import json,glob
for f in glob.glob('outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-phase2/**/*sh_${L}*results*.json',recursive=True):
    d=json.load(open(f)); data=d.get('data',d)
    em=sum(1 for x in data if x.get('exact_match')); print(f'phase2 EM {em}/{len(data)} = {em/len(data)*100:.1f}%')
"
echo "================ DONE ================"
