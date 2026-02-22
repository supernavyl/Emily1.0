"""Together AI provider — open-weight models at scale.

Together serves community models (Qwen3 235B, Llama 4 Maverick, etc.)
via an OpenAI-compatible ``/v1/chat/completions`` endpoint.
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider

_BASE_URL = "https://api.together.xyz/v1"


class TogetherProvider(OpenAICompatibleProvider):
    """Async streaming provider for Together AI hosted models.

    Args:
        api_key: Together AI API key.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "Together"

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout=timeout)

    def supports_vision(self) -> bool:
        """Llama 4 Maverick supports image inputs."""
        return True
