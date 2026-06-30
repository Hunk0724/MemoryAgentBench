#!/bin/bash
set -u
source /home/yhchiang/miniconda3/etc/profile.d/conda.sh
conda activate MABench
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
cd /home/yhchiang/MemoryAgentBench
python docs/0612_research_method_improve_with_evidence/scripts/u5_smoke_test.py
