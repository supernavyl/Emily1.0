"""
Token stream processor for Emily's LLM output.

Handles:
- Buffering streaming tokens into complete sentences for TTS handoff
- Abbreviation-aware sentence boundary detection
- Text cleanup: strips markdown, URLs, code blocks, and formatting artifacts
- Thinking block extraction (for QwQ-32B <think>...</think> blocks)
- Cancellation support (user interrupts mid-stream)
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from observability.logger import get_logger

log = get_logger(__name__)

_THINKING_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)

_ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st",
    "vs", "etc", "inc", "ltd", "corp", "dept", "univ",
    "approx", "est", "govt", "assn",
}

_MARKDOWN_BOLD_ITALIC = re.compile(r"\*{1,3}(.+?)\*{1,3}")
_MARKDOWN_INLINE_CODE = re.compile(r"`([^`]+)`")
_MARKDOWN_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_URL_PATTERN = re.compile(r"https?://\S+")
_BULLET_PATTERN = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED_LIST = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)


def clean_for_tts(text: str) -> str:
    """
    Strip markdown formatting, URLs, and artifacts that sound unnatural
    when spoken aloud.

    Args:
        text: Raw LLM output text.

    Returns:
        Cleaned text suitable for TTS synthesis.
    """
    text = _MARKDOWN_CODE_BLOCK.sub("", text)
    text = _MARKDOWN_IMAGE.sub(r"\1", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _MARKDOWN_BOLD_ITALIC.sub(r"\1", text)
    text = _MARKDOWN_INLINE_CODE.sub(r"\1", text)
    text = _MARKDOWN_HEADING.sub("", text)
    text = _URL_PATTERN.sub("", text)
    text = _BULLET_PATTERN.sub("", text)
    text = _NUMBERED_LIST.sub("", text)
    text = re.sub(r"[_~|>]", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _is_sentence_boundary(buffer: str, pos: int) -> bool:
    """
    Check if the character at `pos` is a real sentence boundary.

    Filters out abbreviations (Dr., Mr.), decimal numbers (3.14),
    ellipses, and URLs.

    Args:
        buffer: Full text buffer.
        pos: Index of the `.`, `!`, or `?` character.

    Returns:
        True if this is a genuine sentence ending.
    """
    if pos >= len(buffer) or buffer[pos] not in ".!?":
        return False

    char = buffer[pos]

    if char == ".":
        if pos + 1 < len(buffer) and buffer[pos + 1] == ".":
            return False

        if pos > 0 and buffer[pos - 1].isdigit():
            if pos + 1 < len(buffer) and buffer[pos + 1].isdigit():
                return False

        word_start = pos - 1
        while word_start >= 0 and buffer[word_start].isalpha():
            word_start -= 1
        word_start += 1
        word = buffer[word_start:pos].lower()
        if word in _ABBREVIATIONS:
            return False

        if pos > 0 and buffer[pos - 1].isupper() and (pos < 2 or not buffer[pos - 2].isalpha()):
            return False

    after = pos + 1
    while after < len(buffer) and buffer[after] in ".!?":
        after += 1

    if after >= len(buffer):
        return False

    if buffer[after] == " " and after + 1 < len(buffer) and buffer[after + 1].isupper():
        return True

    if buffer[after] == "\n":
        return True

    return False


class StreamProcessor:
    """
    Processes a raw token stream into sentence-level chunks for TTS.

    Strips <think>...</think> blocks from QwQ-32B / DeepSeek-R1 output.
    Cleans markdown formatting and artifacts for natural speech.
    """

    def __init__(self, tts_chunk_min_chars: int = 20) -> None:
        """
        Args:
            tts_chunk_min_chars: Minimum characters before flushing a TTS chunk.
                Lower values reduce latency, higher values improve prosody.
        """
        self._tts_chunk_min = tts_chunk_min_chars

    async def iter_sentences(
        self,
        token_stream: AsyncIterator[str],
        strip_thinking: bool = True,
    ) -> AsyncIterator[str]:
        """
        Buffer tokens into complete sentences.

        Args:
            token_stream: Async iterator of token strings.
            strip_thinking: If True, remove <think>...</think> blocks.

        Yields:
            Complete sentence strings, suitable for TTS synthesis.
        """
        buffer = ""
        in_thinking = False
        thinking_buffer = ""

        async for token in token_stream:
            if strip_thinking:
                if "<think>" in token:
                    in_thinking = True
                if in_thinking:
                    thinking_buffer += token
                    if "</think>" in token:
                        in_thinking = False
                        log.debug(
                            "thinking_block_extracted",
                            length=len(thinking_buffer),
                        )
                        thinking_buffer = ""
                    continue

            buffer += token

            if len(buffer) < self._tts_chunk_min:
                continue

            split_pos = self._find_best_split(buffer)
            if split_pos is not None:
                sentence = clean_for_tts(buffer[:split_pos + 1].strip())
                if sentence:
                    yield sentence
                buffer = buffer[split_pos + 1:].lstrip()

        if buffer.strip():
            sentence = clean_for_tts(buffer.strip())
            if sentence:
                yield sentence

    async def collect_full_response(
        self,
        token_stream: AsyncIterator[str],
        strip_thinking: bool = True,
    ) -> tuple[str, str]:
        """
        Collect the complete response from a token stream.

        Args:
            token_stream: Async iterator of token strings.
            strip_thinking: If True, strip <think> blocks.

        Returns:
            Tuple of (cleaned_response, thinking_content).
        """
        full = ""
        async for token in token_stream:
            full += token

        thinking = ""
        if strip_thinking:
            for match in _THINKING_BLOCK_PATTERN.finditer(full):
                thinking += match.group(0)
            full = _THINKING_BLOCK_PATTERN.sub("", full).strip()

        return full, thinking

    def _find_best_split(self, buffer: str) -> int | None:
        """
        Find the best split position in the buffer.

        Tries sentence boundaries first, then falls back to clause
        boundaries (commas, semicolons, colons, dashes) for lower latency.

        Args:
            buffer: Current text buffer.

        Returns:
            Index of the split punctuation, or None.
        """
        best = None
        for i in range(len(buffer) - 1, self._tts_chunk_min - 1, -1):
            if buffer[i] in ".!?" and _is_sentence_boundary(buffer, i):
                best = i
                break

        if best is not None:
            return best

        for i in range(len(buffer) - 1, self._tts_chunk_min - 1, -1):
            if buffer[i] in ".!?":
                after = i + 1
                while after < len(buffer) and buffer[after] in ".!?":
                    after += 1
                if after < len(buffer) and buffer[after] == " ":
                    return i

        if len(buffer) >= self._tts_chunk_min * 2:
            for i in range(len(buffer) - 1, self._tts_chunk_min - 1, -1):
                if buffer[i] in ",;:\u2014" and i + 1 < len(buffer) and buffer[i + 1] == " ":
                    return i

        return None
