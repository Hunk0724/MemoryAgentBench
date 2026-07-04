#!/bin/bash
# Project run-wrapper (same env pattern as run_fc_sh.sh): conda + source .env,
# then run the no_p5 per-query Resolution dump (Figure C data). Uses this
# machine's key OPENAI_API_KEY_FOR_GX10 (from .env) for embedding — key USED,
# never printed. P3 groups are cache-hit -> no gemma call.
#   bash tools/run_resolution_per_query_no_p5.sh [sizes...]
set -u
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
source "$CONDA_SH"; conda activate MABench
cd "$REPO_ROOT"
set -a; [[ -f .env ]] && . .env; set +a
python docs/0615_intro_framework_after_problem_statement/scripts/compute_resolution_per_query_no_p5.py "$@"
