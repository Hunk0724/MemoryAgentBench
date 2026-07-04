#!/bin/bash
# Linux (GX10 / aarch64) resource sampler — GX10 adaptation of tools/sample_resource.sh.
# Emits the SAME JSONL schema so tools/summarize_resource.py works UNCHANGED.
# The macOS version (sample_resource.sh) is left untouched; run_gemma_matrix.sh
# selects this file via `uname` on Linux.
#
# Samples every N seconds:
#   {ts, used_gb, wired_gb, compressed_gb, app_mem_gb, swap_used,
#    cpu_user, cpu_sys, cpu_idle, ollama: <api/ps json or null>}
#
# Linux mapping (vs macOS fields):
#   used_gb  = MemTotal - MemAvailable      (committed RAM; on GB10 unified memory
#                                            this INCLUDES the ollama-loaded model)
#   wired_gb = MemTotal - MemFree - Buffers - Cached  (stricter "used", excl. page cache)
#   cpu_user = 100 * (1 - idle_delta/total_delta) from /proc/stat between samples
#   swap_used= SwapTotal - SwapFree
#   compressed_gb / app_mem_gb : no Linux analogue -> 0
#   ollama   = /api/ps (size_vram = model GPU-resident bytes); cross-platform
set -u
OUT="${1:?need output jsonl path}"
INTERVAL="${2:-5}"
mkdir -p "$(dirname "$OUT")"

kb_to_gb() { awk -v k="$1" 'BEGIN { printf "%.3f", k / 1024 / 1024 }'; }
# total (sum jiffies) and idle (idle+iowait) from /proc/stat
read_cpu() { awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5+$6; exit}' /proc/stat; }

PREV_TOTAL=0; PREV_IDLE=0
read PREV_TOTAL PREV_IDLE < <(read_cpu)

while true; do
  TS=$(date +%s)

  # /proc/meminfo (values in kB)
  MEMTOTAL=$(awk '/^MemTotal:/{print $2; exit}' /proc/meminfo)
  MEMAVAIL=$(awk '/^MemAvailable:/{print $2; exit}' /proc/meminfo)
  MEMFREE=$(awk '/^MemFree:/{print $2; exit}' /proc/meminfo)
  BUFFERS=$(awk '/^Buffers:/{print $2; exit}' /proc/meminfo)
  CACHED=$(awk '/^Cached:/{print $2; exit}' /proc/meminfo)
  SWAPTOTAL=$(awk '/^SwapTotal:/{print $2; exit}' /proc/meminfo)
  SWAPFREE=$(awk '/^SwapFree:/{print $2; exit}' /proc/meminfo)

  USED_KB=$(( ${MEMTOTAL:-0} - ${MEMAVAIL:-0} ))
  WIRED_KB=$(( ${MEMTOTAL:-0} - ${MEMFREE:-0} - ${BUFFERS:-0} - ${CACHED:-0} ))
  [ "$WIRED_KB" -lt 0 ] && WIRED_KB=0
  SWAP_KB=$(( ${SWAPTOTAL:-0} - ${SWAPFREE:-0} ))
  USED_GB=$(kb_to_gb "$USED_KB")
  WIRED_GB=$(kb_to_gb "$WIRED_KB")
  SWAP_GB=$(kb_to_gb "$SWAP_KB")

  # CPU% via /proc/stat delta since previous sample
  read CUR_TOTAL CUR_IDLE < <(read_cpu)
  DT=$(( CUR_TOTAL - PREV_TOTAL )); DI=$(( CUR_IDLE - PREV_IDLE ))
  if [ "$DT" -gt 0 ]; then
    CPU_USER=$(awk -v di="$DI" -v dt="$DT" 'BEGIN{printf "%.1f", 100.0*(dt-di)/dt}')
    CPU_IDLE=$(awk -v di="$DI" -v dt="$DT" 'BEGIN{printf "%.1f", 100.0*di/dt}')
  else
    CPU_USER="0"; CPU_IDLE="0"
  fi
  PREV_TOTAL=$CUR_TOTAL; PREV_IDLE=$CUR_IDLE

  # Ollama loaded models (null if daemon down)
  OLLAMA_PS=$(curl -s --max-time 1 http://localhost:11434/api/ps 2>/dev/null || echo 'null')
  [ -z "$OLLAMA_PS" ] && OLLAMA_PS='null'

  printf '{"ts":%s,"used_gb":%s,"wired_gb":%s,"compressed_gb":%s,"app_mem_gb":"%s","swap_used":"%s","cpu_user":"%s","cpu_sys":"%s","cpu_idle":"%s","ollama":%s}\n' \
    "$TS" "$USED_GB" "$WIRED_GB" "0" "0" "$SWAP_GB" "$CPU_USER" "0" "$CPU_IDLE" "$OLLAMA_PS" >> "$OUT"

  sleep "$INTERVAL"
done
