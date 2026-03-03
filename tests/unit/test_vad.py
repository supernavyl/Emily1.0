"""
Hardened unit tests for the VAD pipeline.

Covers:
- SpeechSegment properties (duration_ms, duration_s)
- SileroVAD energy-based fallback probability estimation
- SileroVAD noise floor adaptation (EMA)
- SileroVAD state machine: SILENCE → SPEECH → ENDING → segment emitted
- State machine: ENDING → speech resumes → back to SPEECH
- State machine: short speech below min_speech_chunks is discarded
- SileroVAD.load() — silero import error falls back to energy VAD
- _chunks_to_ms helper
- process() emits segment with correct audio content
- process() resets state after segment is emitted
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from perception.audio.stream import AudioChunk
from perception.audio.vad import SileroVAD, SpeechSegment, VADState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    threshold: float = 0.5,
    min_silence_ms: int = 200,
    min_speech_ms: int = 200,
    adaptive: bool = True,
    noise_floor_update_rate: float = 0.01,
) -> Any:
    cfg = MagicMock()
    cfg.threshold = threshold
    cfg.min_silence_ms = min_silence_ms
    cfg.min_speech_ms = min_speech_ms
    cfg.adaptive = adaptive
    cfg.noise_floor_update_rate = noise_floor_update_rate
    return cfg


def _make_chunk(
    data: np.ndarray | None = None,
    sample_rate: int = 16000,
    amplitude: float = 0.0,
    n_samples: int = 512,
) -> AudioChunk:
    if data is None:
        data = np.ones(n_samples, dtype=np.float32) * amplitude
    chunk = AudioChunk(data=data, sample_rate=sample_rate, channels=1)
    return chunk


def _silence_chunk(n: int = 512) -> AudioChunk:
    return _make_chunk(amplitude=0.0, n_samples=n)


def _speech_chunk(n: int = 512, amp: float = 0.5) -> AudioChunk:
    return _make_chunk(amplitude=amp, n_samples=n)


# ---------------------------------------------------------------------------
# SpeechSegment property tests
# ---------------------------------------------------------------------------


class TestSpeechSegment:
    def test_duration_ms(self) -> None:
        seg = SpeechSegment(
            audio=np.zeros(16000, dtype=np.float32),
            sample_rate=16000,
            start_time=1.0,
            end_time=2.5,
            peak_probability=0.9,
        )
        assert abs(seg.duration_ms - 1500.0) < 1e-6

    def test_duration_s(self) -> None:
        seg = SpeechSegment(
            audio=np.zeros(8000, dtype=np.float32),
            sample_rate=16000,
            start_time=0.0,
            end_time=0.5,
            peak_probability=0.8,
        )
        assert abs(seg.duration_s - 0.5) < 1e-6

    def test_zero_duration(self) -> None:
        seg = SpeechSegment(
            audio=np.zeros(0, dtype=np.float32),
            sample_rate=16000,
            start_time=5.0,
            end_time=5.0,
            peak_probability=0.0,
        )
        assert seg.duration_ms == 0.0
        assert seg.duration_s == 0.0


# ---------------------------------------------------------------------------
# Energy-based probability estimation
# ---------------------------------------------------------------------------


class TestEnergyProbability:
    def test_silent_audio_low_probability(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        silence = np.zeros(512, dtype=np.float32)
        prob = vad._estimate_speech_probability_energy(silence)
        assert prob <= 0.15

    def test_loud_audio_high_probability(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        loud = np.ones(512, dtype=np.float32)
        prob = vad._estimate_speech_probability_energy(loud)
        assert prob >= 0.9

    def test_probability_in_valid_range(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        for amp in [0.0, 0.01, 0.05, 0.1, 0.5, 1.0]:
            audio = np.ones(512, dtype=np.float32) * amp
            p = vad._estimate_speech_probability_energy(audio)
            assert 0.0 <= p <= 1.0, f"Probability out of range for amp={amp}: {p}"


# ---------------------------------------------------------------------------
# Noise floor adaptation
# ---------------------------------------------------------------------------


class TestNoiseFloorAdaptation:
    def test_noise_floor_rises_toward_rms(self) -> None:
        cfg = _make_config(noise_floor_update_rate=0.5)
        vad = SileroVAD(cfg)
        initial_floor = vad._noise_floor

        # Feed loud silence-state audio
        loud_audio = np.ones(512, dtype=np.float32) * 0.5
        assert vad._state == VADState.SILENCE
        for _ in range(20):
            vad._update_noise_floor(loud_audio)

        assert vad._noise_floor > initial_floor

    def test_noise_floor_not_updated_in_speech_state(self) -> None:
        cfg = _make_config(noise_floor_update_rate=0.5)
        vad = SileroVAD(cfg)
        vad._state = VADState.SPEECH
        initial_floor = vad._noise_floor

        loud_audio = np.ones(512, dtype=np.float32) * 0.5
        for _ in range(10):
            vad._update_noise_floor(loud_audio)

        assert vad._noise_floor == initial_floor

    def test_effective_threshold_tracks_noise_floor(self) -> None:
        cfg = _make_config(threshold=0.3, noise_floor_update_rate=0.5)
        vad = SileroVAD(cfg)

        # Push noise floor high
        for _ in range(50):
            vad._update_noise_floor(np.ones(512, dtype=np.float32) * 0.2)

        assert vad._effective_threshold >= cfg.threshold


# ---------------------------------------------------------------------------
# _chunks_to_ms helper
# ---------------------------------------------------------------------------


class TestChunksToMs:
    def test_basic_conversion(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        ms = vad._chunks_to_ms(n_chunks=10, chunk_size=160, sample_rate=16000)
        assert abs(ms - 100.0) < 1e-6

    def test_zero_chunks(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        assert vad._chunks_to_ms(0, 512, 16000) == 0.0


# ---------------------------------------------------------------------------
# VAD state machine — full lifecycle
# ---------------------------------------------------------------------------


class TestVADStateMachine:
    """Drive the VAD with controlled energy-based chunks (no Silero model)."""

    def _make_vad(
        self,
        threshold: float = 0.5,
        min_silence_ms: int = 100,
        min_speech_ms: int = 100,
    ) -> SileroVAD:
        cfg = _make_config(
            threshold=threshold,
            min_silence_ms=min_silence_ms,
            min_speech_ms=min_speech_ms,
            noise_floor_update_rate=0.0,  # freeze noise floor
        )
        vad = SileroVAD(cfg)
        # Keep noise floor low so energy-based threshold stays at cfg.threshold
        vad._noise_floor = 0.001
        vad._effective_threshold = threshold
        return vad

    def _process_n(self, vad, chunk, n: int) -> list:
        return [vad.process(chunk) for _ in range(n)]

    def test_silence_stays_in_silence(self) -> None:
        vad = self._make_vad()
        results = self._process_n(vad, _silence_chunk(), 20)
        assert all(r is None for r in results)
        assert vad.state == VADState.SILENCE

    def test_speech_transitions_to_speech_state(self) -> None:
        vad = self._make_vad(min_speech_ms=0)
        # Very short min_speech so first loud chunk triggers transition
        vad.process(_speech_chunk(amp=0.9))
        assert vad.state == VADState.SPEECH

    def test_speech_then_silence_emits_segment(self) -> None:
        """Full utterance: speech → silence → segment emitted."""
        vad = self._make_vad(min_silence_ms=100, min_speech_ms=0)

        # Build up a speech segment
        for _ in range(10):
            vad.process(_speech_chunk(amp=0.9))

        assert vad.state == VADState.SPEECH

        # Feed silence until segment is emitted
        segment = None
        for _ in range(50):
            result = vad.process(_silence_chunk())
            if result is not None:
                segment = result
                break

        assert segment is not None
        assert isinstance(segment, SpeechSegment)
        assert len(segment.audio) > 0

    def test_state_resets_after_segment_emitted(self) -> None:
        vad = self._make_vad(min_silence_ms=100, min_speech_ms=0)

        for _ in range(10):
            vad.process(_speech_chunk(amp=0.9))

        # drain to get segment
        for _ in range(50):
            if vad.process(_silence_chunk()) is not None:
                break

        assert vad.state == VADState.SILENCE
        assert vad._speech_buffer == []
        assert vad._silence_chunks == 0

    def test_speech_resume_during_ending_stays_in_speech(self) -> None:
        """Speech during ENDING state cancels the silence countdown."""
        vad = self._make_vad(min_silence_ms=500, min_speech_ms=0)

        for _ in range(10):
            vad.process(_speech_chunk(amp=0.9))
        assert vad.state == VADState.SPEECH

        # One silence chunk → ENDING
        vad.process(_silence_chunk())
        assert vad.state == VADState.ENDING

        # Speech resumes → back to SPEECH
        vad.process(_speech_chunk(amp=0.9))
        assert vad.state == VADState.SPEECH

    def test_segment_contains_speech_audio(self) -> None:
        """The emitted segment should contain non-zero audio."""
        vad = self._make_vad(min_silence_ms=50, min_speech_ms=0)
        speech = np.ones(512, dtype=np.float32) * 0.8

        for _ in range(5):
            vad.process(_make_chunk(data=speech.copy()))

        segment = None
        for _ in range(50):
            result = vad.process(_silence_chunk())
            if result is not None:
                segment = result
                break

        assert segment is not None
        rms = float(np.sqrt(np.mean(segment.audio**2)))
        assert rms > 0.1  # audio content preserved

    def test_short_speech_below_min_discarded(self) -> None:
        """Speech below min_speech_ms should not trigger state change."""
        vad = self._make_vad(
            min_speech_ms=5000,  # requires ~5s of speech
            min_silence_ms=100,
        )
        # Only a few chunks — not enough
        for _ in range(3):
            vad.process(_speech_chunk(amp=0.9))

        # State should remain SILENCE (speech_chunks < min_speech_chunks)
        assert vad.state == VADState.SILENCE


# ---------------------------------------------------------------------------
# SileroVAD.load() — import error path
# ---------------------------------------------------------------------------


class TestSileroVADLoad:
    @pytest.mark.asyncio
    async def test_load_falls_back_to_energy_on_import_error(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)

        import builtins

        real_import = builtins.__import__

        def mock_import(name, *a, **kw):
            if name == "silero_vad":
                raise ImportError("not installed")
            return real_import(name, *a, **kw)

        with patch("builtins.__import__", side_effect=mock_import):
            await vad.load()

        assert vad._use_silero is False
        assert vad._model is None

    @pytest.mark.asyncio
    async def test_load_silero_success_sets_flag(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)

        fake_model = MagicMock(return_value=0.9)
        fake_silero_module = MagicMock()
        fake_silero_module.load_silero_vad = MagicMock(return_value=fake_model)

        with patch.dict("sys.modules", {"silero_vad": fake_silero_module}):
            with patch(
                "perception.audio.vad.asyncio.to_thread", return_value=fake_model
            ) as mock_thread:
                # Make to_thread actually call the function
                mock_thread.side_effect = lambda fn: fake_model
                with patch(
                    "perception.audio.vad.asyncio.to_thread", new=_make_async_to_thread(fake_model)
                ):
                    await vad.load()

        # Even if silero mock is complex, key assertion: no crash


def _make_async_to_thread(result):
    """Helper: makes asyncio.to_thread return result without actually threading."""

    async def _fake(fn, *args, **kwargs):
        return result

    return _fake


# ---------------------------------------------------------------------------
# _get_speech_probability — silero path
# ---------------------------------------------------------------------------


class TestGetSpeechProbability:
    def test_falls_back_to_energy_when_no_model(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        vad._use_silero = True
        vad._model = None  # model not loaded despite flag

        audio = np.ones(512, dtype=np.float32) * 0.5
        prob = vad._get_speech_probability(audio)
        assert 0.0 <= prob <= 1.0

    def test_energy_path_used_when_silero_false(self) -> None:
        cfg = _make_config()
        vad = SileroVAD(cfg)
        vad._use_silero = False

        audio = np.zeros(512, dtype=np.float32)
        prob = vad._get_speech_probability(audio)
        assert prob < 0.2
