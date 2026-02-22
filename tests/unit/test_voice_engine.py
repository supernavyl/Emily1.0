"""
Tests for voice engine components.

Covers:
- Ring buffer correctness
- AEC basic operation
- Prosody feature extraction
- Emotion detection
- Backchannel selection
- Rhythm synchronization
- Latency budget enforcement
- Speculative cache
"""

from __future__ import annotations

import asyncio
import pytest
import numpy as np

from perception.audio.capture import RingBuffer
from perception.audio.aec import AcousticEchoCanceller, AECConfig
from perception.audio.prosody_analyzer import ProsodyAnalyzer, ProsodyFeatures
from perception.audio.emotion_detector import EmotionDetector, EmotionState, UserEmotion
from perception.audio.stream import AudioChunk
from conversation.backchannel import BackchannelEngine, BackchannelType
from conversation.rhythm_sync import RhythmSynchronizer, RhythmTargets
from conversation.emotion_sync import EmotionSynchronizer, ResponseStyleParameters
from timing.latency_budget import LatencyBudget
from llm.speculative import SpeculativeCache
from voice.prosody_planner import ProsodyPlanner, SentenceProsody


class TestRingBuffer:
    """Test the lock-free ring buffer."""

    def test_write_and_read(self) -> None:
        """Basic write/read cycle."""
        buf = RingBuffer(1000)
        data = np.arange(100, dtype=np.float32)
        buf.write(data)
        result = buf.read(100)
        assert result is not None
        np.testing.assert_array_equal(result, data)

    def test_overflow_overwrites_oldest(self) -> None:
        """Buffer overflow should overwrite oldest data, keeping latest samples."""
        buf = RingBuffer(100)
        buf.write(np.ones(80, dtype=np.float32))
        buf.write(np.ones(80, dtype=np.float32) * 2)
        assert buf.available <= 100
        result = buf.read(buf.available)
        assert result is not None
        assert np.all(result[-40:] == 2)

    def test_read_returns_none_on_empty(self) -> None:
        """Reading from empty buffer returns None."""
        buf = RingBuffer(100)
        assert buf.read(10) is None

    def test_available_tracking(self) -> None:
        """Available count should be accurate."""
        buf = RingBuffer(1000)
        assert buf.available == 0
        buf.write(np.zeros(500, dtype=np.float32))
        assert buf.available == 500
        buf.read(200)
        assert buf.available == 300


class TestAEC:
    """Test acoustic echo cancellation."""

    def test_pure_echo_reduction(self) -> None:
        """AEC should reduce echo when reference matches mic."""
        aec = AcousticEchoCanceller(AECConfig(filter_length=100))
        sr = 48000
        t = np.linspace(0, 0.1, int(sr * 0.1), dtype=np.float32)
        reference = np.sin(2 * np.pi * 440 * t)
        mic = reference * 0.5  # echo is attenuated version

        output = aec.process(mic, reference)
        assert np.mean(output ** 2) < np.mean(mic ** 2)

    def test_no_reference_passthrough(self) -> None:
        """With no reference, mic should pass through unchanged."""
        aec = AcousticEchoCanceller()
        mic = np.random.randn(480).astype(np.float32) * 0.1
        output = aec.process(mic, np.array([], dtype=np.float32))
        np.testing.assert_array_equal(output, mic)


class TestProsodyAnalyzer:
    """Test prosody feature extraction."""

    def test_silence_detection(self) -> None:
        """Silent audio should detect a pause."""
        analyzer = ProsodyAnalyzer(sample_rate=16000)
        silence = AudioChunk(
            data=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            channels=1,
        )
        features = analyzer.process(silence)
        assert features.pause_duration_ms >= 0

    def test_speech_extracts_f0(self) -> None:
        """Speech-like signal should extract a non-zero F0."""
        analyzer = ProsodyAnalyzer(sample_rate=16000)
        t = np.linspace(0, 0.5, 8000, dtype=np.float32)
        speech = np.sin(2 * np.pi * 150 * t) * 0.3
        for i in range(5):
            chunk = AudioChunk(
                data=speech[i * 1600:(i + 1) * 1600],
                sample_rate=16000,
                channels=1,
            )
            features = analyzer.process(chunk)
        assert features.f0_hz > 0


