"""DeepFilterNet noise reduction wrapper for the audio pipeline.

Lazily loads the DeepFilterNet model on first use.  If the library is not
installed, all calls pass audio through unchanged — zero overhead.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class NoiseReducer:
    """Real-time noise reduction using DeepFilterNet.

    Usage::

        nr = NoiseReducer()
        clean = nr.process(audio_chunk, sample_rate=16000)
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._state: object | None = None
        self._available = False
        self._init_attempted = False

    def _lazy_init(self) -> None:
        """Attempt to load DeepFilterNet on first call."""
        if self._init_attempted:
            return
        self._init_attempted = True

        try:
            from df.enhance import enhance, init_df  # type: ignore[import-untyped]

            self._model, self._state, _ = init_df()
            self._enhance = enhance
            self._available = True
            logger.info("noise_reducer_loaded")
        except ImportError:
            logger.info("noise_reducer_unavailable (deepfilternet not installed — passthrough)")
        except Exception as exc:
            logger.warning("noise_reducer_init_failed: %s", exc)

    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Denoise an audio chunk.

        Args:
            audio: float32 mono audio array.
            sample_rate: Sample rate in Hz (must be 16000 or 48000 for DeepFilterNet).

        Returns:
            Denoised audio, or the original array if DeepFilterNet is unavailable.
        """
        self._lazy_init()
        if not self._available:
            return audio

        try:
            import torch

            # DeepFilterNet expects a torch tensor [channels, samples]
            tensor = torch.from_numpy(audio).unsqueeze(0)
            enhanced = self._enhance(self._model, self._state, tensor, sample_rate)
            return enhanced.squeeze(0).numpy().astype(np.float32)
        except Exception as exc:
            logger.debug("noise_reducer_process_error: %s", exc)
            return audio

    @property
    def available(self) -> bool:
        """True if DeepFilterNet is loaded and ready."""
        self._lazy_init()
        return self._available
