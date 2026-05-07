"""
Profile NV-Embed-v2 GPU memory peak — per-batch measurement that mirrors
HippoRAG-v2's actual call pattern (one model.encode() call per inner batch).

Key finding: model.encode([many, texts], ...) does NOT auto-chunk. The
batch_size param is unused at the model side; HippoRAG splits with an
outer Python loop and calls encode() with batch_size-sized lists.

We measure the per-batch peak which IS the true GPU peak HippoRAG hits.

Run:
    HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface \\
    conda run -n hipporag_env --no-capture-output \\
        python analysis/profile_nvembed_vram.py
"""

import os
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
os.environ["HF_HOME"] = str(BASE / ".cache/huggingface")
os.environ["TRANSFORMERS_CACHE"] = str(BASE / ".cache/huggingface/hub")
os.environ["HF_HUB_CACHE"] = str(BASE / ".cache/huggingface/hub")

import gc
import json
import time

import psutil
import torch
from transformers import AutoModel

OPENIE_PATH = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json"
OUT_PATH = BASE / "analysis/results/nvembed_vram_profile.json"
MODEL_NAME = "nvidia/NV-Embed-v2"


def memstats(label):
    rss = psutil.Process().memory_info().rss / 2**30
    cuda_alloc = torch.cuda.memory_allocated() / 2**30
    cuda_reserved = torch.cuda.memory_reserved() / 2**30
    cuda_peak = torch.cuda.max_memory_allocated() / 2**30
    print(
        f"[{label:<48}] RSS={rss:6.2f}G | alloc={cuda_alloc:6.2f}G "
        f"reserved={cuda_reserved:6.2f}G peak={cuda_peak:6.2f}G"
    )
    return {
        "label": label,
        "rss_gb": round(rss, 2),
        "cuda_alloc_gb": round(cuda_alloc, 2),
        "cuda_reserved_gb": round(cuda_reserved, 2),
        "cuda_peak_gb": round(cuda_peak, 2),
    }


def cleanup():
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()


def profile_one_batch(model, texts, max_length, label):
    """Encode exactly ONE batch (= len(texts)). This mirrors a single inner call
    of HippoRAG's batch loop. Returns peak CUDA during this call."""
    cleanup()
    torch.cuda.reset_peak_memory_stats()
    pre = memstats(f"  pre  {label}")
    t0 = time.time()
    try:
        with torch.no_grad():
            out = model.encode(texts, instruction="", max_length=max_length)
        torch.cuda.synchronize()
        elapsed = time.time() - t0
        # move to CPU + free GPU tensor
        out_cpu = out.detach().cpu().numpy() if torch.is_tensor(out) else out
        del out
        cleanup()
        post = memstats(f"  post {label} ({elapsed:.2f}s)")
        return {
            "label": label,
            "n_texts": len(texts),
            "max_length": max_length,
            "elapsed_s": round(elapsed, 3),
            "pre": pre,
            "post": post,
            "peak_during_encode_gb": post["cuda_peak_gb"],
            "peak_delta_gb": round(post["cuda_peak_gb"] - pre["cuda_alloc_gb"], 2),
            "ok": True,
        }
    except torch.cuda.OutOfMemoryError as e:
        cleanup()
        post = memstats(f"  OOM  {label}")
        return {
            "label": label,
            "n_texts": len(texts),
            "max_length": max_length,
            "ok": False,
            "error": "OOM: " + str(e)[:200],
            "pre": pre,
            "post": post,
        }


def load_real_corpus():
    oie = json.load(open(OPENIE_PATH))
    chunks = []
    facts = []
    for doc in oie.get("docs", []):
        passage = doc.get("passage", "")
        if passage:
            chunks.append(passage)
        for tri in doc.get("extracted_triples", []):
            if isinstance(tri, list) and len(tri) == 3:
                facts.append(f"{tri[0]} {tri[1]} {tri[2]}")
    return chunks, facts


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = {"device": torch.cuda.get_device_name(0), "tests": []}

    print("=" * 80)
    print("NV-Embed-v2 per-batch VRAM profile (mirrors HippoRAG inner-call pattern)")
    print("=" * 80)
    print(
        f"Total CUDA memory pool (GB10 unified): "
        f"{torch.cuda.get_device_properties(0).total_memory / 2**30:.1f} GB"
    )

    chunks, facts = load_real_corpus()
    print(f"corpus: {len(chunks)} chunks, {len(facts)} facts (6k FC-MH)")
    results["corpus"] = {"n_chunks": len(chunks), "n_facts": len(facts)}

    print("\n--- Phase 1: model load (fp16) ---")
    results["tests"].append(memstats("baseline (before load)"))
    t0 = time.time()
    model = AutoModel.from_pretrained(
        MODEL_NAME, trust_remote_code=True, device_map="cuda:0", torch_dtype=torch.float16
    )
    model.eval()
    torch.cuda.synchronize()
    print(f"  load time: {time.time() - t0:.1f}s")
    after_load = memstats("after model load (fp16)")
    results["tests"].append(after_load)
    results["model_weights_gb"] = after_load["cuda_alloc_gb"]

    print("\n--- Phase 2: 1 query (typical query-time pattern) ---")
    results["tests"].append(
        profile_one_batch(model, ["Who is the current chief executive of Apple?"], 512, "1 query × max512")
    )

    print("\n--- Phase 3: per-batch encode at varying batch_size (facts, max_len=128) ---")
    print("(mirrors HippoRAG inner call with batch_size=N — short fact strings)")
    for bs in [1, 2, 4, 8, 16, 32]:
        if bs > len(facts):
            break
        sample = facts[:bs]
        results["tests"].append(profile_one_batch(model, sample, 128, f"facts bs={bs} max_len=128"))

    print("\n--- Phase 4: per-batch encode at varying batch_size (facts, max_len=512) ---")
    for bs in [1, 2, 4, 8, 16, 32]:
        if bs > len(facts):
            break
        sample = facts[:bs]
        results["tests"].append(profile_one_batch(model, sample, 512, f"facts bs={bs} max_len=512"))

    print("\n--- Phase 5: per-batch encode at varying batch_size (chunks, max_len=512) ---")
    print("(chunks are 512-token packed numbered facts)")
    for bs in [1, 2, 4, 8, 12]:
        if bs > len(chunks):
            break
        sample = chunks[:bs]
        results["tests"].append(profile_one_batch(model, sample, 512, f"chunks bs={bs} max_len=512"))

    print("\n--- Phase 6: chunks with HippoRAG default max_len=2048 ---")
    for bs in [1, 4, 8]:
        if bs > len(chunks):
            break
        sample = chunks[:bs]
        results["tests"].append(profile_one_batch(model, sample, 2048, f"chunks bs={bs} max_len=2048"))

    final = memstats("FINAL")
    results["final"] = final
    valid_peaks = [
        t["peak_during_encode_gb"]
        for t in results["tests"]
        if isinstance(t, dict) and t.get("ok") and "peak_during_encode_gb" in t
    ]
    if valid_peaks:
        results["overall_observed_peak_gb"] = max(valid_peaks)

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {OUT_PATH}")
    if valid_peaks:
        print(f"Overall CUDA peak observed (excluding OOMs): {max(valid_peaks):.2f} GB")
    print(f"Model weights baseline: {results['model_weights_gb']:.2f} GB")


if __name__ == "__main__":
    main()
