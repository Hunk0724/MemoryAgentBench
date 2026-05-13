"""Hardware monitor sidecar — polls CPU/RAM/GPU + phase tag from run.log.

Usage (called by run_with_monitoring.sh, not manually):
    python scripts/hw_monitor_sidecar.py \\
        --log-dir monitoring_logs/<timestamp>_<name> \\
        --run-log monitoring_logs/<timestamp>_<name>/run.log \\
        --target-pid <pid> \\
        --interval 2 \\
        [--summary-only]  # after run finishes, generate hw_phase_summary.md

Outputs:
    hw_timeline.csv         per-sample row (ts, phase, gpu_mem_gb, gpu_util_pct, ram_used_gb, ram_total_gb, cpu_pct_sys, cpu_pct_proc, rss_gb)
    hw_phase_summary.md     per-phase aggregation (generated on --summary-only invocation)
"""
import argparse
import csv
import json
import os
import re
import signal
import sys
import time
from collections import defaultdict
from pathlib import Path

import psutil

# ─────────────────────────────────────────────────────────────────────
# Phase state machine
# ─────────────────────────────────────────────────────────────────────
# NOTE (2026-05-12 fix): the earlier per-line regex list mis-ordered phases
# because "Processing 100 queries for context 0" is printed BEFORE the
# first send_message() triggers HippoRAG indexing — so a literal
# "Processing N queries" marker fires too early and tags the indexing
# window as 'query'. Reliable order found by inspecting actual run.log:
#
#   "Running test on factconsolidation_XX"   ← dataset boundary (has timestamp)
#   "Loading checkpoint shards"              ← NV-Embed-v2 model load = indexing begins
#   "HippoRAG build vectorstore finished"    ← indexing complete = query begins
#   "Total time taken"                       ← dataset done
#
# We carry `dataset` in the state machine so tags become e.g.
# "indexing/sh_6k", "query/sh_6k", "indexing/mh_6k", "query/mh_6k".

DATASET_RE = re.compile(r"Running test on factconsolidation_(\w+)")
INDEXING_RE = re.compile(r"Loading checkpoint shards")
QUERY_RE = re.compile(r"HippoRAG build vectorstore finished")
DATASET_DONE_RE = re.compile(r"Total time taken")


def update_phase(line: str, state: dict) -> str:
    """Update phase state machine in-place; return current phase tag.

    `state` keys: 'phase', 'dataset' (str|None).
    """
    m = DATASET_RE.search(line)
    if m:
        state["dataset"] = m.group(1)
        state["phase"] = f"setup/{state['dataset']}"
        return state["phase"]
    ds = state.get("dataset") or "unknown"
    if INDEXING_RE.search(line):
        state["phase"] = f"indexing/{ds}"
        return state["phase"]
    if QUERY_RE.search(line):
        state["phase"] = f"query/{ds}"
        return state["phase"]
    if DATASET_DONE_RE.search(line):
        state["phase"] = f"done/{ds}"
        return state["phase"]
    return state["phase"]

# Gemini pricing (per 1M tokens, USD) — placeholders, override via env if needed
GEMINI_PRICING = {
    "gemini-3.1-flash-lite-preview": {"input_per_1m": 0.075, "output_per_1m": 0.30},
    "gemini-2.5-flash-lite": {"input_per_1m": 0.075, "output_per_1m": 0.30},
    "gemini-3.1-flash": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "default": {"input_per_1m": 0.10, "output_per_1m": 0.40},
}


def get_pricing(model_name: str) -> dict:
    for key, p in GEMINI_PRICING.items():
        if key != "default" and key in model_name:
            return p
    return GEMINI_PRICING["default"]


