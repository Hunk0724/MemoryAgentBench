#!/usr/bin/env bash
# gpt-4o backbone extension @ 64k, 4 methods (+ ours prereq) sequential.
#
# Order: ours_no_p5 FIRST — main method + builds the P1 extraction cache at
#   analysis/results/p1_caches__gpt-4o/extraction_cache_p1_64k.json
# that (b) mem0+P1 reuses. Zep is independent (path A: reuses gpt-4o-mini
# cached edges, only answer LLM at gpt-4o).
#
# Full swap: MEM0_TRIPLE_MODEL=gpt-4o so P1/P2 extraction also uses gpt-4o
# (matches plan_a.sh for gpt-4.1-mini pattern; clean backbone-scaling story).
#
# Usage:
#   RUN_OAI_KEY_NAME=OPENAI_API_KEY_D bash run_gpt4o_64k_3methods.sh
#
# Optional smoke: N_ABLATION=2 to run only first 2 qids per context per method.
# Optional key: ZEP_KEY_NAME=ZEP_API_KEY_A (default) to reuse cached Zep edges.

set -uo pipefail
KEY_NAME="${RUN_OAI_KEY_NAME:-OPENAI_API_KEY_D}"
ZEP_KEY_NAME="${ZEP_KEY_NAME:-ZEP_API_KEY_A}"
export MODEL_TAG=gpt-4o
export MEM0_TRIPLE_MODEL=gpt-4o   # full swap
export RUN_OAI_KEY_NAME="$KEY_NAME"
LENGTH=64k

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "==== gpt-4o × 64k × 4 methods (ours main, b, vanilla, Zep) + ours (cache-builder) (sequential) ===="
echo "OpenAI key : \$$KEY_NAME"
echo "Zep key    : \$$ZEP_KEY_NAME"
echo "Full swap  : MEM0_TRIPLE_MODEL=$MEM0_TRIPLE_MODEL"
[ -n "${N_ABLATION:-}" ] && echo "SMOKE mode: N_ABLATION=$N_ABLATION" || echo "FULL run"
echo ""

# Methods to run — "ours" first builds cache; then main + baselines
METHODS=(
    "ours"          # 1st: builds P1 extraction cache (also gives +P5 as bonus appendix data)
    "ours_no_p5"    # main method (identity grouping + argmax)
    "b"             # (b) mem0+P1 destructive baseline (reuses ours' cache)
    "vanilla"       # vanilla mem0 native extract+update (no cache dependency)
)
for m in "${METHODS[@]}"; do
    echo ""
    echo "==== [$(date +%H:%M:%S)] gpt-4o method=$m ===="
    bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh "$LENGTH" "$m"
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "!!!! method=$m exit=$rc  ABORT (rest of sequence not run)"
        exit $rc
    fi
    echo "==== [$(date +%H:%M:%S)] method=$m DONE ===="
done

# --- Zep path A rerun (reuse gpt-4o-mini cached edges, answer LLM at gpt-4o) ---
echo ""
echo "==== [$(date +%H:%M:%S)] method=Zep (path A rerun) ===="
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
# shellcheck disable=SC1090
source "$CONDA_SH"; conda activate MABench
set -a; [ -f .env ] && . .env; set +a
export OPENAI_API_KEY="${!KEY_NAME}"
export ZEP_API_KEY="${!ZEP_KEY_NAME}"
python analysis/rerun_zep_with_ollama_backbone.py \
    --length "$LENGTH" \
    --backbone gpt-4o \
    --provider openai \
    --out-agent-name "Structure_rag_gpt-4o-zep"
echo "==== [$(date +%H:%M:%S)] method=Zep DONE ===="

echo ""
echo "==== gpt-4o × 64k × 4 methods (ours main, b, vanilla, Zep) + ours (cache-builder) COMPLETE ===="
echo "Cost logs: analysis/cost_logs/*_${MODEL_TAG}_*.jsonl"
