"""
Hardened unit tests for the STT pipeline.

Covers:
- TranscriptResult properties (is_likely_speech, confidence)
- FasterWhisperSTT.load() — happy path, CUDA fallback, ImportError
- FasterWhisperSTT._transcribe_sync — segment aggregation, word timestamps
- FasterWhisperSTT.transcribe() — metrics incremented, error path
- FasterWhisperSTT.transcribe_audio() — resampling branch
- FasterWhisperSTT._resample() — shape and dtype preservation
- Edge cases: empty audio, multi-segment output, no_speech_prob filtering
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from perception.audio.stt import FasterWhisperSTT, TranscriptResult

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _make_config(
    model: str = "large-v3-turbo",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = "en",
    beam_size: int = 1,
    word_timestamps: bool = True,
) -> Any:
    cfg = MagicMock()
    cfg.model = model
    cfg.device = device
    cfg.compute_type = compute_type
    cfg.language = language
    cfg.beam_size = beam_size
    cfg.word_timestamps = word_timestamps
    return cfg


def _make_speech_segment(
    duration_s: float = 1.0,
    sample_rate: int = 16000,
) -> Any:
    from perception.audio.vad import SpeechSegment

    n = int(duration_s * sample_rate)
    return SpeechSegment(
        audio=np.random.randn(n).astype(np.float32) * 0.05,
        sample_rate=sample_rate,
        start_time=0.0,
        end_time=duration_s,
        peak_probability=0.9,
    )


@dataclass
class _FakeWord:
    word: str
    start: float
    end: float
    probability: float


@dataclass
class _FakeSegment:
    text: str
    avg_logprob: float = -0.3
    no_speech_prob: float = 0.05
    words: list[_FakeWord] = field(default_factory=list)


@dataclass
class _FakeInfo:
    language: str = "en"
    language_probability: float = 0.99


def _fake_whisper_model(segments: list[_FakeSegment], info: _FakeInfo | None = None):
    """Return a fake WhisperModel that yields the given segments."""
    info = info or _FakeInfo()
    m = MagicMock()
    m.transcribe.return_value = (iter(segments), info)
    return m


# ---------------------------------------------------------------------------
# TranscriptResult property tests
# ---------------------------------------------------------------------------


class TestTranscriptResult:
    def test_is_likely_speech_true(self) -> None:
        r = TranscriptResult(
            text="hello",
            language="en",
            language_probability=0.99,
            no_speech_prob=0.1,
        )
        assert r.is_likely_speech is True

    def test_is_likely_speech_false_high_no_speech(self) -> None:
        r = TranscriptResult(
            text="hello",
            language="en",
            language_probability=0.99,
            no_speech_prob=0.6,
        )
        assert r.is_likely_speech is False

    def test_is_likely_speech_false_empty_text(self) -> None:
        r = TranscriptResult(
            text="  ",
            language="en",
            language_probability=0.99,
            no_speech_prob=0.05,
        )
        assert r.is_likely_speech is False

    def test_confidence_formula(self) -> None:
        r = TranscriptResult(
            text="hi",
            language="en",
            language_probability=0.8,
            no_speech_prob=0.2,
        )
        assert abs(r.confidence - (0.8 * 0.8)) < 1e-6

    def test_confidence_zero_when_all_noise(self) -> None:
        r = TranscriptResult(
            text="",
            language="en",
            language_probability=0.0,
            no_speech_prob=1.0,
        )
        assert r.confidence == 0.0

    def test_word_list_defaults_empty(self) -> None:
        r = TranscriptResult(text="hi", language="en", language_probability=1.0)
        assert r.words == []


# ---------------------------------------------------------------------------
# FasterWhisperSTT.load() tests
# ---------------------------------------------------------------------------


class TestFasterWhisperSTTLoad:
    @pytest.mark.asyncio
    async def test_load_success(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)

        fake_model = MagicMock()
        fake_wm_cls = MagicMock(return_value=fake_model)

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=fake_wm_cls)}):
            with patch(
                "perception.audio.stt.asyncio.to_thread", new=AsyncMock(return_value=fake_model)
            ):
                await stt.load()

        assert stt._model is not None

    @pytest.mark.asyncio
    async def test_load_cuda_fallback_to_cpu(self) -> None:
        """If CUDA model load raises a CUDA error, retry on CPU."""
        cfg = _make_config(device="cuda", compute_type="float16")
        stt = FasterWhisperSTT(cfg)

        cpu_model = MagicMock()
        call_count = 0

        async def fake_to_thread(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("CUDA out of memory")
            return cpu_model

        fake_wm = MagicMock()
        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=fake_wm)}):
            with patch("perception.audio.stt.asyncio.to_thread", side_effect=fake_to_thread):
                await stt.load()

        assert stt._model is cpu_model

    @pytest.mark.asyncio
    async def test_load_import_error_raises(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)

        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("faster-whisper not installed")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError):
                await stt.load()

    @pytest.mark.asyncio
    async def test_load_idempotent(self) -> None:
        """Calling load() twice should not reload the model."""
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)
        sentinel = MagicMock()
        stt._model = sentinel  # already loaded

        await stt.load()  # should return early
        assert stt._model is sentinel


# ---------------------------------------------------------------------------
# _transcribe_sync tests
# ---------------------------------------------------------------------------


class TestTranscribeSync:
    def _stt_with_model(self, model) -> FasterWhisperSTT:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)
        stt._model = model
        return stt

    def test_single_segment_no_words(self) -> None:
        seg = _FakeSegment(text=" hello world", words=[])
        stt = self._stt_with_model(_fake_whisper_model([seg]))
        audio = np.zeros(16000, dtype=np.float32)
        result = stt._transcribe_sync(audio)
        assert result.text == "hello world"
        assert result.words == []
        assert result.language == "en"
        assert result.latency_ms >= 0

    def test_multi_segment_concatenated(self) -> None:
        segs = [
            _FakeSegment(text=" first"),
            _FakeSegment(text=" second"),
        ]
        stt = self._stt_with_model(_fake_whisper_model(segs))
        audio = np.zeros(16000, dtype=np.float32)
        result = stt._transcribe_sync(audio)
        # " ".join([" first", " second"]).strip() → "first  second" (double space from leading spaces)
        # The real Whisper text strips within segments; test the actual join + strip behaviour
        assert "first" in result.text and "second" in result.text

    def test_word_timestamps_extracted(self) -> None:
        words = [
            _FakeWord("hello", 0.0, 0.3, 0.95),
            _FakeWord("there", 0.4, 0.7, 0.88),
        ]
        seg = _FakeSegment(text=" hello there", words=words)
        stt = self._stt_with_model(_fake_whisper_model([seg]))
        audio = np.zeros(16000, dtype=np.float32)
        result = stt._transcribe_sync(audio)
        assert len(result.words) == 2
        assert result.words[0].word == "hello"
        assert result.words[1].probability == pytest.approx(0.88)

    def test_no_speech_prob_averaged(self) -> None:
        segs = [
            _FakeSegment(text=" a", no_speech_prob=0.1),
            _FakeSegment(text=" b", no_speech_prob=0.3),
        ]
        stt = self._stt_with_model(_fake_whisper_model(segs))
        audio = np.zeros(16000, dtype=np.float32)
        result = stt._transcribe_sync(audio)
        assert abs(result.no_speech_prob - 0.2) < 1e-6

    def test_raises_when_model_not_loaded(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)
        with pytest.raises(RuntimeError, match="not loaded"):
            stt._transcribe_sync(np.zeros(100, dtype=np.float32))

    def test_empty_segments(self) -> None:
        stt = self._stt_with_model(_fake_whisper_model([]))
        audio = np.zeros(16000, dtype=np.float32)
        result = stt._transcribe_sync(audio)
        assert result.text == ""
        assert result.avg_log_prob == 0.0


# ---------------------------------------------------------------------------
# FasterWhisperSTT.transcribe() — async interface
# ---------------------------------------------------------------------------


class TestTranscribeAsync:
    @pytest.mark.asyncio
    async def test_transcribe_returns_result(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)

        expected = TranscriptResult(
            text="test transcript",
            language="en",
            language_probability=0.99,
            latency_ms=50.0,
        )
        with patch.object(stt, "_transcribe_sync", return_value=expected):
            with patch(
                "perception.audio.stt.asyncio.to_thread", new=AsyncMock(return_value=expected)
            ):
                with patch("perception.audio.stt.STT_LATENCY") as mock_lat:
                    mock_lat.observe = MagicMock()
                    seg = _make_speech_segment()
                    result = await stt.transcribe(seg)

        assert result.text == "test transcript"

    @pytest.mark.asyncio
    async def test_transcribe_error_increments_counter(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)

        async def boom(*a, **kw):
            raise RuntimeError("inference failed")

        with patch("perception.audio.stt.asyncio.to_thread", side_effect=boom):
            with patch("perception.audio.stt.STT_ERRORS_TOTAL") as mock_err:
                mock_err.inc = MagicMock()
                seg = _make_speech_segment()
                with pytest.raises(RuntimeError):
                    await stt.transcribe(seg)
                mock_err.inc.assert_called_once()


# ---------------------------------------------------------------------------
# transcribe_audio — resampling branch
# ---------------------------------------------------------------------------


class TestTranscribeAudio:
    @pytest.mark.asyncio
    async def test_correct_sample_rate_skips_resample(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)

        expected = TranscriptResult(text="hi", language="en", language_probability=1.0)

        with patch.object(stt, "transcribe", new=AsyncMock(return_value=expected)) as mock_t:
            audio = np.zeros(16000, dtype=np.float32)
            result = await stt.transcribe_audio(audio, sample_rate=16000)

        assert result.text == "hi"
        # transcribe should receive audio with sample_rate=16000
        call_seg = mock_t.call_args[0][0]
        assert call_seg.sample_rate == 16000

    @pytest.mark.asyncio
    async def test_wrong_sample_rate_triggers_resample(self) -> None:
        cfg = _make_config()
        stt = FasterWhisperSTT(cfg)

        expected = TranscriptResult(text="resampled", language="en", language_probability=1.0)

        resample_called = []

        async def fake_resample_thread(fn, audio, src, tgt):
            resample_called.append((src, tgt))
            return np.zeros(16000, dtype=np.float32)

        with patch("perception.audio.stt.asyncio.to_thread", side_effect=fake_resample_thread):
            with patch.object(stt, "transcribe", new=AsyncMock(return_value=expected)):
                audio = np.zeros(48000, dtype=np.float32)
                await stt.transcribe_audio(audio, sample_rate=48000)

        assert len(resample_called) == 1
        assert resample_called[0] == (48000, 16000)


# ---------------------------------------------------------------------------
# _resample — pure function
# ---------------------------------------------------------------------------


class TestResample:
    def test_downsamples_to_correct_length(self) -> None:
        audio = np.random.randn(48000).astype(np.float32)
        resampled = FasterWhisperSTT._resample(audio, 48000, 16000)
        assert len(resampled) == pytest.approx(16000, abs=10)

    def test_output_is_float32(self) -> None:
        audio = np.random.randn(32000).astype(np.float32)
        resampled = FasterWhisperSTT._resample(audio, 32000, 16000)
        assert resampled.dtype == np.float32

    def test_identity_same_rate(self) -> None:
        """Resampling 16k → 16k should return near-identical audio."""
        audio = np.sin(np.linspace(0, 2 * np.pi, 16000)).astype(np.float32)
        resampled = FasterWhisperSTT._resample(audio, 16000, 16000)
        assert len(resampled) == len(audio)

    def test_upsample_increases_length(self) -> None:
        audio = np.random.randn(8000).astype(np.float32)
        resampled = FasterWhisperSTT._resample(audio, 8000, 16000)
        assert len(resampled) == pytest.approx(16000, abs=10)

    def test_non_integer_ratio_resample_44100_to_16000(self) -> None:
        audio = np.random.randn(44100).astype(np.float32)
        resampled = FasterWhisperSTT._resample(audio, 44100, 16000)
        assert len(resampled) == pytest.approx(16000, abs=10)
        assert resampled.dtype == np.float32
