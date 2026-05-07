"""Gemini LLM adapter for HippoRAG, mirrors CacheOpenAI interface.

Routes based on .env:
  - GOOGLE_GENAI_USE_VERTEXAI=True → Vertex AI via ADC
    (uses GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION)
  - Otherwise → AI Studio via Google_API_KEY
"""
import os
import re
import time
from copy import deepcopy
from typing import List, Tuple

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from .base import BaseLLM, LLMConfig
from .openai_gpt import cache_response  # reuse the SQLite cache decorator
from ..utils.config_utils import BaseConfig
from ..utils.llm_utils import TextChatMessage
from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


def _messages_to_gemini(messages: List[TextChatMessage]):
    """Convert OpenAI-style chat messages to Gemini (system_instruction, contents) pair."""
    system = None
    contents = []
    for m in messages:
        role = m.get("role")
        text = m.get("content", "")
        if role == "system":
            system = text if system is None else f"{system}\n\n{text}"
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
    return system, contents


class CacheGemini(BaseLLM):
    """Gemini LLM backend compatible with HippoRAG's BaseLLM interface."""

    @classmethod
    def from_experiment_config(cls, global_config: BaseConfig) -> "CacheGemini":
        config_dict = global_config.__dict__
        cache_dir = os.path.join(global_config.save_dir, "llm_cache")
        api_key = getattr(global_config, "llm_api_key", None)
        return cls(cache_dir=cache_dir, api_key=api_key, **config_dict)

    def __init__(self, cache_dir, cache_filename: str = None,
                 llm_name: str = "gemini-3.1-flash-lite-preview",
                 api_key: str = None, **kwargs) -> None:
        super().__init__()
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        if cache_filename is None:
            cache_filename = f"{llm_name.replace('/', '_')}_cache.sqlite"
        self.cache_file_name = os.path.join(self.cache_dir, cache_filename)
        self.llm_name = llm_name
        self._init_llm_config(**kwargs)

        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        if use_vertex:
            self.client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            )
        else:
            self.client = genai.Client(api_key=api_key or os.environ.get("Google_API_KEY"))

    def _init_llm_config(self, **kwargs) -> None:
        config_dict = {
            "llm_name": self.llm_name,
            "generate_params": {
                "model": self.llm_name,
                "max_output_tokens": kwargs.get("max_new_tokens", 400),
                "temperature": kwargs.get("temperature", 0.0),
            },
        }
        self.llm_config = LLMConfig.from_dict(config_dict=config_dict)

    @cache_response
    def infer(self, messages: List[TextChatMessage], **kwargs) -> Tuple[str, dict]:
        params = deepcopy(self.llm_config.generate_params)
        if kwargs:
            params.update(kwargs)

        system_instruction, contents = _messages_to_gemini(messages)

        gen_config = types.GenerateContentConfig(
            temperature=params["temperature"],
            max_output_tokens=params["max_output_tokens"],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if system_instruction:
            gen_config.system_instruction = system_instruction

        max_retries = 10
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=params["model"],
                    contents=contents,
                    config=gen_config,
                )
                break
            except (ClientError, ServerError) as e:
                code = getattr(e, "code", None)
                if code not in (429, 503) or attempt == max_retries - 1:
                    raise
                msg = str(e)
                m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
                delay = float(m.group(1)) + 2 if m else min(2 ** attempt * 5, 60)
                logger.warning(f"[gemini retry] {code} attempt {attempt + 1}/{max_retries}, sleep {delay:.1f}s")
                time.sleep(delay)

        text = response.text if response.text is not None else ""
        um = response.usage_metadata
        metadata = {
            "prompt_tokens": getattr(um, "prompt_token_count", 0),
            "completion_tokens": getattr(um, "candidates_token_count", 0),
            "finish_reason": str(getattr(response.candidates[0], "finish_reason", "stop")) if response.candidates else "stop",
        }
        return text, metadata
