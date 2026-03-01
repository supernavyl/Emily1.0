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
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger

if TYPE_CHECKING:
    from config import STTConfig
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

    _TARGET_SAMPLE_RATE = 16000

    def __init__(self, config: STTConfig) -> None:
        """
        Args:
            config: STT configuration.
        """
        self.config = config
        if getattr(config, "profile", "fast") == "accurate":
            self._streaming_beam_size = getattr(config, "voice_accurate_beam_size", 3)
        else:
            self._streaming_beam_size = getattr(config, "voice_fast_beam_size", 1)

        self._window_duration_s = getattr(config, "streaming_window_duration_s", 3.0)
        self._process_interval_s = getattr(config, "streaming_process_interval_s", 0.15)
        self._min_buffer_s = getattr(config, "streaming_min_buffer_s", 0.3)
        self._commit_skip_threshold_s = getattr(config, "streaming_commit_skip_threshold_s", 0.2)
        self._rms_gate_threshold = getattr(config, "streaming_rms_gate_threshold", 0.006)
        self._commit_confidence = getattr(config, "streaming_commit_confidence", 0.7)
        self._reject_low_confidence = getattr(config, "streaming_reject_low_confidence", 0.65)
        self._min_final_words = getattr(config, "streaming_min_final_words", 3)
        self._min_unique_ratio = getattr(config, "streaming_min_unique_ratio", 0.45)
        self._max_repeat_ratio = getattr(config, "streaming_max_repeat_ratio", 0.6)
        self._short_utterance_confidence = getattr(
            config, "streaming_short_utterance_confidence", 0.8
        )

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

        if self._buffer_duration_s > self._window_duration_s:
            excess = self._buffer_duration_s - self._window_duration_s
            while excess > 0 and self._audio_buffer:
                removed = self._audio_buffer.pop(0)
                excess -= len(removed) / sr
            self._buffer_duration_s = sum(len(a) / sr for a in self._audio_buffer)

        now = time.monotonic()
        if now - self._last_process_time < self._process_interval_s:
            return self._make_frame()

        if self._buffer_duration_s < self._min_buffer_s:
            return None

        # Energy gate: skip transcription when buffer is near-silent.
        # Configurable threshold allows higher capture in quiet/far-field setups.
        if self._audio_buffer:
            combined = np.concatenate(self._audio_buffer)
            rms = float(np.sqrt(np.mean(combined**2)))
            if rms < self._rms_gate_threshold:
                return self._make_frame()

        self._last_process_time = now
        result = await self._transcribe_buffer()
        if result is None:
            return self._make_frame()

        self._update_hypotheses(result)
        return self._make_frame()

    @staticmethod
    def _downsample(audio: np.ndarray, src_rate: int) -> np.ndarray:
        """
        Resample audio to 16kHz with polyphase FIR filtering.

        Handles non-integer source rates (for example 44.1kHz) without
        introducing systematic timing drift from integer decimation.
        """
        if src_rate == StreamingSTTEngine._TARGET_SAMPLE_RATE:
            return audio.astype(np.float32, copy=False)

        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(src_rate, StreamingSTTEngine._TARGET_SAMPLE_RATE)
        return resample_poly(
            audio,
            StreamingSTTEngine._TARGET_SAMPLE_RATE // g,
            src_rate // g,
        ).astype(np.float32)

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
                vad_filter=getattr(self.config, "use_whisper_vad", False),
                vad_parameters={
                    "threshold": getattr(self.config, "whisper_vad_threshold", 0.1),
                    "min_speech_duration_ms": getattr(self.config, "whisper_vad_min_speech_ms", 0),
                    "min_silence_duration_ms": getattr(
                        self.config, "whisper_vad_min_silence_ms", 300
                    ),
                },
                no_speech_threshold=getattr(self.config, "no_speech_threshold", 0.7),
            )

            words = []
            text_parts = []
            for segment in segments_iter:
                # Skip segments Whisper itself flags as likely non-speech.
                if getattr(segment, "no_speech_prob", 0.0) > getattr(
                    self.config, "no_speech_threshold", 0.7
                ):
                    log.debug(
                        "stt_segment_rejected_no_speech",
                        text=segment.text.strip(),
                        no_speech_prob=f"{segment.no_speech_prob:.2f}",
                    )
                    continue
                text_parts.append(segment.text)
                if segment.words:
                    for w in segment.words:
                        words.append(
                            Word(
                                text=w.word,
                                start=w.start,
                                end=w.end,
                                confidence=w.probability,
                            )
                        )

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
            if w.confidence >= self._commit_confidence:
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
            partial_text=self._committed_text
            + " "
            + " ".join(w.text for w in self._speculative_words).strip(),
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
            time_since_last >= self._commit_skip_threshold_s or not has_existing
        ):
            result = await self._transcribe_buffer()
            if result:
                self._update_hypotheses(result)

        all_words = self._committed_words + self._speculative_words
        for w in all_words:
            w.is_committed = True

        avg_confidence = float(np.mean([w.confidence for w in all_words])) if all_words else 0.0

        # Reject low-confidence transcripts as Whisper hallucinations.
        # Real speech with beam_size=1 typically scores > 0.75 per word.
        if all_words and avg_confidence < self._reject_low_confidence:
            return self._reject_final_transcript("low_confidence", all_words, avg_confidence)

        quality_reason = self._quality_rejection_reason(all_words, avg_confidence)
        if quality_reason is not None:
            return self._reject_final_transcript(quality_reason, all_words, avg_confidence)

        final = FinalTranscript(
            text=" ".join(w.text for w in all_words).strip(),
            words=all_words,
            language=self._language,
            confidence=avg_confidence,
            duration_ms=self._buffer_duration_s * 1000,
            latency_ms=0.0,
        )

        if final.text.strip():
            self._committed_count += 1
            self._last_committed_text = final.text.strip()

        self.reset()
        log.info("stt_utterance_committed", text=final.text[:80], words=len(final.words))
        return final

    @staticmethod
    def _normalize_token(token: str) -> str:
        """Lowercase and strip punctuation to compare lexical diversity."""
        return re.sub(r"[^a-z0-9']+", "", token.lower())

    def _quality_rejection_reason(
        self,
        words: list[Word],
        avg_confidence: float,
    ) -> str | None:
        """Return a rejection reason when final words look like fragmented noise."""
        if not words:
            return None

        tokens = [self._normalize_token(w.text) for w in words]
        tokens = [t for t in tokens if t]
        if not tokens:
            return "fragmented"

        token_count = len(tokens)
        unique_ratio = len(set(tokens)) / token_count
        max_repeat_ratio = max(tokens.count(t) for t in set(tokens)) / token_count

        if (
            token_count < self._min_final_words
            and avg_confidence < self._short_utterance_confidence
        ):
            return "fragmented"
        if unique_ratio < self._min_unique_ratio:
            return "repetitive"
        if max_repeat_ratio > self._max_repeat_ratio:
            return "repetitive"
        return None

    def _reject_final_transcript(
        self,
        reason: str,
        words: list[Word],
        avg_confidence: float,
    ) -> FinalTranscript:
        """Reset state and emit a consistent empty transcript rejection."""
        text_preview = " ".join(w.text for w in words)[:80]
        log.debug(
            "stt_utterance_rejected",
            reason=reason,
            text=text_preview,
            words=len(words),
            avg_confidence=f"{avg_confidence:.2f}",
        )
        duration_ms = self._buffer_duration_s * 1000
        self.reset()
        return FinalTranscript(
            text="",
            words=[],
            language=self._language,
            confidence=0.0,
            duration_ms=duration_ms,
            latency_ms=0.0,
        )

    def reset(self) -> None:
        """Clear all buffers for a new utterance."""
        self._audio_buffer.clear()
        self._buffer_duration_s = 0.0
        self._committed_words.clear()
        self._speculative_words.clear()
        self._committed_text = ""
