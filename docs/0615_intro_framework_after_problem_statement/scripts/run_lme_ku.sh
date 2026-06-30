#!/bin/bash
# LongMemEval-KU runner over OUR mem0 pipeline (one SHARD), then optional judge.
#   Usage: RUN_OAI_KEY_NAME=OPENAI_API_KEY_A SHARD=0 NSHARD=4 \
#            bash run_lme_ku.sh <method> [limit] [judge]
#     method = ours | b | vanilla        (zep handled separately)
#     limit  = 0 (all 78 KU) or N for smoke
#     judge  = 1 to run official evaluate_qa.py on THIS shard's hyp (default 0;
#              for sharded runs judge the concatenated hyp via the orchestrator)
#   SHARD/NSHARD (env): split the 78 KU questions across NSHARD parallel processes
#     (idx % NSHARD == SHARD). Each shard gets its OWN sub_dataset suffix -> its own
#     qdrant store + caches + hyp file, so concurrent processes never collide.
# Mirrors run_fc_sh.sh's env recipe; LongMemEval-specific isolation.
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

if [[ -n "${RUN_OAI_KEY_NAME:-}" ]]; then
  export OPENAI_API_KEY="${!RUN_OAI_KEY_NAME}"
  echo "[key] using \$$RUN_OAI_KEY_NAME ...${OPENAI_API_KEY: -6}"
fi
[[ -z "${OPENAI_API_KEY:-}" ]] && { echo "[key] ERROR: no OPENAI_API_KEY"; exit 1; }

METHOD="${1:?need method (ours|b|vanilla)}"
LIMIT="${2:-0}"
JUDGE="${3:-0}"
SHARD="${SHARD:-0}"
NSHARD="${NSHARD:-1}"
SHARDSFX=""
[[ "$NSHARD" -gt 1 ]] && SHARDSFX="_s${SHARD}n${NSHARD}"

DATA=$LME_DATA_DIR/longmemeval_s_cleaned.json
JUDGE_PY=$REPO_ROOT/llm_based_eval/evaluate_qa_official.py
SUBDS="longmemeval_s_ku${SHARDSFX}"
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
HYPDIR=docs/0615_intro_framework_after_problem_statement/lme_hyps
STOREBASE=$REPO_ROOT/analysis/results/expanded/stores
PC=$PWD/analysis/results/p1_caches/lme
mkdir -p "$LOGROOT" "$PC" "$HYPDIR" "$PWD/analysis/results/phase0"

export MEM0_COST_LOG="$LOGROOT/cost_lme_${METHOD}${SHARDSFX}.jsonl"; : > "$MEM0_COST_LOG"

if [[ "$METHOD" == "ours" ]]; then
  AG=Structure_rag_gpt-4o-mini-mem0_512_openai_unified.yaml
  export MEM0_TRIPLE_MODEL=gpt-4o-mini
  export MEM0_EXTRACTION_CACHE="$PC/extraction_ours${SHARDSFX}.json"
  export MEM0_TRIPLE_CACHE="$PC/triple_ours${SHARDSFX}.json"
  export MEM0_SUBJECT_CACHE="$PC/subject_ours${SHARDSFX}.json"
  export MEM0_GROUPING_CACHE="$PC/grouping_ours${SHARDSFX}.json"
  export MEM0_CONFLICT_CACHE="$PC/conflict_ours${SHARDSFX}.json"
  # global (S,P) inverted index (MEM0_SP_INDEX_PATH) intentionally UNSET — ours'
  # phase2 query builds its (S,P) map on-the-fly from per-candidate triple metadata
  # and never reads the global index (only phase0_query hybrid_retrieve uses it).
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/lme_ours${SHARDSFX}_p1"
  export MEM0_ADD_MODE=phase0_structural
  export MEM0_QUERY_MODE=phase2
  rm -rf "$MEM0_CAND_LOG_DIR" "$MEM0_GROUPING_CACHE" "$MEM0_CONFLICT_CACHE" \
         "$MEM0_SUBJECT_CACHE" "$MEM0_EXTRACTION_CACHE" "$MEM0_TRIPLE_CACHE"
elif [[ "$METHOD" == "b" ]]; then
  AG=Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest.yaml
  export MEM0_TRIPLE_MODEL=gpt-4o-mini
  export MEM0_EXTRACTION_CACHE="$PC/extraction_ours${SHARDSFX}.json"  # held-fixed P1 (reuse ours' shard cache)
  unset MEM0_ADD_MODE MEM0_QUERY_MODE MEM0_TRIPLE_CACHE
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/lme_b${SHARDSFX}_p1"
  rm -rf "$MEM0_CAND_LOG_DIR"
else  # vanilla
  AG=Structure_rag_gpt-4o-mini-mem0_512_openai_native.yaml
  unset MEM0_ADD_MODE MEM0_QUERY_MODE MEM0_EXTRACTION_CACHE MEM0_TRIPLE_CACHE
  export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/lme_vanilla${SHARDSFX}_p1"
  rm -rf "$MEM0_CAND_LOG_DIR"
fi
mkdir -p "$MEM0_CAND_LOG_DIR"

# fresh store for this method+shard. agent.py:273 suffixes the yaml `path:` field
# (NOT collection_name) with __<sub_dataset>, and isolates history.db per
# <sub_dataset>__<agent_fp>. Clean both so a re-run starts empty.
BASEPATH=$(grep -oP '^\s*path:\s*\K\S+' "$AGDIR/$AG" | head -1)
rm -rf "${BASEPATH}__${SUBDS}" 2>/dev/null
rm -f "$HOME/.mem0/history__${SUBDS}__"*.db 2>/dev/null

HYP="$HYPDIR/lme_ku_${METHOD}${SHARDSFX}.jsonl"
[[ "$LIMIT" != "0" ]] && HYP="$HYPDIR/lme_ku_${METHOD}_smoke${LIMIT}.jsonl"
rm -f "$HYP"
HYP_ABS="$PWD/$HYP"

echo "================ LME-KU $METHOD shard $SHARD/$NSHARD (limit=$LIMIT) ================"; date
python docs/0615_intro_framework_after_problem_statement/scripts/run_longmemeval_ku.py \
  --agent_config "$AGDIR/$AG" --data "$DATA" --out "$HYP" \
  --sub_dataset "$SUBDS" --qtype knowledge-update --limit "$LIMIT" \
  --shard "$SHARD" --nshard "$NSHARD"
RC=$?
date; echo "[lme $METHOD shard $SHARD/$NSHARD] gen exit=$RC"
[[ $RC -ne 0 ]] && exit $RC

JUDGE_MODEL="${JUDGE_MODEL:-gpt-4o-mini}"   # cheap for validation; gpt-4o for paper-final
if [[ "$JUDGE" == "1" ]]; then
  echo "---- official judge ($JUDGE_MODEL; paper-final=gpt-4o) ----"
  ( cd "$(dirname "$JUDGE_PY")" && OPENAI_API_KEY="$OPENAI_API_KEY" python "$(basename "$JUDGE_PY")" "$JUDGE_MODEL" "$HYP_ABS" "$DATA" ) \
    2>&1 || echo "[judge] failed (deps? run separately)"
fi
echo "================ DONE LME-KU $METHOD shard $SHARD/$NSHARD ================"
