"""Anthropic adapter implementing LLMClientProtocol for LLMFleet.

Wraps ``emily_chat.models.providers.anthropic.AnthropicProvider`` so
Claude models (Opus, Sonnet, Haiku) can be routed from the agent fleet
the same way as Ollama/TabbyAPI backends.

Key translation work:
- Splits the ``system`` ``ChatMessage`` out of the list (Anthropic API
  requires the system prompt as a top-level field, not a message).
- Converts ``StreamChunk`` (base provider) → ``CompletionChunk`` (fleet).
- Maps ``enable_thinking`` + ``thinking_budget`` into ``GenerationSettings``.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from emily_chat.models.base import ModelSpec
from emily_chat.models.streaming_engine import GenerationSettings
from llm.client import ChatMessage, CompletionChunk, CompletionResult, EmbeddingResult
from observability.logger import get_logger

log = get_logger(__name__)


class AnthropicFleetClient:
    """Adapts ``AnthropicProvider`` to ``LLMClientProtocol`` for ``LLMFleet``.

    Maintains a lazily-created provider instance so the ``anthropic``
    package is only imported when an Anthropic tier is actually used.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_thinking_budget: int = 16_000,
    ) -> None:
        """
        Args:
            api_key: Anthropic API key (falls back to ``ANTHROPIC_API_KEY`` env var).
            default_thinking_budget: Token budget for extended thinking when
                ``enable_thinking=True`` and no per-call budget is passed.
                Default 16 000 suits Claude Opus 4.6's reasoning depth.
        """
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._default_thinking_budget = default_thinking_budget
        self._provider: Any | None = None

    def _get_provider(self) -> Any:
        """Lazily import and create the AnthropicProvider."""
        if self._provider is None:
            from emily_chat.models.providers.anthropic import AnthropicProvider

            self._provider = AnthropicProvider(api_key=self._api_key)
        return self._provider

    async def health_check(self) -> bool:
        """Return True if an API key is configured."""
        return bool(self._api_key)

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 8192,
        repeat_penalty: float = 1.1,
        model_tier: str = "cloud_best",
        enable_thinking: bool = True,
        thinking_budget: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[CompletionChunk]:
        """Stream a Claude completion, yielding ``CompletionChunk`` objects.

        Args:
            model: Anthropic model ID (e.g. ``"claude-opus-4-6"``).
            messages: Fleet-style ``ChatMessage`` list, may include a
                ``system`` role entry.
            temperature: Sampling temperature.
            top_p: Ignored by Anthropic (included for protocol compat).
            max_tokens: Maximum output tokens.
            repeat_penalty: Ignored by Anthropic (included for protocol compat).
            model_tier: Tier label for metrics.
            enable_thinking: When True, enables extended thinking using
                ``thinking_budget`` tokens.
            thinking_budget: Override the instance default thinking budget.
            **kwargs: Absorbs any extra kwargs passed by fleet callers.

        Yields:
            ``CompletionChunk`` objects (text only; thinking chunks are
            swallowed here since LLMFleet doesn't have a thinking channel).
        """
        provider = self._get_provider()

        # Anthropic requires system prompt as a top-level field, not a message
        system_prompt = ""  # noqa
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content  # noqa
            else:
                chat_messages.append({"role": msg.role, "content": msg.content})

        budget = (
            thinking_budget
            if thinking_budget is not None
            else (self._default_thinking_budget if enable_thinking else 0)
        )
        settings = GenerationSettings(
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=budget,
        )

        # Build a minimal ModelSpec for the provider contract
        from emily_chat.models.registry import get_model

        spec = get_model(model)
        if spec is None:
            spec = ModelSpec(
                id=model,
                display=model,
                provider="anthropic",
                model_id=model,
            )

        log.debug(
            "anthropic_fleet_stream",
            model=model,
            tier=model_tier,
            thinking_budget=budget,
            max_tokens=max_tokens,
        )

        async for chunk in provider.stream(
            chat_messages,
            system_prompt,
            settings,
            spec,
        ):
            if chunk.type == "text":
                yield CompletionChunk(content=chunk.content, done=False, model=model)
            elif chunk.type == "stop":
                yield CompletionChunk(content="", done=True, model=model)
            # thinking and usage chunks are not forwarded — LLMFleet
            # callers use chat_stream for text tokens only

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 8192,
        repeat_penalty: float = 1.1,
        model_tier: str = "cloud_best",
        enable_thinking: bool = True,
        thinking_budget: int | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        """Non-streaming Claude completion.

        Args:
            model: Anthropic model ID.
            messages: Conversation messages.
            temperature: Sampling temperature.
            top_p: Ignored (protocol compat).
            max_tokens: Maximum output tokens.
            repeat_penalty: Ignored (protocol compat).
            model_tier: Tier label for metrics.
            enable_thinking: Enable extended thinking.
            thinking_budget: Override default thinking budget.
            **kwargs: Absorbs extra fleet kwargs.

        Returns:
            ``CompletionResult`` with the full response text.
        """
        t0 = time.monotonic()
        content = ""
        total_tokens = 0
        prompt_tokens = 0

        async for chunk in self.chat_stream(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            repeat_penalty=repeat_penalty,
            model_tier=model_tier,
            enable_thinking=enable_thinking,
            thinking_budget=thinking_budget,
        ):
            if not chunk.done:
                content += chunk.content

        return CompletionResult(
            content=content,
            model=model,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    async def embed(self, model: str, text: str) -> EmbeddingResult:
        """Not supported — Anthropic does not offer an embeddings endpoint."""
        raise NotImplementedError(
            "AnthropicFleetClient does not support embeddings. "
            "Use the Ollama BGE-M3 embedding tier instead."
        )

    async def keep_alive(self, model: str, duration: str = "30m") -> None:
        """No-op — Anthropic API is stateless."""

    async def close(self) -> None:
        """No-op — no persistent connection to close."""
