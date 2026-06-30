#!/bin/bash
# Serial Gemma weak-model regime runner — for each model SIZE:
#   1. ollama pull + warm up
#   2. start resource sampler in background
#   3. for L in 6k 32k 64k:
#        run_fc_sh.sh L ours       (writes extraction cache for this size+L)
#        run_fc_sh.sh L ours_struct (reuses cache; structural-only ablation)
#   4. stop sampler, stop model, verify unloaded
# Then move to next SIZE. Each model isolated by MODEL_TAG (stores/caches/outputs
# all suffixed with __gemma3-<size>) — no collision with OpenAI cells.
#
# Usage:
#   bash tools/run_gemma_matrix.sh           # all sizes 1b → 4b → 12b → 27b
#   SIZES="1b 4b" bash tools/run_gemma_matrix.sh   # subset
#   LENGTHS="6k 32k" bash tools/run_gemma_matrix.sh
#
# Required env (from .env):
#   OPENAI_API_KEY_A — used for OpenAI embedding (text-embedding-3-small)
#
# Prereqs (must be done manually before first run; this script does NOT install):
#   - ollama installed and ollama daemon running (ollama serve)
#   - models pulled (or this script will pull on first use)
#   - MABench conda env activated by entering this script
set -u
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
source "$CONDA_SH"
conda activate MABench
cd "$REPO_ROOT"
set -a; [[ -f .env ]] && . .env; set +a

# OpenAI for embedding (kept unchanged across sizes)
export OPENAI_API_KEY="${OPENAI_API_KEY_A:?need OPENAI_API_KEY_A in .env for embedding}"
echo "[setup] OpenAI key A loaded for embedding"

# Ollama settings (defaults; override via env if needed)
export MEM0_TRIPLE_OLLAMA_URL="${MEM0_TRIPLE_OLLAMA_URL:-http://localhost:11434}"
export OLLAMA_NUM_CTX="${OLLAMA_NUM_CTX:-8192}"

# Sanity: Ollama daemon up?
if ! curl -s --max-time 2 "$MEM0_TRIPLE_OLLAMA_URL/api/version" >/dev/null; then
  echo "[error] Ollama daemon not reachable at $MEM0_TRIPLE_OLLAMA_URL"
  echo "        run 'ollama serve' (or open Ollama.app) first, then re-run this script."
  exit 1
fi
echo "[setup] Ollama daemon reachable at $MEM0_TRIPLE_OLLAMA_URL"

# Matrix axes (override via env). Default order: 1b smoke first,
# then 12b (mid baseline) → 4b (low) → 27b (capstone).
SIZES="${SIZES:-1b 12b 4b 27b}"
LENGTHS="${LENGTHS:-6k 32k 64k}"
METHODS="${METHODS:-ours ours_struct}"

# Output / log roots
LOGROOT="docs/0615_intro_framework_after_problem_statement/logs"
RESROOT="docs/0615_intro_framework_after_problem_statement/logs/gemma_resource"
mkdir -p "$LOGROOT" "$RESROOT"
TS=$(date +%Y%m%d_%H%M%S)
MATRIX_LOG="$LOGROOT/gemma_matrix_${TS}.log"

# Summary table (printed at end + saved as md)
SUMMARY_MD="$LOGROOT/gemma_matrix_${TS}_summary.md"
{
  echo "# Gemma weak-model matrix — run $TS"
  echo
  echo "| Size | Length | Method | exit | EM | runtime |"
  echo "| :---: | :---: | :---: | :---: | :---: | :---: |"
} > "$SUMMARY_MD"

