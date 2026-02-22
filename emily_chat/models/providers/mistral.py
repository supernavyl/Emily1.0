"""Mistral provider — EU/GDPR-compliant models.

Mistral exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint.
All inference runs in EU data centres, making it suitable for
GDPR-sensitive workloads.

Key behaviours:
* Mistral Large 3: general-purpose with vision support.
* Codestral 2: code-specialised (best FIM per cost).
* Mistral Small 3: edge-optimised 24B model.
* Auth uses a ``Bearer`` token like other providers.
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider

_BASE_URL = "https://api.mistral.ai/v1"


class MistralProvider(OpenAICompatibleProvider):
    """Async streaming provider for Mistral AI models.

    Args:
        api_key: Mistral API key.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "Mistral"

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout=timeout)

    def supports_vision(self) -> bool:
        """Mistral Large 3 supports image inputs."""
        return True
