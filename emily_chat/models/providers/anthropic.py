"""Anthropic Claude provider with extended-thinking support.

Normalises Anthropic's streaming events (``content_block_start``,
``content_block_delta``, ``message_delta``, ``message_stop``) into
:class:`StreamChunk` objects.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from emily_chat.models.providers.base import BaseProvider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from emily_chat.models.registry import ModelSpec


class AnthropicProvider(BaseProvider):
    """Streams Claude 4.6 responses with extended-thinking extraction.

    The provider lazily creates the async client on first use so the
    import doesn't fail when the ``anthropic`` package is missing.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client: object | None = None

    def _get_client(self) -> object:
        """Lazily create the ``AsyncAnthropic`` client.

        Raises:
            ImportError: If the ``anthropic`` package is not installed.
            ValueError: If no API key is available.
        """
        if self._client is not None:
            return self._client

        if not self._api_key:
            raise ValueError("No Anthropic API key. Set ANTHROPIC_API_KEY or pass api_key=.")

        import anthropic  # type: ignore[import-untyped]

        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a Claude completion, yielding normalised chunks.

        Extended thinking is enabled when ``settings.thinking_budget > 0``
        and the model supports it.

        Args:
            messages: Conversation history.
            system_prompt: The full Emily system prompt.
            settings: Generation parameters.
            model_spec: The resolved model specification from the registry.

        Yields:
            :class:`StreamChunk` instances.
        """
        resolved_model_id = model_spec.model_id

        client = self._get_client()

        kwargs: dict = {
            "model": resolved_model_id,
            "max_tokens": settings.max_tokens,
            "system": system_prompt,
            "messages": messages,
            "stream": True,
        }

        if settings.thinking_budget > 0:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": settings.thinking_budget,
            }
            # Anthropic requires temperature=1 when extended thinking is on
            kwargs["temperature"] = 1
        else:
            kwargs["temperature"] = settings.temperature

        if settings.stop:
            kwargs["stop_sequences"] = settings.stop

        input_tokens = 0
        output_tokens = 0

        async with client.messages.stream(
            **{k: v for k, v in kwargs.items() if k != "stream"}
        ) as stream:  # type: ignore[union-attr]
            async for event in stream:
                chunk = _map_event(event)
                if chunk is not None:
                    yield chunk

            # After the stream completes, grab the final message for usage
            final = await stream.get_final_message()  # type: ignore[union-attr]
            input_tokens = getattr(final.usage, "input_tokens", 0)
            output_tokens = getattr(final.usage, "output_tokens", 0)

        yield StreamChunk(
            type=ChunkType.USAGE,
            metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
        yield StreamChunk(type=ChunkType.STOP)

    async def validate_key(self, api_key: str) -> bool:
        """Validate an Anthropic API key by sending a minimal request.

        Args:
            api_key: The API key to test.

        Returns:
            ``True`` if the key is accepted.
        """
        try:
            import anthropic  # type: ignore[import-untyped]

            test_client = anthropic.AsyncAnthropic(api_key=api_key)
            await test_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True
        except Exception:
            return False


def _map_event(event: object) -> StreamChunk | None:
    """Convert a single Anthropic stream event into a :class:`StreamChunk`.

    Returns ``None`` for events we don't need to propagate.
    """
    event_type = getattr(event, "type", "")

    if event_type == "content_block_delta":
        delta = getattr(event, "delta", None)
        if delta is None:
            return None
        delta_type = getattr(delta, "type", "")
        if delta_type == "thinking_delta":
            return StreamChunk(type=ChunkType.THINKING, content=getattr(delta, "thinking", ""))
        if delta_type == "text_delta":
            return StreamChunk(type=ChunkType.TEXT, content=getattr(delta, "text", ""))

    return None
