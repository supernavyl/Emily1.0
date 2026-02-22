"""
Speculative pre-generation cache for Emily.

When turn completion probability reaches 0.65 (below the 0.85 response threshold),
the LLM begins generating speculatively with the partial transcript.

If the final transcript matches within 20% edit distance, the cached
response is used, saving 100-200ms of response latency.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class SpeculativeEntry:
    """A single speculative generation cache entry."""

    partial_transcript: str
    generated_text: str
    timestamp: float = field(default_factory=time.monotonic)
    model_used: str = ""
    generation_time_ms: float = 0.0


class SpeculativeCache:
    """
    Manages speculative pre-generation entries.

    Keeps the most recent speculation and discards stale ones.
    Caches are discarded if the transcript diverges > 20% edit distance.
    """

    _MAX_AGE_S = 10.0
    _MAX_DIVERGENCE = 0.20

    def __init__(self) -> None:
        self._current: SpeculativeEntry | None = None
        self._hits = 0
        self._misses = 0
        self._task: asyncio.Task | None = None

    def store(self, partial: str, generated: str, model: str = "", gen_time_ms: float = 0) -> None:
        """
        Store a speculative generation result.

        Args:
            partial: The partial transcript used for generation.
            generated: The generated response text.
            model: Model name used.
            gen_time_ms: How long generation took.
        """
        self._current = SpeculativeEntry(
            partial_transcript=partial,
            generated_text=generated,
            model_used=model,
            generation_time_ms=gen_time_ms,
        )
        log.debug(
            "speculative_stored",
            partial_len=len(partial),
            generated_len=len(generated),
        )

    def check(self, final_transcript: str) -> str | None:
        """
        Check if the cached speculation matches the final transcript.

        Args:
            final_transcript: The committed final STT transcript.

        Returns:
            The cached response if it matches, else None.
        """
        if self._current is None:
            self._misses += 1
            return None

        age = time.monotonic() - self._current.timestamp
        if age > self._MAX_AGE_S:
            log.debug("speculative_stale", age_s=f"{age:.1f}")
            self._current = None
            self._misses += 1
            return None

        divergence = self._compute_divergence(
            self._current.partial_transcript,
            final_transcript,
        )

        if divergence <= self._MAX_DIVERGENCE:
            self._hits += 1
            result = self._current.generated_text
            log.info(
                "speculative_hit",
                divergence=f"{divergence:.2f}",
                saved_ms=f"{self._current.generation_time_ms:.0f}",
            )
            self._current = None
            return result

        self._misses += 1
        log.debug("speculative_miss", divergence=f"{divergence:.2f}")
        self._current = None
        return None

    @staticmethod
    def _compute_divergence(partial: str, final: str) -> float:
        """Compute normalized edit distance between partial and final transcripts."""
        a = partial.lower().strip()
        b = final.lower().strip()

        n, m = len(a), len(b)
        if max(n, m) == 0:
            return 0.0

        prev = list(range(m + 1))
        curr = [0] * (m + 1)
        for i in range(1, n + 1):
            curr[0] = i
            for j in range(1, m + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            prev, curr = curr, prev

        return prev[m] / max(n, m)

    def discard(self) -> None:
        """Discard the current speculation."""
        self._current = None

    @property
    def hit_rate(self) -> float:
        """Cache hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def stats(self) -> dict[str, int | float]:
        """Cache statistics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "has_pending": self._current is not None,
        }
