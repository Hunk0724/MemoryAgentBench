#!/usr/bin/env bash
# Wrapper: run any command with hardware + API monitoring sidecar.
#
# Usage:
#   scripts/run_with_monitoring.sh <run-name> "<command-line>"
#
# Example:
#   scripts/run_with_monitoring.sh A4_cold_rebuild "bash run_hipporag_gemini.sh"
#
# Outputs (under monitoring_logs/<timestamp>_<run-name>/):
#   run.log                  command stdout+stderr
#   hw_timeline.csv          per-2s hw samples + phase tag
#   api_usage.jsonl          per-API-call token counts
#   hw_phase_summary.md      generated post-run aggregation
#   manifest.json            command + git SHA + env

set -uo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <run-name> '<command-line>'" >&2
    echo "Example: $0 A4_cold_rebuild 'bash run_hipporag_gemini.sh'" >&2
    exit 1
fi

RUN_NAME="$1"
shift
CMD="$*"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TS=$(date +%Y-%m-%d_%H%M%S)
LOG_DIR="$REPO_ROOT/monitoring_logs/${TS}_${RUN_NAME}"
mkdir -p "$LOG_DIR"

RUN_LOG="$LOG_DIR/run.log"
API_LOG="$LOG_DIR/api_usage.jsonl"
MANIFEST="$LOG_DIR/manifest.json"
SIDECAR_PID_FILE="$LOG_DIR/sidecar.pid"

# Write manifest
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
GIT_DIRTY=$(git status --porcelain 2>/dev/null | wc -l)
cat > "$MANIFEST" <<JSON
{
  "run_name": "${RUN_NAME}",
  "command": "${CMD}",
  "start_time_iso": "$(date -Iseconds)",
  "git_sha": "${GIT_SHA}",
  "git_dirty_files": ${GIT_DIRTY},
  "embedding_batch_size_env": "${HIPPORAG_EMBED_BATCH_SIZE:-default}",
  "hf_home": "${HF_HOME:-default}"
}
JSON

echo "================================================================"
echo "[wrapper] Run: $RUN_NAME"
echo "[wrapper] Cmd: $CMD"
echo "[wrapper] Log dir: $LOG_DIR"
echo "[wrapper] Git SHA: $GIT_SHA (dirty files: $GIT_DIRTY)"
echo "================================================================"

# Export API usage log path so gemini_llm.py picks it up
export API_USAGE_LOG="$API_LOG"

# Make sure HF_HOME is set if not already
if [[ -z "${HF_HOME:-}" ]]; then
    export HF_HOME="$REPO_ROOT/.cache/huggingface"
fi

# Touch run.log so sidecar can tail
: > "$RUN_LOG"

# Sidecar Python — needs psutil. MABench env has it; base python3 does not.
# Override with SIDECAR_PYTHON env var if needed.
SIDECAR_PY="${SIDECAR_PYTHON:-/home/yhchiang/miniconda3/envs/MABench/bin/python}"
if [[ ! -x "$SIDECAR_PY" ]]; then
    echo "[wrapper] WARNING: $SIDECAR_PY not executable, falling back to python3" >&2
    SIDECAR_PY="python3"
fi

# Start the command in background, capture PID
bash -c "$CMD" > "$RUN_LOG" 2>&1 &
CMD_PID=$!
echo "[wrapper] Command pid: $CMD_PID"

# Start sidecar
$SIDECAR_PY "$REPO_ROOT/scripts/hw_monitor_sidecar.py" \
    --log-dir "$LOG_DIR" \
    --run-log "$RUN_LOG" \
    --target-pid "$CMD_PID" \
    --interval 2 \
    > "$LOG_DIR/sidecar.log" 2>&1 &
SIDECAR_PID=$!
echo "$SIDECAR_PID" > "$SIDECAR_PID_FILE"
echo "[wrapper] Sidecar pid: $SIDECAR_PID"

# Forward signals to command
trap 'echo "[wrapper] signal received, stopping..."; kill -TERM "$CMD_PID" "$SIDECAR_PID" 2>/dev/null; wait' INT TERM

# Wait for command
wait "$CMD_PID"
CMD_EXIT=$?

echo "[wrapper] Command exited with $CMD_EXIT"

# Stop sidecar gently
if kill -0 "$SIDECAR_PID" 2>/dev/null; then
    kill -TERM "$SIDECAR_PID"
    wait "$SIDECAR_PID" 2>/dev/null
fi

# Generate summary
echo "[wrapper] Generating summary..."
$SIDECAR_PY "$REPO_ROOT/scripts/hw_monitor_sidecar.py" \
    --log-dir "$LOG_DIR" \
    --summary-only

# Update manifest with end time + exit code
python3 -c "
import json, time, datetime
p = '$MANIFEST'
d = json.load(open(p))
d['end_time_iso'] = datetime.datetime.now().isoformat()
d['cmd_exit_code'] = $CMD_EXIT
json.dump(d, open(p, 'w'), indent=2)
"

echo "================================================================"
echo "[wrapper] DONE. Summary at:"
echo "  $LOG_DIR/hw_phase_summary.md"
echo "================================================================"

exit "$CMD_EXIT"
