"""Abstract base class that every LLM provider must implement.

All providers normalise their API's streaming format into a common
:class:`~emily_chat.models.streaming_engine.StreamChunk` sequence so that
the rest of the application never deals with provider-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from emily_chat.models.registry import ModelSpec
    from emily_chat.models.streaming_engine import GenerationSettings, StreamChunk


class BaseProvider(ABC):
    """Contract that every LLM provider backend must fulfil.

    Subclasses are responsible for:
    * Opening / managing their own ``httpx.AsyncClient``.
    * Translating :class:`GenerationSettings` into provider-native params.
    * Yielding a sequence of :class:`StreamChunk` objects that the unified
      :class:`~emily_chat.models.streaming_engine.EmilyStreamingEngine`
      can consume.
    """

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion as an async iterator of :class:`StreamChunk`.

        Args:
            messages: Conversation history in OpenAI-style
                ``[{"role": ..., "content": ...}]`` format.
            system_prompt: The assembled Emily system prompt.
            settings: Temperature, max tokens, reasoning effort, etc.
            model_spec: The resolved model specification from the registry.

        Yields:
            :class:`StreamChunk` instances of type ``"thinking"``,
            ``"text"``, ``"usage"``, ``"error"``, or ``"stop"``.
        """
        ...  # pragma: no cover
        # yield is required so the type-checker sees an AsyncIterator
        yield  # type: ignore[misc]

    @abstractmethod
    async def validate_key(self, api_key: str) -> bool:
        """Check whether *api_key* is accepted by the provider.

        Args:
            api_key: The raw API key string.

        Returns:
            ``True`` if the key is valid, ``False`` otherwise.
        """
        ...  # pragma: no cover

    def supports_thinking(self) -> bool:
        """Return ``True`` if any model from this provider emits reasoning."""
        return False

    def supports_vision(self) -> bool:
        """Return ``True`` if any model from this provider accepts images."""
        return False

    async def close(self) -> None:
        """Release underlying HTTP clients.  Override if needed."""
