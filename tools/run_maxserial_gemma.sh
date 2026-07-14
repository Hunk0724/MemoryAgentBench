#!/bin/bash
# Task F wrapper — Don't Ask (maxserial_theircode.py) × gemma tier.
# Sources .env INTERNALLY (project convention) so the caller never materializes it:
#   - OPENAI_API_KEY  -> embedding (text-embedding-3-small); bank_emb cache + query embeds
#   - OLLAMA_CHAT_URL -> dual-client mode (chat.completions -> local Ollama gemma)
# Usage: bash tools/run_maxserial_gemma.sh <gemma3:SIZE> [extra maxserial args e.g. --limit 5]
set -u
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
set -a; [ -f .env ] && . .env; set +a
: "${OPENAI_API_KEY:=${OPENAI_API_KEY_A:-${OPENAI_API_KEY_FOR_GX10:-}}}"
export OPENAI_API_KEY
[ -n "$OPENAI_API_KEY" ] && echo "[wrap] OPENAI_API_KEY: SET" || echo "[wrap] OPENAI_API_KEY: UNSET (embed will fail)"
export OLLAMA_CHAT_URL="${OLLAMA_CHAT_URL:-http://localhost:11434/v1}"
export PIPELINE_MODEL="${1:?need gemma3:SIZE}"; shift
source "$HOME/miniconda3/etc/profile.d/conda.sh" && conda activate MABench
echo "[wrap] PIPELINE_MODEL=$PIPELINE_MODEL  chat=$OLLAMA_CHAT_URL  length=6k  extra=$*"
exec python docs/0615_intro_framework_after_problem_statement/scripts/maxserial_theircode.py --length 6k "$@"
