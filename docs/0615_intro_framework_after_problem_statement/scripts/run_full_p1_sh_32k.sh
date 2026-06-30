#!/bin/bash
# OURS, FULL FC-SH 32k: fresh P1 unified extraction + phase0 conservative write
# (+ (S,P) index) + phase2 query-time resolution + raw-question retrieval +
# batch embedding. All caches are FRESH, p1_-prefixed paths (self-populating; do
# NOT collide with the old l2 extraction_cache_32k / triple_cache_32k). Isolated
# unified store / output_dir. vanilla mem0 baseline is run separately later.
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
set -a; [[ -f .env ]] && . .env; set +a

L=32k
TAG=unified
LOGROOT=docs/0615_intro_framework_after_problem_statement/logs
DCONF=configs/data_conf/Conflict_Resolution
AGDIR=configs/agent_conf/RAG_Agents/gpt-4o-mini
AG=Structure_rag_gpt-4o-mini-mem0_512_openai_unified.yaml
STOREBASE=/home/yhchiang/MemoryAgentBench/analysis/results/expanded/stores
PC=$PWD/analysis/results/p1_caches          # fresh, isolated cache home
mkdir -p "$LOGROOT" "$PC" "$PWD/analysis/results/phase0"

# Extraction / triple / subject: FRESH p1 caches (self-populating; reusable for
# later analysis). Do NOT point at the old l2 caches.
export MEM0_TRIPLE_MODEL=gpt-4o-mini
export MEM0_EXTRACTION_CACHE="$PC/extraction_cache_p1_${L}.json"
export MEM0_TRIPLE_CACHE="$PC/triple_cache_p1_${L}.json"
export MEM0_SUBJECT_CACHE="$PC/subject_cache_p1_${L}.json"
export MEM0_GROUPING_CACHE="$PC/grouping_cache_p1_${L}.json"
export MEM0_CONFLICT_CACHE="$PC/conflict_cache_p1_${L}.json"
export MEM0_SP_INDEX_PATH="$PWD/analysis/results/phase0/sp_index_p1_sh_${L}.json"
export MEM0_CAND_LOG_DIR="$PWD/$LOGROOT/sh_${L}_p1"

export MEM0_ADD_MODE=phase0_structural
export MEM0_QUERY_MODE=phase2
# (full run: no MEM0_MAX_MEMORIZE_CHUNKS, no MEM0_MEMORIZE_ONLY)

OUTDIR="outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-${TAG}"
# Fresh per-run state (store / sp_index / query-time caches / cand log / result
# json -> avoid stale state + benchmark resume-skip). The extraction/triple/
# subject p1 caches are intentionally KEPT (self-populate; reusable).
rm -rf "$MEM0_CAND_LOG_DIR" "$MEM0_SP_INDEX_PATH" \
       "$MEM0_GROUPING_CACHE" "$MEM0_CONFLICT_CACHE" \
       "$STOREBASE/qdrant_gpt4o_512_openai_unified__factconsolidation_sh_${L}" \
       "$OUTDIR/Conflict_Resolution/"*sh_${L}*results*.json
mkdir -p "$MEM0_CAND_LOG_DIR"

echo "================ OURS FULL FC-SH ${L} (P1 + phase0 + phase2 + raw-q + batch-emb) ================"
date
python main.py --agent_config "$AGDIR/$AG" \
  --dataset_config "$DCONF/Factconsolidation_sh_${L}.yaml" --force \
  > "$LOGROOT/run_ours_p1_${L}.log" 2>&1
echo "[ours] exit=$?"
date

echo "================ EM ================"
python3 -c "
import json, glob
fs = glob.glob('$OUTDIR/**/*sh_${L}*results*.json', recursive=True)
if fs:
    rows = json.load(open(fs[0])).get('data')
    em = sum(1 for x in rows if x.get('exact_match'))
    print(f'OURS P1 FC-SH ${L}: EM {em}/{len(rows)} = {em/len(rows)*100:.1f}%')
    print(f'result json: {fs[0]}')
else:
    print('no result json found -- check $LOGROOT/run_ours_p1_${L}.log')
"
echo "================ DONE ours ${L} ================"
