"""Ollama LLM provider — local model inference via the Ollama API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class OllamaLLM(LLMProvider):
    """Streaming chat completion via the ``ollama`` Python client."""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url
        self._client: object | None = None
        logger.info("OllamaLLM configured: model=%s url=%s", model, base_url)

    def _get_client(self) -> object:
        """Lazy-load the async Ollama client."""
        if self._client is None:
            from ollama import AsyncClient  # type: ignore[import-untyped]

            self._client = AsyncClient(host=self._base_url)
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream LLM tokens from Ollama."""
        client = self._get_client()

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        logger.debug("Ollama request: model=%s messages=%d", self._model, len(full_messages))

        try:
            stream = await client.chat(  # type: ignore[union-attr]
                model=self._model,
                messages=full_messages,
                stream=True,
            )

            async for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
        except Exception:
            logger.exception("Ollama streaming error")
            raise
