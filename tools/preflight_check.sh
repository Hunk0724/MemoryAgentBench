#!/bin/bash
# Preflight sanity check BEFORE a full gemma cell — institutionalizes the
# "don't run 100 queries only to find a config error" lesson (p3_only/num_ctx).
# Usage: bash tools/preflight_check.sh <SIZE> <L> <METHOD>
#   e.g. bash tools/preflight_check.sh 27b 6k ours_struct
set -u
SIZE="${1:?need SIZE}"; L="${2:?need L}"; METHOD="${3:?need METHOD}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"
cd "$REPO_ROOT"
MODEL="gemma3:$SIZE"; TAG="gemma3-$SIZE"
PC="analysis/results/p1_caches__${TAG}"
FAIL=0
say(){ printf '  %-46s %s\n' "$1" "$2"; }
echo "=== PREFLIGHT: size=$SIZE L=$L method=$METHOD ==="

# 1) caches present (reuse -> no re-extraction / faithful held-fixed write)
for f in "extraction_cache_p1_${L}.json" "triple_cache_p1_${L}.json"; do
  if [ -s "$PC/$f" ]; then say "cache $f" "OK ($(wc -c <"$PC/$f") B)"; else say "cache $f" "MISSING -> will invoke $MODEL to (re)extract"; fi
done

# 2) ollama daemon + model
URL="${MEM0_TRIPLE_OLLAMA_URL:-http://localhost:11434}"
if curl -s --max-time 3 "$URL/api/version" >/dev/null; then say "ollama daemon ($URL)" "reachable"; else say "ollama daemon" "UNREACHABLE"; FAIL=1; fi
if ollama list 2>/dev/null | grep -q "^${MODEL}\b"; then say "model $MODEL pulled" "OK"; else say "model $MODEL" "NOT pulled"; FAIL=1; fi

# 3) OpenAI key for embedding
if [ -n "${OPENAI_API_KEY_A:-}" ] || { [ -f .env ] && grep -q OPENAI_API_KEY_A .env; }; then say "OPENAI_API_KEY_A (embedding)" "present"; else say "OPENAI_API_KEY_A" "MISSING"; FAIL=1; fi

# 4) method-specific: LLM-grouping variants need adequate num_ctx (p3_only lesson)
case "$METHOD" in
  ours_p3_only_no_struct|ours_no_p5|ours)
    say "num_ctx (LLM grouping/answer)" "${OLLAMA_NUM_CTX:-<ollama default>} -> ensure >=8192; VERIFY grouping_cache non-empty on first queries"
    [ "$METHOD" = "ours_p3_only_no_struct" ] && say "!! p3_only runs P3 over TOP-100" "known-overload; expect low even with big ctx"
    ;;
  ours_struct)
    say "grouping" "deterministic (S,P)+argmax, NO LLM grouping — num_ctx N/A for grouping" ;;
esac

# 5) code-change sanity: normalize + fact-level ordinal actually loaded
python3 - <<'PY'
import sys
try:
    from methods.phase0_triple_extractor import normalize_predicate as NP
    ok = NP("is produced by") == NP("was produced by")  # tense merge = L2 active
    print(f"  {'normalize L2 (is/was produced by merge)':<46} {'OK' if ok else 'NOT ACTIVE'}")
    import inspect, mem0.memory.main as M
    src = inspect.getsource(M.Memory._add_phase0_structural)
    print(f"  {'fact-level ordinal (chunk_ordinal + _fi)':<46} {'OK' if 'chunk_ordinal + _fi' in src else 'NOT FOUND'}")
except Exception as e:
    print("  code check FAILED:", e); sys.exit(3)
PY

echo "=== RESULT: $([ $FAIL -eq 0 ] && echo 'PASS — safe to run' || echo 'FAIL — fix above before running') ==="
exit $FAIL
