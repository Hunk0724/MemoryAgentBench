"""Phase 3 v2.0.2 — Enriched Memory Output.

Spec: docs/method_design_v2.0.2_spec.md §B.4 (Enriched context format LOCKED).

W3 Step 2 implementation:
- enriched_context_renderer.render_enriched_context(active_chain, supersession_events, ...)
- Hook in HippoRAG.qa() between passages and Question: line.
- LLM prompt template UNCHANGED — only retrieval_context body extended.
"""
from .enriched_context_renderer import (
    render_enriched_context,
    render_reasoning_hint,
    render_change_log,
)

__all__ = [
    "render_enriched_context",
    "render_reasoning_hint",
    "render_change_log",
]
