"""Google Gemini provider with thinking/reasoning support.

Streams Gemini 3 / 2.5 completions via direct ``httpx`` SSE against
the ``generativelanguage.googleapis.com`` REST API.  Uses the
``alt=sse`` query parameter so the response is Server-Sent Events,
matching the streaming pattern of the OpenAI provider.

Key behaviours:
* Thinking is enabled via ``thinkingConfig`` in the request body.
  Parts with ``"thought": true`` are emitted as *thinking* chunks;
  regular parts become *text* chunks.
* System prompt uses the ``systemInstruction`` field (not a message).
* Conversation roles are mapped: ``"assistant"`` → ``"model"``.
* Usage is extracted from ``usageMetadata`` on each chunk (the last
  chunk carries final totals).
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

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(BaseProvider):
    """Async streaming provider for Google Gemini models.

    Args:
        api_key: The Google AI API key.
        base_url: Override the API base (useful for proxies / Vertex AI).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _BASE_URL,
        timeout: float = 180.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    # ── BaseProvider interface ────────────────────────────────

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> AsyncIterator[StreamChunk]:
        """Yield :class:`StreamChunk` objects from the Gemini streaming API.

        Args:
            messages: Conversation history (OpenAI-style role/content dicts).
            system_prompt: Emily's assembled system prompt.
            settings: Generation tunables.
            model_spec: Resolved model from the registry.

        Yields:
            ``StreamChunk`` with ``type`` of ``thinking``, ``text``,
            ``usage``, or ``stop``.
        """
        body = self._build_request_body(messages, system_prompt, settings, model_spec)
        url = (
            f"{self._base_url}/models/{model_spec.model_id}"
            f":streamGenerateContent?alt=sse&key={self._api_key}"
        )

        async with self._client.stream("POST", url, json=body) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield StreamChunk(
                    type=ChunkType.ERROR,
                    content=f"Google API error {response.status_code}: "
                    f"{error_body.decode(errors='replace')}",
                )
                return

            last_usage: dict[str, Any] = {}
            async for line in response.aiter_lines():
                for chunk in _parse_sse_line(line, last_usage):
                    yield chunk

        if last_usage:
            yield StreamChunk(type=ChunkType.USAGE, metadata=last_usage)
        yield StreamChunk(type=ChunkType.STOP)

    async def validate_key(self, api_key: str) -> bool:
        """Check *api_key* against the Gemini models list endpoint.

        Args:
            api_key: Raw API key to validate.

        Returns:
            ``True`` if the key is accepted.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}/models?key={api_key}",
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def supports_thinking(self) -> bool:
        """All registered Gemini models support thinking."""
        return True

    def supports_vision(self) -> bool:
        """All registered Gemini models support image inputs."""
        return True

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ── request building ─────────────────────────────────────

    def _build_request_body(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> dict[str, Any]:
        """Assemble the JSON body for the Gemini streaming endpoint.

        Args:
            messages: Conversation messages (OpenAI-style).
            system_prompt: System prompt string.
            settings: Generation settings.
            model_spec: Model specification.

        Returns:
            The request body dict.
        """
        contents = _convert_messages(messages)

        generation_config: dict[str, Any] = {
            "temperature": settings.temperature,
            "topP": settings.top_p,
        }
        if settings.max_tokens > 0:
            generation_config["maxOutputTokens"] = settings.max_tokens

        if model_spec.thinking and settings.thinking_budget > 0:
            generation_config["thinkingConfig"] = {
                "thinkingBudget": settings.thinking_budget,
                "includeThoughts": True,
            }

        body: dict[str, Any] = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "generationConfig": generation_config,
        }

        return body


# ── message conversion ───────────────────────────────────────


def _convert_messages(messages: list[dict]) -> list[dict[str, Any]]:
    """Convert OpenAI-style messages to Gemini ``contents`` format.

    Gemini uses ``"model"`` instead of ``"assistant"`` and wraps text
    in a ``parts`` array.

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts.

    Returns:
        List of Gemini-format content objects.
    """
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "assistant":
            role = "model"
        elif role == "system":
            continue
        text = msg.get("content", "")
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents


# ── SSE parsing ──────────────────────────────────────────────


def _parse_sse_line(
    line: str,
    usage_accum: dict[str, Any],
) -> list[StreamChunk]:
    """Parse a single SSE line from the Gemini streaming response.

    Gemini SSE lines have the form ``data: {json}``.  Each JSON object
    may contain multiple parts (thinking + text) and usage metadata.

    Args:
        line: A raw line from the SSE stream.
        usage_accum: Mutable dict that accumulates the latest usage
            metadata (updated in place).

    Returns:
        A list of :class:`StreamChunk` objects extracted from the line
        (may be empty for non-data lines).
    """
    if not line.startswith("data:"):
        return []

    payload = line[len("data:"):].strip()
    if not payload:
        return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Malformed Gemini SSE JSON: %s", payload[:200])
        return []

    chunks: list[StreamChunk] = []

    # Extract content parts from candidates
    candidates = data.get("candidates")
    if candidates:
        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        for part in parts:
            text = part.get("text", "")
            if not text:
                continue
            is_thought = part.get("thought", False)
            if is_thought:
                chunks.append(
                    StreamChunk(type=ChunkType.THINKING, content=text, tokens=1)
                )
            else:
                chunks.append(
                    StreamChunk(type=ChunkType.TEXT, content=text, tokens=1)
                )

    # Accumulate usage metadata (last chunk carries final totals)
    usage = data.get("usageMetadata")
    if usage:
        usage_accum["prompt_tokens"] = usage.get("promptTokenCount", 0)
        usage_accum["completion_tokens"] = usage.get("candidatesTokenCount", 0)
        thinking_tokens = usage.get("thoughtsTokenCount", 0)
        if thinking_tokens:
            usage_accum["reasoning_tokens"] = thinking_tokens

    return chunks
