"""Edge TTS provider — free, high-quality Microsoft TTS via edge-tts."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

EDGE_TTS_SAMPLE_RATE = 24000


class EdgeTTSProvider(TTSProvider):
    """Text-to-speech via Microsoft Edge's online TTS service."""

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self._voice = voice
        logger.info("EdgeTTSProvider configured: voice=%s", voice)

    def set_voice(self, voice: str) -> None:
        """Switch the active Edge TTS voice at runtime."""
        self._voice = voice
        logger.info("EdgeTTSProvider voice changed to %s", voice)

    @staticmethod
    def _mp3_bytes_to_ndarray(mp3_bytes: bytes) -> np.ndarray:
        """Convert MP3 bytes to a float32 numpy array using soundfile."""
        import soundfile as sf  # type: ignore[import-untyped]

        buf = io.BytesIO(mp3_bytes)
        audio, _sample_rate = sf.read(buf, dtype="float32")
        # Ensure mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)

    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize speech and return a float32 audio array."""
        import edge_tts  # type: ignore[import-untyped]

        if not text.strip():
            return np.empty(0, dtype=np.float32)

        communicate = edge_tts.Communicate(text, self._voice)

        mp3_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_chunks.append(chunk["data"])

        if not mp3_chunks:
            logger.warning("Edge TTS produced no audio for: %s", text[:80])
            return np.empty(0, dtype=np.float32)

        mp3_data = b"".join(mp3_chunks)
        audio = self._mp3_bytes_to_ndarray(mp3_data)
        logger.debug("Edge TTS synthesized %d samples for: %s", len(audio), text[:60])
        return audio

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        """Synthesize each text chunk and yield audio arrays."""
        async for text in text_chunks:
            if not text.strip():
                continue
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio
