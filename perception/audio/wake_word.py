"""
Wake word detection for Emily using openWakeWord.

Implements a streaming wake word detector that:
- Processes audio chunks in real-time
- Detects "Hey Emily" (custom ONNX model) or a built-in model as fallback
- Emits detection events to the PerceptionBus

The detector runs continuously and is independent of VAD — wake word detection
happens on raw PCM before VAD gating.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger
from observability.metrics import WAKE_WORDS_DETECTED

if TYPE_CHECKING:
    from config import WakeWordConfig
    from perception.audio.stream import AudioChunk

log = get_logger(__name__)


@dataclass
class WakeWordEvent:
    """A wake word detection event."""

    keyword: str
    score: float
    timestamp: float
    audio_context: np.ndarray  # Short pre-roll audio before detection


class WakeWordDetector:
    """
    openWakeWord-based wake word detector.

    Processes audio chunks through the openWakeWord ONNX model and emits
    WakeWordEvent when the detection score exceeds the configured threshold.

    Falls back to a keyword-spotting stub when openWakeWord is not available.
    """

    _PRE_ROLL_MS = 500  # ms of audio to capture before detection event

    def __init__(self, config: WakeWordConfig) -> None:
        """
        Args:
            config: Wake word configuration.
        """
        self.config = config
        self._model: object | None = None
        self._use_oww = False
        self._pre_roll_buffer: list[np.ndarray] = []
        self._pre_roll_max_chunks = 20  # ~640ms at 16kHz/1024 chunk
        self._detection_cooldown_s = 2.0
        self._last_detection_time: float = 0.0

    async def load(self) -> None:
        """
        Load the openWakeWord model.

        If a custom model path is configured, loads that ONNX file.
        Otherwise uses the built-in "hey_emily" model if available,
        or falls back to a stub.

        Uses ``inference_framework`` from config (default "onnx") to avoid
        the tflite-runtime dependency, which has no Python 3.13 wheels.
        """
        try:
            from openwakeword.model import Model  # type: ignore[import-untyped]

            framework = getattr(self.config, "inference_framework", "onnx")

            if self.config.custom_model_path:
                self._model = await asyncio.to_thread(
                    Model,
                    wakeword_models=[self.config.custom_model_path],
                    inference_framework=framework,
                )
                log.info(
                    "wake_word_custom_model_loaded",
                    path=self.config.custom_model_path,
                    framework=framework,
                )
            else:
                self._model = await asyncio.to_thread(
                    Model,
                    inference_framework=framework,
                )
                log.info("wake_word_default_model_loaded", framework=framework)
            self._use_oww = True
        except ImportError:
            log.warning("openwakeword_not_installed", fallback="stub_detector")
            self._use_oww = False
        except Exception as exc:
            log.error("wake_word_load_error", error=str(exc))
            self._use_oww = False

    def _get_pre_roll_audio(self) -> np.ndarray:
        """Return the accumulated pre-roll audio buffer."""
        if not self._pre_roll_buffer:
            return np.zeros(1024, dtype=np.float32)
        return np.concatenate(self._pre_roll_buffer[-self._pre_roll_max_chunks :])

    def _update_pre_roll(self, audio: np.ndarray) -> None:
        """Add audio to the pre-roll ring buffer."""
        self._pre_roll_buffer.append(audio.copy())
        if len(self._pre_roll_buffer) > self._pre_roll_max_chunks:
            self._pre_roll_buffer.pop(0)

    def process(self, chunk: AudioChunk) -> WakeWordEvent | None:
        """
        Process a single audio chunk for wake word detection.

        Args:
            chunk: Raw audio chunk from the stream.

        Returns:
            WakeWordEvent if wake word detected, None otherwise.
        """
        self._update_pre_roll(chunk.data)

        # Enforce cooldown to prevent double-detections
        now = time.monotonic()
        if now - self._last_detection_time < self._detection_cooldown_s:
            return None

        score = self._score_chunk(chunk.data)

        if score >= self.config.threshold:
            self._last_detection_time = now
            WAKE_WORDS_DETECTED.inc()
            event = WakeWordEvent(
                keyword="hey_emily",
                score=score,
                timestamp=now,
                audio_context=self._get_pre_roll_audio(),
            )
            log.info("wake_word_detected", keyword=event.keyword, score=f"{score:.3f}")
            return event

        return None

    def _score_chunk(self, audio: np.ndarray) -> float:
        """
        Get the wake word detection score for an audio chunk.

        Args:
            audio: Float32 mono PCM, shape (chunk_size,).

        Returns:
            Detection confidence score in [0.0, 1.0].
        """
        if not self._use_oww or self._model is None:
            # Stub: never triggers (returns 0.0)
            return 0.0

        try:
            # openWakeWord expects audio as int16
            audio_int16 = (audio * 32768).astype(np.int16)
            prediction = self._model.predict(audio_int16)  # type: ignore[union-attr]
            # prediction is a dict of {model_name: score}
            if prediction:
                return float(max(prediction.values()))
            return 0.0
        except Exception as exc:
            log.debug("wake_word_score_error", error=str(exc))
            return 0.0

    async def process_async(self, chunk: AudioChunk) -> WakeWordEvent | None:
        """
        Async variant of process() — runs scoring in thread pool if model is heavy.

        Args:
            chunk: Raw audio chunk.

        Returns:
            WakeWordEvent if detected, else None.
        """
        if self._use_oww:
            return await asyncio.to_thread(self.process, chunk)
        return self.process(chunk)