run_one_cell() {
  local SIZE="$1" L="$2" METHOD="$3"
  local MODEL="gemma3:$SIZE"
  local MODEL_TAG="gemma3-$SIZE"
  local CELL_START=$(date +%s)

  export MEM0_TRIPLE_MODEL="$MODEL"
  export MODEL_TAG
  echo "[$(date +%H:%M:%S)] >>> CELL  size=$SIZE  L=$L  method=$METHOD" | tee -a "$MATRIX_LOG"

  bash "$REPO_ROOT/docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh" "$L" "$METHOD" 2>&1 \
    | tee -a "$MATRIX_LOG" | tail -8
  local RC=${PIPESTATUS[0]}

  # EM 從 OUTDIR results.json 算出
  local OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified"
  [ "$METHOD" = "ours_struct" ] && OUTDIR="${OUTDIR}_struct"
  [ "$METHOD" = "b" ] && OUTDIR="${OUTDIR}_dest"
  [ "$METHOD" = "vanilla" ] && OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-native"
  OUTDIR="${OUTDIR}__${MODEL_TAG}"

  local RES_FILE
  RES_FILE=$(ls "$REPO_ROOT/$OUTDIR"/Conflict_Resolution/*sh_${L}*results*.json 2>/dev/null | head -1)
  local EM_STR="?"
  if [ -n "$RES_FILE" ]; then
    EM_STR=$(python3 -c "
import json
d = json.load(open('$RES_FILE'))['data']
em = sum(1 for x in d if x.get('exact_match'))
print(f'{em}/{len(d)}')
" 2>/dev/null || echo "?")
  fi

  local CELL_DUR=$(( $(date +%s) - CELL_START ))
  local CELL_MIN=$(( CELL_DUR / 60 ))
  echo "[$(date +%H:%M:%S)] <<< CELL done  rc=$RC  EM=$EM_STR  ${CELL_MIN}min" | tee -a "$MATRIX_LOG"
  echo "| $SIZE | $L | $METHOD | $RC | $EM_STR | ${CELL_MIN}min |" >> "$SUMMARY_MD"
}

for SIZE in $SIZES; do
  MODEL="gemma3:$SIZE"
  MODEL_TAG="gemma3-$SIZE"
  RESLOG="$RESROOT/${MODEL_TAG}_${TS}.jsonl"

  echo "" | tee -a "$MATRIX_LOG"
  echo "===============================================" | tee -a "$MATRIX_LOG"
  echo "[$(date +%H:%M:%S)] BEGIN SIZE=$SIZE" | tee -a "$MATRIX_LOG"
  echo "===============================================" | tee -a "$MATRIX_LOG"

  # 1. pull (no-op if already present) — first-time only blocks here
  echo "[$(date +%H:%M:%S)] ollama pull $MODEL" | tee -a "$MATRIX_LOG"
  ollama pull "$MODEL" 2>&1 | tee -a "$MATRIX_LOG" | tail -3

  # 2. warm up — load weights into RAM
  echo "[$(date +%H:%M:%S)] warm up $MODEL (load into RAM)" | tee -a "$MATRIX_LOG"
  echo "hi" | ollama run "$MODEL" --keepalive 30m > /dev/null 2>&1 || true

  # 3. start sampler in background
  echo "[$(date +%H:%M:%S)] start resource sampler -> $RESLOG" | tee -a "$MATRIX_LOG"
  bash "$REPO_ROOT/tools/sample_resource.sh" "$RESLOG" 5 &
  SAMPLER_PID=$!

  # 4. run 6 cells (L x METHOD), serial; ours MUST precede ours_struct per length
  for L in $LENGTHS; do
    for METHOD in $METHODS; do
      run_one_cell "$SIZE" "$L" "$METHOD"
    done
  done

  # 5. stop sampler
  echo "[$(date +%H:%M:%S)] stop sampler (pid=$SAMPLER_PID)" | tee -a "$MATRIX_LOG"
  kill "$SAMPLER_PID" 2>/dev/null
  wait "$SAMPLER_PID" 2>/dev/null

  # 6. force-unload model
  echo "[$(date +%H:%M:%S)] ollama stop $MODEL" | tee -a "$MATRIX_LOG"
  ollama stop "$MODEL" 2>&1 | tee -a "$MATRIX_LOG"

  # 7. verify unloaded
  sleep 3
  PS_AFTER=$(curl -s --max-time 2 "$MEM0_TRIPLE_OLLAMA_URL/api/ps" 2>/dev/null || echo '{}')
  echo "[$(date +%H:%M:%S)] after unload api/ps: $PS_AFTER" | tee -a "$MATRIX_LOG"

  # 8. summarize resource usage for this size
  echo "[$(date +%H:%M:%S)] resource summary:" | tee -a "$MATRIX_LOG"
  python3 "$REPO_ROOT/tools/summarize_resource.py" "$RESLOG" 2>&1 | tee -a "$MATRIX_LOG"
done

echo "" | tee -a "$MATRIX_LOG"
echo "===============================================" | tee -a "$MATRIX_LOG"
echo "[$(date +%H:%M:%S)] ALL SIZES DONE — see $SUMMARY_MD" | tee -a "$MATRIX_LOG"
echo "===============================================" | tee -a "$MATRIX_LOG"
cat "$SUMMARY_MD"
