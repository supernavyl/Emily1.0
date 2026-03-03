"""Abstract base classes for all voice-engine providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class STTProvider(ABC):
    """Speech-to-text provider interface."""

    @abstractmethod
    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe a complete audio buffer and return the full text."""
        ...

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[np.ndarray],
        sample_rate: int,
    ) -> AsyncIterator[str]:
        """Transcribe an async stream of audio chunks, yielding partial transcripts."""
        ...
        # Make the method an async generator so subclasses can use yield.
        # This unreachable yield keeps the type-checker happy.
        yield ""  # pragma: no cover


class LLMProvider(ABC):
    """Large language model provider interface."""

    @abstractmethod
    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream an LLM response token-by-token."""
        ...
        yield ""  # pragma: no cover


class TTSProvider(ABC):
    """Text-to-speech provider interface."""

    @abstractmethod
    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize speech for the given text and return a float32 audio array."""
        ...

    @abstractmethod
    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        """Synthesize speech from a stream of text chunks, yielding audio arrays."""
        ...
        yield np.empty(0, dtype=np.float32)  # pragma: no cover

    def set_voice(self, voice: str) -> None:  # noqa: B027
        """Switch the active voice at runtime. No-op by default."""
