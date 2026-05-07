import os

from ..utils.logging_utils import get_logger
from ..utils.config_utils import BaseConfig

from .openai_gpt import CacheOpenAI
from .base import BaseLLM

logger = get_logger(__name__)


def _get_llm_class(config: BaseConfig):
    llm_name = getattr(config, 'llm_name', '') or ''
    if 'gemini' in llm_name.lower():
        from .gemini_llm import CacheGemini
        return CacheGemini.from_experiment_config(config)
    if config.llm_base_url is not None and 'localhost' in config.llm_base_url and os.getenv('OPENAI_API_KEY') is None:
        os.environ['OPENAI_API_KEY'] = 'sk-'
    return CacheOpenAI.from_experiment_config(config)
    