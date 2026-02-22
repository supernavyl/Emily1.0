"""Factory that resolves a :class:`ModelSpec` to a concrete :class:`BaseProvider`.

Each provider is instantiated lazily and cached by provider name so that
subsequent requests for the same provider reuse the underlying HTTP client.
API keys are read from environment variables.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emily_chat.models.providers.base import BaseProvider
    from emily_chat.models.registry import ModelSpec


class ProviderUnavailableError(Exception):
    """Raised when a provider cannot be constructed (missing key, etc.)."""


_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "together": "TOGETHER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

_cache: dict[str, BaseProvider] = {}


def _require_key(provider: str) -> str:
    """Return the API key for *provider* or raise.

    Args:
        provider: Provider name (e.g. ``"openai"``).

    Returns:
        The API key string.

    Raises:
        ProviderUnavailableError: If the environment variable is unset.
    """
    env_var = _ENV_MAP.get(provider)
    if env_var is None:
        raise ProviderUnavailableError(f"Unknown provider: {provider}")
    key = os.environ.get(env_var, "")
    if not key:
        raise ProviderUnavailableError(
            f"No API key for {provider}. Set the {env_var} environment variable."
        )
    return key


def _build_provider(provider: str) -> BaseProvider:
    """Construct a fresh :class:`BaseProvider` for *provider*.

    Args:
        provider: Provider name from :attr:`ModelSpec.provider`.

    Returns:
        A ready-to-use provider instance.

    Raises:
        ProviderUnavailableError: If the API key is missing or provider unknown.
    """
    if provider == "ollama":
        from emily_chat.models.providers.ollama import OllamaProvider

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return OllamaProvider(base_url=host)

    if provider == "llamacpp":
        from emily_chat.models.providers.llamacpp import LlamaCppProvider

        return LlamaCppProvider()

    key = _require_key(provider)

    if provider == "openai":
        from emily_chat.models.providers.openai import OpenAIProvider

        return OpenAIProvider(api_key=key)

    if provider == "anthropic":
        from emily_chat.models.providers.anthropic import AnthropicProvider

        return AnthropicProvider(api_key=key)

    if provider == "google":
        from emily_chat.models.providers.google import GoogleProvider

        return GoogleProvider(api_key=key)

    if provider == "groq":
        from emily_chat.models.providers.groq import GroqProvider

        return GroqProvider(api_key=key)

    if provider == "xai":
        from emily_chat.models.providers.xai import XAIProvider

        return XAIProvider(api_key=key)

    if provider == "deepseek":
        from emily_chat.models.providers.deepseek import DeepSeekProvider

        return DeepSeekProvider(api_key=key)

    if provider == "together":
        from emily_chat.models.providers.together import TogetherProvider

        return TogetherProvider(api_key=key)

    if provider == "mistral":
        from emily_chat.models.providers.mistral import MistralProvider

        return MistralProvider(api_key=key)

    if provider == "openrouter":
        from emily_chat.models.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(api_key=key)

    raise ProviderUnavailableError(f"Unknown provider: {provider}")


def get_provider(model_spec: ModelSpec) -> BaseProvider:
    """Return a cached :class:`BaseProvider` for the given model spec.

    Args:
        model_spec: The resolved model specification.

    Returns:
        A provider instance ready for streaming.

    Raises:
        ProviderUnavailableError: If the provider cannot be constructed.
    """
    provider_name = model_spec.provider
    if provider_name in _cache:
        return _cache[provider_name]

    instance = _build_provider(provider_name)
    _cache[provider_name] = instance
    return instance


async def close_all() -> None:
    """Close every cached provider's HTTP client."""
    for provider in _cache.values():
        await provider.close()
    _cache.clear()
