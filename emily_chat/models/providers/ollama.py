"""Ollama provider — 100% local inference with auto-discovery.

Ollama runs on the local machine and streams responses as
newline-delimited JSON (not SSE).  This provider auto-discovers
locally installed models and creates :class:`ModelSpec` entries for
them at runtime.

Key behaviours:
* Streaming via ``POST /api/chat`` with JSON-per-line responses.
* Auto-discovery via ``GET /api/tags``.
* No API key — just connectivity to ``localhost:11434``.
* Think-tag extraction for local DeepSeek R1 / Qwen3 / QwQ models.
* All inference is free (``cost = $0``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from emily_chat.models.providers._openai_compat import ThinkTagExtractor
from emily_chat.models.providers.base import BaseProvider
from emily_chat.models.registry import ModelSpec
from emily_chat.models.streaming_engine import (
    ChunkType,
    GenerationSettings,
    StreamChunk,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_CHAT_ENDPOINT = "/api/chat"
_TAGS_ENDPOINT = "/api/tags"

_THINK_TAG_PATTERNS = (
    "deepseek-r1",
    "deepseek-r2",
    "qwen3",
    "qwq",
)


class OllamaProvider(BaseProvider):
    """Async streaming provider for locally running Ollama models.

    Args:
        base_url: Ollama server URL.  Defaults to ``http://localhost:11434``.
        timeout: Per-request timeout in seconds.  Local inference can be
            slow on modest hardware, so the default is generous.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            headers={"Content-Type": "application/json"},
        )

    # ── BaseProvider interface ────────────────────────────────

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> AsyncIterator[StreamChunk]:
        """Yield :class:`StreamChunk` objects from Ollama's JSON-line stream.

        Ollama streams one JSON object per line::

            {"message": {"content": "tok"}, "done": false}
            {"message": {"content": ""},    "done": true,
             "eval_count": 50, "prompt_eval_count": 20}

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

        try:
            async with self._client.stream("POST", url, json=body) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield StreamChunk(
                        type=ChunkType.ERROR,
                        content=f"Ollama error {response.status_code}: "
                        f"{error_body.decode(errors='replace')}",
                    )
                    return

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Malformed Ollama JSON: %s", line[:200])
                        continue

                    content = data.get("message", {}).get("content", "")

                    if content:
                        if extractor:
                            for chunk in extractor.feed(content):
                                yield chunk
                        else:
                            yield StreamChunk(
                                type=ChunkType.TEXT,
                                content=content,
                                tokens=1,
                            )

                    if data.get("done"):
                        tool_calls = data.get("message", {}).get("tool_calls", [])
                        if tool_calls:
                            # Model wants to call tools — emit tool_call and return
                            # (no USAGE or STOP; the caller handles the agentic loop)
                            yield StreamChunk(
                                type=ChunkType.TOOL_CALL,
                                metadata={"tool_calls": tool_calls},
                            )
                            return

                        if extractor:
                            for remaining in extractor.flush():
                                yield remaining
                        yield StreamChunk(
                            type=ChunkType.USAGE,
                            metadata={
                                "prompt_tokens": data.get("prompt_eval_count", 0),
                                "completion_tokens": data.get("eval_count", 0),
                                "reasoning_tokens": 0,
                            },
                        )
                        yield StreamChunk(type=ChunkType.STOP)
                        return

        except httpx.ConnectError:
            yield StreamChunk(
                type=ChunkType.ERROR,
                content=(
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Is Ollama running? Start it with: ollama serve"
                ),
            )
        except httpx.HTTPError as exc:
            yield StreamChunk(
                type=ChunkType.ERROR,
                content=f"Ollama HTTP error: {exc}",
            )

    async def validate_key(self, api_key: str) -> bool:
        """Check whether Ollama is reachable (no key required).

        Args:
            api_key: Ignored — Ollama uses no authentication.

        Returns:
            ``True`` if the Ollama server responds.
        """
        try:
            resp = await self._client.get(f"{self._base_url}{_TAGS_ENDPOINT}")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def supports_thinking(self) -> bool:
        """Local DeepSeek R1 and Qwen3 models support thinking."""
        return True

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ── auto-discovery ────────────────────────────────────────

    async def discover_models(self) -> list[dict[str, Any]]:
        """Query Ollama for locally installed models.

        Returns:
            A list of dicts with ``name``, ``size``, and ``modified_at``
            keys for each installed model.  Returns an empty list if
            Ollama is unreachable.
        """
        try:
            resp = await self._client.get(f"{self._base_url}{_TAGS_ENDPOINT}")
            if resp.status_code != 200:
                return []
            data = resp.json()
            models = data.get("models", [])
            return [
                {
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "modified_at": m.get("modified_at", ""),
                }
                for m in models
            ]
        except httpx.HTTPError:
            return []

    # ── request body ──────────────────────────────────────────

    def _build_request_body(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> dict[str, Any]:
        """Assemble the JSON body for Ollama's ``/api/chat`` endpoint.

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
            "options": {
                "temperature": settings.temperature,
            },
        }

        if settings.max_tokens > 0:
            body["options"]["num_predict"] = settings.max_tokens

        if settings.top_p != 1.0:
            body["options"]["top_p"] = settings.top_p

        if settings.tools:
            body["tools"] = settings.tools

        return body

    # ── think-tag detection ───────────────────────────────────

    @staticmethod
    def _uses_think_tags(model_id: str) -> bool:
        """Return ``True`` for models that embed ``<think>`` tags.

        Ollama model names look like ``deepseek-r1:32b`` or ``qwen3:72b``.

        Args:
            model_id: The Ollama model name.
        """
        lower = model_id.lower()
        return any(p in lower for p in _THINK_TAG_PATTERNS)

    # ── spec factory ──────────────────────────────────────────

    @staticmethod
    def create_local_spec(model_name: str) -> ModelSpec:
        """Build a :class:`ModelSpec` for a locally discovered Ollama model.

        Args:
            model_name: The Ollama model name (e.g. ``"qwen3:72b"``).

        Returns:
            A new :class:`ModelSpec` with ``provider="ollama"`` and zero cost.
        """
        model_name.split(":")[0] if ":" in model_name else model_name
        has_thinking = any(p in model_name.lower() for p in _THINK_TAG_PATTERNS)
        return ModelSpec(
            display=f"Emily \u2014 Local ({model_name})",
            provider="ollama",
            model_id=model_name,
            input_usd=0.0,
            output_usd=0.0,
            speed="hardware-dependent",
            tier="local",
            thinking=has_thinking,
            notes=f"Local Ollama model: {model_name}. 100% private.",
        )
