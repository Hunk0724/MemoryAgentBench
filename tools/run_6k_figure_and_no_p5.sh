#!/bin/bash
# One-shot 6k driver for: (1) refresh struct figure numbers on NEW code
# (normalize + fact-level ordinal) for 1b/4b/12b, then (2) run ours_no_p5
# (P3 LLM grouping on the small post-routing pool) across all 4 sizes.
# 27b struct is NOT re-run (already NEW-code: 65/74). Single GPU -> serial.
#
# Safety valve: after the FIRST no_p5 cell (12b), verify the grouping cache is
# non-empty (num_ctx / truncation regression check) BEFORE spending GPU on the
# other 3 no_p5 cells. Empty -> abort phase2b, drop a marker to investigate.
set -u
cd /home/yhchiang/MemoryAgentBench
LOGDIR=docs/0615_intro_framework_after_problem_statement/logs
MARK="$LOGDIR/6k_run_markers"
rm -rf "$MARK"; mkdir -p "$MARK"
PLOG="$LOGDIR/run_6k_fig_and_no_p5.log"
: > "$PLOG"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$PLOG"; }

say "PHASE1  struct 1b/4b/12b @6k  (refresh figure numbers, NEW code)"
SIZES="1b 4b 12b" LENGTHS="6k" METHODS="ours_struct" bash tools/run_gemma_matrix.sh >> "$PLOG" 2>&1
touch "$MARK/PHASE1_STRUCT_DONE"
say "PHASE1 done"

say "PHASE2a  no_p5 12b @6k  (startup confirm)"
SIZES="12b" LENGTHS="6k" METHODS="ours_no_p5" bash tools/run_gemma_matrix.sh >> "$PLOG" 2>&1
GCHK=$(python3 - <<'PY'
import json
p="analysis/results/p1_caches__gemma3-12b/grouping_cache_no_p5_6k.json"
try:
    d=json.load(open(p))
    ne=sum(1 for v in d.values() if isinstance(v,(list,dict)) and len(v)>0)
    print(("OK" if ne>0 else "EMPTY")+f" nonempty={ne} total={len(d)}")
except Exception as e:
    print(f"MISSING {e}")
PY
)
say "grouping check (12b no_p5): $GCHK"
touch "$MARK/PHASE2A_12B_DONE"

if [[ "$GCHK" == OK* ]]; then
  say "PHASE2b  no_p5 1b/4b/27b @6k"
  SIZES="1b 4b 27b" LENGTHS="6k" METHODS="ours_no_p5" bash tools/run_gemma_matrix.sh >> "$PLOG" 2>&1
  touch "$MARK/PHASE2B_DONE"
else
  say "!! grouping EMPTY/MISSING -> ABORT phase2b (num_ctx/truncation regression?)"
  touch "$MARK/NO_P5_ABORT"
fi
say "ALL DONE"
touch "$MARK/ALL_DONE"
