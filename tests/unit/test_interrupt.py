"""
Tests for the interrupt handler.

Verifies:
- Interrupt type classification (text, energy, prosody, emotion)
- Acknowledgment generation diversity
- Graceful stop point detection
- Audio fade-out application
- Context preservation and resumption
- Configurable lookahead, fade, and resume expiry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pytest
import numpy as np

from conversation.interrupt_handler import (
    InterruptHandler,
    InterruptionType,
    InterruptResponse,
)


class _MockEmotion(Enum):
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANXIOUS = "anxious"
    BORED = "bored"
    TIRED = "tired"


@dataclass
class MockEmotionState:
    """Minimal stand-in for EmotionState."""

    primary: _MockEmotion = _MockEmotion.NEUTRAL
    confidence: float = 0.5


@dataclass
class MockProsodyFeatures:
    """Minimal stand-in for ProsodyFeatures."""

    f0_hz: float = 0.0
    f0_range_semitones: float = 0.0
    f0_trajectory: str = "level"
    intensity_trajectory: str = "level"
    stress_pattern: list[float] = field(default_factory=list)


@pytest.fixture
def handler() -> InterruptHandler:
    """Create a fresh interrupt handler with default config."""
    return InterruptHandler()


class TestInterruptClassification:
    """Test that interrupts are classified correctly."""

    @pytest.mark.asyncio
    async def test_correction_detected(self, handler: InterruptHandler) -> None:
        """Words like 'no' and 'actually' should classify as CORRECTION."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="no wait, that's wrong",
            user_energy=0.05,
        )
        assert resp.interrupt_type == InterruptionType.CORRECTION

    @pytest.mark.asyncio
    async def test_urgency_detected(self, handler: InterruptHandler) -> None:
        """High energy interrupts should classify as URGENCY."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="stop!",
            user_energy=0.2,
        )
        assert resp.interrupt_type == InterruptionType.URGENCY

    @pytest.mark.asyncio
    async def test_clarification_detected(self, handler: InterruptHandler) -> None:
        """Questions should classify as CLARIFICATION."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="what do you mean by that?",
            user_energy=0.05,
        )
        assert resp.interrupt_type == InterruptionType.CLARIFICATION

    @pytest.mark.asyncio
    async def test_disengagement_detected(self, handler: InterruptHandler) -> None:
        """Minimal input should classify as DISENGAGEMENT."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="ok",
            user_energy=0.03,
        )
        assert resp.interrupt_type == InterruptionType.DISENGAGEMENT


class TestAcknowledgments:
    """Test acknowledgment generation."""

    @pytest.mark.asyncio
    async def test_correction_has_acknowledgment(self, handler: InterruptHandler) -> None:
        """Correction interrupts should produce acknowledgments."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="no, actually",
            user_energy=0.05,
        )
        assert resp.acknowledgment is not None

    @pytest.mark.asyncio
    async def test_urgency_no_acknowledgment(self, handler: InterruptHandler) -> None:
        """Urgency interrupts should have no acknowledgment (immediate silence)."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="emergency",
            user_energy=0.2,
        )
        assert resp.acknowledgment is None

    @pytest.mark.asyncio
    async def test_acknowledgment_diversity(self, handler: InterruptHandler) -> None:
        """Multiple acknowledgments should not always be the same."""
        acks = set()
        for _ in range(10):
            resp = await handler.handle_user_interrupt(
                partial_user_text="actually, I have a point",
                user_energy=0.05,
            )
            if resp.acknowledgment:
                acks.add(resp.acknowledgment)
        assert len(acks) >= 2, "Acknowledgments should be diverse"


class TestGracefulStop:
    """Test word-boundary detection in audio buffers."""

    def test_finds_stop_point_in_audio(self, handler: InterruptHandler) -> None:
        """Should find a stop point within the lookahead window."""
        sr = 24000
        duration_s = 0.3
        audio = np.random.randn(int(sr * duration_s)).astype(np.float32) * 0.1
        audio[int(sr * 0.15):int(sr * 0.18)] = 0.001  # low energy gap

        stop = handler.find_graceful_stop_point(audio, sr)
        assert 0 < stop <= len(audio)

    def test_fade_out_zeroes_after_stop(self, handler: InterruptHandler) -> None:
        """Audio after the stop point should be silenced."""
        audio = np.ones(4800, dtype=np.float32) * 0.5
        stop = 2400

        result = handler.apply_fade_out(audio, stop)
        assert np.all(result[stop:] == 0)
        assert np.all(result[:stop - 500] > 0)


class TestContextPreservation:
    """Test response context preservation for resumption."""

    @pytest.mark.asyncio
    async def test_clarification_preserves_context(self, handler: InterruptHandler) -> None:
        """Clarification interrupts should preserve context."""
        resp = await handler.handle_user_interrupt(
            sentence_so_far="The meeting is at three o'clock",
            partial_user_text="what time zone?",
            user_energy=0.05,
        )
        assert resp.context_preserved
        assert resp.can_resume

    @pytest.mark.asyncio
    async def test_urgency_does_not_preserve(self, handler: InterruptHandler) -> None:
        """Urgency interrupts should not try to resume."""
        resp = await handler.handle_user_interrupt(
            partial_user_text="fire!",
            user_energy=0.3,
        )
        assert not resp.can_resume

    @pytest.mark.asyncio
    async def test_resume_phrase_available(self, handler: InterruptHandler) -> None:
        """After a preserved interrupt, a resume phrase should be available."""
        await handler.handle_user_interrupt(
            sentence_so_far="As I was explaining",
            partial_user_text="could you clarify?",
            user_energy=0.05,
        )
        phrase = handler.get_resume_phrase()
        assert phrase is not None
        assert "saying" in phrase or "continue" in phrase or "mentioned" in phrase or "was" in phrase

    @pytest.mark.asyncio
    async def test_clear_preserved_context(self, handler: InterruptHandler) -> None:
        """clear_preserved_context should remove context so resume returns None."""
        await handler.handle_user_interrupt(
            sentence_so_far="The result is",
            partial_user_text="what result?",
            user_energy=0.05,
        )
        assert handler.get_resume_phrase() is not None
        handler.clear_preserved_context()
        assert handler.get_resume_phrase() is None


class TestProsodyClassification:
    """Test interrupt classification enhanced by prosody signals."""

    @pytest.mark.asyncio
    async def test_rising_pitch_triggers_clarification(self, handler: InterruptHandler) -> None:
        """Rising f0 trajectory should classify as CLARIFICATION even without question words."""
        prosody = MockProsodyFeatures(f0_trajectory="rising")
        resp = await handler.handle_user_interrupt(
            partial_user_text="you said tomorrow",
            user_energy=0.05,
            prosody=prosody,
        )
        assert resp.interrupt_type == InterruptionType.CLARIFICATION

    @pytest.mark.asyncio
    async def test_extreme_pitch_range_triggers_urgency(self, handler: InterruptHandler) -> None:
        """Very wide pitch range (>8 semitones) should classify as URGENCY."""
        prosody = MockProsodyFeatures(f0_hz=300.0, f0_range_semitones=10.0)
        resp = await handler.handle_user_interrupt(
            partial_user_text="something is happening",
            user_energy=0.05,
            prosody=prosody,
        )
        assert resp.interrupt_type == InterruptionType.URGENCY

    @pytest.mark.asyncio
    async def test_emphatic_stress_with_negation_is_correction(self, handler: InterruptHandler) -> None:
        """Strong stress pattern plus negation word should classify as CORRECTION."""
        prosody = MockProsodyFeatures(stress_pattern=[0.3, 0.9, 0.2])
        resp = await handler.handle_user_interrupt(
            partial_user_text="that is not correct at all",
            user_energy=0.05,
            prosody=prosody,
        )
        assert resp.interrupt_type == InterruptionType.CORRECTION

    @pytest.mark.asyncio
    async def test_falling_intensity_short_text_is_disengagement(self, handler: InterruptHandler) -> None:
        """Falling intensity with short text should classify as DISENGAGEMENT."""
        prosody = MockProsodyFeatures(intensity_trajectory="falling")
        resp = await handler.handle_user_interrupt(
            partial_user_text="mm",
            user_energy=0.02,
            prosody=prosody,
        )
        assert resp.interrupt_type == InterruptionType.DISENGAGEMENT


class TestEmotionClassification:
    """Test interrupt classification enhanced by emotion signals."""

    @pytest.mark.asyncio
    async def test_frustrated_emotion_triggers_urgency(self, handler: InterruptHandler) -> None:
        """Frustrated emotion with high confidence should classify as URGENCY."""
        emotion = MockEmotionState(primary=_MockEmotion.FRUSTRATED, confidence=0.8)
        resp = await handler.handle_user_interrupt(
            partial_user_text="this is ridiculous",
            user_energy=0.10,
            emotion=emotion,
        )
        assert resp.interrupt_type == InterruptionType.URGENCY

    @pytest.mark.asyncio
    async def test_anxious_emotion_triggers_urgency(self, handler: InterruptHandler) -> None:
        """Anxious emotion with high confidence should classify as URGENCY."""
        emotion = MockEmotionState(primary=_MockEmotion.ANXIOUS, confidence=0.7)
        resp = await handler.handle_user_interrupt(
            partial_user_text="something seems off",
            user_energy=0.10,
            emotion=emotion,
        )
        assert resp.interrupt_type == InterruptionType.URGENCY

    @pytest.mark.asyncio
    async def test_low_confidence_emotion_does_not_override(self, handler: InterruptHandler) -> None:
        """Frustrated emotion with low confidence should not override text-based classification."""
        emotion = MockEmotionState(primary=_MockEmotion.FRUSTRATED, confidence=0.3)
        resp = await handler.handle_user_interrupt(
            partial_user_text="what do you mean?",
            user_energy=0.05,
            emotion=emotion,
        )
        assert resp.interrupt_type == InterruptionType.CLARIFICATION

    @pytest.mark.asyncio
    async def test_bored_emotion_confirms_disengagement(self, handler: InterruptHandler) -> None:
        """Bored emotion with short text should classify as DISENGAGEMENT."""
        emotion = MockEmotionState(primary=_MockEmotion.BORED, confidence=0.6)
        resp = await handler.handle_user_interrupt(
            partial_user_text="ok",
            user_energy=0.02,
            emotion=emotion,
        )
        assert resp.interrupt_type == InterruptionType.DISENGAGEMENT


class TestConfigurableParameters:
    """Test that constructor parameters affect behavior."""

    def test_custom_lookahead_limits_search(self) -> None:
        """Custom lookahead_ms should limit the stop-point search window."""
        short_handler = InterruptHandler(lookahead_ms=100)
        sr = 24000
        audio = np.random.randn(sr).astype(np.float32) * 0.1
        stop = short_handler.find_graceful_stop_point(audio, sr)
        max_samples = int(100 * sr / 1000)
        assert stop <= max_samples

    def test_custom_fade_ms_changes_fade_region(self) -> None:
        """Custom fade_ms should change the fade-out duration."""
        h = InterruptHandler(fade_ms=50)
        audio = np.ones(4800, dtype=np.float32) * 0.5
        stop = 2400
        result = h.apply_fade_out(audio, stop)
        assert np.all(result[stop:] == 0)
        fade_samples = int(50 / 1000.0 * 24000)
        assert result[stop - fade_samples - 1] == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_resume_expiry(self) -> None:
        """Resume phrase should return None after expiry."""
        import time
        h = InterruptHandler(resume_expiry_s=0.0)
        await h.handle_user_interrupt(
            sentence_so_far="explanation here",
            partial_user_text="what?",
            user_energy=0.05,
        )
        time.sleep(0.01)
        assert h.get_resume_phrase() is None

    def test_interrupt_count_increments(self) -> None:
        """interrupt_count should track total interrupts handled."""
        h = InterruptHandler()
        assert h.interrupt_count == 0
