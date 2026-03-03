"""Stateful filter that strips <think>...</think> blocks from streamed LLM tokens.

Handles the case where tag boundaries split across chunks — e.g. a chunk
ending with ``</th`` followed by a chunk starting with ``ink>``.

Used by both EmilyLLMProvider and _EmilyLLMBridge to ensure internal
reasoning never leaks into TTS output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Maximum partial-tag bytes to hold back (len("<think>") - 1 = 6)
_TAG_HOLDBACK = 6


async def strip_think_tags(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Async generator that strips ``<think>...</think>`` blocks from a token stream.

    Buffers text internally to handle tags split across chunk boundaries.
    Holds back up to 6 characters at the tail of non-think content to
    detect partial ``<think`` openings.

    Args:
        tokens: Raw LLM token stream (may contain think blocks).

    Yields:
        Cleaned text tokens with all think-block content removed.
    """
    buf = ""
    in_think = False

    async for token in tokens:
        buf += token

        while True:
            if not in_think:
                idx = buf.find("<think>")
                if idx != -1:
                    if idx > 0:
                        yield buf[:idx]
                    buf = buf[idx + 7 :]
                    in_think = True
                else:
                    # Emit everything except a tail that might be a partial "<think"
                    safe = len(buf) - _TAG_HOLDBACK
                    if safe > 0:
                        yield buf[:safe]
                        buf = buf[safe:]
                    break
            else:
                idx = buf.find("</think>")
                if idx != -1:
                    buf = buf[idx + 8 :]
                    in_think = False
                else:
                    break

    # Flush remaining buffer after stream ends
    if buf and not in_think:
        yield buf
