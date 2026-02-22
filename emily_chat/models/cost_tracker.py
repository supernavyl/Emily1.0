"""Cost estimation for LLM API calls.

Pricing is stored per-million tokens on each :class:`ModelSpec`.  This
module converts raw token counts into USD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emily_chat.models.registry import ModelSpec

_PER_MILLION = 1_000_000.0


def estimate_cost(
    model: ModelSpec,
    tokens_in: int,
    tokens_out: int,
    tokens_thinking: int = 0,
) -> float:
    """Return the estimated cost in USD for a single generation.

    Reasoning/thinking tokens are billed at the *output* rate — this
    matches the pricing model used by OpenAI o-series and Anthropic
    extended thinking.

    Args:
        model: The model spec (carries per-million-token prices).
        tokens_in: Number of input/prompt tokens.
        tokens_out: Number of output/completion tokens (excluding thinking).
        tokens_thinking: Number of reasoning/thinking tokens.

    Returns:
        Estimated cost in USD.
    """
    input_cost = (tokens_in / _PER_MILLION) * model.input_usd
    output_cost = ((tokens_out + tokens_thinking) / _PER_MILLION) * model.output_usd
    return input_cost + output_cost


def format_cost(usd: float) -> str:
    """Format a USD cost for display in the UI.

    Args:
        usd: The dollar amount.

    Returns:
        A human-readable string like ``"$0.0124"`` or ``"< $0.0001"``.
    """
    if usd < 0.0001:
        return "< $0.0001"
    return f"${usd:.4f}"
