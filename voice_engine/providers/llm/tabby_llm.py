"""TabbyAPI LLM provider — local exllamav2 inference via OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class TabbyLLM(LLMProvider):
    """Streaming chat completion via TabbyAPI's OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:5000/v1",
        api_key: str = "",
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._client: object | None = None
        logger.info("TabbyLLM configured: model=%s url=%s", model or "server-default", base_url)

    def _get_client(self) -> object:
        """Lazy-load the async OpenAI client pointed at TabbyAPI."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key or "no-key",
                base_url=self._base_url,
            )
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream LLM tokens from TabbyAPI."""
        client = self._get_client()

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        logger.debug("TabbyAPI request: model=%s messages=%d", self._model, len(full_messages))

        try:
            kwargs: dict[str, object] = {
                "messages": full_messages,
                "stream": True,
            }
            # TabbyAPI uses whatever model is loaded; only pass model if explicitly set
            if self._model:
                kwargs["model"] = self._model

            stream = await client.chat.completions.create(**kwargs)  # type: ignore[union-attr]

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception:
            logger.exception("TabbyAPI streaming error")
            raise
