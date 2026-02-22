"""
LLM client protocol for Emily.

Defines the interface that all LLM backends (Ollama, llama-cpp-python, etc.)
must implement. Using ``typing.Protocol`` enables structural subtyping — any
class with matching method signatures is considered a valid implementation
without inheriting from a base class.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from llm.client import ChatMessage, CompletionChunk, CompletionResult, EmbeddingResult


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Structural protocol every LLM backend must satisfy."""

    async def health_check(self) -> bool:
        """Return True if the backend is operational."""
        ...

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        repeat_penalty: float = 1.1,
        model_tier: str = "fast",
    ) -> AsyncIterator[CompletionChunk]:
        """Yield ``CompletionChunk`` objects as the model generates tokens."""
        ...
        yield  # type: ignore[misc]

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
        """Return a complete non-streaming response."""
        ...

    async def embed(self, model: str, text: str) -> EmbeddingResult:
        """Generate an embedding vector for *text*."""
        ...

    async def keep_alive(self, model: str, duration: str = "30m") -> None:
        """Keep a model warm in memory (no-op for in-process backends)."""
        ...

    async def close(self) -> None:
        """Release resources held by the client."""
        ...
