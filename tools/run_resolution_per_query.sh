#!/bin/bash
# Project run-wrapper (same env pattern as run_fc_sh.sh): activate conda + source
# .env, then run the per-query pool-based Resolution dump. Uses this machine's key
# OPENAI_API_KEY_FOR_GX10 (from .env) for embedding — key is USED, never printed.
#   bash tools/run_resolution_per_query.sh [sizes...]
set -u
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
source "$CONDA_SH"; conda activate MABench
cd "$REPO_ROOT"
set -a; [[ -f .env ]] && . .env; set +a
python docs/0615_intro_framework_after_problem_statement/scripts/compute_resolution_per_query_6k.py "$@"
