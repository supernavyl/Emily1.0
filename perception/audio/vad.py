"""
Voice Activity Detection for Emily using Silero VAD.

Implements a streaming VAD with:
- Silero VAD ONNX model for speech probability estimation
- Adaptive noise-floor threshold learning
- Speech segment boundary detection with configurable min/max durations
- Hysteresis to avoid rapid state flipping

Architecture:
    AudioChunk → VAD.process() → SpeechSegment | None

Each AudioChunk is classified as speech or non-speech.
When a speech segment ends (silence detected), a complete SpeechSegment
is emitted containing all accumulated audio for that utterance.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger

if TYPE_CHECKING:
    from config import VADConfig
    from perception.audio.stream import AudioChunk

log = get_logger(__name__)


class VADState(Enum):
    SILENCE = auto()
    SPEECH = auto()
    ENDING = auto()  # speech detected but waiting for silence confirmation


@dataclass
class SpeechSegment:
    """A complete speech segment extracted by VAD."""

    audio: np.ndarray
    sample_rate: int
    start_time: float
    end_time: float
    peak_probability: float

    @property
    def duration_ms(self) -> float:
        """Duration of the speech segment in milliseconds."""
        return (self.end_time - self.start_time) * 1000.0

    @property
    def duration_s(self) -> float:
        """Duration in seconds."""
        return self.end_time - self.start_time


class SileroVAD:
    """
    Silero VAD wrapper with adaptive threshold.

    Loads the Silero VAD ONNX model and processes audio chunks in real-time.
    Falls back to an energy-based VAD if Silero is unavailable.
    """

    _SILERO_SAMPLE_RATE = 16000

    def __init__(self, config: VADConfig) -> None:
        """
        Args:
            config: VAD configuration parameters.
        """
        self.config = config
        self._model: object | None = None
        self._state = VADState.SILENCE
        self._speech_buffer: list[np.ndarray] = []
        self._silence_chunks = 0
        self._speech_chunks = 0
        self._segment_start: float = 0.0
        self._noise_floor: float = 0.001  # Initial estimate, adapts over time
        self._use_silero = False

        # Threshold adapts upward from the noise floor to prevent false triggers
        self._effective_threshold = config.threshold

    async def load(self) -> None:
        """
        Load the Silero VAD model.

        Falls back to energy-based VAD if silero_vad is not installed.
        """
        try:
            from silero_vad import load_silero_vad  # type: ignore[import-untyped]

            self._model = await asyncio.to_thread(load_silero_vad)
            self._use_silero = True
            log.info("silero_vad_loaded")
        except ImportError:
            log.warning("silero_vad_unavailable", fallback="energy_vad")
            self._use_silero = False

    def _estimate_speech_probability_energy(self, audio: np.ndarray) -> float:
        """Energy-based speech probability (fallback for when Silero unavailable)."""
        rms = float(np.sqrt(np.mean(audio**2)))
        # Simple sigmoid-like mapping from RMS to probability
        threshold = self._noise_floor * 3
        if rms < threshold:
            return 0.1
        elif rms > threshold * 5:
            return 0.95
        else:
            return 0.1 + 0.85 * (rms - threshold) / (threshold * 4)

    def _get_speech_probability(self, audio: np.ndarray) -> float:
        """
        Get speech probability for an audio chunk.

        Args:
            audio: Float32 PCM audio, mono, 16kHz.

        Returns:
            Speech probability in [0.0, 1.0].
        """
        if self._use_silero and self._model is not None:
            try:
                import torch  # type: ignore[import-untyped]

                tensor = torch.FloatTensor(audio)
                # Synchronous call is safe: Silero runs on ~512-sample tensors
                # and completes in <1ms even on CPU.
                prob = float(self._model(tensor, self._SILERO_SAMPLE_RATE).item())
                return prob
            except Exception as exc:
                log.debug("silero_inference_error", error=str(exc))
                return self._estimate_speech_probability_energy(audio)
        return self._estimate_speech_probability_energy(audio)

    def _update_noise_floor(self, audio: np.ndarray) -> None:
        """
        Adaptively update the estimated noise floor using EMA.

        Only updates during confirmed silence periods.
        """
        if self._state == VADState.SILENCE:
            rms = float(np.sqrt(np.mean(audio**2)))
            alpha = self.config.noise_floor_update_rate
            self._noise_floor = (1 - alpha) * self._noise_floor + alpha * rms
            # Effective threshold stays above noise floor with margin
            self._effective_threshold = max(
                self.config.threshold,
                self._noise_floor * 4.0,
            )

    def _chunks_to_ms(self, n_chunks: int, chunk_size: int, sample_rate: int) -> float:
        """Convert chunk count to milliseconds."""
        return (n_chunks * chunk_size / sample_rate) * 1000.0

    def process(self, chunk: AudioChunk) -> SpeechSegment | None:
        """
        Process a single audio chunk through the VAD.

        Args:
            chunk: Raw audio chunk from the capture stream.

        Returns:
            A completed SpeechSegment if an utterance just ended, else None.
        """
        prob = self._get_speech_probability(chunk.data)
        self._update_noise_floor(chunk.data)

        chunk_ms = chunk.duration_ms
        min_silence_chunks = max(1, int(self.config.min_silence_ms / chunk_ms))
        min_speech_chunks = max(1, int(self.config.min_speech_ms / chunk_ms))

        if self._state == VADState.SILENCE:
            if prob > self._effective_threshold:
                self._speech_chunks += 1
                self._speech_buffer.append(chunk.data.copy())
                if self._speech_chunks >= min_speech_chunks:
                    self._state = VADState.SPEECH
                    self._segment_start = chunk.timestamp - (self._speech_chunks * chunk_ms / 1000)
                    log.debug(
                        "vad_speech_start",
                        prob=f"{prob:.3f}",
                        threshold=f"{self._effective_threshold:.3f}",
                    )
            else:
                self._speech_chunks = 0
                self._speech_buffer.clear()

        elif self._state == VADState.SPEECH:
            self._speech_buffer.append(chunk.data.copy())
            if prob <= self._effective_threshold:
                self._silence_chunks += 1
                self._state = VADState.ENDING
            else:
                self._silence_chunks = 0

        elif self._state == VADState.ENDING:
            self._speech_buffer.append(chunk.data.copy())
            if prob > self._effective_threshold:
                # Speech resumed
                self._silence_chunks = 0
                self._state = VADState.SPEECH
            else:
                self._silence_chunks += 1
                if self._silence_chunks >= min_silence_chunks:
                    # Speech segment complete
                    segment = SpeechSegment(
                        audio=np.concatenate(self._speech_buffer),
                        sample_rate=chunk.sample_rate,
                        start_time=self._segment_start,
                        end_time=chunk.timestamp,
                        peak_probability=prob,
                    )
                    log.info(
                        "vad_speech_segment",
                        duration_ms=f"{segment.duration_ms:.0f}",
                        samples=len(segment.audio),
                    )
                    self._reset()
                    return segment

        return None

    def _reset(self) -> None:
        """Reset internal state after completing a speech segment."""
        self._state = VADState.SILENCE
        self._speech_buffer = []
        self._silence_chunks = 0
        self._speech_chunks = 0
        self._segment_start = 0.0

    @property
    def state(self) -> VADState:
        """Current VAD state."""
        return self._state

    @property
    def noise_floor(self) -> float:
        """Current estimated noise floor RMS."""
        return self._noise_floor