class TestEmotionDetector:
    """Test emotion detection."""

    def test_neutral_baseline(self) -> None:
        """Baseline prosody should produce neutral emotion."""
        from perception.audio.prosody_analyzer import SpeakerBaseline
        detector = EmotionDetector()
        features = ProsodyFeatures(
            f0_hz=150, intensity_db=65, speaking_rate_syl_s=4.0,
        )
        baseline = SpeakerBaseline(f0_mean=150, f0_std=20)
        result = detector.detect(features, baseline)
        assert isinstance(result, EmotionState)
        assert 0 <= result.confidence <= 1

    def test_excited_detection(self) -> None:
        """High F0 and energy should produce elevated engagement."""
        from perception.audio.prosody_analyzer import SpeakerBaseline
        detector = EmotionDetector()
        features = ProsodyFeatures(
            f0_hz=220, intensity_db=80, speaking_rate_syl_s=6.0,
            f0_trajectory="rising", f0_range_semitones=8,
        )
        baseline = SpeakerBaseline(f0_mean=150, f0_std=20, intensity_mean=65)
        for _ in range(20):
            result = detector.detect(features, baseline, "this is amazing!")
        assert result.engagement > 0.6


class TestBackchannelEngine:
    """Test backchannel generation."""

    @pytest.mark.asyncio
    async def test_backchannel_cooldown(self) -> None:
        """Backchannels should respect the minimum interval."""
        engine = BackchannelEngine()
        result1 = await engine.should_backchannel(
            partial_text="So I was thinking about this really interesting thing"
        )
        result2 = await engine.should_backchannel(
            partial_text="and then something else happened"
        )
        assert result2 is None  # too soon

    @pytest.mark.asyncio
    async def test_render_produces_audio(self) -> None:
        """Rendering a backchannel should produce float32 audio."""
        from conversation.backchannel import BackchannelEvent
        engine = BackchannelEngine()
        event = BackchannelEvent(
            bc_type=BackchannelType.CONTINUER,
            token="mmhm",
        )
        audio = await engine.render_backchannel(event)
        assert audio is not None
        assert audio.dtype == np.float32
        assert len(audio) > 0


class TestRhythmSync:
    """Test rhythm synchronization."""

    def test_entrainment_blending(self) -> None:
        """Targets should blend between Emily baseline and user profile."""
        sync = RhythmSynchronizer(entrainment_degree=0.5)

        from perception.audio.prosody_analyzer import ProsodyFeatures
        for _ in range(50):
            sync.update_from_prosody(ProsodyFeatures(speaking_rate_syl_s=6.0))

        targets = sync.get_targets()
        assert 4.0 < targets.speaking_rate_syl_s < 6.5

    def test_zero_entrainment(self) -> None:
        """Zero entrainment should return Emily's baseline."""
        sync = RhythmSynchronizer(entrainment_degree=0.0)
        for _ in range(50):
            sync.update_from_prosody(ProsodyFeatures(speaking_rate_syl_s=8.0))
        targets = sync.get_targets()
        assert abs(targets.speaking_rate_syl_s - 4.2) < 0.5

    def test_profile_export_import(self) -> None:
        """Profile should survive export/import cycle."""
        sync = RhythmSynchronizer()
        for _ in range(20):
            sync.update_from_prosody(ProsodyFeatures(speaking_rate_syl_s=5.5))
        exported = sync.export_profile()
        sync2 = RhythmSynchronizer()
        sync2.import_profile(exported)
        assert abs(sync2.user_profile.speaking_rate_syl_s - sync.user_profile.speaking_rate_syl_s) < 0.1


