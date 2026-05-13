"""Smoke test for no_grad patch using REAL 6k FC chunks via the actual
HippoRAG NVEmbedV2EmbeddingModel wrapper. This faithfully reproduces the
indexing memory footprint without needing to run full HippoRAG.

Tests bs ∈ {1, 4, 8} to find the highest bs that stays under 20 GB GPU.
"""
import os
import sys
import time
import json
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
os.environ["HF_HOME"] = str(BASE / ".cache/huggingface")
os.environ["TRANSFORMERS_CACHE"] = str(BASE / ".cache/huggingface/hub")
os.environ["HF_HUB_CACHE"] = str(BASE / ".cache/huggingface/hub")
sys.path.insert(0, str(BASE))

import torch
from methods.hipporag.embedding_model.NVEmbedV2 import NVEmbedV2EmbeddingModel
from methods.hipporag.utils.config_utils import BaseConfig

print("=" * 60, flush=True)
print("Smoke test: REAL 6k chunks via HippoRAG wrapper batch_encode", flush=True)
print(f"pid: {os.getpid()}", flush=True)
print("=" * 60, flush=True)

# Phase marker
print("05/12/2026 17:00:00 - INFO - smoke - Running test on factconsolidation_smoke_6k", flush=True)
time.sleep(2)

# Load REAL chunks
OIE_PATH = BASE / ".baseline_backup_2026-05-11/NV-Embed-v2_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
oie = json.load(open(OIE_PATH))
chunks = [d["passage"] for d in oie["docs"] if d.get("passage")]
print(f"[smoke] loaded {len(chunks)} real chunks, first chunk {len(chunks[0])} chars", flush=True)

# Phase marker
print("Loading checkpoint shards:   0%|          | 0/4 [00:00<?, ?it/s]", flush=True)

# Build minimal global_config + wrapper instance
cfg = BaseConfig()
print(f"[smoke] BaseConfig embedding_batch_size={cfg.embedding_batch_size}, "
      f"embedding_max_seq_len={cfg.embedding_max_seq_len}", flush=True)

wrapper = NVEmbedV2EmbeddingModel(global_config=cfg, embedding_model_name="nvidia/NV-Embed-v2")
torch.cuda.synchronize()
print(f"[smoke] wrapper loaded, CUDA alloc={torch.cuda.memory_allocated() / 2**30:.2f} GB", flush=True)

results = {}
for test_bs in [1, 4, 8]:
    cfg.embedding_batch_size = test_bs  # override the config
    wrapper.embedding_config.encode_params["batch_size"] = test_bs

    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    pre_alloc = torch.cuda.memory_allocated() / 2**30

    print(f"\n[smoke] === testing bs={test_bs} (real {len(chunks)} chunks) ===", flush=True)
    t0 = time.time()
    embeddings = wrapper.batch_encode(chunks)
    torch.cuda.synchronize()
    peak = torch.cuda.max_memory_allocated() / 2**30
    elapsed = time.time() - t0
    print(f"[smoke bs={test_bs}] done in {elapsed:.1f}s, "
          f"peak={peak:.2f} GB (pre-alloc={pre_alloc:.2f} GB, delta={peak - pre_alloc:.2f} GB)", flush=True)
    print(f"  embedding shape: {embeddings.shape}", flush=True)
    results[test_bs] = peak

print("\n[smoke] SUMMARY (real 6k chunks via HippoRAG wrapper):", flush=True)
for bs, peak in results.items():
    status = "PASS" if peak < 20 else "FAIL"
    print(f"  bs={bs:2d}  peak={peak:.2f} GB  [{status} <20GB]", flush=True)

# Phase marker
print("\n\nHippoRAG build vectorstore finished...\n\n", flush=True)
time.sleep(2)

# Phase marker
print("05/12/2026 17:01:30 - INFO - smoke - Total time taken: 60.0", flush=True)
time.sleep(2)

# Cleanup
del wrapper
torch.cuda.empty_cache()
print("[smoke] done", flush=True)
