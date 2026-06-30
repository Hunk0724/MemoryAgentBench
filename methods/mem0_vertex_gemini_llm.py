"""
Mem0 LLM provider that uses Vertex AI Gemini via the new `google.genai` SDK
(matches HippoRAG-v2's CacheGemini wrapper, ADC auth, no API key needed).

Routes through Vertex AI when GOOGLE_GENAI_USE_VERTEXAI=True is set.
Mem0 invokes this via LlmFactory by setting provider="vertex_gemini" after
registering this module.
"""

import json
import os
import re
import time
from typing import Dict, List, Optional

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from mem0.configs.llms.base import BaseLlmConfig
from mem0.llms.base import LLMBase


def _messages_to_gemini(messages: List[Dict[str, str]]):
    """OpenAI-style messages -> (system_instruction, contents)."""
    system = None
    contents = []
    for m in messages:
        role = m.get("role")
        text = m.get("content", "")
        if role == "system":
            system = text if system is None else f"{system}\n\n{text}"
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role in ("assistant", "model"):
            contents.append({"role": "model", "parts": [{"text": text}]})
    return system, contents


def _tools_to_gemini(tools):
    """Convert OpenAI tool schema to Gemini function declarations.

    Mem0 calls with `tools=[{"type":"function","function":{...}}]`.
    """
    if not tools:
        return None

    def _strip(d):
        if isinstance(d, dict):
            return {k: _strip(v) for k, v in d.items() if k != "additionalProperties"}
        if isinstance(d, list):
            return [_strip(x) for x in d]
        return d

    decls = []
    for t in tools:
        fn = t.get("function") if "function" in t else t
        decls.append(_strip(fn))
    return [types.Tool(function_declarations=decls)]


class VertexGeminiLLM(LLMBase):
    """Mem0 LLMBase impl using google.genai + Vertex AI ADC."""

    def __init__(self, config: Optional[BaseLlmConfig] = None):
        super().__init__(config)
        if not self.config.model:
            self.config.model = "gemini-3.1-flash-lite-preview"

        if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true":
            self.client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
        else:
            api_key = os.environ.get("Google_API_KEY") or os.environ.get("GEMINI_API_KEY")
            self.client = genai.Client(api_key=api_key)

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        response_format=None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
    ):
        system_instruction, contents = _messages_to_gemini(messages)

        cfg_kwargs = {
            "temperature": self.config.temperature if self.config.temperature is not None else 0.1,
            "max_output_tokens": self.config.max_tokens or 2048,
            "thinking_config": types.ThinkingConfig(thinking_level="minimal"),
        }
        if self.config.top_p is not None:
            cfg_kwargs["top_p"] = self.config.top_p
        if response_format and isinstance(response_format, dict) and response_format.get("type") == "json_object":
            cfg_kwargs["response_mime_type"] = "application/json"

        gemini_tools = _tools_to_gemini(tools)
        if gemini_tools:
            cfg_kwargs["tools"] = gemini_tools

        cfg = types.GenerateContentConfig(**cfg_kwargs)
        if system_instruction:
            cfg.system_instruction = system_instruction

        max_retries = 8
        for attempt in range(max_retries):
            try:
                resp = self.client.models.generate_content(
                    model=self.config.model,
                    contents=contents,
                    config=cfg,
                )
                break
            except (ClientError, ServerError) as e:
                code = getattr(e, "code", None)
                if code not in (429, 503) or attempt == max_retries - 1:
                    raise
                m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
                time.sleep(float(m.group(1)) + 2 if m else min(2 ** attempt * 5, 60))

        if not gemini_tools:
            text = resp.text or ""
            # Per-call debug to diagnose chunk-level fact extraction failures.
            self._n_calls = getattr(self, "_n_calls", 0) + 1
            user_prompt = ""
            for c in contents:
                for p in c.get("parts", []):
                    user_prompt += p.get("text", "")
            head_user = user_prompt[:150].replace("\n", " | ")
            head_resp = text[:200].replace("\n", " | ")
            print(f"[VG#{self._n_calls}] usr_len={len(user_prompt)} resp_len={len(text)} | "
                  f"usr_head={head_user!r} | resp={head_resp!r}", flush=True)
            if not text:
                # Diagnostic: print finish_reason / safety to help debug empty responses
                try:
                    cand = resp.candidates[0] if resp.candidates else None
                    fr = getattr(cand, "finish_reason", None) if cand else None
                    sr = getattr(cand, "safety_ratings", None) if cand else None
                    print(f"[VertexGemini] empty text — finish_reason={fr}, safety={sr}", flush=True)
                except Exception:
                    pass
            return text

        # Tools mode: return Mem0-expected dict
        text = resp.text or ""
        tool_calls = []
        try:
            for part in resp.candidates[0].content.parts:
                fn = getattr(part, "function_call", None)
                if fn and getattr(fn, "name", None):
                    args = dict(fn.args) if fn.args else {}
                    tool_calls.append({"name": fn.name, "arguments": args})
        except Exception:
            pass
        return {"content": text or None, "tool_calls": tool_calls}
