"""Chatterbox TTS provider — expressive speech with emotion exaggeration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

CHATTERBOX_SAMPLE_RATE = 24000


class ChatterboxTTS(TTSProvider):
    """Text-to-speech via Chatterbox (local inference, emotion-aware).

    Chatterbox supports an ``exaggeration`` dial (0.0–1.0) that amplifies
    emotional expression and paralinguistic tags like ``[laughs]``, ``[sighs]``.
    The Turbo variant uses ~1GB VRAM.
    """

    def __init__(
        self,
        exaggeration: float = 0.5,
        ref_audio_path: str | None = None,
    ) -> None:
        self._exaggeration = max(0.0, min(1.0, exaggeration))
        self._ref_audio_path = ref_audio_path
        self._model: object | None = None
        logger.info(
            "ChatterboxTTS configured: exaggeration=%.2f ref_audio=%s",
            self._exaggeration,
            ref_audio_path,
        )

    def _get_model(self) -> object:
        """Lazy-load the Chatterbox model on first use."""
        if self._model is None:
            from chatterbox.tts import ChatterboxTTS as CBModel  # type: ignore[import-untyped]

            logger.info("Loading Chatterbox model on CUDA ...")
            self._model = CBModel.from_pretrained("cuda")
            logger.info("Chatterbox model loaded.")
        return self._model

    def set_voice(self, voice: str) -> None:
        """Set reference audio path for voice cloning."""
        self._ref_audio_path = voice
        logger.info("ChatterboxTTS ref audio set to %s", voice)

    def _get_exaggeration(self) -> float:
        """Map emotional state to exaggeration level (best-effort)."""
        try:
            from persona.emotional_state import get_emotional_state

            emo = get_emotional_state().state
            # Higher enthusiasm/engagement → more exaggeration
            # Higher concern → moderate boost (expressive worry)
            exag = 0.2 + 0.35 * emo.enthusiasm + 0.25 * emo.engagement + 0.15 * emo.concern
            return max(0.0, min(1.0, exag))
        except Exception:
            return self._exaggeration

    def _synthesize_sync(self, text: str) -> np.ndarray:
        """Blocking synthesis — run in an executor."""
        model = self._get_model()
        exag = self._get_exaggeration()

        kwargs: dict = {"text": text, "exaggeration": exag}
        if self._ref_audio_path:
            kwargs["audio_prompt_path"] = self._ref_audio_path

        wav = model.generate(**kwargs)  # type: ignore[union-attr]

        # Chatterbox returns a torch Tensor — convert to float32 ndarray
        audio = np.asarray(wav.squeeze().cpu(), dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.flatten()

        logger.debug(
            "Chatterbox synthesized %d samples (exag=%.2f) for: %s",
            len(audio),
            exag,
            text[:60],
        )
        return audio

    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize speech and return float32 audio at 24 kHz."""
        if not text.strip():
            return np.empty(0, dtype=np.float32)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)

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