def get_process_tree_pids(parent_pid: int) -> set:
    """Return parent_pid + all descendant PIDs (recursive)."""
    pids = {parent_pid}
    try:
        proc = psutil.Process(parent_pid)
        for child in proc.children(recursive=True):
            pids.add(child.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return pids


def query_gpu_mem_aggregated(parent_pid: int) -> tuple:
    """Return (tree_gpu_mem_gb, total_gpu_mem_gb).

    tree_gpu_mem_gb: sum of GPU mem across parent_pid and all descendants
    total_gpu_mem_gb: sum across ALL processes on the GPU (sanity check for other users)

    NOTE (2026-05-12 fix): earlier version only looked at parent_pid which is
    the wrapper bash (no GPU usage). Real GPU user is a deep descendant:
    bash run_hipporag_gemini.sh → conda run → python main.py. We now walk
    the process tree to find the true GPU-using process(es).
    """
    tree_pids = get_process_tree_pids(parent_pid)
    try:
        import subprocess
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return 0.0, 0.0
        tree_mib = 0.0
        total_mib = 0.0
        for line in out.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and parts[0].isdigit():
                pid = int(parts[0])
                try:
                    mem = float(parts[1])
                except ValueError:
                    continue
                total_mib += mem
                if pid in tree_pids:
                    tree_mib += mem
        return tree_mib / 1024.0, total_mib / 1024.0
    except Exception:
        return 0.0, 0.0


def query_gpu_util() -> float:
    """Return overall GPU utilization %. Returns -1 if unavailable."""
    try:
        import subprocess
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return -1.0
        return float(out.stdout.strip().split("\n")[0])
    except Exception:
        return -1.0


def detect_phase_from_log(log_path: Path, offset_holder: dict, state: dict) -> str:
    """Read new lines from log_path since last offset, update phase state machine."""
    if not log_path.exists():
        return state["phase"]
    try:
        with open(log_path, "rb") as f:
            f.seek(offset_holder.get("offset", 0))
            new_data = f.read()
            offset_holder["offset"] = f.tell()
        if not new_data:
            return state["phase"]
        text = new_data.decode("utf-8", errors="replace")
        prev_phase = state["phase"]
        for line in text.split("\n"):
            new_phase = update_phase(line, state)
            if new_phase != prev_phase:
                print(f"[sidecar] phase → {new_phase} (matched: {line.strip()[:80]})", flush=True)
                prev_phase = new_phase
    except Exception as e:
        print(f"[sidecar] log read error: {e}", file=sys.stderr, flush=True)
    return state["phase"]


def write_timeline_row(writer, ts: float, phase: str, target_pid: int):
    """Sample one row of metrics."""
    vm = psutil.virtual_memory()
    cpu_sys = psutil.cpu_percent(interval=None)

    # Aggregate process-tree RSS + CPU (real GPU user is a deep descendant)
    rss_gb = 0.0
    cpu_proc = 0.0
    tree_pid_count = 0
    try:
        proc = psutil.Process(target_pid)
        all_procs = [proc] + proc.children(recursive=True)
        tree_pid_count = len(all_procs)
        for p in all_procs:
            try:
                rss_gb += p.memory_info().rss / 2**30
                cpu_proc += p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    gpu_mem_tree_gb, gpu_mem_total_gb = query_gpu_mem_aggregated(target_pid)
    gpu_util = query_gpu_util()

    writer.writerow({
        "ts": f"{ts:.2f}",
        "phase": phase,
        "gpu_mem_tree_gb": f"{gpu_mem_tree_gb:.3f}",
        "gpu_mem_total_gb": f"{gpu_mem_total_gb:.3f}",
        "gpu_util_pct": f"{gpu_util:.1f}",
        "ram_used_gb": f"{vm.used / 2**30:.2f}",
        "ram_total_gb": f"{vm.total / 2**30:.2f}",
        "cpu_pct_sys": f"{cpu_sys:.1f}",
        "cpu_pct_proc_tree": f"{cpu_proc:.1f}",
        "rss_tree_gb": f"{rss_gb:.2f}",
        "tree_pid_count": tree_pid_count,
    })


def poll_loop(log_dir: Path, run_log: Path, target_pid: int, interval: float):
    """Main poll loop. Exits when target_pid dies or SIGTERM received."""
    timeline_csv = log_dir / "hw_timeline.csv"
    cols = ["ts", "phase",
            "gpu_mem_tree_gb", "gpu_mem_total_gb", "gpu_util_pct",
            "ram_used_gb", "ram_total_gb",
            "cpu_pct_sys", "cpu_pct_proc_tree",
            "rss_tree_gb", "tree_pid_count"]

    with open(timeline_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        f.flush()

        phase_state = {"phase": "init", "dataset": None}
        log_offset = {"offset": 0}

        stop = {"flag": False}
        def _handle_term(signum, frame):
            stop["flag"] = True
        signal.signal(signal.SIGTERM, _handle_term)
        signal.signal(signal.SIGINT, _handle_term)

        # Warm psutil counters
        psutil.cpu_percent(interval=None)
        try:
            psutil.Process(target_pid).cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            pass

        print(f"[sidecar] starting poll loop, pid={target_pid}, interval={interval}s", flush=True)

        while not stop["flag"]:
            ts = time.time()
            current_phase = detect_phase_from_log(run_log, log_offset, phase_state)

            try:
                if not psutil.pid_exists(target_pid):
                    print(f"[sidecar] target pid {target_pid} no longer exists, exiting", flush=True)
                    break
                write_timeline_row(writer, ts, current_phase, target_pid)
                f.flush()
            except Exception as e:
                print(f"[sidecar] sample error: {e}", file=sys.stderr, flush=True)

            time.sleep(interval)

    print(f"[sidecar] wrote {timeline_csv}", flush=True)


def aggregate_summary(log_dir: Path):
    """Generate hw_phase_summary.md from hw_timeline.csv + api_usage.jsonl."""
    timeline_csv = log_dir / "hw_timeline.csv"
    api_log = log_dir / "api_usage.jsonl"
    summary_md = log_dir / "hw_phase_summary.md"
    manifest = log_dir / "manifest.json"

    if not timeline_csv.exists():
        print(f"[sidecar] no timeline csv, skipping summary", file=sys.stderr)
        return

    # Load timeline (backwards-compatible: handle both old + new column names)
    by_phase = defaultdict(list)
    all_samples = []
    numeric_cols = [
        "ts", "gpu_util_pct", "ram_used_gb",
        "cpu_pct_sys", "cpu_pct_proc_tree", "cpu_pct_proc",
        "rss_tree_gb", "rss_gb", "tree_pid_count",
        "gpu_mem_tree_gb", "gpu_mem_total_gb", "gpu_mem_gb",
    ]
    with open(timeline_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k in numeric_cols:
                if k in row:
                    row[k] = float(row[k]) if row[k] not in (None, "") else 0.0
            # Canonicalize: new columns
            row["_gpu_tree"] = row.get("gpu_mem_tree_gb", row.get("gpu_mem_gb", 0.0))
            row["_gpu_total"] = row.get("gpu_mem_total_gb", row.get("gpu_mem_gb", 0.0))
            row["_rss"] = row.get("rss_tree_gb", row.get("rss_gb", 0.0))
            row["_cpu_proc"] = row.get("cpu_pct_proc_tree", row.get("cpu_pct_proc", 0.0))
            by_phase[row["phase"]].append(row)
            all_samples.append(row)

    # Load API usage
    api_calls = []
    if api_log.exists():
        with open(api_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    api_calls.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Build phase ordering by first occurrence
    phase_order = []
    seen = set()
    for row in all_samples:
        if row["phase"] not in seen:
            seen.add(row["phase"])
            phase_order.append(row["phase"])

    # Phase wall time = sum of consecutive runs (NOT last-first, since a phase may
    # appear, switch out, then reappear; we want the actual TIME spent in that phase).
    # Approximate per-sample dt as median sampling interval.
    phase_wall = defaultdict(float)
    phase_intervals = defaultdict(list)
    if len(all_samples) >= 2:
        dts = [all_samples[i + 1]["ts"] - all_samples[i]["ts"]
               for i in range(len(all_samples) - 1)]
        dts_sorted = sorted(dts)
        median_dt = dts_sorted[len(dts_sorted) // 2] if dts_sorted else 2.0
        for i, row in enumerate(all_samples):
            dt = (all_samples[i + 1]["ts"] - row["ts"]) if i + 1 < len(all_samples) else median_dt
            # Cap dt at 3× median to avoid blow-up from gaps
            dt = min(dt, 3.0 * median_dt)
            phase_wall[row["phase"]] += dt

    # Phase time bounds (for API call attribution — first/last ts of phase samples)
    phase_bounds = {}
    for phase in phase_order:
        rows = by_phase[phase]
        if rows:
            phase_bounds[phase] = (rows[0]["ts"], rows[-1]["ts"])

    # Attribute API calls to phases by timestamp
    api_by_phase = defaultdict(list)
    for call in api_calls:
        ts = call.get("ts", 0)
        attributed = "unknown"
        for phase, (start, end) in phase_bounds.items():
            if start <= ts <= end + 5:  # 5s slack
                attributed = phase
        api_by_phase[attributed].append(call)

    # Write summary
    with open(summary_md, "w") as f:
        f.write(f"# Hardware + API Summary — {log_dir.name}\n\n")

        if manifest.exists():
            try:
                m = json.load(open(manifest))
                f.write(f"**Command**: `{m.get('command', '?')}`\n")
                f.write(f"**Started**: {m.get('start_time_iso', '?')}\n")
                f.write(f"**Git SHA**: `{m.get('git_sha', '?')}`\n\n")
            except Exception:
                pass

        if all_samples:
            wall = all_samples[-1]["ts"] - all_samples[0]["ts"]
            f.write(f"**Total wall time**: {wall:.1f}s ({wall/60:.1f} min)\n\n")

        # Per-phase rows
        f.write("## Per-phase summary\n\n")
        f.write("> `GPU tree`: GPU memory used by the run's process tree (target + descendants).\n")
        f.write("> `GPU total`: ALL processes on the GPU (sanity vs other users).\n")
        f.write("> `wall`: sum of sample intervals tagged with this phase (correctly handles phase re-entry).\n\n")
        f.write("| Phase | wall | GPU tree peak | GPU total peak | RAM peak | CPU mean (sys/proc) | RSS peak | API calls | in tok | out tok | cost (USD) |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|\n")

        total_in = total_out = total_cost = total_calls = 0
        for phase in phase_order:
            rows = by_phase[phase]
            if not rows:
                continue
            wall = phase_wall.get(phase, 0.0)
            gpu_tree_peak = max(r["_gpu_tree"] for r in rows)
            gpu_total_peak = max(r["_gpu_total"] for r in rows)
            ram_peak = max(r["ram_used_gb"] for r in rows)
            cpu_sys_mean = sum(r["cpu_pct_sys"] for r in rows) / len(rows)
            cpu_proc_mean = sum(r["_cpu_proc"] for r in rows) / len(rows)
            rss_peak = max(r["_rss"] for r in rows)

            api_phase = api_by_phase.get(phase, [])
            in_tok = sum(c.get("prompt_tokens", 0) for c in api_phase)
            out_tok = sum(c.get("completion_tokens", 0) for c in api_phase)
            cost = 0.0
            for c in api_phase:
                p = get_pricing(c.get("model", ""))
                cost += c.get("prompt_tokens", 0) / 1e6 * p["input_per_1m"]
                cost += c.get("completion_tokens", 0) / 1e6 * p["output_per_1m"]

            total_in += in_tok
            total_out += out_tok
            total_cost += cost
            total_calls += len(api_phase)

            f.write(
                f"| `{phase}` | {wall:.0f}s | "
                f"{gpu_tree_peak:.2f} GB | {gpu_total_peak:.2f} GB | {ram_peak:.1f} GB | "
                f"{cpu_sys_mean:.0f}% / {cpu_proc_mean:.0f}% | {rss_peak:.1f} GB | "
                f"{len(api_phase)} | {in_tok:,} | {out_tok:,} | ${cost:.4f} |\n"
            )

        # Totals row
        if all_samples:
            total_wall = sum(phase_wall.values())
            f.write(
                f"| **TOTAL** | {total_wall:.0f}s | — | — | — | — | — | "
                f"{total_calls} | {total_in:,} | {total_out:,} | ${total_cost:.4f} |\n\n"
            )

        # Quality check — was 20 GB GPU exceeded?
        if all_samples:
            max_gpu_tree = max(r["_gpu_tree"] for r in all_samples)
            max_gpu_total = max(r["_gpu_total"] for r in all_samples)
            f.write("## Hardware invariant check\n\n")
            ok = "✓" if max_gpu_tree < 20.0 else "✗"
            f.write(f"- GPU tree peak < 20 GB: **{ok}** (observed {max_gpu_tree:.2f} GB)\n")
            f.write(f"- GPU total peak (all procs): {max_gpu_total:.2f} GB\n")

            high_gpu_phases = [
                phase for phase in phase_order
                if by_phase[phase] and max(r["_gpu_tree"] for r in by_phase[phase]) > 5.0
            ]
            if high_gpu_phases:
                f.write(f"- Phases with GPU > 5 GB (tree): {', '.join(f'`{p}`' for p in high_gpu_phases)}\n")

        # API call detail (optional, top-5 most expensive)
        if api_calls:
            sorted_calls = sorted(api_calls, key=lambda c: c.get("prompt_tokens", 0) + c.get("completion_tokens", 0), reverse=True)[:5]
            f.write("\n## Top 5 largest API calls (by total tokens)\n\n")
            f.write("| ts | model | in tok | out tok | cache hit |\n")
            f.write("|---|---|---|---|---|\n")
            for c in sorted_calls:
                f.write(
                    f"| {c.get('ts', 0):.0f} | {c.get('model', '?')} | "
                    f"{c.get('prompt_tokens', 0):,} | {c.get('completion_tokens', 0):,} | "
                    f"{c.get('cache_hit', False)} |\n"
                )

    print(f"[sidecar] wrote {summary_md}", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log-dir", required=True, type=Path)
    p.add_argument("--run-log", type=Path, default=None)
    p.add_argument("--target-pid", type=int, default=None)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--summary-only", action="store_true",
                   help="Skip polling, just generate summary from existing CSV + JSONL")
    args = p.parse_args()

    args.log_dir.mkdir(parents=True, exist_ok=True)

    if args.summary_only:
        aggregate_summary(args.log_dir)
        return

    if args.target_pid is None or args.run_log is None:
        print("ERROR: must supply --target-pid and --run-log for poll mode", file=sys.stderr)
        sys.exit(1)

    poll_loop(args.log_dir, args.run_log, args.target_pid, args.interval)


if __name__ == "__main__":
    main()
