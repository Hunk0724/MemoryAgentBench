#!/usr/bin/env bash
# Wrapper: run Zep(only-return-fact) diagnostic for one length.
#
# Usage:
#   RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_.../scripts/run_zep_edges_only.sh 6k
#   RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_.../scripts/run_zep_edges_only.sh 6k --limit 5
#
# Cost per full length: ~$0.10 (74-66 gpt-4o-mini calls)

set -euo pipefail

L="${1:?usage: bash run_zep_edges_only.sh <6k|32k|64k> [--limit N]}"
shift || true

# Locate repo root from script path
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
cd "$REPO_ROOT"

# Load env (assumes .env exports OPENAI_API_KEY_A..E). We NEVER read/print keys.
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$REPO_ROOT/.env"
    set +a
fi

KEY_NAME="${RUN_OAI_KEY_NAME:-OPENAI_API_KEY_A}"
# Indirect expand: OPENAI_API_KEY=$KEY_NAME_value (bash indirect)
export OPENAI_API_KEY="${!KEY_NAME:?RUN_OAI_KEY_NAME=$KEY_NAME not set in env}"

# Activate MABench (miniforge or miniconda)
if [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
    # shellcheck disable=SC1091
    . "$HOME/miniforge3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    # shellcheck disable=SC1091
    . "$HOME/miniconda3/etc/profile.d/conda.sh"
fi
conda activate MABench

echo "==> Zep(edges-only) diagnostic: L=$L  extra_args=$*"
python "$REPO_ROOT/analysis/rerun_zep_edges_only.py" --length "$L" "$@"
