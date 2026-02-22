"""
Speech-to-Text engine for Emily using Faster-Whisper.

Wraps Faster-Whisper large-v3 for CUDA-accelerated transcription with:
- Word-level timestamps
- Confidence scores per segment
- Language auto-detection
- Async interface (inference runs in thread pool to avoid blocking the event loop)

Architecture:
    SpeechSegment → STT.transcribe() → TranscriptResult
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import numpy as np

from config import STTConfig
from observability.logger import get_logger
from observability.metrics import STT_ERRORS_TOTAL, STT_LATENCY
from observability.tracing import async_trace_span
from perception.audio.vad import SpeechSegment

log = get_logger(__name__)


@dataclass
class WordTimestamp:
    """A single word with its timing information."""

    word: str
    start: float
    end: float
    probability: float


@dataclass
class TranscriptResult:
    """Full transcription result from STT."""

    text: str
    language: str
    language_probability: float
    words: list[WordTimestamp] = field(default_factory=list)
    latency_ms: float = 0.0
    avg_log_prob: float = 0.0
    no_speech_prob: float = 0.0

    @property
    def is_likely_speech(self) -> bool:
        """True if the segment is likely actual speech (not noise)."""
        return self.no_speech_prob < 0.5 and len(self.text.strip()) > 0

    @property
    def confidence(self) -> float:
        """Overall confidence score, combining language and speech probability."""
        return (1.0 - self.no_speech_prob) * self.language_probability


class FasterWhisperSTT:
    """
    Async wrapper around Faster-Whisper for streaming STT.

    The WhisperModel is loaded once and reused across all transcriptions.
    CUDA float16 inference is used by default for maximum speed on the RTX 4090.
    """

    def __init__(self, config: STTConfig) -> None:
        """
        Args:
            config: STT configuration (model size, device, compute_type, etc.).
        """
        self.config = config
        self._model: object | None = None
        self._model_lock = asyncio.Lock()

    async def load(self) -> None:
        """
        Load the Faster-Whisper model.

        Falls back gracefully if faster_whisper is not installed or CUDA is
        unavailable, trying CPU float32 as a fallback.
        """
        async with self._model_lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel  # type: ignore[import-untyped]
                model = await asyncio.to_thread(
                    self._load_model, WhisperModel
                )
                self._model = model
                log.info(
                    "stt_model_loaded",
                    model=self.config.model,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                )
            except ImportError:
                log.error("faster_whisper_not_installed")
                raise
            except Exception as exc:
                if "cuda" in str(exc).lower():
                    log.warning("cuda_unavailable_falling_back_to_cpu", error=str(exc))
                    from faster_whisper import WhisperModel  # type: ignore[import-untyped]
                    model = await asyncio.to_thread(
                        self._load_model_cpu, WhisperModel
                    )
                    self._model = model
                else:
                    raise

    def _load_model(self, WhisperModel: type) -> object:
        """Synchronous model load for thread pool execution."""
        return WhisperModel(
            self.config.model,
            device=self.config.device,
            compute_type=self.config.compute_type,
        )

    def _load_model_cpu(self, WhisperModel: type) -> object:
        """CPU fallback model load."""
        return WhisperModel(
            self.config.model,
            device="cpu",
            compute_type="int8",
        )

    def _transcribe_sync(self, audio: np.ndarray) -> TranscriptResult:
        """
        Synchronous transcription — runs in thread pool.

        Args:
            audio: Float32 mono PCM audio at 16kHz.

        Returns:
            TranscriptResult with text, words, and metadata.
        """
        if self._model is None:
            raise RuntimeError("STT model not loaded. Call load() first.")

        t0 = time.monotonic()

        segments_iter, info = self._model.transcribe(  # type: ignore[union-attr]
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            word_timestamps=self.config.word_timestamps,
            vad_filter=False,  # We handle VAD ourselves
        )

        full_text_parts: list[str] = []
        all_words: list[WordTimestamp] = []
        total_avg_log_prob = 0.0
        total_no_speech_prob = 0.0
        n_segments = 0

        for segment in segments_iter:
            full_text_parts.append(segment.text)
            total_avg_log_prob += segment.avg_logprob
            total_no_speech_prob += segment.no_speech_prob
            n_segments += 1

            if self.config.word_timestamps and segment.words:
                for word in segment.words:
                    all_words.append(
                        WordTimestamp(
                            word=word.word,
                            start=word.start,
                            end=word.end,
                            probability=word.probability,
                        )
                    )

        latency_ms = (time.monotonic() - t0) * 1000.0

        return TranscriptResult(
            text=" ".join(full_text_parts).strip(),
            language=info.language,
            language_probability=info.language_probability,
            words=all_words,
            latency_ms=latency_ms,
            avg_log_prob=total_avg_log_prob / max(n_segments, 1),
            no_speech_prob=total_no_speech_prob / max(n_segments, 1),
        )

    async def transcribe(self, segment: SpeechSegment) -> TranscriptResult:
        """
        Transcribe a speech segment asynchronously.

        Args:
            segment: A VAD-gated speech segment.

        Returns:
            TranscriptResult with full transcription.

        Raises:
            RuntimeError: If the model has not been loaded.
        """
        async with async_trace_span("stt.transcribe", attributes={"duration_s": f"{segment.duration_s:.2f}"}):
            try:
                result = await asyncio.to_thread(
                    self._transcribe_sync, segment.audio
                )
                STT_LATENCY.observe(result.latency_ms / 1000.0)
                log.info(
                    "stt_transcribed",
                    text_preview=result.text[:80],
                    language=result.language,
                    latency_ms=f"{result.latency_ms:.0f}",
                    confidence=f"{result.confidence:.3f}",
                    no_speech_prob=f"{result.no_speech_prob:.3f}",
                )
                return result
            except Exception as exc:
                STT_ERRORS_TOTAL.inc()
                log.error("stt_transcription_error", error=str(exc))
                raise

    async def transcribe_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptResult:
        """
        Transcribe raw audio array directly (without a SpeechSegment wrapper).

        Args:
            audio: Float32 mono PCM audio.
            sample_rate: Audio sample rate. If not 16000, resampling is applied.

        Returns:
            TranscriptResult.
        """
        if sample_rate != 16000:
            audio = await asyncio.to_thread(self._resample, audio, sample_rate, 16000)

        from perception.audio.vad import SpeechSegment as _Seg
        segment = _Seg(
            audio=audio,
            sample_rate=16000,
            start_time=time.monotonic(),
            end_time=time.monotonic() + len(audio) / 16000,
            peak_probability=1.0,
        )
        return await self.transcribe(segment)

    @staticmethod
    def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
        """Simple linear resampling (placeholder — use resampy/librosa in production)."""
        ratio = target_rate / orig_rate
        n_samples = int(len(audio) * ratio)
        return np.interp(
            np.linspace(0, len(audio) - 1, n_samples),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)
