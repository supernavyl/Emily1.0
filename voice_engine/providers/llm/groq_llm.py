"""Groq LLM provider — ultra-fast inference via the Groq API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class GroqLLM(LLMProvider):
    """Streaming chat completion via the Groq API."""

    def __init__(self, api_key: str, model: str = "llama-3.1-70b-versatile") -> None:
        self._api_key = api_key
        self._model = model
        self._client: object | None = None
        logger.info("GroqLLM configured: model=%s", model)

    def _get_client(self) -> object:
        """Lazy-load the async Groq client."""
        if self._client is None:
            from groq import AsyncGroq  # type: ignore[import-untyped]

            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream LLM tokens from Groq."""
        client = self._get_client()

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        logger.debug("Groq request: model=%s messages=%d", self._model, len(full_messages))

        try:
            stream = await client.chat.completions.create(  # type: ignore[union-attr]
                model=self._model,
                messages=full_messages,  # type: ignore[arg-type]
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception:
            logger.exception("Groq streaming error")
            raise
