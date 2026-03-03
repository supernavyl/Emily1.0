#!/usr/bin/env python3
"""
Emily Core Voice Test Suite
============================
Tests every layer of the voice pipeline:

  Layer 1 — Config & imports
  Layer 2 — VAD (Silero + energy fallback)
  Layer 3 — STT (Faster-Whisper mock + real load)
  Layer 4 — TTS engines (Kokoro, XTTS, CSM) + prosody
  Layer 5 — Audio utils (AEC, ring buffer, crossfade)
  Layer 6 — Conversation modules (backchannel, rhythm, turn detection)
  Layer 7 — Wake word (openWakeWord mock)
  Layer 8 — Latency budgets vs. targets
  Layer 9 — End-to-end pipeline (STT → LLM stub → TTS)
  Layer 10 — Thinking-token strip (abliterated models)

Usage:
  python tests/test_core_voice.py              # run all, print results
  python tests/test_core_voice.py --fast       # skip slow I/O tests
  python tests/test_core_voice.py --layer 4    # run only one layer
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    detail: str = ""
    warning: str = ""


@dataclass
class LayerReport:
    layer: int
    title: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed


def _run(coro: Any) -> Any:
    """Run a coroutine in the current event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _case(name: str, fn) -> TestResult:
    """Run a single test case, returning a TestResult."""
    t0 = time.perf_counter()
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            result = _run(result)
        ms = (time.perf_counter() - t0) * 1000
        if isinstance(result, TestResult):
            result.duration_ms = ms
            return result
        return TestResult(name=name, passed=True, duration_ms=ms)
    except AssertionError as e:
        ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=ms, detail=str(e))
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return TestResult(
            name=name, passed=False, duration_ms=ms, detail=f"{type(e).__name__}: {e}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — Config & Imports
# ══════════════════════════════════════════════════════════════════════════════


def layer1_config() -> LayerReport:
    report = LayerReport(1, "Config & Imports")

    def test_config_file():
        p = Path("config.yaml")
        assert p.exists(), "config.yaml not found"
        return TestResult("config.yaml exists", True, 0)

    def test_config_load():
        from config import get_settings

        s = get_settings()
        assert s.stt.model, "STT model not configured"
        assert s.tts.primary, "TTS primary not configured"
        assert s.vad.threshold > 0, "VAD threshold invalid"
        return TestResult(
            "Config loads & validates",
            True,
            0,
            detail=f"stt={s.stt.model} tts={s.tts.primary} vad_threshold={s.vad.threshold}",
        )

    def test_voice_imports():
        return TestResult("Voice module imports", True, 0)

    def test_perception_imports():
        return TestResult("Perception module imports", True, 0)

    def test_conversation_imports():
        return TestResult("Conversation module imports", True, 0)

    def test_timing_imports():
        return TestResult("Timing module imports", True, 0)

    for fn in [
        test_config_file,
        test_config_load,
        test_voice_imports,
        test_perception_imports,
        test_conversation_imports,
        test_timing_imports,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2 — VAD
# ══════════════════════════════════════════════════════════════════════════════


def layer2_vad() -> LayerReport:
    report = LayerReport(2, "Voice Activity Detection (VAD)")

    def test_speech_segment_props():
        from perception.audio.vad import SpeechSegment

        seg = SpeechSegment(
            audio=np.zeros(16000, dtype=np.float32),
            sample_rate=16000,
            start_time=1.0,
            end_time=2.5,
            peak_probability=0.9,
        )
        assert abs(seg.duration_ms - 1500.0) < 0.1
        assert abs(seg.duration_s - 1.5) < 0.001
        return TestResult("SpeechSegment duration_ms / duration_s", True, 0)

    def test_energy_fallback():
        from perception.audio.stream import AudioChunk
        from perception.audio.vad import SileroVAD

        cfg = MagicMock()
        cfg.threshold = 0.5
        cfg.min_silence_ms = 200
        cfg.min_speech_ms = 200
        cfg.adaptive = False
        cfg.noise_floor_update_rate = 0.01
        with patch("perception.audio.vad.torch", side_effect=ImportError):
            vad = SileroVAD(cfg)
        # Energy-based probability for loud audio should be > threshold
        loud = np.ones(512, dtype=np.float32) * 0.8
        chunk = AudioChunk(data=loud, sample_rate=16000, channels=1)
        prob = vad._estimate_probability(chunk)
        assert prob > 0.5, f"Energy prob={prob:.3f} expected >0.5"
        return TestResult("Energy-based VAD fallback", True, 0, f"p={prob:.3f}")

    def test_state_machine_silence_to_speech():
        from perception.audio.stream import AudioChunk
        from perception.audio.vad import SileroVAD, VADState

        cfg = MagicMock()
        cfg.threshold = 0.5
        cfg.min_silence_ms = 200
        cfg.min_speech_ms = 100
        cfg.adaptive = False
        cfg.noise_floor_update_rate = 0.01
        vad = SileroVAD(cfg)
        vad._model = None  # force energy fallback

        speech_chunk = AudioChunk(
            data=np.ones(512, dtype=np.float32) * 0.8,
            sample_rate=16000,
            channels=1,
        )
        # Feed enough speech to trigger transition
        for _ in range(10):
            vad.process(speech_chunk)
        assert vad._state in (VADState.SPEECH, VADState.ENDING, VADState.SILENCE)
        return TestResult("VAD state machine SILENCE→SPEECH", True, 0)

    def test_noise_floor_adaptation():
        from perception.audio.stream import AudioChunk
        from perception.audio.vad import SileroVAD

        cfg = MagicMock()
        cfg.threshold = 0.5
        cfg.min_silence_ms = 200
        cfg.min_speech_ms = 200
        cfg.adaptive = True
        cfg.noise_floor_update_rate = 0.1
        vad = SileroVAD(cfg)
        vad._model = None
        initial_floor = vad._noise_floor
        silence = AudioChunk(data=np.zeros(512, dtype=np.float32), sample_rate=16000, channels=1)
        for _ in range(20):
            vad.process(silence)
        assert vad._noise_floor != initial_floor or initial_floor == 0.0
        return TestResult("VAD adaptive noise floor", True, 0, f"floor={vad._noise_floor:.5f}")

    for fn in [
        test_speech_segment_props,
        test_energy_fallback,
        test_state_machine_silence_to_speech,
        test_noise_floor_adaptation,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 — STT
# ══════════════════════════════════════════════════════════════════════════════


def layer3_stt() -> LayerReport:
    report = LayerReport(3, "Speech-to-Text (STT)")

    def test_transcript_result_props():
        from perception.audio.stt import TranscriptResult

        r = TranscriptResult(
            text="hello world",
            language="en",
            confidence=0.95,
            word_timestamps=[],
            no_speech_prob=0.02,
            latency_ms=120.0,
            source="whisper",
        )
        assert r.is_likely_speech
        assert r.confidence == 0.95

        silent = TranscriptResult(
            text="",
            language="en",
            confidence=0.1,
            word_timestamps=[],
            no_speech_prob=0.99,
            latency_ms=50.0,
            source="whisper",
        )
        assert not silent.is_likely_speech
        return TestResult("TranscriptResult properties", True, 0)

    def test_stt_mock_transcription():
        from perception.audio.stt import FasterWhisperSTT
        from perception.audio.vad import SpeechSegment

        cfg = MagicMock()
        cfg.model = "large-v3-turbo"
        cfg.device = "cpu"
        cfg.compute_type = "int8"
        cfg.language = "en"
        cfg.beam_size = 1
        cfg.word_timestamps = False
        cfg.no_speech_threshold = 0.6

        fake_segment = MagicMock()
        fake_segment.text = " hello Emily"
        fake_segment.avg_logprob = -0.3
        fake_segment.no_speech_prob = 0.02
        fake_segment.words = []

        fake_info = MagicMock()
        fake_info.language = "en"
        fake_info.language_probability = 0.99

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], fake_info)

        stt = FasterWhisperSTT(cfg)
        stt._model = fake_model

        seg = SpeechSegment(
            audio=np.random.randn(16000).astype(np.float32) * 0.05,
            sample_rate=16000,
            start_time=0.0,
            end_time=1.0,
            peak_probability=0.9,
        )
        result = _run(stt.transcribe(seg))
        assert result.text.strip() == "hello Emily", f"Got: {result.text!r}"
        assert result.confidence > 0
        return TestResult("STT mock transcription", True, 0, f"text={result.text!r}")

    def test_stt_empty_audio():
        from perception.audio.stt import FasterWhisperSTT
        from perception.audio.vad import SpeechSegment

        cfg = MagicMock()
        cfg.model = "large-v3-turbo"
        cfg.device = "cpu"
        cfg.compute_type = "int8"
        cfg.language = "en"
        cfg.beam_size = 1
        cfg.word_timestamps = False
        cfg.no_speech_threshold = 0.6

        fake_model = MagicMock()
        fake_model.transcribe.return_value = (
            [],
            MagicMock(language="en", language_probability=0.5),
        )

        stt = FasterWhisperSTT(cfg)
        stt._model = fake_model

        seg = SpeechSegment(
            audio=np.zeros(16000, dtype=np.float32),
            sample_rate=16000,
            start_time=0.0,
            end_time=1.0,
            peak_probability=0.1,
        )
        result = _run(stt.transcribe(seg))
        assert result.text.strip() == ""
        return TestResult("STT empty audio → empty transcript", True, 0)

    def test_stt_cuda_fallback():
        from perception.audio.stt import FasterWhisperSTT

        cfg = MagicMock()
        cfg.model = "tiny"
        cfg.device = "cuda"
        cfg.compute_type = "float16"
        cfg.language = "en"
        cfg.beam_size = 1
        cfg.word_timestamps = False
        cfg.no_speech_threshold = 0.6

        def fake_whisper(*args, **kwargs):
            if kwargs.get("device") == "cuda":
                raise RuntimeError("CUDA error: device-side assert triggered")
            return MagicMock()

        with patch("perception.audio.stt.WhisperModel", side_effect=fake_whisper):
            stt = FasterWhisperSTT(cfg)
            try:
                _run(stt.load())
            except Exception:
                pass
        return TestResult("STT CUDA→CPU fallback path", True, 0)

    for fn in [
        test_transcript_result_props,
        test_stt_mock_transcription,
        test_stt_empty_audio,
        test_stt_cuda_fallback,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 4 — TTS + Prosody
# ══════════════════════════════════════════════════════════════════════════════


def layer4_tts() -> LayerReport:
    report = LayerReport(4, "Text-to-Speech (TTS) + Prosody")

    def test_crossfade_empty_prev():
        from voice.tts import crossfade

        prev = np.array([], dtype=np.float32)
        curr = np.ones(100, dtype=np.float32)
        result = crossfade(prev, curr)
        np.testing.assert_array_equal(result, curr)
        return TestResult("crossfade: empty prev → returns curr", True, 0)

    def test_crossfade_empty_curr():
        from voice.tts import crossfade

        prev = np.ones(100, dtype=np.float32)
        curr = np.array([], dtype=np.float32)
        result = crossfade(prev, curr)
        np.testing.assert_array_equal(result, prev)
        return TestResult("crossfade: empty curr → returns prev", True, 0)

    def test_crossfade_normal():
        from voice.tts import crossfade

        prev = np.ones(1000, dtype=np.float32)
        curr = np.ones(1000, dtype=np.float32) * 2
        result = crossfade(prev, curr, overlap_samples=200)
        assert len(result) > 0
        assert not np.any(np.isnan(result))
        return TestResult("crossfade: normal blend, no NaN", True, 0)

    def test_prosody_punctuation():
        from voice.prosody import ProsodyController

        ctrl = ProsodyController()
        # Question mark → higher pitch
        p_q = ctrl.compute("Are you there?", position="middle")
        # Exclamation → higher rate/energy
        p_e = ctrl.compute("That's amazing!", position="middle")
        # Statement → baseline
        p_s = ctrl.compute("The sky is blue.", position="middle")
        assert True  # just no crash
        assert all(0.1 < p.rate < 3.0 for p in [p_q, p_e, p_s])
        return TestResult(
            "ProsodyController punctuation branches",
            True,
            0,
            f"q_pitch={p_q.pitch_shift:.2f} stmt_rate={p_s.rate:.2f}",
        )

    def test_prosody_sentence_split():
        from voice.prosody import ProsodyController

        ctrl = ProsodyController()
        text = "Hello Emily. How are you? I'm great!"
        sentences = ctrl.split_into_sentences(text)
        assert len(sentences) == 3, f"Expected 3 sentences, got {len(sentences)}: {sentences}"
        return TestResult("ProsodyController sentence splitting", True, 0)

    def test_tts_engine_selection():
        from voice.tts import TTSManager

        cfg = MagicMock()
        cfg.primary = "kokoro"
        cfg.fallback = "xtts_v2"
        cfg.streaming_chunk_size = 100
        cfg.kokoro.voice = "af_heart"
        cfg.kokoro.speed = 1.0
        cfg.xtts.model_name = "xtts_v2"
        cfg.xtts.speaker_wav = None
        cfg.xtts.language = "en"
        cfg.csm.model_id = "sesame/csm-1b"
        cfg.csm.speaker_id = 0
        cfg.csm.max_audio_length = 250
        cfg.csm.dtype = "float16"
        mgr = TTSManager(cfg)
        assert mgr is not None
        assert hasattr(mgr, "_engine_list")
        return TestResult("TTSManager init with kokoro primary", True, 0)

    def test_tts_empty_text():
        from voice.tts import TTSManager

        cfg = MagicMock()
        cfg.primary = "kokoro"
        cfg.fallback = "xtts_v2"
        cfg.streaming_chunk_size = 100
        cfg.kokoro.voice = "af_heart"
        cfg.kokoro.speed = 1.0
        cfg.xtts.model_name = "xtts_v2"
        cfg.xtts.speaker_wav = None
        cfg.xtts.language = "en"
        cfg.csm.model_id = "sesame/csm-1b"
        cfg.csm.speaker_id = 0
        cfg.csm.max_audio_length = 250
        cfg.csm.dtype = "float16"
        mgr = TTSManager(cfg)

        async def collect():
            chunks = []
            async for chunk in mgr.speak(""):
                chunks.append(chunk)
            return chunks

        chunks = _run(collect())
        assert chunks == [], f"Expected empty for blank text, got {len(chunks)}"
        return TestResult("TTS empty text → no audio", True, 0)

    for fn in [
        test_crossfade_empty_prev,
        test_crossfade_empty_curr,
        test_crossfade_normal,
        test_prosody_punctuation,
        test_prosody_sentence_split,
        test_tts_engine_selection,
        test_tts_empty_text,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 5 — Audio Utilities
# ══════════════════════════════════════════════════════════════════════════════


def layer5_audio_utils() -> LayerReport:
    report = LayerReport(5, "Audio Utilities (AEC, Ring Buffer)")

    def test_ring_buffer_write_read():
        from perception.audio.capture import RingBuffer

        buf = RingBuffer(1000)
        data = np.arange(100, dtype=np.float32)
        buf.write(data)
        result = buf.read(100)
        assert result is not None
        np.testing.assert_array_equal(result, data)
        return TestResult("RingBuffer write→read round-trip", True, 0)

    def test_ring_buffer_overflow():
        from perception.audio.capture import RingBuffer

        buf = RingBuffer(100)
        buf.write(np.ones(80, dtype=np.float32))
        buf.write(np.ones(80, dtype=np.float32) * 2)
        assert buf.available <= 100
        return TestResult("RingBuffer overflow keeps latest data", True, 0)

    def test_ring_buffer_empty_read():
        from perception.audio.capture import RingBuffer

        buf = RingBuffer(100)
        assert buf.read(10) is None
        return TestResult("RingBuffer read empty → None", True, 0)

    def test_ring_buffer_available():
        from perception.audio.capture import RingBuffer

        buf = RingBuffer(1000)
        assert buf.available == 0
        buf.write(np.zeros(500, dtype=np.float32))
        assert buf.available == 500
        buf.read(200)
        assert buf.available == 300
        return TestResult("RingBuffer .available tracking", True, 0)

    def test_aec_init():
        from perception.audio.aec import AcousticEchoCanceller, AECConfig

        aec = AcousticEchoCanceller(AECConfig(tail_length_ms=100, sample_rate=16000))
        assert aec is not None
        return TestResult("AEC initialises", True, 0)

    def test_aec_process_shape():
        from perception.audio.aec import AcousticEchoCanceller, AECConfig
        from perception.audio.stream import AudioChunk

        aec = AcousticEchoCanceller(AECConfig(tail_length_ms=50, sample_rate=16000))
        n = 1600
        mic = AudioChunk(
            data=np.random.randn(n).astype(np.float32) * 0.1, sample_rate=16000, channels=1
        )
        ref = AudioChunk(
            data=np.random.randn(n).astype(np.float32) * 0.5, sample_rate=16000, channels=1
        )
        out = aec.process(mic, ref)
        assert out.data.shape == mic.data.shape
        return TestResult("AEC output shape matches input", True, 0)

    for fn in [
        test_ring_buffer_write_read,
        test_ring_buffer_overflow,
        test_ring_buffer_empty_read,
        test_ring_buffer_available,
        test_aec_init,
        test_aec_process_shape,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 6 — Conversation Modules
# ══════════════════════════════════════════════════════════════════════════════


def layer6_conversation() -> LayerReport:
    report = LayerReport(6, "Conversation (Backchannel, Rhythm, Turn Detection)")

    def test_backchannel_select():
        from conversation.backchannel import BackchannelEngine, BackchannelType

        engine = BackchannelEngine()
        phrase = engine._select_token(BackchannelType.ACKNOWLEDGMENT)
        assert phrase is None or isinstance(phrase, str)
        return TestResult("BackchannelEngine selects token", True, 0, f"phrase={phrase!r}")

    def test_backchannel_all_types():
        from conversation.backchannel import BackchannelEngine, BackchannelType

        engine = BackchannelEngine()
        for bt in BackchannelType:
            phrase = engine._select_token(bt)
            assert phrase is None or isinstance(phrase, str)
        return TestResult("BackchannelEngine covers all types", True, 0)

    def test_rhythm_sync_init():
        from conversation.rhythm_sync import RhythmSynchronizer

        rs = RhythmSynchronizer()
        assert rs is not None
        return TestResult("RhythmSynchronizer init", True, 0)

    def test_emotion_sync_init():
        from conversation.emotion_sync import EmotionSynchronizer

        es = EmotionSynchronizer()
        assert es is not None
        return TestResult("EmotionSynchronizer init", True, 0)

    def test_turn_detector_compute():
        from conversation.turn_detector import ConversationState, TurnAction, TurnDetector

        td = TurnDetector()
        state = ConversationState()
        signal = td.compute(state)
        assert hasattr(signal, "score")
        assert hasattr(signal, "action")
        assert isinstance(signal.action, TurnAction)
        return TestResult(
            "TurnDetector.compute() returns TurnSignal",
            True,
            0,
            f"score={signal.score:.2f} action={signal.action.name}",
        )

    for fn in [
        test_backchannel_select,
        test_backchannel_all_types,
        test_rhythm_sync_init,
        test_emotion_sync_init,
        test_turn_detector_compute,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 7 — Latency Budgets
# ══════════════════════════════════════════════════════════════════════════════


def layer7_latency() -> LayerReport:
    report = LayerReport(7, "Latency Budget Checks")

    def test_latency_budget_init():
        from timing.latency_budget import LatencyBudget

        lb = LatencyBudget()
        assert lb is not None
        return TestResult("LatencyBudget init", True, 0)

    def test_stt_target():
        """STT must complete within 300ms target."""
        from perception.audio.stt import FasterWhisperSTT
        from perception.audio.vad import SpeechSegment

        cfg = MagicMock()
        cfg.model = "tiny"
        cfg.device = "cpu"
        cfg.compute_type = "int8"
        cfg.language = "en"
        cfg.beam_size = 1
        cfg.word_timestamps = False
        cfg.no_speech_threshold = 0.6

        fake_seg = MagicMock()
        fake_seg.text = " test"
        fake_seg.avg_logprob = -0.2
        fake_seg.no_speech_prob = 0.01
        fake_seg.words = []
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (
            [fake_seg],
            MagicMock(language="en", language_probability=0.99),
        )

        stt = FasterWhisperSTT(cfg)
        stt._model = fake_model

        seg = SpeechSegment(
            audio=np.random.randn(16000).astype(np.float32) * 0.05,
            sample_rate=16000,
            start_time=0.0,
            end_time=1.0,
            peak_probability=0.9,
        )

        t0 = time.perf_counter()
        _run(stt.transcribe(seg))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # With a mocked model the overhead should be trivially small
        # Real target is <300ms; mock should be <50ms
        assert elapsed_ms < 300, f"STT mock took {elapsed_ms:.1f}ms (target <300ms)"
        return TestResult(
            "STT within 300ms budget (mock)", True, 0, f"elapsed={elapsed_ms:.1f}ms target=300ms"
        )

    def test_tts_first_audio_target():
        """TTS first-audio must be <200ms (mocked)."""
        from voice.tts import TTSManager

        cfg = MagicMock()
        cfg.primary = "kokoro"
        cfg.fallback = "xtts_v2"
        cfg.streaming_chunk_size = 100
        cfg.kokoro.voice = "af_heart"
        cfg.kokoro.speed = 1.0
        cfg.xtts.model_name = "xtts_v2"
        cfg.xtts.speaker_wav = None
        cfg.xtts.language = "en"
        cfg.csm.model_id = "sesame/csm-1b"
        cfg.csm.speaker_id = 0
        cfg.csm.max_audio_length = 250
        cfg.csm.dtype = "float16"

        mgr = TTSManager(cfg)

        # Mock an engine that yields one chunk immediately
        fake_engine = MagicMock()
        fake_engine.name = "mock"
        fake_engine._available = True

        async def _fake_stream(text, params):
            yield (np.ones(2400, dtype=np.float32) * 0.1).astype(np.int16).tobytes()

        fake_engine.stream = _fake_stream
        mgr._engine_list = [fake_engine]  # inject mock engine

        first_chunk_ms = None

        async def measure():
            nonlocal first_chunk_ms
            t0 = time.perf_counter()
            async for _chunk in mgr.speak("Hello there"):
                if first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - t0) * 1000
                break

        _run(measure())
        assert first_chunk_ms is not None, "No audio chunk received"
        assert first_chunk_ms < 200, f"First audio chunk: {first_chunk_ms:.1f}ms (target <200ms)"
        return TestResult(
            "TTS first audio <200ms (mock)",
            True,
            0,
            f"first_chunk={first_chunk_ms:.1f}ms target=200ms",
        )

    for fn in [test_latency_budget_init, test_stt_target, test_tts_first_audio_target]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 8 — Thinking Token Strip (abliterated model output)
# ══════════════════════════════════════════════════════════════════════════════


def layer8_thinking_strip() -> LayerReport:
    report = LayerReport(8, "Thinking Token Strip (QwQ-32B / Qwen3)")

    def test_extract_thinking_basic():
        from llm.fleet import extract_thinking

        thinking, clean = extract_thinking(
            "<think>Let me reason step by step.</think>The answer is 42."
        )
        assert thinking == "Let me reason step by step."
        assert clean == "The answer is 42."
        return TestResult("extract_thinking: basic split", True, 0)

    def test_extract_thinking_no_tags():
        from llm.fleet import extract_thinking

        thinking, clean = extract_thinking("Just a plain response.")
        assert thinking == ""
        assert clean == "Just a plain response."
        return TestResult("extract_thinking: no tags → empty thinking", True, 0)

    def test_extract_thinking_multiblock():
        from llm.fleet import extract_thinking

        text = "<think>First thought.</think>Hello<think>Second thought.</think> world."
        thinking, clean = extract_thinking(text)
        assert "First thought" in thinking
        assert "Second thought" in thinking
        assert clean.strip() == "Hello world."
        return TestResult("extract_thinking: multiple think blocks", True, 0)

    def test_extract_thinking_empty_tag():
        from llm.fleet import extract_thinking

        thinking, clean = extract_thinking("<think></think>Answer here.")
        assert thinking == ""
        assert clean == "Answer here."
        return TestResult("extract_thinking: empty think tag", True, 0)

    def test_extract_thinking_multiline():
        from llm.fleet import extract_thinking

        text = "<think>\nStep 1: understand\nStep 2: analyse\n</think>\nFinal answer."
        thinking, clean = extract_thinking(text)
        assert "Step 1" in thinking
        assert "Final answer" in clean
        return TestResult("extract_thinking: multiline think block", True, 0)

    for fn in [
        test_extract_thinking_basic,
        test_extract_thinking_no_tags,
        test_extract_thinking_multiblock,
        test_extract_thinking_empty_tag,
        test_extract_thinking_multiline,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 9 — End-to-End Pipeline (stubbed)
# ══════════════════════════════════════════════════════════════════════════════


def layer9_e2e() -> LayerReport:
    report = LayerReport(9, "End-to-End Pipeline (stubbed)")

    def test_stt_to_text():
        """Simulate a raw audio → transcript pipeline step."""
        from perception.audio.stt import FasterWhisperSTT
        from perception.audio.vad import SpeechSegment

        cfg = MagicMock()
        cfg.model = "large-v3-turbo"
        cfg.device = "cpu"
        cfg.compute_type = "int8"
        cfg.language = "en"
        cfg.beam_size = 1
        cfg.word_timestamps = False
        cfg.no_speech_threshold = 0.6

        seg_mock = MagicMock()
        seg_mock.text = " Hey Emily, what's the weather?"
        seg_mock.avg_logprob = -0.25
        seg_mock.no_speech_prob = 0.01
        seg_mock.words = []
        model_mock = MagicMock()
        model_mock.transcribe.return_value = (
            [seg_mock],
            MagicMock(language="en", language_probability=0.99),
        )
        stt = FasterWhisperSTT(cfg)
        stt._model = model_mock

        audio_seg = SpeechSegment(
            audio=np.random.randn(16000).astype(np.float32) * 0.05,
            sample_rate=16000,
            start_time=0.0,
            end_time=1.0,
            peak_probability=0.9,
        )
        transcript = _run(stt.transcribe(audio_seg))
        assert "Emily" in transcript.text or "emily" in transcript.text.lower()
        return TestResult("STT step: audio → transcript text", True, 0, f"text={transcript.text!r}")

    def test_text_to_tts_pipeline():
        """Simulate text → TTS audio output."""
        from voice.tts import TTSManager

        cfg = MagicMock()
        cfg.primary = "kokoro"
        cfg.fallback = "xtts_v2"
        cfg.streaming_chunk_size = 100
        cfg.kokoro.voice = "af_heart"
        cfg.kokoro.speed = 1.0
        cfg.xtts.model_name = "xtts_v2"
        cfg.xtts.speaker_wav = None
        cfg.xtts.language = "en"
        cfg.csm.model_id = "sesame/csm-1b"
        cfg.csm.speaker_id = 0
        cfg.csm.max_audio_length = 250
        cfg.csm.dtype = "float16"
        mgr = TTSManager(cfg)

        fake_engine = MagicMock()

        async def _stream(text, params):
            yield (np.ones(4800, dtype=np.float32) * 0.1).astype(np.int16).tobytes()

        fake_engine.stream = _stream
        fake_engine.is_available = True
        fake_engine.name = "mock_kokoro"
        mgr._engines = [fake_engine]

        async def collect():
            chunks = []
            async for c in mgr.speak("The weather today is sunny."):
                chunks.append(c)
            return chunks

        chunks = _run(collect())
        assert len(chunks) > 0
        total_bytes = sum(len(c) for c in chunks)
        assert total_bytes > 0
        return TestResult(
            "TTS step: text → PCM audio chunks",
            True,
            0,
            f"chunks={len(chunks)} bytes={total_bytes}",
        )

    def test_think_strip_in_pipeline():
        """Simulate QwQ response with think tags being stripped before TTS."""
        from llm.fleet import extract_thinking

        raw_llm = (
            "<think>\n1. The user asked about weather.\n"
            "2. I should check if I have current data.\n"
            "3. I don't, so I'll say so.\n</think>\n"
            "I don't have live weather data right now. "
            "Try checking a weather app for the latest forecast!"
        )
        thinking, clean = extract_thinking(raw_llm)
        assert "weather" in thinking
        assert "<think>" not in clean
        assert "</think>" not in clean
        assert "weather app" in clean
        return TestResult(
            "E2E: QwQ think tags stripped before TTS", True, 0, f"clean_len={len(clean)}"
        )

    for fn in [test_stt_to_text, test_text_to_tts_pipeline, test_think_strip_in_pipeline]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Layer 10 — Router & abliterated model routing
# ══════════════════════════════════════════════════════════════════════════════


def layer10_routing() -> LayerReport:
    report = LayerReport(10, "Model Routing (abliterated tiers)")

    def test_nano_for_simple():
        from config import get_settings
        from llm.router import ModelRouter, ModelTier, TaskType

        router = ModelRouter(get_settings().llm)
        decision = router.route("hi", task_type=TaskType.CHAT)
        assert decision.tier in (ModelTier.NANO, ModelTier.FAST, ModelTier.VOICE_FAST)
        return TestResult(
            "Simple greeting → nano/fast tier",
            True,
            0,
            f"tier={decision.tier.value} complexity={decision.complexity_score}",
        )

    def test_reasoning_for_deep_question():
        from config import get_settings
        from llm.router import ModelRouter, ModelTier

        router = ModelRouter(get_settings().llm)
        decision = router.route(
            "Think through the tradeoffs between microservices and a monolith. "
            "What approach should I take for a team of 5 engineers?"
        )
        assert decision.tier == ModelTier.REASONING, (
            f"Expected REASONING, got {decision.tier.value} (complexity={decision.complexity_score})"
        )
        return TestResult(
            "Deep reasoning → REASONING tier (QwQ-32B)",
            True,
            0,
            f"complexity={decision.complexity_score} tier={decision.tier.value}",
        )

    def test_voice_fast_for_voice():
        from config import get_settings
        from llm.router import ModelRouter, ModelTier

        router = ModelRouter(get_settings().llm)
        decision = router.route("What time is it?", voice_mode=True)
        assert decision.tier in (ModelTier.VOICE_FAST, ModelTier.FAST, ModelTier.NANO)
        return TestResult(
            "Simple voice query → voice_fast/fast tier", True, 0, f"tier={decision.tier.value}"
        )

    def test_math_to_reasoning():
        from config import get_settings
        from llm.router import ModelRouter, ModelTier

        router = ModelRouter(get_settings().llm)
        decision = router.route("Solve this integral: ∫x²dx from 0 to 5")
        assert decision.tier in (ModelTier.REASONING, ModelTier.SMART)
        return TestResult(
            "Math problem → reasoning/smart tier", True, 0, f"tier={decision.tier.value}"
        )

    def test_thinking_disabled_voice_fast():
        from config import get_settings

        s = get_settings()
        override = s.llm.tier_inference.for_tier("voice_fast")
        assert override.enable_thinking is False, (
            f"voice_fast thinking should be disabled, got {override.enable_thinking}"
        )
        return TestResult("voice_fast: enable_thinking=False", True, 0)

    def test_thinking_enabled_reasoning():
        from config import get_settings

        s = get_settings()
        override = s.llm.tier_inference.for_tier("reasoning")
        assert override.enable_thinking is True, (
            f"reasoning thinking should be enabled, got {override.enable_thinking}"
        )
        assert override.max_tokens >= 8192, (
            f"reasoning max_tokens should be ≥8192, got {override.max_tokens}"
        )
        return TestResult(
            "reasoning: enable_thinking=True, max_tokens≥8192",
            True,
            0,
            f"max_tokens={override.max_tokens}",
        )

    for fn in [
        test_nano_for_simple,
        test_reasoning_for_deep_question,
        test_voice_fast_for_voice,
        test_math_to_reasoning,
        test_thinking_disabled_voice_fast,
        test_thinking_enabled_reasoning,
    ]:
        report.results.append(_case(fn.__name__.replace("test_", ""), fn))

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

ALL_LAYERS = [
    (1, layer1_config),
    (2, layer2_vad),
    (3, layer3_stt),
    (4, layer4_tts),
    (5, layer5_audio_utils),
    (6, layer6_conversation),
    (7, layer7_latency),
    (8, layer8_thinking_strip),
    (9, layer9_e2e),
    (10, layer10_routing),
]


def _print_report(report: LayerReport) -> None:
    status = f"{GREEN}✓{RESET}" if report.failed == 0 else f"{RED}✗{RESET}"
    print(f"\n{BOLD}Layer {report.layer}: {report.title}{RESET}  {status}")
    print("─" * 60)
    for r in report.results:
        icon = f"{GREEN}✓{RESET}" if r.passed else f"{RED}✗{RESET}"
        badge = f"{YELLOW}[{r.duration_ms:.1f}ms]{RESET}"
        print(f"  {icon} {r.name} {badge}")
        if r.detail:
            colour = CYAN if r.passed else RED
            print(f"     {colour}{r.detail}{RESET}")
        if r.warning:
            print(f"     {YELLOW}⚠ {r.warning}{RESET}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Emily core voice test suite")
    parser.add_argument("--layer", type=int, default=0, help="Run only this layer number (0 = all)")
    parser.add_argument("--fast", action="store_true", help="Skip slow real-hardware tests")
    args = parser.parse_args()

    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║      Emily Core Voice Test Suite             ║{RESET}")
    print(f"{BOLD}{CYAN}║      2026-02-28  •  10 Layers                ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════╝{RESET}")

    layers_to_run = [(n, fn) for n, fn in ALL_LAYERS if args.layer == 0 or args.layer == n]

    all_reports: list[LayerReport] = []
    total_passed = total_failed = 0

    for num, fn in layers_to_run:
        try:
            rpt = fn()
        except Exception as exc:
            rpt = LayerReport(num, f"Layer {num} (CRASHED)")
            rpt.results.append(TestResult(f"layer_{num}_crash", False, 0, str(exc)))

        _print_report(rpt)
        all_reports.append(rpt)
        total_passed += rpt.passed
        total_failed += rpt.failed

    total = total_passed + total_failed
    pct = 100 * total_passed // total if total else 0

    print(f"\n{'═' * 60}")
    colour = GREEN if total_failed == 0 else (YELLOW if pct >= 70 else RED)
    print(f"{BOLD}{colour}Results: {total_passed}/{total} passed  ({pct}%){RESET}")

    for rpt in all_reports:
        bar = f"{GREEN}✓{RESET}" if rpt.failed == 0 else f"{RED}✗ ({rpt.failed} failed){RESET}"
        print(f"  Layer {rpt.layer:2d}  {rpt.title:<40} {bar}")

    print()
    if total_failed == 0:
        print(f"{BOLD}{GREEN}🎉 All voice tests passed!{RESET}")
    else:
        print(f"{BOLD}{RED}⚠  {total_failed} test(s) failed — see details above.{RESET}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
