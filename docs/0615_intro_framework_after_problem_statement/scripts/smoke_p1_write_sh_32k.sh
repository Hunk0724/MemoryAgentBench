#!/bin/bash
# WRITE-TIME EXTRACTION SMOKE: FC-SH 32k, FRESH P1 unified extraction (no
# extraction cache), first 5 input chunks only, MEMORIZE-ONLY (no query-time).
# Goal: compare our real-method P1 extraction against the "perfect" frozen
# extraction_cache_32k.json (the GT) for the same 5 chunks -- confirm P1 quality
# does not drop too much before committing to the full 32k ingest. Isolated
# store / output_dir (the _smoke config) so nothing real is touched.
set -u
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
LME_DATA_DIR="${LME_DATA_DIR:-$REPO_ROOT/data/longmemeval}"
export LME_DATA="${LME_DATA:-$LME_DATA_DIR/longmemeval_s_cleaned.json}"
source "$CONDA_SH"
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd $REPO_ROOT
set -a; [[ -f .env ]] && . .env; set +a

L=32k
TAG=unified_smoke
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
DCONF=configs/data_conf/Conflict_Resolution
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
AG=Structure_rag_gpt-4o-mini-mem0_512_openai_unified_smoke.yaml
STOREBASE=$REPO_ROOT/analysis/results/expanded/stores
SMK=$PWD/analysis/results/smoke
mkdir -p "$LOGROOT" "$SMK"

# FRESH P1 extraction: do NOT set MEM0_EXTRACTION_CACHE.
# Plain mem0 ADD (no MEM0_ADD_MODE): ~1 extraction + 1 update-decision LLM call
# per chunk -> cheap; triples/query-time not needed for an extraction smoke.
export MEM0_CAND_LOG_DIR="$SMK/cand_${TAG}_${L}"   # mem0 logs P1 facts -> extraction.jsonl here
export MEM0_MAX_MEMORIZE_CHUNKS=5                   # first 5 chunks only
export MEM0_MEMORIZE_ONLY=1                         # stop after memorize, no query-time

OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-${TAG}"
rm -rf "$MEM0_CAND_LOG_DIR" \
       "$STOREBASE/qdrant_gpt4o_512_openai_unified_smoke"* \
       "$OUTDIR" \
       "outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_${TAG}"
mkdir -p "$MEM0_CAND_LOG_DIR"

echo "============ P1 WRITE SMOKE sh_${L}: first 5 chunks, fresh P1, memorize-only ============"
python main.py --agent_config "$AGDIR/$AG" \
  --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
  > "$LOGROOT/smoke_${TAG}_${L}.log" 2>&1
echo "[smoke] exit=$?  log: $LOGROOT/smoke_${TAG}_${L}.log"

echo "============ P1 vs GT extraction comparison (per chunk, aligned by index) ============"
python3 - "$MEM0_CAND_LOG_DIR/extraction.jsonl" <<'PY'
import json, sys, os, re

p1_path = sys.argv[1]
gt = json.load(open("analysis/results/extraction_cache_32k.json"))
gt_chunks = list(gt.values())   # dict insertion order == chunk order 0..63

def norm(t): return re.sub(r"\s+", " ", (t or "").strip().rstrip(".").lower())

p1_lines = [json.loads(l) for l in open(p1_path)] if os.path.exists(p1_path) else []
print(f"P1 logged {len(p1_lines)} chunk(s); GT has {len(gt_chunks)} chunks total.\n")

tot_p1 = tot_gt = tot_inter = 0
for i, rec in enumerate(p1_lines):
    p1 = rec.get("facts") or []
    g  = gt_chunks[i] if i < len(gt_chunks) else []
    sp1, sg = {norm(x) for x in p1}, {norm(x) for x in g}
    inter = sp1 & sg
    missing = sg - sp1     # in GT (perfect) but P1 missed
    extra   = sp1 - sg     # P1 produced, not in GT
    tot_p1 += len(p1); tot_gt += len(g); tot_inter += len(inter)
    rec_pct = len(inter)/len(sg)*100 if sg else 0
    print(f"--- chunk {i}: P1={len(p1)}  GT={len(g)}  overlap={len(inter)}  "
          f"recall_vs_GT={rec_pct:.0f}%  (missed={len(missing)}, extra={len(extra)}) ---")
    for m in list(missing)[:5]:  print(f"     [GT-only/missed] {m[:90]}")
    for e in list(extra)[:5]:    print(f"     [P1-only/extra ] {e[:90]}")

if tot_gt:
    print(f"\n=== TOTAL (5 chunks): P1={tot_p1} GT={tot_gt} overlap={tot_inter} "
          f"| micro recall_vs_GT={tot_inter/tot_gt*100:.1f}% "
          f"| P1/GT count ratio={tot_p1/tot_gt:.2f} ===")
PY
echo "============ DONE smoke ============"
