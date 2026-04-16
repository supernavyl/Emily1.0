"""Kokoro TTS provider — high-quality local text-to-speech."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger
from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = get_logger(__name__)
KOKORO_SAMPLE_RATE = 24000

# Strip paralinguistic markers that Kokoro can't render (e.g. Nicole voice)
_PARALINGUISTIC_RE = re.compile(
    r"\[(?:laughs?|sighs?|gasps?|whispers?|cries|yawns?|groans?|hums?"
    r"|chuckles?|giggles?|clears?\s*throat)\]",
    re.IGNORECASE,
)


class KokoroTTS(TTSProvider):
    """Text-to-speech via the ``kokoro`` package (local inference)."""

    def __init__(self, voice: str = "af_nicole", lang_code: str = "a") -> None:
        self._voice = voice
        self._lang_code = lang_code
        self._pipeline: object | None = None
        logger.info("KokoroTTS configured: voice=%s lang=%s", voice, lang_code)

    def _get_pipeline(self) -> object:
        """Lazy-load the Kokoro pipeline."""
        if self._pipeline is None:
            from kokoro import KPipeline  # type: ignore[import-untyped]

            logger.info("Loading Kokoro pipeline (lang_code=%s, device=cpu) ...", self._lang_code)
            self._pipeline = KPipeline(lang_code=self._lang_code, device="cpu")
            logger.info("Kokoro pipeline loaded on CPU.")
        return self._pipeline

    def set_voice(self, voice: str) -> None:
        """Switch the active voice at runtime."""
        self._voice = voice
        logger.info("KokoroTTS voice changed to %s", voice)

    def _get_emotional_speed(self) -> float:
        """Compute speech speed from the emotional state singleton (best-effort)."""
        try:
            from persona.emotional_state import get_emotional_state

            emo = get_emotional_state().state
            speed = 0.88 + 0.12 * emo.engagement + 0.06 * emo.enthusiasm
            return max(0.7, min(1.8, speed))
        except Exception:
            return 1.0

    def _synthesize_sync(self, text: str) -> np.ndarray:
        """Blocking synthesis — run in an executor."""
        text = _PARALINGUISTIC_RE.sub("", text).strip()
        if not text:
            return np.empty(0, dtype=np.float32)

        pipeline = self._get_pipeline()
        speed = self._get_emotional_speed()
        audio_parts: list[np.ndarray] = []

        for _graphemes, _phonemes, audio_chunk in pipeline(  # type: ignore[union-attr]
            text, voice=self._voice, speed=speed
        ):
            if audio_chunk is not None:
                audio_np = np.asarray(audio_chunk, dtype=np.float32)
                if audio_np.ndim > 1:
                    audio_np = audio_np.flatten()
                audio_parts.append(audio_np)

        if not audio_parts:
            logger.warning("Kokoro produced no audio for text: %s", text[:80])
            return np.empty(0, dtype=np.float32)

        return np.concatenate(audio_parts)

    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize speech for the given text and return float32 audio at 24 kHz."""
        if not text.strip():
            return np.empty(0, dtype=np.float32)

        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self._synthesize_sync, text)
        logger.debug("Kokoro synthesized %d samples for: %s", len(audio), text[:60])
        return audio

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        """Synthesize each incoming text chunk and yield audio arrays."""
        async for text in text_chunks:
            if not text.strip():
                continue
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio
