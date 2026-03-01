"""Core abstractions for the model/provider layer.

Every LLM provider normalises its streaming output into :class:`StreamChunk`
objects so the rest of the application never touches provider-specific types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """A single normalised piece of a streaming LLM response.

    Attributes:
        type: ``"thinking"`` for reasoning tokens, ``"text"`` for visible
              response tokens, ``"usage"`` for final token/cost accounting,
              or ``"stop"`` when generation is complete.
        content: Text payload (empty string for usage/stop).
        usage: Token counts and cost data (only meaningful when *type* is
               ``"usage"``).
    """

    type: Literal["thinking", "text", "usage", "stop"]
    content: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Describes a single model variant available in the registry.

    Attributes:
        id: Internal registry key (e.g. ``"claude-sonnet-4-6"``).
        display: Human-readable name shown in the UI (e.g. ``"Emily — Sonnet"``).
        provider: Provider identifier (e.g. ``"anthropic"``).
        model_id: Provider-side model string sent in API calls.
        context: Maximum context window in tokens.
        thinking: Whether the model supports extended thinking / reasoning.
        vision: Whether the model accepts image inputs.
        input_cost_per_mtok: Price per 1 M input tokens (USD).
        output_cost_per_mtok: Price per 1 M output tokens (USD).
        speed: Qualitative speed tier.
        tier: Quality tier label.
        default: Whether this is the default model.
        best_for: Notable strengths.
    """

    id: str
    display: str
    provider: str
    model_id: str
    context: int = 200_000
    thinking: bool = False
    vision: bool = False
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    speed: str = "medium"
    tier: str = "good"
    default: bool = False
    best_for: list[str] = field(default_factory=list)


@dataclass
class GenerationSettings:
    """Per-request generation parameters.

    Attributes:
        temperature: Sampling temperature (0.0-1.0).
        max_tokens: Maximum output tokens.
        thinking_budget: Token budget for extended thinking (0 = disabled).
        reasoning_effort: ``"low"`` | ``"medium"`` | ``"high"`` for OpenAI
            o-series models.  Ignored by other providers.
        stop_sequences: Optional stop strings.
    """

    temperature: float = 0.5
    max_tokens: int = 8192
    thinking_budget: int = 8000
    reasoning_effort: str = "medium"
    stop_sequences: list[str] = field(default_factory=list)


class BaseProvider(ABC):
    """Abstract base for all LLM provider implementations.

    Each provider translates its vendor-specific streaming API into a uniform
    :class:`StreamChunk` async iterator.
    """

    @abstractmethod
    async def stream(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        settings: GenerationSettings,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion, yielding normalised :class:`StreamChunk` objects.

        Args:
            model_id: The provider-side model identifier.
            messages: Conversation history as ``{"role": ..., "content": ...}`` dicts.
            system_prompt: The assembled system prompt (identity + skill + context).
            settings: Generation parameters.

        Yields:
            :class:`StreamChunk` instances in order: zero or more ``thinking``,
            zero or more ``text``, one ``usage``, one ``stop``.
        """
        ...  # pragma: no cover
        # yield is needed so the type-checker sees this as an AsyncIterator
        yield StreamChunk(type="stop")  # type: ignore[misc]

    @abstractmethod
    async def validate_key(self, api_key: str) -> bool:
        """Check whether *api_key* is accepted by the provider.

        Args:
            api_key: The raw API key string.

        Returns:
            ``True`` if the key is valid.
        """
        ...  # pragma: no cover
