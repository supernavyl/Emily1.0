"""
Streaming STT with partial hypothesis tracking for Emily.

Extends Faster-Whisper with real-time partial hypothesis output:
- partial_hypothesis: updated every processing cycle (feeds turn detector)
- committed_words: locked-in words that won't change
- speculative_words: words that may be revised

Partial hypothesis enables:
- Emily to start planning response before user finishes
- Interrupt detection before sentence is complete
- Backchannel triggering on partial content
- Completion prediction
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np

from config import STTConfig
from observability.logger import get_logger
from perception.audio.stream import AudioChunk

log = get_logger(__name__)


@dataclass
class Word:
    """A single recognized word with timing and confidence."""

    text: str
    start: float
    end: float
    confidence: float
    is_committed: bool = False


@dataclass
class PartialHypothesis:
    """A streaming partial recognition result."""

    text: str
    words: list[Word]
    timestamp: float
    is_final: bool = False


@dataclass
class STTFrame:
    """Per-frame STT output for the conversation engine."""

    partial_text: str
    committed_words: list[Word]
    speculative_words: list[Word]
    word_confidences: list[float]
    language_detected: str
    emotion_markers: list[str]
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class FinalTranscript:
    """Committed final transcript at turn end."""

    text: str
    words: list[Word]
    language: str
    confidence: float
    duration_ms: float
    latency_ms: float


class StreamingSTTEngine:
    """
    Real-time streaming STT with partial hypothesis tracking.

    Wraps Faster-Whisper and adds a sliding window approach for
    continuous partial updates. Words above confidence threshold
    are committed (locked); others remain speculative.
    """

    _COMMIT_CONFIDENCE = 0.7
    _WINDOW_DURATION_S = 3.0
    _PROCESS_INTERVAL_S = 0.15
    _COMMIT_SKIP_THRESHOLD_S = 0.2
    _TARGET_SAMPLE_RATE = 16000

    def __init__(self, config: STTConfig) -> None:
        """
        Args:
            config: STT configuration.
        """
        self.config = config
        self._streaming_beam_size = getattr(config, "voice_fast_beam_size", 1)
        self._model: object | None = None
        self._audio_buffer: list[np.ndarray] = []
        self._buffer_duration_s: float = 0.0
        self._committed_words: list[Word] = []
        self._speculative_words: list[Word] = []
        self._committed_text: str = ""
        self._last_process_time: float = 0.0
        self._language: str = "en"
        self._running = False
        self._committed_count: int = 0
        self._last_committed_text: str = ""

    async def load(self) -> None:
        """Load the Faster-Whisper model."""
        try:
            from faster_whisper import WhisperModel

            def _load() -> object:
                try:
                    return WhisperModel(
                        self.config.model,
                        device=self.config.device,
                        compute_type=self.config.compute_type,
                    )
                except Exception:
                    return WhisperModel(
                        self.config.model,
                        device="cpu",
                        compute_type="int8",
                    )

            self._model = await asyncio.to_thread(_load)
            log.info("streaming_stt_loaded", model=self.config.model)
        except ImportError:
            log.error("faster_whisper_not_installed")

    async def process_chunk(self, chunk: AudioChunk) -> STTFrame | None:
        """
        Feed an audio chunk and get an updated partial hypothesis.

        Args:
            chunk: Audio chunk (any sample rate; downsampled to 16kHz internally).

        Returns:
            STTFrame with current partial/committed text, or None if
            not enough audio accumulated for processing.
        """
        data = chunk.data.copy()
        sr = chunk.sample_rate

        if sr != self._TARGET_SAMPLE_RATE:
            data = self._downsample(data, sr)
            sr = self._TARGET_SAMPLE_RATE

        self._audio_buffer.append(data)
        self._buffer_duration_s += len(data) / sr

        if self._buffer_duration_s > self._WINDOW_DURATION_S:
            excess = self._buffer_duration_s - self._WINDOW_DURATION_S
            while excess > 0 and self._audio_buffer:
                removed = self._audio_buffer.pop(0)
                excess -= len(removed) / sr
            self._buffer_duration_s = sum(
                len(a) / sr for a in self._audio_buffer
            )

        now = time.monotonic()
        if now - self._last_process_time < self._PROCESS_INTERVAL_S:
            return self._make_frame()

        if self._buffer_duration_s < 0.3:
            return None

        self._last_process_time = now
        result = await self._transcribe_buffer()
        if result is None:
            return self._make_frame()

        self._update_hypotheses(result)
        return self._make_frame()

    @staticmethod
    def _downsample(audio: np.ndarray, src_rate: int) -> np.ndarray:
        """Downsample audio to 16kHz using proper anti-aliased decimation."""
        factor = src_rate // 16000
        if factor > 1 and len(audio) >= factor * 2:
            from scipy.signal import decimate
            return decimate(audio, factor, ftype="fir", zero_phase=False).astype(
                np.float32
            )
        return audio

    async def _transcribe_buffer(self) -> dict | None:
        """Transcribe the current audio buffer (already at 16kHz)."""
        if self._model is None or not self._audio_buffer:
            return None

        audio = np.concatenate(self._audio_buffer)

        try:
            t0 = time.monotonic()
            segments_iter, info = await asyncio.to_thread(
                self._model.transcribe,
                audio,
                language=self.config.language,
                beam_size=self._streaming_beam_size,
                word_timestamps=True,
                vad_filter=False,
            )

            words = []
            text_parts = []
            for segment in segments_iter:
                text_parts.append(segment.text)
                if segment.words:
                    for w in segment.words:
                        words.append(Word(
                            text=w.word,
                            start=w.start,
                            end=w.end,
                            confidence=w.probability,
                        ))

            latency_ms = (time.monotonic() - t0) * 1000.0

            return {
                "text": " ".join(text_parts).strip(),
                "words": words,
                "language": info.language,
                "language_probability": info.language_probability,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            log.debug("streaming_stt_error", error=str(exc))
            return None

    def _update_hypotheses(self, result: dict) -> None:
        """Update committed and speculative word lists from new transcription."""
        self._language = result.get("language", "en")
        new_words = result.get("words", [])

        committed = []
        speculative = []

        for w in new_words:
            if w.confidence >= self._COMMIT_CONFIDENCE:
                w.is_committed = True
                committed.append(w)
            else:
                speculative.append(w)

        self._committed_words = committed
        self._speculative_words = speculative
        self._committed_text = " ".join(w.text for w in committed).strip()

    def _make_frame(self) -> STTFrame:
        """Build an STTFrame from current state."""
        all_words = self._committed_words + self._speculative_words
        return STTFrame(
            partial_text=self._committed_text + " " + " ".join(
                w.text for w in self._speculative_words
            ).strip(),
            committed_words=list(self._committed_words),
            speculative_words=list(self._speculative_words),
            word_confidences=[w.confidence for w in all_words],
            language_detected=self._language,
            emotion_markers=self._detect_emotion_markers(),
        )

    def _detect_emotion_markers(self) -> list[str]:
        """Detect disfluencies and emphasis from the partial text."""
        markers = []
        text = self._committed_text.lower()
        if any(h in text for h in ("uh", "um", "hmm")):
            markers.append("hesitation")
        if "!" in text:
            markers.append("emphasis")
        if "..." in text:
            markers.append("trailing_off")
        return markers

    async def commit_utterance(self) -> FinalTranscript:
        """
        Commit the current buffer as a final transcript.

        Called by the turn detector when a turn is confirmed.
        Skips re-transcription if a recent result (< 200ms old) already exists.

        Returns:
            FinalTranscript with all accumulated words.
        """
        time_since_last = time.monotonic() - self._last_process_time
        has_existing = bool(self._committed_words or self._speculative_words)

        if self._audio_buffer and (
            time_since_last >= self._COMMIT_SKIP_THRESHOLD_S or not has_existing
        ):
            result = await self._transcribe_buffer()
            if result:
                self._update_hypotheses(result)

        all_words = self._committed_words + self._speculative_words
        for w in all_words:
            w.is_committed = True

        final = FinalTranscript(
            text=" ".join(w.text for w in all_words).strip(),
            words=all_words,
            language=self._language,
            confidence=np.mean([w.confidence for w in all_words]) if all_words else 0.0,
            duration_ms=self._buffer_duration_s * 1000,
            latency_ms=0.0,
        )

        if final.text.strip():
            self._committed_count += 1
            self._last_committed_text = final.text.strip()

        self.reset()
        log.info("stt_utterance_committed", text=final.text[:80], words=len(final.words))
        return final

    def reset(self) -> None:
        """Clear all buffers for a new utterance."""
        self._audio_buffer.clear()
        self._buffer_duration_s = 0.0
        self._committed_words.clear()
        self._speculative_words.clear()
        self._committed_text = ""
