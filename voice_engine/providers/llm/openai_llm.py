"""OpenAI-compatible LLM provider (also works with Ollama's OpenAI compat layer)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class OpenAILLM(LLMProvider):
    """Streaming chat completion via the OpenAI API (or any compatible endpoint)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client: object | None = None
        logger.info(
            "OpenAILLM configured: model=%s base_url=%s",
            model,
            base_url or "default",
        )

    def _get_client(self) -> object:
        """Lazy-load the async OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI

            kwargs: dict[str, str] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream LLM tokens from the OpenAI chat completions endpoint."""
        client = self._get_client()

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        logger.debug("OpenAI request: model=%s messages=%d", self._model, len(full_messages))

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
            logger.exception("OpenAI streaming error")
            raise
