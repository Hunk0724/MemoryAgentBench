"""Snapshot run state — write a manifest BEFORE a GPU run so future you knows
exactly what code + cache state produced a given EM number.

Usage:
  python analysis/runtime/snapshot_run_state.py \
      --run-dir monitoring_logs/2026-MM-DD_HHMMSS_ablation_X \
      --ablation-name X \
      --notes "any text"

Writes <run-dir>/run_manifest.pre.json with:
  - timestamp (ISO 8601)
  - git: commit hash + dirty flag + branch
  - code identity: hash of key code files (HippoRAG.py, config_utils.py)
  - cache identity: hash of key cache files (graph.graphml, proposition_index.json)
  - env: relevant env vars (HIPPORAG_*)
  - ablation_name + notes

After the run, call snapshot_run_state.py again with --post to write
<run-dir>/run_manifest.post.json with:
  - all files created/modified in run-dir
  - any cache files whose hash changed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")


def file_hash(path: Path, max_bytes: int = 10_000_000) -> dict:
    """Return {sha256_prefix, size, mtime}. Truncates very large files."""
    if not path.exists():
        return {"exists": False}
    st = path.stat()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(max_bytes))
    return {
        "exists": True,
        "size_bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "sha256_prefix": h.hexdigest()[:16],
        "truncated_at": max_bytes if st.st_size > max_bytes else None,
    }


# Code files whose state defines algorithm
CODE_FILES = [
    "methods/hipporag/HippoRAG.py",
    "methods/hipporag/utils/config_utils.py",
    "methods/hipporag/phase2a",
    "methods/hipporag/phase2b",
    "methods/hipporag/phase3",
    "agent.py",
]

# Cache files (heavy artifacts that get reused across runs)
CACHE_PATTERN_512 = (
    "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/"
    "chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2"
)
CACHE_FILES = [
    f"{CACHE_PATTERN_512}/graph.graphml",
    f"{CACHE_PATTERN_512}/chunk_embeddings/vdb_chunk.parquet",
    f"{CACHE_PATTERN_512}/entity_embeddings/vdb_entity.parquet",
    f"{CACHE_PATTERN_512}/fact_embeddings/vdb_fact.parquet",
    f"{CACHE_PATTERN_512}/supersession_index.json",
    f"{CACHE_PATTERN_512}/proposition_index.json",
]


def collect_state(run_dir: Path, ablation_name: str, notes: str) -> dict:
    """Capture everything needed to reproduce / identify a run."""
    # git info
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=BASE, text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=BASE, text=True
        ).strip()
        # dirty?
        diff = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"], cwd=BASE
        ).returncode
        dirty = diff != 0
    except Exception as e:
        commit = f"ERROR: {e}"
        branch = "unknown"
        dirty = None

    state = {
        "timestamp": datetime.now().isoformat(),
        "run_dir": str(run_dir.relative_to(BASE)) if run_dir.is_absolute() else str(run_dir),
        "ablation_name": ablation_name,
        "notes": notes,
        "git": {
            "commit_hash": commit,
            "branch": branch,
            "working_tree_dirty": dirty,
        },
        "code_files": {
            f: file_hash(BASE / f) if (BASE / f).is_file() else {"is_dir": (BASE / f).is_dir()}
            for f in CODE_FILES
        },
        "cache_files": {f: file_hash(BASE / f) for f in CACHE_FILES},
        "env_vars": {
            k: v for k, v in os.environ.items()
            if k.startswith("HIPPORAG_") or k.startswith("GOOGLE_") or k.startswith("OPENAI_")
        },
    }
    # redact API key values, keep only existence flag
    for k in list(state["env_vars"]):
        if "KEY" in k or "TOKEN" in k or "SECRET" in k:
            state["env_vars"][k] = "<REDACTED, exists>"
    return state


def post_diff(run_dir: Path, pre_state: dict) -> dict:
    """After a run, list files created/modified in run_dir + which cache files changed."""
    post = {
        "timestamp": datetime.now().isoformat(),
        "files_in_run_dir": [],
        "cache_files_changed": {},
    }
    if run_dir.is_dir():
        for p in sorted(run_dir.rglob("*")):
            if p.is_file() and p.name not in ("run_manifest.pre.json", "run_manifest.post.json"):
                st = p.stat()
                post["files_in_run_dir"].append({
                    "path": str(p.relative_to(run_dir)),
                    "size_bytes": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                })

    # Compare cache files
    for f, pre_h in pre_state.get("cache_files", {}).items():
        post_h = file_hash(BASE / f)
        if pre_h.get("sha256_prefix") != post_h.get("sha256_prefix") or \
           pre_h.get("size_bytes") != post_h.get("size_bytes"):
            post["cache_files_changed"][f] = {
                "before": pre_h,
                "after": post_h,
            }
    return post


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="Target monitoring_logs/<TS>_ablation_X dir")
    ap.add_argument("--ablation-name", default="unspecified")
    ap.add_argument("--notes", default="")
    ap.add_argument("--post", action="store_true",
                    help="Write post-run manifest (compares against pre-run)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    if not args.post:
        state = collect_state(run_dir, args.ablation_name, args.notes)
        out = run_dir / "run_manifest.pre.json"
        json.dump(state, open(out, "w"), indent=2, default=str)
        print(f"[snapshot pre] wrote {out}")
        print(f"  commit={state['git']['commit_hash'][:8]}  dirty={state['git']['working_tree_dirty']}")
        n_cache = sum(1 for v in state["cache_files"].values() if v.get("exists"))
        print(f"  cache files present: {n_cache}/{len(CACHE_FILES)}")
    else:
        pre_path = run_dir / "run_manifest.pre.json"
        if not pre_path.exists():
            raise FileNotFoundError(f"No pre-manifest at {pre_path}; run without --post first")
        pre_state = json.load(open(pre_path))
        post = post_diff(run_dir, pre_state)
        out = run_dir / "run_manifest.post.json"
        json.dump(post, open(out, "w"), indent=2, default=str)
        print(f"[snapshot post] wrote {out}")
        print(f"  new files in run-dir: {len(post['files_in_run_dir'])}")
        print(f"  cache files changed: {len(post['cache_files_changed'])}")


if __name__ == "__main__":
    main()
