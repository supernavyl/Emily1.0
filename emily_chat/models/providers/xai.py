"""xAI provider — Grok 4.1 and future Grok models.

xAI exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint.
Grok models are known for creative writing, humor, and emotional
intelligence (#1 EQ benchmark).
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider

_BASE_URL = "https://api.x.ai/v1"


class XAIProvider(OpenAICompatibleProvider):
    """Async streaming provider for xAI Grok models.

    Args:
        api_key: xAI API key.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "xAI"

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout=timeout)

    def supports_vision(self) -> bool:
        """Grok 4.1 supports image inputs."""
        return True
