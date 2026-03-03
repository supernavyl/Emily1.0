"""Anthropic Claude LLM provider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class ClaudeLLM(LLMProvider):
    """Streaming chat completion via the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model
        self._client: object | None = None
        logger.info("ClaudeLLM configured: model=%s", model)

    def _get_client(self) -> object:
        """Lazy-load the async Anthropic client."""
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream LLM tokens from Claude."""
        client = self._get_client()

        # Claude expects messages without an explicit system role in the list;
        # the system prompt is a separate top-level parameter.
        logger.debug("Claude request: model=%s messages=%d", self._model, len(messages))

        try:
            async with client.messages.stream(  # type: ignore[union-attr]
                model=self._model,
                max_tokens=4096,
                system=system,
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except Exception:
            logger.exception("Claude streaming error")
            raise
