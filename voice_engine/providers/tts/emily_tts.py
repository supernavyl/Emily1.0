"""Emily TTS provider — wraps Emily's TTSManager behind VoiceEngine's TTSProvider."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

try:
    from observability.tracing import async_trace_span
except ImportError:
    async_trace_span = None  # type: ignore[assignment]


class EmilyTTSProvider(TTSProvider):
    """Wraps Emily's TTSManager (Kokoro/XTTS) behind the VoiceEngine TTSProvider.

    Reuses the already-loaded model instance so there's no double loading.
    Converts int16 PCM bytes (Emily's format) to float32 ndarray (VoiceEngine's format).
    """

    def __init__(self, tts_manager: object) -> None:
        self._tts_manager = tts_manager
        logger.info("EmilyTTSProvider initialised (wrapping TTSManager)")

    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize text and return float32 audio at 24 kHz."""
        _t0 = time.monotonic()
        if not text.strip():
            return np.empty(0, dtype=np.float32)

        # Read live emotional state for prosody adaptation (best-effort)
        emotional_state: dict[str, float] | None = None
        try:
            from persona.emotional_state import get_emotional_state

            emo = get_emotional_state()
            emotional_state = emo.state.to_dict()
        except Exception:
            pass

        pcm_parts: list[bytes] = []
        try:
            async for chunk in self._tts_manager.speak(  # type: ignore[union-attr]
                text,
                emotional_state=emotional_state,
            ):
                pcm_parts.append(chunk)
        except Exception:
            logger.exception("EmilyTTSProvider synthesis failed for: %s", text[:80])
            return np.empty(0, dtype=np.float32)

        if not pcm_parts:
            return np.empty(0, dtype=np.float32)

        # Emily's TTSManager yields raw int16 PCM at 24 kHz — convert to float32
        raw = b"".join(pcm_parts)
        int16_audio = np.frombuffer(raw, dtype=np.int16)
        float32_audio = int16_audio.astype(np.float32) / 32768.0
        logger.debug(
            "TTS synthesize: %.3fs, %d samples", time.monotonic() - _t0, len(float32_audio)
        )
        return float32_audio

    def set_voice(self, voice: str) -> None:
        """Forward voice switch to the underlying TTSManager."""
        if hasattr(self._tts_manager, "set_voice"):
            self._tts_manager.set_voice(voice)  # type: ignore[union-attr]
            logger.info("EmilyTTSProvider voice set to %s", voice)

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        """Stream synthesis — synthesize each text chunk independently."""
        async for text in text_chunks:
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio
