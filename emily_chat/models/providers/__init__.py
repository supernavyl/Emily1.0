"""LLM provider implementations — one module per API backend.

All providers extend :class:`BaseProvider` (or its
:class:`OpenAICompatibleProvider` subclass) and yield
:class:`~emily_chat.models.streaming_engine.StreamChunk` objects.
"""

from emily_chat.models.providers._openai_compat import (
    OpenAICompatibleProvider,
    ThinkTagExtractor,
)
from emily_chat.models.providers.base import BaseProvider
from emily_chat.models.providers.deepseek import DeepSeekProvider
from emily_chat.models.providers.groq import GroqProvider
from emily_chat.models.providers.mistral import MistralProvider
from emily_chat.models.providers.ollama import OllamaProvider
from emily_chat.models.providers.openai import OpenAIProvider
from emily_chat.models.providers.openrouter import OpenRouterProvider
from emily_chat.models.providers.together import TogetherProvider
from emily_chat.models.providers.xai import XAIProvider

__all__ = [
    "BaseProvider",
    "OpenAICompatibleProvider",
    "ThinkTagExtractor",
    "OpenAIProvider",
    "GroqProvider",
    "XAIProvider",
    "DeepSeekProvider",
    "TogetherProvider",
    "MistralProvider",
    "OpenRouterProvider",
    "OllamaProvider",
]
