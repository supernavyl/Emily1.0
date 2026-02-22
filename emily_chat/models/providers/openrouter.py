"""OpenRouter provider — 300+ model pass-through via a single API key.

OpenRouter exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint
that routes to any of 300+ models from dozens of providers.  Users
specify the model by its OpenRouter slug (e.g. ``moonshotai/kimi-k2-thinking``).

Key behaviours:
* Standard OpenAI-compatible SSE streaming.
* Extra ``HTTP-Referer`` and ``X-Title`` headers for attribution.
* Think-tag extraction for models that embed reasoning in
  ``<think>…</think>`` tags (Kimi K2, GLM 4.7, DeepSeek R1, Qwen3).
* A factory method to create :class:`ModelSpec` entries for arbitrary
  user-specified model strings.
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider
from emily_chat.models.registry import ModelSpec

_BASE_URL = "https://openrouter.ai/api/v1"

_THINK_TAG_PATTERNS = (
    "kimi-k2",
    "glm-4",
    "deepseek-r",
    "qwen3",
    "qwq",
)


class OpenRouterProvider(OpenAICompatibleProvider):
    """Async streaming provider for OpenRouter-hosted models.

    Args:
        api_key: OpenRouter API key.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "OpenRouter"

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout=timeout)

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Add OpenRouter-required attribution headers.

        Args:
            api_key: The OpenRouter API key.

        Returns:
            Header dict with ``HTTP-Referer`` and ``X-Title``.
        """
        headers = super()._build_headers(api_key)
        headers["HTTP-Referer"] = "https://emily-chat.app"
        headers["X-Title"] = "Emily Chat"
        return headers

    def supports_thinking(self) -> bool:
        """Many OpenRouter-hosted models support thinking."""
        return True

    def _uses_think_tags(self, model_id: str) -> bool:
        """Return ``True`` for models known to embed ``<think>`` tags.

        Matches against the model slug, which may be a full path like
        ``moonshotai/kimi-k2-thinking``.

        Args:
            model_id: The OpenRouter model identifier.
        """
        lower = model_id.lower()
        return any(p in lower for p in _THINK_TAG_PATTERNS)

    @staticmethod
    def create_custom_spec(
        model_id: str,
        display: str | None = None,
    ) -> ModelSpec:
        """Build a :class:`ModelSpec` for an arbitrary OpenRouter model.

        Used when the user types a custom model string that isn't
        pre-registered.

        Args:
            model_id: The OpenRouter model slug
                (e.g. ``"meta-llama/llama-3.3-70b-instruct"``).
            display: Optional display name.  Defaults to
                ``"Emily \u2014 Custom (<model_id>)"``.

        Returns:
            A new :class:`ModelSpec` with ``provider="openrouter"``.
        """
        short = model_id.split("/")[-1] if "/" in model_id else model_id
        return ModelSpec(
            display=display or f"Emily \u2014 Custom ({short})",
            provider="openrouter",
            model_id=model_id,
            notes=f"OpenRouter pass-through: {model_id}",
        )
