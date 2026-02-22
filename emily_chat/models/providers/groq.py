"""Groq provider — ultra-low-latency inference on LPU hardware.

Groq serves open-weight models (Llama, DeepSeek R1-distill, Qwen3) via
an OpenAI-compatible ``/v1/chat/completions`` endpoint.

Key behaviours:
* Standard chat models (Llama 3.3 70B, Llama 4 Scout): plain text
  streaming, no thinking.
* R1-distill and Qwen3 models: reasoning is embedded in the content
  stream inside ``<think>…</think>`` tags.  The :class:`ThinkTagExtractor`
  in the base class separates these automatically.
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider

_BASE_URL = "https://api.groq.com/openai/v1"

_THINK_TAG_MODEL_PREFIXES = (
    "deepseek-r1",
    "qwen3",
    "qwq",
)


class GroqProvider(OpenAICompatibleProvider):
    """Async streaming provider for Groq-hosted models.

    Args:
        api_key: Groq API key.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "Groq"

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout=timeout)

    def supports_thinking(self) -> bool:
        """R1-distill and Qwen3 models on Groq emit thinking via tags."""
        return True

    def _uses_think_tags(self, model_id: str) -> bool:
        """Return ``True`` for R1-distill, Qwen3, and QwQ models.

        Args:
            model_id: The Groq model identifier.
        """
        lower = model_id.lower()
        return any(lower.startswith(p) for p in _THINK_TAG_MODEL_PREFIXES)
