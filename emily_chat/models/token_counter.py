"""Token counting for OpenAI-family models via tiktoken.

Provides per-model encoding lookup and helpers for counting tokens in
plain text and in chat-message lists.
"""

from __future__ import annotations

import tiktoken

# Mapping from our model_id strings to tiktoken encoding names.
# All current GPT-4o / GPT-5 / o-series models use cl100k_base or the
# newer o200k_base.  tiktoken.encoding_for_model handles known aliases;
# this fallback map covers future / hypothetical model IDs.
_ENCODING_FALLBACK = "o200k_base"

# Per-message overhead tokens in the chat format (role + separators).
_MSG_OVERHEAD = 4  # <|im_start|>{role}\n ... <|im_end|>\n


def _get_encoding(model_id: str) -> tiktoken.Encoding:
    """Resolve the tiktoken encoding for *model_id*.

    Args:
        model_id: The OpenAI model identifier (e.g. ``"gpt-5"``).

    Returns:
        A :class:`tiktoken.Encoding` instance.
    """
    try:
        return tiktoken.encoding_for_model(model_id)
    except KeyError:
        return tiktoken.get_encoding(_ENCODING_FALLBACK)


def count_tokens(text: str, model_id: str = "gpt-4o") -> int:
    """Count the number of tokens in *text* for *model_id*.

    Args:
        text: Plain text string.
        model_id: OpenAI model identifier for encoding selection.

    Returns:
        Token count.
    """
    enc = _get_encoding(model_id)
    return len(enc.encode(text))


def count_messages(messages: list[dict], model_id: str = "gpt-4o") -> int:
    """Estimate the token count for a chat-completion message list.

    Each message contributes its content tokens plus a small fixed
    overhead for role delimiters.  A final ``+2`` accounts for the
    assistant-reply priming tokens.

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts.
        model_id: OpenAI model identifier for encoding selection.

    Returns:
        Estimated total token count.
    """
    enc = _get_encoding(model_id)
    total = 0
    for msg in messages:
        total += _MSG_OVERHEAD
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(enc.encode(content))
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(enc.encode(part.get("text", "")))
    total += 2  # assistant-reply priming
    return total
