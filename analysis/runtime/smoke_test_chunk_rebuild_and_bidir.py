"""Smoke test — C-v2 changes:
  1. Verdict bidirectional aggregation
  2. B2 chunk_rebuild filter

Tests:
  T1. Verdict.older_contradicting_pool_pids field exists (dataclass smoke)
  T2. _make_verdict populates older list correctly (synthetic ts cases)
  T3. chunk_rebuild: no old in chunk → unchanged
  T4. chunk_rebuild: 1 old in chunk → that prop text gone, others kept, ordered
  T5. chunk_rebuild: all old → empty
  T6. real chunk 0: remove prop[0,5] → that fact gone, others kept (loose)
  T7. config flags exist + default False (vanilla path preserved)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

BASE = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(BASE))

from methods.hipporag.phase2c.chunk_rebuild import rebuild_chunk_minus_old  # noqa: E402
from methods.hipporag.phase2b.data_structures import Verdict  # noqa: E402
from methods.hipporag.phase2b.verdict import _decide_verdict_mechanically  # noqa: E402
from methods.hipporag.utils.config_utils import BaseConfig  # noqa: E402

RAG = BASE / ("outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/"
              "chunksize_512/context_id_0/"
              "gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2")


def assert_ok(cond, msg, fail_info=""):
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        if fail_info:
            print(f"      {fail_info}")
        raise AssertionError(msg)


def main():
    # ─── T1: Verdict dataclass has new field ──────────────────────────────
    print("T1 — Verdict.older_contradicting_pool_pids field")
    v = Verdict(status="current", confidence="high")
    assert_ok(hasattr(v, "older_contradicting_pool_pids"),
              "Verdict has older_contradicting_pool_pids attribute")
    d = v.to_dict()
    assert_ok(d.get("older_contradicting_pool_pids") == [],
              "default → empty list in to_dict()",
              fail_info=f"got {d.get('older_contradicting_pool_pids')!r}")

    # ─── T2: _make_verdict populates earlier correctly ────────────────────
    print("\nT2 — _make_verdict populates older_contradicting_pool_pids")
    focus = SimpleNamespace(id="F", text="F text", timestamp=(5, 5))
    propositions = {
        "P_OLDER": SimpleNamespace(id="P_OLDER", timestamp=(2, 0), text="older"),
        "P_LATER": SimpleNamespace(id="P_LATER", timestamp=(7, 0), text="later"),
        "P_OLDER2": SimpleNamespace(id="P_OLDER2", timestamp=(1, 0), text="older2"),
    }

    # Case A: contradicting includes both older & later → status superseded,
    # older list should still contain the older pool pids
    out = _decide_verdict_mechanically(
        focus=focus,
        contradicting_pids=["P_LATER", "P_OLDER", "P_OLDER2"],
        parse_failed=False,
        propositions=propositions,
        pool_size=3,
        sources=[],
        llm_reason="test"
    )
    assert_ok(out.status == "superseded", "status=superseded when later exists")
    assert_ok(out.superseder_id == "P_LATER", "superseder = latest")
    assert_ok(set(out.older_contradicting_pool_pids) == {"P_OLDER", "P_OLDER2"},
              "older list captures all earlier pool pids",
              fail_info=f"got {out.older_contradicting_pool_pids}")

    # Case B: contradicting includes only older → status current low conf,
    # but older list should still be populated
    out = _decide_verdict_mechanically(
        focus=focus,
        contradicting_pids=["P_OLDER", "P_OLDER2"],
        parse_failed=False,
        propositions=propositions,
        pool_size=2, sources=[], llm_reason="test2"
    )
    assert_ok(out.status == "current", "status=current when no later")
    assert_ok(out.confidence == "low", "confidence=low (defensive)")
    assert_ok(set(out.older_contradicting_pool_pids) == {"P_OLDER", "P_OLDER2"},
              "older list still captured when focus is newer",
              fail_info=f"got {out.older_contradicting_pool_pids}")

    # Case C: no contradicting → older empty
    out = _decide_verdict_mechanically(
        focus=focus, contradicting_pids=[], parse_failed=False,
        propositions=propositions, pool_size=0, sources=[], llm_reason=""
    )
    assert_ok(out.older_contradicting_pool_pids == [],
              "no contradicting → older list empty")

    # ─── T3: chunk_rebuild — no old in chunk ──────────────────────────────
    print("\nT3 — chunk_rebuild: no chain_old in chunk → unchanged")
    syn_props = {
        "p1": SimpleNamespace(text="Alice is the CEO of Acme.", timestamp=(0, 0)),
        "p2": SimpleNamespace(text="Bob is married to Carol.", timestamp=(0, 1)),
        "p3": SimpleNamespace(text="David lives in Paris.", timestamp=(0, 2)),
    }
    original = "Some chunk text. 0. Alice is the CEO of Acme. 1. Bob is married to Carol."
    out = rebuild_chunk_minus_old(
        original, ["p1", "p2"], set(), syn_props
    )
    assert_ok(out == original, "no overlap with chain_old → original returned")

    # ─── T4: chunk_rebuild — 1 old removed, others kept in order ──────────
    print("\nT4 — chunk_rebuild: remove 1 prop, order preserved")
    out = rebuild_chunk_minus_old(
        original, ["p1", "p2", "p3"], {"p2"}, syn_props
    )
    assert_ok("Alice is the CEO" in out, "Alice (non-old) kept")
    assert_ok("David lives in Paris" in out, "David (non-old) kept")
    assert_ok("Bob is married" not in out, "Bob (old) removed",
              fail_info=f"out={out}")
    # Order: Alice (ts=0,0) before David (ts=0,2)
    assert_ok(out.index("Alice") < out.index("David"),
              "order: Alice (pos 0) before David (pos 2)")

    # ─── T5: chunk_rebuild — all olds → empty ─────────────────────────────
    print("\nT5 — chunk_rebuild: all props old → empty")
    out = rebuild_chunk_minus_old(
        original, ["p1", "p2", "p3"], {"p1", "p2", "p3"}, syn_props
    )
    assert_ok(out == "", "all old → empty string", fail_info=f"out={out!r}")

    # ─── T6: real chunk 0 ──────────────────────────────────────────────────
    print("\nT6 — chunk_rebuild on real chunk 0")
    df = pd.read_parquet(RAG / "chunk_embeddings/vdb_chunk.parquet")
    props_all = json.load(open(RAG / "proposition_index.json"))["propositions"]
    chunk_text_by_id = dict(zip(df["hash_id"], df["content"]))
    by_chunk = defaultdict(list)
    prop_idx = {}
    for p in props_all:
        by_chunk[p["source_chunk_id"]].append(p["id"])
        prop_idx[p["id"]] = SimpleNamespace(
            id=p["id"], text=p["text"], timestamp=tuple(p["timestamp"]),
            entities=p["entities"], source_chunk_id=p["source_chunk_id"],
        )
    cid0 = list(chunk_text_by_id.keys())[0]
    chunk0 = chunk_text_by_id[cid0]
    pids0 = sorted(by_chunk[cid0], key=lambda pid: prop_idx[pid].timestamp[1])
    # Remove prop at position 5
    target_pid = pids0[5]
    target_text = prop_idx[target_pid].text
    print(f"  target prop: '{target_text}'")
    out = rebuild_chunk_minus_old(
        chunk0, pids0, {target_pid}, prop_idx
    )
    # Check: target text not in out (modulo canonicalization)
    # We can only do an entity-substring check since chunk text != prop text
    target_entities = prop_idx[target_pid].entities
    # The target's entities should NOT all appear in remaining text together
    # (they may appear individually due to other props mentioning same entities)
    # Simpler: count occurrences of target_text as substring
    assert_ok(target_text not in out,
              f"target prop text '{target_text[:50]}...' removed",
              fail_info=f"prefix of out: {out[:200]}")
    # Other props should be present
    other_pid = pids0[0]
    other_text = prop_idx[other_pid].text
    assert_ok(other_text in out,
              f"other prop '{other_text[:40]}' still present",
              fail_info=f"prefix of out: {out[:200]}")

    # ─── T7: config flags exist + default False ──────────────────────────
    print("\nT7 — config flags default False (vanilla path preserved)")
    cfg = BaseConfig()
    assert_ok(cfg.enable_phase2_filter_chunk_rebuild is False,
              "enable_phase2_filter_chunk_rebuild default False")
    assert_ok(cfg.enable_phase2_verdict_bidirectional is False,
              "enable_phase2_verdict_bidirectional default False")
    # Both ON
    cfg2 = BaseConfig(
        enable_phase2_filter_chunk_rebuild=True,
        enable_phase2_verdict_bidirectional=True,
    )
    assert_ok(cfg2.enable_phase2_filter_chunk_rebuild and cfg2.enable_phase2_verdict_bidirectional,
              "both flags can be set True via kwargs")

    print("\n" + "=" * 60)
    print("✅ ALL SMOKE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
