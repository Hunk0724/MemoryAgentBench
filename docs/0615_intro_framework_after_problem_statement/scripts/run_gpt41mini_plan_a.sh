#!/usr/bin/env bash
# Plan A — gpt-4.1-mini backbone extension @ 64k, 5 methods sequential.
#
# Order: ours (full) FIRST — builds the P1 extraction cache at
#   analysis/results/p1_caches__gpt-4.1-mini/extraction_cache_p1_64k.json
# that ours_no_p5 / ours_struct / ours_p3_only / (b) mem0+P1 all reuse.
#
# Zep uses Zep cloud (separate runner), does not need the P1 cache.
# For gpt-4.1-mini Zep runs, we bypass the hardcoded gpt-4o-mini path in
# run_zep_fc.sh and call main.py directly with the gpt-4.1-mini Zep YAML.
#
# Usage:
#   RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash run_gpt41mini_plan_a.sh
#
# Optional smoke: N_ABLATION=2 to run only first 2 qids per context per method.

set -uo pipefail
KEY_NAME="${RUN_OAI_KEY_NAME:-OPENAI_API_KEY_A}"
export MODEL_TAG=gpt-4.1-mini
export RUN_OAI_KEY_NAME="$KEY_NAME"
LENGTH=64k

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "==== Plan A: gpt-4.1-mini x 64k x 5 methods (sequential) ===="
echo "key: \$$KEY_NAME"
[ -n "${N_ABLATION:-}" ] && echo "SMOKE mode: N_ABLATION=$N_ABLATION" || echo "FULL run"
echo ""

# --- 4 mem0-based methods ---
METHODS=(
    "ours"                    # 1st: builds P1 extraction cache
    "ours_no_p5"              # main method (P3 + argmax, no P5)
    "ours_struct"             # ablation: no P3, argmax only
    "ours_p3_only_no_struct"  # ablation: only P3 LLM grouping
    "b"                       # (b) mem0+P1 destructive baseline
)
for m in "${METHODS[@]}"; do
    echo ""
    echo "==== [$(date +%H:%M:%S)] method=$m ===="
    bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh "$LENGTH" "$m"
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "!!!!  method=$m exit=$rc  ABORT (rest of sequence not run)"
        exit $rc
    fi
    echo "==== [$(date +%H:%M:%S)] method=$m DONE ===="
done

# --- Zep (5th) — direct main.py call with gpt-4.1-mini Zep YAML ---
echo ""
echo "==== [$(date +%H:%M:%S)] method=Zep ===="
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
# shellcheck disable=SC1090
source "$CONDA_SH"; conda activate MABench
set -a; [ -f .env ] && . .env; set +a
export OPENAI_API_KEY="${!KEY_NAME}"
export PYTHONUNBUFFERED=1
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
OUTDIR="outputs/gpt-4.1-mini-zep"
mkdir -p "$OUTDIR/Conflict_Resolution" "$LOGROOT"
rm -f "$OUTDIR/Conflict_Resolution/"*sh_${LENGTH}*results*.json
python main.py \
    --agent_config "configs/agent_conf/RAG_Agents/gpt-4.1-mini/Structure_rag_gpt-4.1-mini-zep_512_temp0.yaml" \
    --dataset_config "configs/data_conf/Conflict_Resolution/Factconsolidation_sh_${LENGTH}.yaml" \
    --force \
    ${N_ABLATION:+--max_test_queries_ablation "$N_ABLATION"} \
    > "$LOGROOT/run_zep_${LENGTH}__gpt-4.1-mini.log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
    echo "!!!!  Zep exit=$rc"; exit $rc
fi
echo "==== [$(date +%H:%M:%S)] Zep DONE ===="

echo ""
echo "==== [$(date +%H:%M:%S)] Plan A COMPLETE ===="
echo ""
echo "Post-run SOP:"
echo "  1. python analysis/rigor_audit.py --length 64k"
echo "  2. If any cell != OK -> python analysis/rebuild_aggregated_from_perqid.py"
echo "  3. Update paper_current/results/pool_acc_crosstab.md with new gpt-4.1-mini row"
echo "  4. Update paper_current/style_rules_tables_figures_writing.md landscape"
