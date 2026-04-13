#!/bin/bash
# Run HippoRAG-v2 on FC-SH 6k and FC-MH 6k
# Conda env: hipporag_env | GPU: 0 | HF cache: MemoryAgentBench_old

source ~/.bashrc
conda activate hipporag_env

export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1
root=$(pwd)

agent_config="Structure_rag_gpt-4o-mini-hippo_rag_v2_nv.yaml"

echo "===== [1/2] FC-SH 6k ====="
CUDA_VISIBLE_DEVICES=0 python main.py \
    --agent_config  configs/agent_conf/RAG_Agents/gpt-4o-mini/${agent_config} \
    --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml
echo "===== FC-SH 6k Done ====="

echo "===== [2/2] FC-MH 6k ====="
CUDA_VISIBLE_DEVICES=0 python main.py \
    --agent_config  configs/agent_conf/RAG_Agents/gpt-4o-mini/${agent_config} \
    --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml
echo "===== FC-MH 6k Done ====="

# bash bash_files/sh/run_hipporag_fc.sh
