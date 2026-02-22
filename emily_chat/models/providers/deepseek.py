"""DeepSeek provider — V3.2 and R2 models.

DeepSeek exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint.

Key behaviours:
* DeepSeek V3.2: standard text streaming, no thinking.
* DeepSeek R2: reasoning is embedded in the content stream inside
  ``<think>…</think>`` tags.  The :class:`ThinkTagExtractor` in the
  base class separates these automatically.
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider

_BASE_URL = "https://api.deepseek.com"

_THINK_TAG_MODELS = ("deepseek-r", "deepseek-reasoner")


class DeepSeekProvider(OpenAICompatibleProvider):
    """Async streaming provider for DeepSeek models.

    Args:
        api_key: DeepSeek API key.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "DeepSeek"

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout=timeout)

    def supports_thinking(self) -> bool:
        """DeepSeek R2 emits thinking via ``<think>`` tags."""
        return True

    def _uses_think_tags(self, model_id: str) -> bool:
        """Return ``True`` for R-series reasoning models.

        Args:
            model_id: The DeepSeek model identifier.
        """
        lower = model_id.lower()
        return any(lower.startswith(p) for p in _THINK_TAG_MODELS)