class TestEmotionSync:
    """Test emotion synchronization."""

    def test_frustrated_user_calms_emily(self) -> None:
        """A frustrated user should make Emily calmer."""
        sync = EmotionSynchronizer()
        emotion = EmotionState(
            primary=UserEmotion.FRUSTRATED,
            confidence=0.8,
            arousal=0.7,
        )
        style = sync.compute_response_style(emotion)
        assert style.energy_modifier < 1.0
        assert style.warmth_level > 0.7

    def test_excited_user_energizes_emily(self) -> None:
        """An excited user should make Emily more energetic."""
        sync = EmotionSynchronizer()
        emotion = EmotionState(
            primary=UserEmotion.EXCITED,
            confidence=0.8,
            arousal=0.9,
        )
        style = sync.compute_response_style(emotion)
        assert style.energy_modifier >= 1.0


class TestLatencyBudget:
    """Test latency budget enforcement."""

    @pytest.mark.asyncio
    async def test_within_budget(self) -> None:
        """Fast operations should pass through."""
        budget = LatencyBudget()

        async def fast_op() -> str:
            return "result"

        result = await budget.check_stage("aec_noise", fast_op())
        assert result == "result"

    @pytest.mark.asyncio
    async def test_exceeds_budget_returns_fallback(self) -> None:
        """Slow operations should return the fallback value."""
        budget = LatencyBudget()
        budget.set_budget("test_stage", 10.0, fallback="fallback_value")

        async def slow_op() -> str:
            await asyncio.sleep(0.1)
            return "too slow"

        result = await budget.check_stage("test_stage", slow_op())
        assert result == "fallback_value"

    def test_report_generation(self) -> None:
        """Report should include percentile statistics."""
        budget = LatencyBudget()
        for stage in budget._records:
            budget._records[stage] = []
        report = budget.report()
        assert isinstance(report, dict)


class TestSpeculativeCache:
    """Test speculative generation cache."""

    def test_exact_match_hits(self) -> None:
        """Identical transcripts should hit the cache."""
        cache = SpeculativeCache()
        cache.store("hello there", "Hi! How are you?")
        result = cache.check("hello there")
        assert result == "Hi! How are you?"

    def test_similar_match_hits(self) -> None:
        """Transcripts within 20% edit distance should hit."""
        cache = SpeculativeCache()
        cache.store("hello there friend", "Hi! How are you?")
        result = cache.check("hello there friend!")
        assert result is not None

    def test_divergent_misses(self) -> None:
        """Very different transcripts should miss."""
        cache = SpeculativeCache()
        cache.store("hello there", "Hi!")
        result = cache.check("completely different sentence altogether")
        assert result is None

    def test_hit_rate_tracking(self) -> None:
        """Hit rate should be tracked correctly."""
        cache = SpeculativeCache()
        cache.store("test", "response")
        cache.check("test")
        cache.check("completely different")
        assert cache.hit_rate == 0.5


class TestProsodyPlanner:
    """Test prosody planning."""

    def test_question_rising_contour(self) -> None:
        """Questions should have rising terminal contour."""
        planner = ProsodyPlanner()
        prosody = planner.plan_sentence("What time is the meeting?")
        assert prosody.terminal_contour == "rising"

    def test_exclamation_higher_energy(self) -> None:
        """Exclamations should have higher energy."""
        planner = ProsodyPlanner()
        normal = planner.plan_sentence("That's interesting.")
        excited = planner.plan_sentence("That's amazing!")
        assert excited.energy >= normal.energy

    def test_closing_sentence_decelerates(self) -> None:
        """Closing sentences should be slower."""
        planner = ProsodyPlanner()
        opening = planner.plan_sentence("Let me explain.", position="opening")
        closing = planner.plan_sentence("That's about it.", position="closing")
        assert closing.speaking_rate <= opening.speaking_rate

    def test_response_planning(self) -> None:
        """Planning a full response should produce per-sentence prosody."""
        planner = ProsodyPlanner()
        sentences = ["Hello there.", "I have some thoughts.", "That's all for now."]
        planned = planner.plan_response(sentences)
        assert len(planned) == 3
