"""
TabbyAPI client for Emily.

TabbyAPI (https://github.com/therealconceptual/tabbyAPI) is an ExLlamaV2-based
OpenAI-compatible inference server — the fastest GPTQ/EXL2 backend available
on RTX-class hardware.  It speaks the standard OpenAI wire protocol:

- Chat streaming: POST /v1/chat/completions  → SSE ``data: {...}`` lines
- Embeddings:     POST /v1/embeddings
- Model list:     GET  /v1/models

Authentication uses the ``x-api-key`` header.  For local-only deployments you
can leave the key empty and disable auth in TabbyAPI's ``config.yml``.

Recommended abliterated EXL2 models for RTX 4090 (24 GB VRAM):
- fast tier   : Qwen2.5-14B-Instruct-abliterated-4.65bpw-EXL2   (~8.5 GB)
- smart tier  : QwQ-32B-abliterated-4.0bpw-EXL2                 (~17 GB)

Abliterated models (Qwen2.5, QwQ) natively emit ``<think>…</think>`` blocks.
Content is yielded verbatim; stripping is handled upstream in
:mod:`llm.streaming` and the ReAct loop, consistent with how the OllamaClient
works.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from llm.client import ChatMessage, CompletionChunk, CompletionResult, EmbeddingResult
from observability.logger import get_logger
from observability.metrics import LLM_FIRST_TOKEN_LATENCY, LLM_REQUESTS_TOTAL

log = get_logger(__name__)

_DEFAULT_BASE_URL = "http://localhost:5000"
_CONNECT_TIMEOUT = 5.0
_SSE_PREFIX = "data: "
_SSE_DONE = "[DONE]"


class TabbyAPIClient:
    """
    Async HTTP client for TabbyAPI (ExLlamaV2 OpenAI-compatible inference server).

    Implements :class:`~llm.base.LLMClientProtocol` so it can be swapped in
    wherever :class:`~llm.client.OllamaClient` is used.

    Maintains a single persistent ``httpx.AsyncClient`` for connection pooling.

    TabbyAPI auth uses the ``x-api-key`` header.  For local deployments with
    auth disabled in TabbyAPI's ``config.yml``, leave *api_key* empty.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = "",
        timeout_s: float = 120.0,
    ) -> None:
        """
        Args:
            base_url: TabbyAPI server base URL (no trailing slash).
            api_key: TabbyAPI ``x-api-key`` value.  Leave empty if auth is
                disabled in TabbyAPI's ``config.yml``.
            timeout_s: Read/write timeout in seconds for non-streaming calls.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _get_client(self) -> httpx.AsyncClient:
        """Return (lazily create) the persistent async HTTP client."""
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["x-api-key"] = self._api_key
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=_CONNECT_TIMEOUT),
                headers=headers,
            )
        return self._client

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert :class:`~llm.client.ChatMessage` list to OpenAI message dicts."""
        result: list[dict[str, Any]] = []
        for m in messages:
            msg: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.images:
                # Inline base64 images as OpenAI vision content-parts
                content_parts: list[dict[str, Any]] = [{"type": "text", "text": m.content}]
                for img in m.images:
                    url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": url, "detail": "auto"}}
                    )
                msg["content"] = content_parts
            result.append(msg)
        return result

    # ------------------------------------------------------------------ #
    # Protocol implementation                                              #
    # ------------------------------------------------------------------ #

    async def health_check(self) -> bool:
        """
        Check if TabbyAPI is reachable and has a model loaded.

        Returns:
            True if the server responds with at least one model entry.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/v1/models")
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = data.get("data", [])
            if not models:
                log.warning("tabbyapi_no_model_loaded", url=self._base_url)
                return False
            log.info(
                "tabbyapi_healthy",
                url=self._base_url,
                loaded_model=models[0].get("id", "?"),
            )
            return True
        except Exception as exc:
            log.debug("tabbyapi_health_check_failed", url=self._base_url, error=str(exc))
            return False

    async def list_models(self) -> list[str]:
        """
        List models currently loaded / available in llama-server / LM Studio.

        Returns:
            List of model ID strings.
        """
        client = await self._get_client()
        resp = await client.get("/v1/models")
        resp.raise_for_status()
        data = resp.json()
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        repeat_penalty: float = 1.1,
        model_tier: str = "fast",
        enable_thinking: bool = True,
    ) -> AsyncIterator[CompletionChunk]:
        """
        Stream a chat completion via POST /v1/chat/completions (SSE).

        Args:
            model: Model ID as reported by ``/v1/models`` (or ``--alias`` name).
            messages: Conversation messages.
            temperature: Sampling temperature.
            top_p: Top-p nucleus sampling.
            max_tokens: Maximum tokens to generate.
            repeat_penalty: Repetition penalty (``frequency_penalty`` equivalent).
            model_tier: Logical tier name for Prometheus metrics.
            enable_thinking: If False, disable Qwen3 ``<think>`` blocks via
                ``chat_template_kwargs``.  Dramatically reduces latency for
                voice-fast calls where reasoning is unnecessary.

        Yields:
            :class:`~llm.client.CompletionChunk` objects as tokens arrive.
        """
        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(messages),
            "stream": True,
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": max(0.0, repeat_penalty - 1.0),
        }
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        if not enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        t0 = time.monotonic()
        first_token = True
        LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="started").inc()

        try:
            async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if not raw_line.startswith(_SSE_PREFIX):
                        continue
                    payload_str = raw_line[len(_SSE_PREFIX) :]
                    if payload_str.strip() == _SSE_DONE:
                        yield CompletionChunk(
                            content="",
                            done=True,
                            model=model,
                        )
                        break

                    try:
                        data = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})
                    content: str = delta.get("content") or ""
                    finish_reason: str | None = choice.get("finish_reason")
                    done = finish_reason is not None

                    if first_token and content:
                        latency = time.monotonic() - t0
                        LLM_FIRST_TOKEN_LATENCY.labels(model_tier=model_tier).observe(latency)
                        log.debug(
                            "tabbyapi_first_token",
                            model=model,
                            tier=model_tier,
                            latency_ms=f"{latency * 1000:.0f}",
                        )
                        first_token = False

                    # Extract token counts from usage chunk (final stream event)
                    usage = data.get("usage") or {}
                    eval_count = usage.get("completion_tokens", 0)
                    prompt_count = usage.get("prompt_tokens", 0)

                    yield CompletionChunk(
                        content=content,
                        done=done,
                        model=model,
                        eval_count=eval_count,
                        prompt_eval_count=prompt_count,
                    )

                    if done:
                        break

            LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="success").inc()

        except Exception as exc:
            LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="error").inc()
            log.error("tabbyapi_stream_error", model=model, error=str(exc))
            raise

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        repeat_penalty: float = 1.1,
        model_tier: str = "fast",
    ) -> CompletionResult:
        """
        Non-streaming chat completion (collects stream internally).

        Args:
            model: Model ID.
            messages: Conversation messages.
            temperature: Sampling temperature.
            top_p: Top-p sampling.
            max_tokens: Max tokens to generate.
            repeat_penalty: Repetition penalty.
            model_tier: Tier label for metrics.

        Returns:
            :class:`~llm.client.CompletionResult` with the full response.
        """
        t0 = time.monotonic()
        full_content = ""
        last_chunk: CompletionChunk | None = None

        async for chunk in self.chat_stream(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            repeat_penalty=repeat_penalty,
            model_tier=model_tier,
        ):
            full_content += chunk.content
            last_chunk = chunk

        latency_ms = (time.monotonic() - t0) * 1000.0
        return CompletionResult(
            content=full_content,
            model=model,
            total_tokens=(last_chunk.eval_count if last_chunk else 0),
            prompt_tokens=(last_chunk.prompt_eval_count if last_chunk else 0),
            latency_ms=latency_ms,
        )

    async def embed(self, model: str, text: str) -> EmbeddingResult:
        """
        Generate an embedding via POST /v1/embeddings.

        Args:
            model: Embedding model ID (e.g. ``"bge-m3"``).
            text: Text to embed.

        Returns:
            :class:`~llm.client.EmbeddingResult` with the embedding vector.
        """
        client = await self._get_client()
        resp = await client.post(
            "/v1/embeddings",
            json={"model": model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        vector: list[float] = items[0].get("embedding", []) if items else []
        return EmbeddingResult(embedding=vector, model=model)

    async def embed_batch(self, model: str, texts: list[str]) -> list[EmbeddingResult]:
        """
        Embed multiple texts concurrently.

        Args:
            model: Embedding model ID.
            texts: List of texts to embed.

        Returns:
            List of :class:`~llm.client.EmbeddingResult` in input order.
        """
        tasks = [self.embed(model, t) for t in texts]
        return list(await asyncio.gather(*tasks))

    async def keep_alive(self, model: str, duration: str = "30m") -> None:
        """
        No-op: TabbyAPI keeps its loaded model resident until explicitly unloaded.

        The method exists to satisfy :class:`~llm.base.LLMClientProtocol` and
        allow callers (e.g. :mod:`conversation.voice_engine`) to call
        ``keep_alive`` without branching on backend type.
        """
        log.debug("tabbyapi_keep_alive_noop", model=model)

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
