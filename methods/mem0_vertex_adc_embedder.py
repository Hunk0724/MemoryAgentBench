"""ADC-compatible Vertex AI embedder for mem0.

Uses the new google.genai SDK (same path as methods/mem0_vertex_gemini_llm.py),
so authentication goes through Application Default Credentials. No service-
account JSON is needed (unlike the upstream mem0/embeddings/vertexai.py which
hard-requires GOOGLE_APPLICATION_CREDENTIALS pointing to a SA JSON file).

Mem0 invokes this by monkey-patching:

    EmbedderFactory.provider_to_class["vertexai"] = \
        "mem0_vertex_adc_embedder.VertexADCEmbedding"

(done in agent.py:_initialize_mem0_agent before Memory() is constructed).

Reference:
- google-genai SDK Client(vertexai=True, project, location) + models.embed_content
  https://mintlify.com/googleapis/python-genai/api/models/embed-content
- text-embedding-004 model, 768-dim by default
"""
from __future__ import annotations

import os
import time
from typing import List, Literal, Optional

from google import genai
from google.genai import types as genai_types

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.embeddings.base import EmbeddingBase


class VertexADCEmbedding(EmbeddingBase):
    """Mem0 embedder backed by Vertex AI text embeddings, via ADC.

    Same auth pattern as VertexGeminiLLM. Drop-in for any embedder that
    expects mem0's EmbeddingBase interface.
    """

    # Map mem0's memory_action semantic to Vertex task_type
    _ACTION_TO_TASK_TYPE = {
        "add":    "RETRIEVAL_DOCUMENT",
        "update": "RETRIEVAL_DOCUMENT",
        "search": "RETRIEVAL_QUERY",
    }

    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        super().__init__(config)
        self.config.model = self.config.model or "text-embedding-004"
        self.config.embedding_dims = self.config.embedding_dims or 768

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT must be set for VertexADCEmbedding. "
                "Tip: source the repo .env, or set in the shell."
            )
        self.client = genai.Client(
            vertexai=True, project=project, location=location,
        )

    # --------------------------------------------------------------------- #
    # core embed
    # --------------------------------------------------------------------- #
    def _embed_with_retry(self, contents: List[str], task_type: str,
                          max_retries: int = 6) -> List[List[float]]:
        cfg = genai_types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self.config.embedding_dims,
        )
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = self.client.models.embed_content(
                    model=self.config.model,
                    contents=contents,
                    config=cfg,
                )
                return [e.values for e in resp.embeddings]
            except Exception as e:  # rate limit, transient server
                last_err = e
                msg = str(e)
                code = getattr(e, "code", None)
                if code not in (429, 503) and "429" not in msg and "503" not in msg:
                    raise
                delay = min(2 ** attempt * 4, 60)
                print(f"[VertexADCEmbedding retry] attempt {attempt+1}/{max_retries}, "
                      f"sleeping {delay}s ({type(e).__name__})", flush=True)
                time.sleep(delay)
        raise last_err  # type: ignore

    def embed(
        self,
        text,
        memory_action: Optional[Literal["add", "search", "update"]] = None,
    ):
        """Mem0's EmbeddingBase.embed signature: takes one string, returns one vector."""
        task_type = self._ACTION_TO_TASK_TYPE.get(memory_action, "SEMANTIC_SIMILARITY")
        text = text or ""
        text = text.replace("\n", " ")
        vectors = self._embed_with_retry([text], task_type)
        return vectors[0]
