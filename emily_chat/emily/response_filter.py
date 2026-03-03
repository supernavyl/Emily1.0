"""Identity-leak detection and cleanup for every outbound text chunk.

The filter runs on every *text* chunk before it reaches the UI.
Thinking / internal-reasoning chunks are exempt — the caller is
responsible for routing them around this filter.
"""

from __future__ import annotations

import re
from typing import ClassVar


class EmilyResponseFilter:
    """Regex-based identity leak detector and replacer.

    All patterns are compiled once at instantiation so per-chunk cost
    is pure matching — no re-compilation overhead.
    """

    _RAW_REPLACEMENTS: ClassVar[list[tuple[str, str]]] = [
        (r"(?i)\bAs Claude[,\s]", "As Emily, "),
        (r"(?i)\bI'?m Claude\b", "I'm Emily"),
        (r"(?i)\bmade by Anthropic\b", "made to help you"),
        (r"(?i)\bAs an AI (?:assistant |language model )?created by Anthropic\b", "As Emily"),
        (r"(?i)\bI'?m (?:ChatGPT|GPT-[\w.]+)\b", "I'm Emily"),
        (r"(?i)\bmade by OpenAI\b", "made to help you"),
        (r"(?i)\bAs an AI (?:assistant |model )?developed by OpenAI\b", "As Emily"),
        (r"(?i)\bI'?m Gemini\b", "I'm Emily"),
        (r"(?i)\bmade by Google\b", "made to help you"),
        (r"(?i)\bI'?m Grok\b", "I'm Emily"),
        (r"(?i)\bmade by xAI\b", "made to help you"),
        (r"(?i)\bI'?m DeepSeek\b", "I'm Emily"),
        (r"(?i)\bI'?m Qwen\b", "I'm Emily"),
        (r"(?i)\bI'?m Kimi\b", "I'm Emily"),
        (r"(?i)\bI'?m Mistral\b", "I'm Emily"),
        (r"(?i)\bI'?m Llama\b", "I'm Emily"),
        (
            r"(?i)\bI'?m (?:an AI|a language model) and I don'?t have\b",
            "I'm Emily and I don't have",
        ),
        (r"(?i)\bAs a large language model\b", "As Emily"),
    ]

    def __init__(self) -> None:
        self._compiled: list[tuple[re.Pattern[str], str]] = [
            (re.compile(pattern), replacement) for pattern, replacement in self._RAW_REPLACEMENTS
        ]

    def filter_chunk(self, chunk: str) -> str:
        """Apply all identity-leak replacements to *chunk*.

        Args:
            chunk: A text fragment from the LLM response stream.

        Returns:
            The chunk with any identity leaks replaced by Emily-safe text.
        """
        for pattern, replacement in self._compiled:
            chunk = pattern.sub(replacement, chunk)
        return chunk
