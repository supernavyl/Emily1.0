"""Unified streaming engine that sits between LLM providers and the UI.

Every provider yields :class:`StreamChunk` objects.  The engine consumes
them, applies the Emily identity filter to *text* chunks (thinking chunks
are exempt), tracks usage, and dispatches to the caller via callbacks.

Two public engines live here:

* :class:`EmilyStreamingEngine` — callback-based, used by the PySide6 UI
  ``AsyncRunner``.
* :class:`StreamingEngine` — async-generator interface for lightweight
  callers that iterate chunks directly.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Optional

from emily_chat.emily.persona import EmilyPersonaEngine
from emily_chat.models.registry import ModelSpec

if TYPE_CHECKING:
    from emily_chat.models.providers.base import BaseProvider

_PROVIDERS: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------


class ChunkType(str, Enum):
    """Discriminator for :class:`StreamChunk`."""

    THINKING = "thinking"
    TEXT = "text"
    USAGE = "usage"
    STOP = "stop"
    ERROR = "error"


@dataclass
class StreamChunk:
    """A single atomic piece of a streaming response.

    Providers yield these; the engine routes them to the appropriate
    callback.
    """

    type: ChunkType
    content: str = ""
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationSettings:
    """Per-request tunables passed through to the provider."""

    temperature: float = 0.5
    max_tokens: int = 4096
    reasoning_effort: str = "medium"
    thinking_budget: int = 8000
    top_p: float = 1.0
    stop: list[str] = field(default_factory=list)


@dataclass
class UsageStats:
    """Accumulated token counts and timing for a single generation."""

    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thinking: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    first_token_ms: int = 0
    model: str = ""
    provider: str = ""


# Callback type aliases for readability
OnText = Callable[[str], None]
OnThinking = Callable[[str], None]
OnMetadata = Callable[[dict[str, Any]], None]
OnDone = Callable[[UsageStats], None]
OnError = Callable[[Exception], None]


class EmilyStreamingEngine:
    """Orchestrates a single streaming generation.

    Typical usage::

        engine = EmilyStreamingEngine(persona)
        await engine.stream(
            provider, model_spec, messages, system_prompt, settings,
            on_thinking=..., on_text=..., on_metadata=...,
            on_done=..., on_error=...,
        )

    Call :meth:`interrupt` to cancel a running generation.
    """

    def __init__(self, persona: EmilyPersonaEngine) -> None:
        self._persona = persona
        self._interrupt = asyncio.Event()

    def interrupt(self) -> None:
        """Signal the running stream to stop at the next chunk boundary."""
        self._interrupt.set()

    async def stream(
        self,
        provider: BaseProvider,
        model_spec: ModelSpec,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        *,
        on_thinking: OnThinking | None = None,
        on_text: OnText | None = None,
        on_metadata: OnMetadata | None = None,
        on_done: OnDone | None = None,
        on_error: OnError | None = None,
    ) -> None:
        """Run a streaming generation end-to-end.

        Args:
            provider: The resolved :class:`BaseProvider` instance.
            model_spec: Which model to use.
            messages: Conversation history.
            system_prompt: Assembled by :class:`EmilyPersonaEngine`.
            settings: Temperature, max_tokens, etc.
            on_thinking: Called for each reasoning/thinking chunk.
            on_text: Called for each response-text chunk (post-filter).
            on_metadata: Called with usage metadata dict.
            on_done: Called once when the stream finishes normally.
            on_error: Called if the stream errors.
        """
        self._interrupt.clear()
        usage = UsageStats(model=model_spec.model_id, provider=model_spec.provider)

        t0 = time.monotonic()
        first_token_seen = False

        try:
            async for chunk in provider.stream(
                messages, system_prompt, settings, model_spec
            ):
                if self._interrupt.is_set():
                    break

                if chunk.type == ChunkType.THINKING:
                    if not first_token_seen:
                        usage.first_token_ms = int(
                            (time.monotonic() - t0) * 1000
                        )
                        first_token_seen = True
                    usage.tokens_thinking += chunk.tokens
                    if on_thinking:
                        on_thinking(chunk.content)

                elif chunk.type == ChunkType.TEXT:
                    if not first_token_seen:
                        usage.first_token_ms = int(
                            (time.monotonic() - t0) * 1000
                        )
                        first_token_seen = True
                    safe = self._persona.filter_response_chunk(chunk.content)
                    usage.tokens_out += chunk.tokens
                    if on_text:
                        on_text(safe)

                elif chunk.type == ChunkType.USAGE:
                    usage.tokens_in = chunk.metadata.get(
                        "prompt_tokens", usage.tokens_in
                    )
                    usage.tokens_out = chunk.metadata.get(
                        "completion_tokens", usage.tokens_out
                    )
                    usage.tokens_thinking = chunk.metadata.get(
                        "reasoning_tokens", usage.tokens_thinking
                    )
                    if on_metadata:
                        on_metadata(chunk.metadata)

                elif chunk.type == ChunkType.ERROR:
                    if on_error:
                        on_error(RuntimeError(chunk.content))
                    return

                elif chunk.type == ChunkType.STOP:
                    break

        except Exception as exc:
            if on_error:
                on_error(exc)
            return

        usage.latency_ms = int((time.monotonic() - t0) * 1000)

        from emily_chat.models.cost_tracker import estimate_cost

        usage.cost_usd = estimate_cost(
            model_spec, usage.tokens_in, usage.tokens_out, usage.tokens_thinking
        )

        if on_done:
            on_done(usage)

    # ------------------------------------------------------------------
    # Async-generator interface (used by AsyncRunner.submit_streaming)
    # ------------------------------------------------------------------

    async def stream_chunks(
        self,
        provider: BaseProvider,
        model_spec: ModelSpec,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
    ) -> AsyncIterator[StreamChunk]:
        """Yield filtered :class:`StreamChunk` objects for async iteration.

        This is an async-generator wrapper around the same logic as
        :meth:`stream`, designed for use with
        :meth:`~emily_chat.ui.async_bridge.AsyncRunner.submit_streaming`.

        Args:
            provider: The resolved :class:`BaseProvider` instance.
            model_spec: Which model to use.
            messages: Conversation history.
            system_prompt: Assembled by :class:`EmilyPersonaEngine`.
            settings: Temperature, max_tokens, etc.

        Yields:
            :class:`StreamChunk` instances of type ``thinking``, ``text``
            (post identity-filter), ``usage``, ``stop``, or ``error``.
        """
        self._interrupt.clear()
        usage = UsageStats(model=model_spec.model_id, provider=model_spec.provider)

        t0 = time.monotonic()
        first_token_seen = False

        try:
            async for chunk in provider.stream(
                messages, system_prompt, settings, model_spec
            ):
                if self._interrupt.is_set():
                    break

                if chunk.type == ChunkType.THINKING:
                    if not first_token_seen:
                        usage.first_token_ms = int(
                            (time.monotonic() - t0) * 1000
                        )
                        first_token_seen = True
                    usage.tokens_thinking += chunk.tokens
                    yield chunk

                elif chunk.type == ChunkType.TEXT:
                    if not first_token_seen:
                        usage.first_token_ms = int(
                            (time.monotonic() - t0) * 1000
                        )
                        first_token_seen = True
                    safe = self._persona.filter_response_chunk(chunk.content)
                    usage.tokens_out += chunk.tokens
                    yield StreamChunk(
                        type=ChunkType.TEXT, content=safe, tokens=chunk.tokens
                    )

                elif chunk.type == ChunkType.USAGE:
                    usage.tokens_in = chunk.metadata.get(
                        "prompt_tokens", usage.tokens_in
                    )
                    usage.tokens_out = chunk.metadata.get(
                        "completion_tokens", usage.tokens_out
                    )
                    usage.tokens_thinking = chunk.metadata.get(
                        "reasoning_tokens", usage.tokens_thinking
                    )
                    yield chunk

                elif chunk.type == ChunkType.ERROR:
                    yield chunk
                    return

                elif chunk.type == ChunkType.STOP:
                    break

        except Exception as exc:
            yield StreamChunk(type=ChunkType.ERROR, content=str(exc))
            return

        usage.latency_ms = int((time.monotonic() - t0) * 1000)

        from emily_chat.models.cost_tracker import estimate_cost

        usage.cost_usd = estimate_cost(
            model_spec, usage.tokens_in, usage.tokens_out, usage.tokens_thinking
        )

        yield StreamChunk(
            type=ChunkType.USAGE,
            metadata={
                "input_tokens": usage.tokens_in,
                "output_tokens": usage.tokens_out,
                "reasoning_tokens": usage.tokens_thinking,
                "cost_usd": usage.cost_usd,
                "latency_ms": usage.latency_ms,
                "first_token_ms": usage.first_token_ms,
                "model": usage.model,
                "provider": usage.provider,
            },
        )
        yield StreamChunk(type=ChunkType.STOP)


# ---------------------------------------------------------------------------
# Lightweight async-generator streaming engine
# ---------------------------------------------------------------------------

_PROVIDER_CLASSES: dict[str, str] = {
    "anthropic": "emily_chat.models.providers.anthropic.AnthropicProvider",
    "openai": "emily_chat.models.providers.openai.OpenAIProvider",
    "google": "emily_chat.models.providers.google.GoogleProvider",
    "groq": "emily_chat.models.providers.groq.GroqProvider",
    "deepseek": "emily_chat.models.providers.deepseek.DeepSeekProvider",
    "together": "emily_chat.models.providers.together.TogetherProvider",
    "xai": "emily_chat.models.providers.xai.XAIProvider",
    "mistral": "emily_chat.models.providers.mistral.MistralProvider",
    "openrouter": "emily_chat.models.providers.openrouter.OpenRouterProvider",
    "ollama": "emily_chat.models.providers.ollama.OllamaProvider",
}

_ENV_KEY_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "together": "TOGETHER_API_KEY",
    "xai": "XAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _get_provider(provider_name: str) -> Any:
    """Return a cached provider instance, creating it on first access."""
    if provider_name in _PROVIDERS:
        return _PROVIDERS[provider_name]

    dotted = _PROVIDER_CLASSES.get(provider_name)
    if dotted is None:
        raise ValueError(f"Unknown provider: {provider_name!r}")

    module_path, cls_name = dotted.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)

    env_var = _ENV_KEY_MAP.get(provider_name)
    api_key = os.environ.get(env_var, "") if env_var else None
    instance = cls(api_key=api_key) if api_key is not None else cls()
    _PROVIDERS[provider_name] = instance
    return instance


class StreamingEngine:
    """Async-generator streaming engine for direct chunk iteration.

    Unlike :class:`EmilyStreamingEngine` this class needs no persona
    dependency — an optional ``persona_filter`` callable can be passed
    per-call instead.
    """

    def __init__(self) -> None:
        self._interrupt = asyncio.Event()

    def interrupt(self) -> None:
        """Signal the running stream to stop."""
        self._interrupt.set()

    async def stream(
        self,
        model_spec: ModelSpec,
        messages: list[dict],
        system_prompt: str,
        settings: Any,
        *,
        persona_filter: Callable[[str], str] | None = None,
        interrupt: asyncio.Event | None = None,
    ) -> AsyncIterator[Any]:
        """Stream a completion, yielding :class:`~emily_chat.models.base.StreamChunk`.

        Args:
            model_spec: Resolved model spec from the registry.
            messages: Conversation history.
            system_prompt: System prompt string.
            settings: Generation settings.
            persona_filter: Optional text transform applied to text chunks.
            interrupt: Optional external interrupt event.

        Yields:
            StreamChunk objects (from ``emily_chat.models.base``).
        """
        from emily_chat.models.base import StreamChunk as BaseChunk

        provider = _get_provider(model_spec.provider)

        t0 = time.monotonic()
        first_token_ms: float | None = None

        try:
            async for chunk in provider.stream(
                model_spec.model_id, messages, system_prompt, settings
            ):
                if (interrupt and interrupt.is_set()) or self._interrupt.is_set():
                    yield BaseChunk(type="stop")
                    return

                if chunk.type == "thinking":
                    if first_token_ms is None:
                        first_token_ms = (time.monotonic() - t0) * 1000
                    yield chunk

                elif chunk.type == "text":
                    if first_token_ms is None:
                        first_token_ms = (time.monotonic() - t0) * 1000
                    content = persona_filter(chunk.content) if persona_filter else chunk.content
                    yield BaseChunk(type="text", content=content)

                elif chunk.type == "usage":
                    latency_ms = (time.monotonic() - t0) * 1000
                    from emily_chat.models.cost_tracker import estimate_cost
                    cost = estimate_cost(
                        model_spec,
                        chunk.usage.get("input_tokens", 0),
                        chunk.usage.get("output_tokens", 0),
                        0,
                    )
                    enriched = {
                        **chunk.usage,
                        "latency_ms": round(latency_ms),
                        "first_token_ms": round(first_token_ms or 0),
                        "cost_usd": cost,
                    }
                    yield BaseChunk(type="usage", usage=enriched)

                elif chunk.type == "stop":
                    yield chunk

        except Exception as exc:
            yield BaseChunk(type="stop", content=str(exc))
            return

        self._interrupt.clear()
