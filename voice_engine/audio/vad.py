"""Silero VAD — voice activity detection for filtering speech from silence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import torch

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

VAD_FRAME_SIZE = 512  # Silero expects 512 samples at 16 kHz (32 ms)


class SileroVAD:
    """Voice activity detector powered by the Silero VAD model."""

    def __init__(self, threshold: float = 0.5) -> None:
        self._threshold = threshold
        self._model: torch.jit.ScriptModule | None = None
        logger.info("SileroVAD configured: threshold=%.2f", threshold)

    def _get_model(self) -> torch.jit.ScriptModule:
        """Lazy-load the Silero VAD model."""
        if self._model is None:
            from silero_vad import load_silero_vad  # type: ignore[import-untyped]

            logger.info("Loading Silero VAD model ...")
            self._model = load_silero_vad()
            logger.info("Silero VAD model loaded.")
        return self._model

    def reset(self) -> None:
        """Reset the model's internal hidden state between utterances."""
        model = self._get_model()
        model.reset_states()  # type: ignore[operator]
        logger.debug("VAD state reset.")

    def is_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        """Return True if the given audio frame contains speech.

        The chunk must be exactly ``VAD_FRAME_SIZE`` samples of float32 mono audio.
        """
        try:
            model = self._get_model()

            audio_f32 = (
                audio_chunk.astype(np.float32) if audio_chunk.dtype != np.float32 else audio_chunk
            )
            tensor = torch.from_numpy(audio_f32)

            confidence: float = model(tensor, sample_rate).item()  # type: ignore[operator]
            return confidence >= self._threshold
        except Exception:
            logger.exception("VAD inference failed — defaulting to no-speech")
            return False

    async def process_stream(
        self,
        audio_stream: AsyncIterator[np.ndarray],
    ) -> AsyncIterator[np.ndarray]:
        """Filter an audio stream, yielding only frames classified as speech.

        Incoming chunks are rebuffered into ``VAD_FRAME_SIZE``-sample frames
        before classification.
        """
        buffer = np.empty(0, dtype=np.float32)

        async for chunk in audio_stream:
            buffer = np.concatenate([buffer, chunk.astype(np.float32)])

            while len(buffer) >= VAD_FRAME_SIZE:
                frame = buffer[:VAD_FRAME_SIZE]
                buffer = buffer[VAD_FRAME_SIZE:]

                if self.is_speech(frame):
                    yield frame
