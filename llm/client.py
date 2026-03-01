"""
Async Ollama client for Emily.

Thin async wrapper around the Ollama REST API supporting:
- Streaming chat completions
- Non-streaming completions
- Embeddings
- Model management (list, load, unload)
- Health checking

All methods are async and use httpx for HTTP transport.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from observability.logger import get_logger
from observability.metrics import LLM_FIRST_TOKEN_LATENCY, LLM_REQUESTS_TOTAL

log = get_logger(__name__)


@dataclass
class ChatMessage:
    """A single chat message."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    images: list[str] = field(default_factory=list)  # base64 images for vision


@dataclass
class CompletionChunk:
    """A streaming completion chunk from Ollama."""

    content: str
    done: bool
    model: str
    eval_count: int = 0
    prompt_eval_count: int = 0


@dataclass
class CompletionResult:
    """A complete (non-streaming) completion result."""

    content: str
    model: str
    total_tokens: int
    prompt_tokens: int
    latency_ms: float


@dataclass
class EmbeddingResult:
    """An embedding result from Ollama."""

    embedding: list[float]
    model: str


class OllamaClient:
    """
    Async HTTP client for the Ollama API.

    Implements :class:`~llm.base.LLMClientProtocol` so it can be used
    interchangeably with other backends (e.g. ``LlamaCppClient``).

    Maintains a persistent httpx.AsyncClient for connection pooling.
    All inference parameters default to config values but can be overridden per call.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout_s: float = 120.0,
    ) -> None:
        """
        Args:
            base_url: Ollama server base URL.
            timeout_s: Request timeout in seconds for non-streaming calls.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return (lazily create) the shared async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
            )
        return self._client

    async def health_check(self) -> bool:
        """
        Check if Ollama is running and reachable.

        Returns:
            True if Ollama responds successfully.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """
        List all models available in Ollama.

        Returns:
            List of model name strings.
        """
        client = await self._get_client()
        resp = await client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]

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
        Stream a chat completion from Ollama.

        Args:
            model: Ollama model name (e.g., "qwen3:14b").
            messages: List of ChatMessage objects.
            temperature: Sampling temperature.
            top_p: Top-p nucleus sampling.
            max_tokens: Maximum tokens to generate.
            repeat_penalty: Repetition penalty.
            model_tier: Logical tier for metrics labeling.

        Yields:
            CompletionChunk objects as they arrive.
        """
        client = await self._get_client()
        payload = {
            "model": model,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    **({"images": m.images} if m.images else {}),
                }
                for m in messages
            ],
            "stream": True,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
                "repeat_penalty": repeat_penalty,
            },
        }
        if not enable_thinking:
            payload["options"]["num_ctx"] = payload["options"].get("num_ctx", 8192)
            payload["think"] = False

        t0 = time.monotonic()
        first_token = True
        LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="started").inc()

        try:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    content = data.get("message", {}).get("content", "")
                    done = data.get("done", False)

                    if first_token and content:
                        latency = time.monotonic() - t0
                        LLM_FIRST_TOKEN_LATENCY.labels(model_tier=model_tier).observe(latency)
                        log.debug(
                            "llm_first_token",
                            model=model,
                            tier=model_tier,
                            latency_ms=f"{latency * 1000:.0f}",
                        )
                        first_token = False

                    yield CompletionChunk(
                        content=content,
                        done=done,
                        model=model,
                        eval_count=data.get("eval_count", 0),
                        prompt_eval_count=data.get("prompt_eval_count", 0),
                    )

                    if done:
                        break

            LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="success").inc()

        except Exception as exc:
            LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="error").inc()
            log.error("llm_stream_error", model=model, error=str(exc))
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
        Non-streaming chat completion.

        Args:
            model: Ollama model name.
            messages: Conversation messages.
            temperature: Sampling temperature.
            top_p: Top-p sampling.
            max_tokens: Max tokens to generate.
            repeat_penalty: Repetition penalty.
            model_tier: Logical tier for metrics.

        Returns:
            CompletionResult with full response.
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
        Generate an embedding for the given text.

        Args:
            model: Embedding model name (e.g., "bge-m3").
            text: Text to embed.

        Returns:
            EmbeddingResult with the embedding vector.
        """
        client = await self._get_client()
        resp = await client.post(
            "/api/embed",
            json={"model": model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings", [[]])
        return EmbeddingResult(
            embedding=embeddings[0] if embeddings else [],
            model=model,
        )

    async def embed_batch(self, model: str, texts: list[str]) -> list[EmbeddingResult]:
        """
        Generate embeddings for multiple texts.

        Args:
            model: Embedding model name.
            texts: List of texts to embed.

        Returns:
            List of EmbeddingResult objects in the same order.
        """
        tasks = [self.embed(model, text) for text in texts]
        return await asyncio.gather(*tasks)

    async def keep_alive(self, model: str, duration: str = "30m") -> None:
        """
        Send a no-op request to Ollama to keep a model loaded in VRAM.

        Prevents cold-start penalty on the first real inference request.

        Args:
            model: Ollama model name to keep warm.
            duration: Keep-alive duration string (e.g. "30m", "1h").
        """
        try:
            client = await self._get_client()
            await client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [],
                    "keep_alive": duration,
                },
            )
            log.info("model_keep_alive", model=model, duration=duration)
        except Exception as exc:
            log.debug("keep_alive_failed", model=model, error=str(exc))

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
