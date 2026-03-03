"""Faster-Whisper STT provider — local, CPU/GPU accelerated transcription."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.providers.base import STTProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# Best-effort tracing and metrics imports (not available in all environments)
try:
    from observability.metrics import STT_LATENCY
    from observability.tracing import async_trace_span
except ImportError:
    async_trace_span = None  # type: ignore[assignment]
    STT_LATENCY = None  # type: ignore[assignment]


class FasterWhisperSTT(STTProvider):
    """Transcription via the ``faster-whisper`` library (CTranslate2 backend)."""

    def __init__(
        self,
        model_size: str = "distil-large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
        beam_size: int = 5,
        language: str = "en",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._language = language
        self._model: object | None = None
        logger.info(
            "FasterWhisperSTT configured: model=%s device=%s",
            model_size,
            device,
        )

    def _get_model(self) -> object:
        """Lazy-load the Whisper model on first use."""
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            logger.info("Loading Faster-Whisper model '%s' ...", self._model_size)
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("Faster-Whisper model loaded.")
        return self._model  # type: ignore[return-value]

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe a complete audio buffer."""
        t0 = time.monotonic()
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, self._transcribe_sync, audio, sample_rate)
        elapsed = time.monotonic() - t0
        if STT_LATENCY is not None:
            STT_LATENCY.observe(elapsed)
        logger.debug("STT transcribe: %.3fs, %d chars", elapsed, len(text))
        return text

    def _transcribe_sync(self, audio: np.ndarray, sample_rate: int) -> str:
        """Blocking transcription — run in an executor."""
        model = self._get_model()
        # Ensure float32 mono
        audio_f32 = audio.astype(np.float32) if audio.dtype != np.float32 else audio

        # Resample to 16 kHz if needed
        if sample_rate != 16000:
            from scipy.signal import resample  # type: ignore[import-untyped]

            num_samples = int(len(audio_f32) * 16000 / sample_rate)
            audio_f32 = resample(audio_f32, num_samples).astype(np.float32)

        segments, info = model.transcribe(  # type: ignore[union-attr]
            audio_f32,
            beam_size=self._beam_size,
            language=self._language,
            vad_filter=True,
        )
        logger.debug("Detected language: %s (p=%.2f)", info.language, info.language_probability)

        parts: list[str] = []
        for segment in segments:
            parts.append(segment.text.strip())

        transcript = " ".join(parts).strip()
        logger.info("Transcript: %s", transcript)
        return transcript

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[np.ndarray],
        sample_rate: int,
    ) -> AsyncIterator[str]:
        """Collect streamed audio chunks, then transcribe the accumulated buffer.

        Faster-Whisper does not support true streaming, so we accumulate all
        chunks and perform a single transcription pass.
        """
        collected: list[np.ndarray] = []
        async for chunk in audio_chunks:
            collected.append(chunk)

        if not collected:
            return

        full_audio = np.concatenate(collected)
        transcript = await self.transcribe(full_audio, sample_rate)
        if transcript:
            yield transcript
