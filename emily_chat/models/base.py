"""Core abstractions for the model/provider layer.

Canonical type definitions:

* :class:`StreamChunk`, :class:`ChunkType`, :class:`GenerationSettings`
  live in :mod:`emily_chat.models.streaming_engine`.
* :class:`BaseProvider` lives in :mod:`emily_chat.models.providers.base`.

This module owns :class:`ModelSpec` and re-exports the above for
backward-compatibility so that ``from emily_chat.models.base import
StreamChunk`` still works.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Re-exports — canonical definitions live elsewhere
from emily_chat.models.streaming_engine import (  # noqa: F401
    ChunkType,
    GenerationSettings,
    StreamChunk,
)


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


# Re-export BaseProvider for backward-compatibility
from emily_chat.models.providers.base import BaseProvider  # noqa: F401
