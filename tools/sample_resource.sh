#!/bin/bash
# Sample machine + Ollama resource usage every N seconds → JSONL.
# Usage:  bash tools/sample_resource.sh <output.jsonl> [interval_sec]
#         (run in background; kill PID to stop)
#
# Each line is one sample:
#   {ts, used_gb, wired_gb, compressed_gb, app_mem_gb, swap_used_gb,
#    cpu_user_pct, cpu_sys_pct, cpu_idle_pct, ollama: <api/ps json or null>}
#
# Notes:
#  - macOS unified memory: no separate GPU VRAM concept; we sample "wired + active + compressed"
#    as a proxy for "what RAM is committed". Apple Silicon GPU shares this pool.
#  - Ollama /api/ps returns loaded models + size_vram (in bytes); null if daemon not running.
#  - intentionally writes JSONL one-line-per-sample so post-hoc parsing is trivial.
set -u
OUT="${1:?need output jsonl path}"
INTERVAL="${2:-5}"
mkdir -p "$(dirname "$OUT")"

while true; do
  TS=$(date +%s)
  # macOS vm_stat — page count × page size = bytes
  VMS=$(vm_stat 2>/dev/null)
  PAGE_SIZE=$(echo "$VMS" | head -1 | grep -oE '[0-9]+' | head -1)
  PAGE_SIZE=${PAGE_SIZE:-4096}
  pages_for() {
    echo "$VMS" | awk -v key="$1" -F: '$1 ~ key { gsub(/[ .]/, "", $2); print $2; exit }'
  }
  P_ACTIVE=$(pages_for "Pages active")
  P_WIRED=$(pages_for "Pages wired down")
  P_COMP=$(pages_for "Pages occupied by compressor")
  # bytes → GB(浮點)
  bytes_to_gb() { awk -v b="$1" 'BEGIN { printf "%.3f", b / 1024 / 1024 / 1024 }'; }
  USED_BYTES=$(( (${P_ACTIVE:-0} + ${P_WIRED:-0} + ${P_COMP:-0}) * PAGE_SIZE ))
  USED_GB=$(bytes_to_gb "$USED_BYTES")
  WIRED_GB=$(bytes_to_gb $(( ${P_WIRED:-0} * PAGE_SIZE )))
  COMP_GB=$(bytes_to_gb $(( ${P_COMP:-0} * PAGE_SIZE )))

  # App-level RAM(top -l 1 抓 PhysMem)
  APP_GB=$(top -l 1 -n 0 2>/dev/null | awk '/PhysMem/ {gsub(/[GM]/,"",$2); print $2; exit}')
  APP_GB=${APP_GB:-0}

  # Swap
  SWAP_USED=$(sysctl -n vm.swapusage 2>/dev/null | awk '{ for(i=1;i<=NF;i++) if($i=="used"){ gsub(/[MG],/,"",$(i+2)); print $(i+2); exit } }')
  SWAP_USED=${SWAP_USED:-0}

  # CPU(top -l 1 抓 CPU usage)
  CPU=$(top -l 1 -n 0 2>/dev/null | awk '/CPU usage/ {gsub(/[%,]/,""); print $3" "$5" "$7; exit}')
  CPU_USER=$(echo "$CPU" | awk '{print $1}')
  CPU_SYS=$(echo "$CPU"  | awk '{print $2}')
  CPU_IDLE=$(echo "$CPU" | awk '{print $3}')

  # Ollama loaded models (null if daemon down)
  OLLAMA_PS=$(curl -s --max-time 1 http://localhost:11434/api/ps 2>/dev/null || echo 'null')
  [ -z "$OLLAMA_PS" ] && OLLAMA_PS='null'

  printf '{"ts":%s,"used_gb":%s,"wired_gb":%s,"compressed_gb":%s,"app_mem_gb":"%s","swap_used":"%s","cpu_user":"%s","cpu_sys":"%s","cpu_idle":"%s","ollama":%s}\n' \
    "$TS" "$USED_GB" "$WIRED_GB" "$COMP_GB" "$APP_GB" "$SWAP_USED" "${CPU_USER:-0}" "${CPU_SYS:-0}" "${CPU_IDLE:-0}" "$OLLAMA_PS" >> "$OUT"

  sleep "$INTERVAL"
done
