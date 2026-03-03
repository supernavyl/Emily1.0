"""llama.cpp server LLM provider — local GGUF inference via OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class LlamaCppLLM(LLMProvider):
    """Streaming chat completion via llama.cpp's built-in OpenAI-compatible server."""

    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:8080/v1",
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._client: object | None = None
        logger.info("LlamaCppLLM configured: model=%s url=%s", model or "server-default", base_url)

    def _get_client(self) -> object:
        """Lazy-load the async OpenAI client pointed at llama.cpp server."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key="no-key",
                base_url=self._base_url,
            )
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream LLM tokens from llama.cpp server."""
        client = self._get_client()

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        logger.debug("llama.cpp request: model=%s messages=%d", self._model, len(full_messages))

        try:
            kwargs: dict[str, object] = {
                "messages": full_messages,
                "stream": True,
            }
            # llama.cpp server uses its loaded model; only pass model if set
            if self._model:
                kwargs["model"] = self._model

            stream = await client.chat.completions.create(**kwargs)  # type: ignore[union-attr]

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception:
            logger.exception("llama.cpp streaming error")
            raise
