"""Smoke test — T1 scoring variants.

Tests:
  T1. adhoc variant produces same result as before (regression safety)
  T2. pure_relevance returns only the relevance term
  T3. proprag_strict requires embedding_model; raises if missing
  T4. proprag_strict on synthetic chain produces a cosine score in [-1, 1]
  T5. config flag default = 'adhoc'; env var override works
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BASE = Path("/home/yhchiang/MemoryAgentBench")
sys.path.insert(0, str(BASE))

from methods.hipporag.phase2a.scoring_variants import score_chains_batch  # noqa: E402
from methods.hipporag.utils.config_utils import BaseConfig  # noqa: E402


def assert_ok(cond, msg, fail=""):
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        if fail:
            print(f"     {fail}")
        raise AssertionError(msg)


def main():
    # Build synthetic propositions
    rng = np.random.default_rng(42)
    emb_dim = 4096
    q_emb = rng.standard_normal(emb_dim).astype("float32")
    q_emb /= np.linalg.norm(q_emb)

    # Three synthetic props
    p_embs = [rng.standard_normal(emb_dim).astype("float32") for _ in range(3)]
    p_embs = [e / np.linalg.norm(e) for e in p_embs]
    props = {
        "p1": SimpleNamespace(id="p1", text="Alice is the CEO of Acme.",
                              entities=["Alice", "Acme"], embedding=p_embs[0].tolist()),
        "p2": SimpleNamespace(id="p2", text="Alice is married to Carol.",
                              entities=["Alice", "Carol"], embedding=p_embs[1].tolist()),
        "p3": SimpleNamespace(id="p3", text="Carol lives in Paris.",
                              entities=["Carol", "Paris"], embedding=p_embs[2].tolist()),
    }
    ppr = {"p1": 0.5, "p2": 0.3, "p3": 0.2}
    chains = [
        {"prop_ids": ["p1"], "entities_path": []},
        {"prop_ids": ["p1", "p2"], "entities_path": [{"Alice"}]},
        {"prop_ids": ["p1", "p2", "p3"], "entities_path": [{"Alice"}, {"Carol"}]},
    ]

    # ─── T1: adhoc ──────────────────────────────────────────────────────
    print("T1 — adhoc returns standard breakdown")
    res = score_chains_batch(chains, props, q_emb, ppr, variant="adhoc")
    assert_ok(len(res) == 3, "returns 3 results for 3 chains")
    s2, b2 = res[1]  # 2-chain
    assert_ok("relevance" in b2 and "coherence" in b2 and "ppr_coverage" in b2 and "length_penalty" in b2,
              "adhoc breakdown has 4 components",
              fail=f"keys: {list(b2.keys())}")
    expected_rel = float(np.dot(p_embs[0], q_emb)) + float(np.dot(p_embs[1], q_emb))
    assert_ok(abs(b2["relevance"] - expected_rel) < 1e-4,
              f"adhoc relevance = Σ cosine (expected {expected_rel:.4f}, got {b2['relevance']:.4f})")
    expected_total = expected_rel + 0.3 * 1.0 + 0.2 * (0.5 + 0.3) + (-0.1) * 2
    assert_ok(abs(s2 - expected_total) < 1e-4,
              f"adhoc total = rel + 0.3·coh + 0.2·ppr − 0.1·len ({expected_total:.4f})")

    # ─── T2: pure_relevance ─────────────────────────────────────────────
    print("\nT2 — pure_relevance returns ONLY relevance term")
    res = score_chains_batch(chains, props, q_emb, ppr, variant="pure_relevance")
    s2, b2 = res[1]
    assert_ok("relevance" in b2 and "coherence" not in b2,
              "pure_relevance breakdown has only relevance")
    assert_ok(abs(s2 - expected_rel) < 1e-4,
              f"pure_relevance score = Σ cosine = {expected_rel:.4f}, got {s2:.4f}")

    # ─── T3: proprag_strict requires embedding model ────────────────────
    print("\nT3 — proprag_strict requires embedding_model")
    raised = False
    try:
        score_chains_batch(chains, props, q_emb, ppr, variant="proprag_strict")
    except ValueError as e:
        if "embedding_model" in str(e):
            raised = True
    assert_ok(raised, "proprag_strict raises ValueError without embedding_model")

    # ─── T4: proprag_strict with mock embedding model ───────────────────
    print("\nT4 — proprag_strict produces cosine in [-1, 1]")

    class MockModel:
        """Returns a deterministic random embedding for each text."""
        def batch_encode(self, texts, norm=True, disable_tqdm=True, batch_size=8):
            embs = []
            for t in texts:
                # Hash text to deterministic seed
                seed = sum(ord(c) for c in t) % 100000
                local = np.random.default_rng(seed)
                e = local.standard_normal(emb_dim).astype("float32")
                if norm:
                    e /= np.linalg.norm(e)
                embs.append(e)
            return np.stack(embs)

    res = score_chains_batch(chains, props, q_emb, ppr,
                              variant="proprag_strict", embedding_model=MockModel())
    assert_ok(len(res) == 3, "returns 3 results")
    s2, b2 = res[1]
    assert_ok(-1.0 <= s2 <= 1.0, f"proprag score in [-1, 1] (got {s2:.4f})")
    assert_ok(b2.get("variant") == "proprag_strict", "breakdown.variant marked correctly")
    # Different chains should generally give different scores
    scores_all = [r[0] for r in res]
    assert_ok(len(set(scores_all)) == 3, "different chains → different scores",
              fail=f"scores: {scores_all}")

    # ─── T5: config flag default + env override ─────────────────────────
    print("\nT5 — config flag default + env override")
    cfg = BaseConfig()
    assert_ok(cfg.phase2a_scoring_variant == "adhoc", "default = 'adhoc'")

    os.environ["HIPPORAG_PHASE2A_SCORING_VARIANT"] = "proprag_strict"
    cfg2 = BaseConfig()
    assert_ok(cfg2.phase2a_scoring_variant == "proprag_strict",
              "env var override works (proprag_strict)")
    os.environ["HIPPORAG_PHASE2A_SCORING_VARIANT"] = "pure_relevance"
    cfg3 = BaseConfig()
    assert_ok(cfg3.phase2a_scoring_variant == "pure_relevance",
              "env var override works (pure_relevance)")

    # Invalid value → keep default
    os.environ["HIPPORAG_PHASE2A_SCORING_VARIANT"] = "bogus"
    cfg4 = BaseConfig()
    assert_ok(cfg4.phase2a_scoring_variant == "adhoc",
              "invalid env value → keep default 'adhoc'")
    del os.environ["HIPPORAG_PHASE2A_SCORING_VARIANT"]

    print("\n" + "=" * 60)
    print("✅ ALL SMOKE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
