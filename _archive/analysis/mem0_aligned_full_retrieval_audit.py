"""
完整 audit: Mem0 aligned MH 100 題, 對每題 search top-100, 統計
chain_new / chain_old 出現比例。

驗證假說: Mem0 的 filter-at-write 把 chain_old 從 vector store 大量刪掉,
所以 retrieval 中 chain_old 比 chain_new 少很多。
"""

import json
import os
import sys
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/home/yhchiang/MemoryAgentBench/.env")
except ImportError:
    pass

sys.path.insert(0, "/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, "/home/yhchiang/MemoryAgentBench/analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts")

from mem0.utils.factory import LlmFactory
LlmFactory.provider_to_class["gemini"] = "mem0_vertex_gemini_llm.VertexGeminiLLM"

from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.configs.prompts import FACT_RETRIEVAL_PROMPT

BASE = Path("/home/yhchiang/MemoryAgentBench")


def make_l1_modified_prompt():
    pattern = re.compile(
        r'Input: Hi\.\s*\nOutput: \{"facts" : \[\]\}\s*\n\s*\n'
        r'Input: There are branches in trees\.\s*\nOutput: \{"facts" : \[\]\}\s*\n\s*\n',
        re.MULTILINE,
    )
    return pattern.sub('', FACT_RETRIEVAL_PROMPT)


def norm(s):
    if not s:
        return ''
    return str(s).strip().lower().rstrip('.,;:!?"\'')


def text_match(h, n):
    h = norm(h); n = norm(n)
    if not h or not n:
        return False
    for art in ('the ', 'a ', 'an '):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def main():
    qdrant_path = str(BASE / ".cache/mem0_aligned_qdrant_mh")
    config_dict = {
        "llm": {"provider": "gemini", "config": {"model": "gemini-3.1-flash-lite-preview", "temperature": 0.1, "max_tokens": 8192}},
        "embedder": {"provider": "huggingface", "config": {"model": "sentence-transformers/all-MiniLM-L6-v2"}},
        "vector_store": {"provider": "qdrant", "config": {"embedding_model_dims": 384, "path": qdrant_path, "collection_name": "mem0_fc_mh"}},
        "custom_fact_extraction_prompt": make_l1_modified_prompt(),
    }
    memory = Memory(config=MemoryConfig(**config_dict))
    user_id = "mem0_aligned_mh"

    mh_gt = {q['query_id']: q for q in json.load(open(BASE / 'analysis/results/mh_512_mquake_analysis.json'))}
    mab_data = json.load(open(BASE / 'outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json'))
    wrapped_qmap = {e["query_id"]: e["query"] for e in mab_data["data"]}

    stats_hop = {'new_in': 0, 'old_in': 0, 'both_in': 0, 'neither': 0, 'total_has_pair': 0}
    stats_q = {'all_new_in': 0, 'all_pair_old_in': 0, 'q_total': 0}

    detail = []
    for qid, q in mh_gt.items():
        wrapped = wrapped_qmap.get(qid)
        if not wrapped:
            continue
        retrieved = memory.search(query=wrapped, user_id=user_id, limit=100)
        results = retrieved.get("results", []) if isinstance(retrieved, dict) else []
        memories_text = [m.get("memory", "") for m in results]

        has_pair_hops = [h for h in q['hops'] if h.get('conflict_type') == 'has_pair']
        if not has_pair_hops:
            continue
        stats_q['q_total'] += 1
        chain_news_in = []
        chain_olds_in = []
        for h in has_pair_hops:
            new_t = h.get('gt_fact_text', '')
            old_t = h.get('old_fact_text', '')
            in_new = any(text_match(m, new_t) for m in memories_text)
            in_old = any(text_match(m, old_t) for m in memories_text)
            chain_news_in.append(in_new)
            chain_olds_in.append(in_old)
            stats_hop['total_has_pair'] += 1
            if in_new and in_old:
                stats_hop['both_in'] += 1
            elif in_new:
                stats_hop['new_in'] += 1
            elif in_old:
                stats_hop['old_in'] += 1
            else:
                stats_hop['neither'] += 1
        if all(chain_news_in):
            stats_q['all_new_in'] += 1
        if any(chain_olds_in):
            stats_q['all_pair_old_in'] += 1
        detail.append({
            'qid': qid,
            'n_pair_hops': len(has_pair_hops),
            'chain_new_in': chain_news_in,
            'chain_old_in': chain_olds_in,
            'n_retrieved': len(memories_text),
        })
        if qid % 10 == 0:
            print(f'  qid {qid}: hop new_in={chain_news_in}, hop old_in={chain_olds_in}')

    t = stats_hop['total_has_pair']
    print(f'\n=== Hop-level (n={t} has_pair hops) ===')
    print(f'  chain_new in top-100:           {stats_hop["new_in"] + stats_hop["both_in"]} ({(stats_hop["new_in"] + stats_hop["both_in"])/t*100:.0f}%)')
    print(f'  chain_old in top-100:           {stats_hop["old_in"] + stats_hop["both_in"]} ({(stats_hop["old_in"] + stats_hop["both_in"])/t*100:.0f}%)')
    print(f'  both in top-100:                {stats_hop["both_in"]} ({stats_hop["both_in"]/t*100:.0f}%)')
    print(f'  only chain_new (filter worked): {stats_hop["new_in"]} ({stats_hop["new_in"]/t*100:.0f}%)')
    print(f'  only chain_old (orphan):        {stats_hop["old_in"]} ({stats_hop["old_in"]/t*100:.0f}%)')
    print(f'  neither:                        {stats_hop["neither"]} ({stats_hop["neither"]/t*100:.0f}%)')

    qt = stats_q['q_total']
    print(f'\n=== Question-level (n={qt} questions with at least 1 has_pair hop) ===')
    print(f'  all chain_new in top-100:       {stats_q["all_new_in"]} ({stats_q["all_new_in"]/qt*100:.0f}%)')
    print(f'  any chain_old in top-100:       {stats_q["all_pair_old_in"]} ({stats_q["all_pair_old_in"]/qt*100:.0f}%)')

    out = BASE / 'analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results/mem0_aligned_chain_presence_audit.json'
    json.dump({'stats_hop': stats_hop, 'stats_q': stats_q, 'detail': detail}, open(out, 'w'), indent=2)
    print(f'\nSaved detail to {out}')


if __name__ == "__main__":
    main()
