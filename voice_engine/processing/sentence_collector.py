"""Collects LLM tokens into complete sentences for natural TTS pacing."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Matches sentence-ending punctuation followed by whitespace or end-of-string.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+|(?<=\.\.\.)\s+")

# Common abbreviations that should NOT trigger sentence splits.
_ABBREVIATIONS_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|Gen|Gov|Sgt|Cpl|Pvt|Lt|Col"
    r"|vs|etc|approx|dept|est|vol"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.$"
)

# Maximum buffer length before we force a split on secondary delimiters.
_LONG_BUFFER_THRESHOLD = 80


class SentenceCollector:
    """Accumulates streaming tokens and extracts complete sentences.

    This class is designed to sit between the LLM token stream and TTS synthesis,
    ensuring that each TTS call receives a grammatically complete sentence for
    natural-sounding speech output.
    """

    def __init__(self, long_threshold: int = _LONG_BUFFER_THRESHOLD) -> None:
        self._buffer: str = ""
        self._long_threshold = long_threshold

    def feed(self, token: str) -> list[str]:
        """Feed a token into the collector.

        Returns a (possibly empty) list of complete sentences extracted from
        the buffer so far.
        """
        self._buffer += token
        sentences: list[str] = []

        while True:
            sentence = self._try_extract()
            if sentence is None:
                break
            sentences.append(sentence)

        return sentences

    def _try_extract(self) -> str | None:
        """Try to extract one complete sentence from the buffer."""
        # Scan for sentence-ending punctuation, skipping abbreviations
        search_start = 0
        while True:
            match = _SENTENCE_END_RE.search(self._buffer, search_start)
            if not match:
                break  # no sentence boundary — fall through to long-buffer check
            split_pos = match.start()
            candidate = self._buffer[:split_pos].strip()
            # Skip past abbreviations like "Dr." or "Mr." and keep searching
            if candidate and _ABBREVIATIONS_RE.search(candidate):
                search_start = match.end()
                continue
            self._buffer = self._buffer[match.end() :]
            if candidate:
                logger.debug("Sentence extracted: %s", candidate[:60])
                return candidate
            return None

        # No sentence boundary found — if the buffer is very long, force a split
        # on secondary delimiters (semicolons, colons, em-dashes, commas) to keep
        # TTS flowing rather than accumulating a silent wall of text.
        if len(self._buffer) > self._long_threshold:
            for delimiter in ("; ", ": ", " — ", ", "):
                idx = self._buffer.find(delimiter)
                if idx > 0:
                    sentence = self._buffer[: idx + len(delimiter)].strip()
                    self._buffer = self._buffer[idx + len(delimiter) :]
                    if sentence:
                        logger.debug("Long-buffer split: %s", sentence[:60])
                        return sentence

        return None

    def flush(self) -> str | None:
        """Return any remaining buffered text, or None if empty."""
        remaining = self._buffer.strip()
        self._buffer = ""
        if remaining:
            logger.debug("Flushed remainder: %s", remaining[:60])
            return remaining
        return None

    def reset(self) -> None:
        """Clear the internal buffer."""
        self._buffer = ""
