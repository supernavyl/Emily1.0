"""Shared base for providers that expose an OpenAI-compatible chat-completions API.

Groq, xAI, DeepSeek, Together, Mistral, and OpenAI itself all speak the
same ``/v1/chat/completions`` SSE protocol.  This module extracts the
common HTTP streaming, SSE parsing, request-body construction, and key
validation so that each concrete provider only supplies its base URL and
any model-specific overrides.

The module also provides :class:`ThinkTagExtractor` — a small state
machine that separates ``<think>…</think>`` reasoning blocks (used by
DeepSeek R1/R2, Groq-hosted R1-distill, and Qwen3) from visible response
text.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from emily_chat.models.providers.base import BaseProvider
from emily_chat.models.registry import ModelSpec
from emily_chat.models.streaming_engine import (
    ChunkType,
    GenerationSettings,
    StreamChunk,
)

logger = logging.getLogger(__name__)

_CHAT_ENDPOINT = "/chat/completions"
_MODELS_ENDPOINT = "/models"


# ---------------------------------------------------------------------------
# ThinkTagExtractor — <think> tag state machine
# ---------------------------------------------------------------------------


class ThinkTagExtractor:
    """Stateful extractor that splits ``<think>…</think>`` from content.

    Streaming APIs deliver content token-by-token, so opening/closing tags
    may arrive across multiple chunks.  This class buffers just enough to
    detect tag boundaries and emits :class:`StreamChunk` objects of the
    correct type.

    Usage::

        extractor = ThinkTagExtractor()
        for raw_text in token_stream:
            for chunk in extractor.feed(raw_text):
                yield chunk
        for chunk in extractor.flush():
            yield chunk
    """

    _OPEN_TAG = "<think>"
    _CLOSE_TAG = "</think>"

    def __init__(self) -> None:
        self._inside_think = False
        self._buffer = ""

    def feed(self, text: str) -> list[StreamChunk]:
        """Process incoming text and return any resolved chunks.

        Args:
            text: Raw text fragment from the SSE stream.

        Returns:
            Zero or more :class:`StreamChunk` objects.
        """
        self._buffer += text
        return self._drain()

    def flush(self) -> list[StreamChunk]:
        """Emit any remaining buffered content at end-of-stream.

        Returns:
            Zero or more :class:`StreamChunk` objects.
        """
        chunks: list[StreamChunk] = []
        if self._buffer:
            chunk_type = ChunkType.THINKING if self._inside_think else ChunkType.TEXT
            chunks.append(
                StreamChunk(type=chunk_type, content=self._buffer, tokens=1)
            )
            self._buffer = ""
        return chunks

    def _drain(self) -> list[StreamChunk]:
        """Consume buffer, emitting chunks whenever a tag boundary is found."""
        chunks: list[StreamChunk] = []

        while True:
            if self._inside_think:
                idx = self._buffer.find(self._CLOSE_TAG)
                if idx == -1:
                    # Might be a partial close tag at the end — keep it buffered
                    safe, held = self._split_partial(self._buffer, self._CLOSE_TAG)
                    if safe:
                        chunks.append(
                            StreamChunk(type=ChunkType.THINKING, content=safe, tokens=1)
                        )
                    self._buffer = held
                    break

                thinking_text = self._buffer[:idx]
                if thinking_text:
                    chunks.append(
                        StreamChunk(type=ChunkType.THINKING, content=thinking_text, tokens=1)
                    )
                self._buffer = self._buffer[idx + len(self._CLOSE_TAG):]
                self._inside_think = False

            else:
                idx = self._buffer.find(self._OPEN_TAG)
                if idx == -1:
                    safe, held = self._split_partial(self._buffer, self._OPEN_TAG)
                    if safe:
                        chunks.append(
                            StreamChunk(type=ChunkType.TEXT, content=safe, tokens=1)
                        )
                    self._buffer = held
                    break

                text_before = self._buffer[:idx]
                if text_before:
                    chunks.append(
                        StreamChunk(type=ChunkType.TEXT, content=text_before, tokens=1)
                    )
                self._buffer = self._buffer[idx + len(self._OPEN_TAG):]
                self._inside_think = True

        return chunks

    @staticmethod
    def _split_partial(buf: str, tag: str) -> tuple[str, str]:
        """Split *buf* so that a possible partial *tag* at the end is held back.

        If the buffer ends with a prefix of *tag* (e.g. ``"<thi"`` for
        ``"<think>"``), that suffix is held in the buffer for the next
        ``feed()`` call.

        Returns:
            ``(safe_to_emit, held_back)``
        """
        for i in range(1, len(tag)):
            if buf.endswith(tag[:i]):
                return buf[:-i], buf[-i:]
        return buf, ""


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(BaseProvider):
    """Base for any provider whose API is wire-compatible with OpenAI.

    Subclasses **must** set :attr:`_provider_name` (used in error messages)
    and typically only need to supply the ``base_url`` at construction time.

    For models that embed reasoning inside ``<think>`` tags, override
    :meth:`_uses_think_tags` to return ``True`` for the relevant model IDs.

    Args:
        api_key: The provider API key.
        base_url: Root URL (e.g. ``"https://api.groq.com/openai/v1"``).
        timeout: Per-request timeout in seconds.
    """

    _provider_name: str = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers=self._build_headers(api_key),
        )

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Return HTTP headers. Override for non-Bearer auth schemes.

        Args:
            api_key: The API key.

        Returns:
            Header dict.
        """
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    # ── streaming ─────────────────────────────────────────────

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> AsyncIterator[StreamChunk]:
        """Yield :class:`StreamChunk` objects via the chat-completions SSE stream.

        Args:
            messages: Conversation history (OpenAI chat format).
            system_prompt: Emily's assembled system prompt.
            settings: Generation tunables.
            model_spec: Resolved model from the registry.

        Yields:
            ``StreamChunk`` with types ``thinking``, ``text``, ``usage``,
            ``error``, or ``stop``.
        """
        body = self._build_request_body(messages, system_prompt, settings, model_spec)
        url = f"{self._base_url}{_CHAT_ENDPOINT}"
        use_think_tags = self._uses_think_tags(model_spec.model_id)
        extractor = ThinkTagExtractor() if use_think_tags else None

        async with self._client.stream("POST", url, json=body) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield StreamChunk(
                    type=ChunkType.ERROR,
                    content=f"{self._provider_name} API error {response.status_code}: "
                    f"{error_body.decode(errors='replace')}",
                )
                return

            async for line in response.aiter_lines():
                chunk = self._parse_sse_line(line, model_spec.model_id)
                if chunk is None:
                    continue

                if extractor and chunk.type == ChunkType.TEXT:
                    for extracted in extractor.feed(chunk.content):
                        yield extracted
                    continue

                yield chunk
                if chunk.type in (ChunkType.STOP, ChunkType.ERROR):
                    if extractor:
                        for remaining in extractor.flush():
                            yield remaining
                    return

        if extractor:
            for remaining in extractor.flush():
                yield remaining

    # ── key validation ────────────────────────────────────────

    async def validate_key(self, api_key: str) -> bool:
        """Validate *api_key* against the models endpoint.

        Args:
            api_key: Raw API key to test.

        Returns:
            ``True`` if the provider accepts the key.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}{_MODELS_ENDPOINT}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ── request body ──────────────────────────────────────────

    def _build_request_body(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> dict[str, Any]:
        """Assemble the JSON body for the chat-completions endpoint.

        Subclasses may override to add provider-specific parameters.

        Args:
            messages: Conversation messages.
            system_prompt: System prompt string.
            settings: Generation settings.
            model_spec: Model specification.

        Returns:
            The request body dict.
        """
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        body: dict[str, Any] = {
            "model": model_spec.model_id,
            "messages": full_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": settings.temperature,
        }

        if settings.top_p != 1.0:
            body["top_p"] = settings.top_p

        if settings.max_tokens > 0:
            body["max_tokens"] = settings.max_tokens

        if settings.stop:
            body["stop"] = settings.stop

        return body

    # ── SSE parsing ───────────────────────────────────────────

    @staticmethod
    def _parse_sse_line(line: str, model_id: str) -> StreamChunk | None:
        """Parse a single SSE line into a :class:`StreamChunk`.

        Handles the standard OpenAI-compatible SSE format used by Groq,
        xAI, Together, DeepSeek, and Mistral.

        Args:
            line: A raw line from the SSE stream.
            model_id: The model ID (unused in the base, available for overrides).

        Returns:
            A :class:`StreamChunk`, or ``None`` for non-data lines.
        """
        if not line.startswith("data:"):
            return None

        payload = line[len("data:"):].strip()

        if payload == "[DONE]":
            return StreamChunk(type=ChunkType.STOP)

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Malformed SSE JSON: %s", payload[:200])
            return None

        usage = data.get("usage")
        if usage:
            meta: dict[str, Any] = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            }
            details = usage.get("completion_tokens_details") or {}
            meta["reasoning_tokens"] = details.get("reasoning_tokens", 0)
            return StreamChunk(type=ChunkType.USAGE, metadata=meta)

        choices = data.get("choices")
        if not choices:
            return None

        delta = choices[0].get("delta", {})
        finish = choices[0].get("finish_reason")

        reasoning = delta.get("reasoning_content")
        if reasoning:
            return StreamChunk(type=ChunkType.THINKING, content=reasoning, tokens=1)

        content = delta.get("content")
        if content:
            return StreamChunk(type=ChunkType.TEXT, content=content, tokens=1)

        if finish:
            return None

        return None

    # ── think-tag hook ────────────────────────────────────────

    def _uses_think_tags(self, model_id: str) -> bool:
        """Return ``True`` if *model_id* embeds reasoning in ``<think>`` tags.

        Override in subclasses (e.g. DeepSeek, Groq) to enable the
        :class:`ThinkTagExtractor` for specific models.

        Args:
            model_id: The provider-side model identifier.
        """
        return False
