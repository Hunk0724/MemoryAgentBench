"""Summarize a resource-sample JSONL file (output of tools/sample_resource.sh).

Reports: duration, mean/p50/p95/peak of used_gb + wired_gb + ollama VRAM bytes,
mean CPU user%, swap peak. Use to verify weak-model regime stayed within
predicted bounds.

Usage:
    python tools/summarize_resource.py <file.jsonl>
"""
import json
import sys
import statistics
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="JSONL output of sample_resource.sh")
    args = ap.parse_args()

    samples = []
    with open(args.file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not samples:
        print(f"[error] no valid samples in {args.file}")
        sys.exit(1)

    ts_first = samples[0]["ts"]
    ts_last = samples[-1]["ts"]
    duration_min = (ts_last - ts_first) / 60.0

    used = [float(s.get("used_gb") or 0) for s in samples]
    wired = [float(s.get("wired_gb") or 0) for s in samples]
    cpu_user = [float(s.get("cpu_user") or 0) for s in samples]

    def stats(xs, label, unit="GB"):
        if not xs:
            print(f"  {label}: no data")
            return
        srt = sorted(xs)
        p50 = srt[len(srt) // 2]
        p95 = srt[int(0.95 * len(srt))]
        print(f"  {label:18s}  mean={statistics.mean(xs):7.2f}  p50={p50:7.2f}  p95={p95:7.2f}  peak={max(xs):7.2f}  {unit}")

    print(f"=== Resource summary: {args.file} ===")
    print(f"  samples: {len(samples)}  duration: {duration_min:.1f} min")
    print()
    stats(used, "RAM used (total)")
    stats(wired, "RAM wired")
    stats(cpu_user, "CPU user %", unit="%")

    # Ollama loaded VRAM peak
    ollama_vram_gb = []
    ollama_models_seen = set()
    for s in samples:
        ol = s.get("ollama")
        if not isinstance(ol, dict):
            continue
        models = ol.get("models", []) or []
        size_total = 0
        for m in models:
            sv = m.get("size_vram") or m.get("size") or 0
            size_total += sv
            if m.get("name"):
                ollama_models_seen.add(m["name"])
        if size_total:
            ollama_vram_gb.append(size_total / 1024 / 1024 / 1024)
    if ollama_vram_gb:
        stats(ollama_vram_gb, "Ollama VRAM(size_vram)")
        print(f"  models seen in samples: {sorted(ollama_models_seen)}")
    else:
        print("  Ollama: never reported a loaded model during this window")


if __name__ == "__main__":
    main()
