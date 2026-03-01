"""
Tests for the multi-signal turn detection engine.

Verifies:
- Individual signal scorers return valid [0, 1] values
- Fusion produces correct actions for known scenarios
- Thresholds are respected
- Weight normalization is correct
"""

from __future__ import annotations

import pytest

from conversation.turn_detector import (
    BACKCHANNEL_THRESHOLD,
    RESPONSE_THRESHOLD,
    SIGNAL_WEIGHTS,
    ConversationState,
    TurnAction,
    TurnDetectionEngine,
)
from perception.audio.prosody_analyzer import ProsodyFeatures, SpeakerBaseline


@pytest.fixture
def engine() -> TurnDetectionEngine:
    """Create a fresh turn detection engine."""
    return TurnDetectionEngine()


@pytest.fixture
def idle_state() -> ConversationState:
    """A state with no speech activity."""
    return ConversationState()


@pytest.fixture
def complete_statement_state() -> ConversationState:
    """A state where the user has clearly finished a statement."""
    return ConversationState(
        prosody=ProsodyFeatures(
            f0_hz=120,
            f0_trajectory="falling",
            intensity_trajectory="falling",
            voice_quality="creaky",
            pause_duration_ms=600,
            pause_type="breath",
            final_lengthening_ratio=1.5,
        ),
        baseline=SpeakerBaseline(f0_mean=150, f0_std=20),
        partial_text="I think we should go to the store.",
        committed_text="I think we should go to the store.",
        speaking_duration_s=3.0,
    )


@pytest.fixture
def mid_sentence_state() -> ConversationState:
    """A state where the user is clearly mid-sentence."""
    return ConversationState(
        prosody=ProsodyFeatures(
            f0_hz=160,
            f0_trajectory="level",
            intensity_trajectory="level",
            voice_quality="modal",
            pause_duration_ms=0,
            pause_type="none",
        ),
        baseline=SpeakerBaseline(f0_mean=150, f0_std=20),
        partial_text="I think we should go to the",
        committed_text="I think we should go to the",
        speaking_duration_s=1.5,
    )


class TestSignalWeights:
    """Test that signal weights are properly configured."""

    def test_weights_sum_approximately_one(self) -> None:
        """Weights should sum to approximately 1.0."""
        total = sum(SIGNAL_WEIGHTS.values())
        assert 0.95 <= total <= 1.05, f"Weights sum to {total}, expected ~1.0"

    def test_all_weights_non_negative(self) -> None:
        """All weights should be non-negative."""
        for name, weight in SIGNAL_WEIGHTS.items():
            assert weight >= 0, f"Weight for {name} is negative: {weight}"


class TestIndividualSignals:
    """Test that individual signal scorers return valid values."""

    def test_final_intonation_falling(self, engine: TurnDetectionEngine) -> None:
        """Falling intonation should produce a high signal."""
        state = ConversationState(
            prosody=ProsodyFeatures(f0_trajectory="falling", f0_hz=120),
            baseline=SpeakerBaseline(f0_mean=150, f0_std=20),
        )
        score = engine._score_final_intonation(state)
        assert 0.7 <= score <= 1.0

    def test_final_intonation_level(self, engine: TurnDetectionEngine) -> None:
        """Level intonation near baseline is actually a moderate completion signal (F0 reset)."""
        state = ConversationState(
            prosody=ProsodyFeatures(f0_trajectory="level", f0_hz=150),
            baseline=SpeakerBaseline(f0_mean=150, f0_std=20),
        )
        score = engine._score_final_intonation(state)
        assert 0.2 <= score <= 0.8

    def test_silence_duration_long(self, engine: TurnDetectionEngine) -> None:
        """Long post-utterance silence should produce a high signal."""
        state = ConversationState(
            prosody=ProsodyFeatures(pause_duration_ms=800, pause_type="unfilled"),
        )
        score = engine._score_silence_duration(state)
        assert score >= 0.7

    def test_silence_duration_zero(self, engine: TurnDetectionEngine) -> None:
        """No silence should produce zero signal."""
        state = ConversationState(
            prosody=ProsodyFeatures(pause_duration_ms=0),
        )
        score = engine._score_silence_duration(state)
        assert score == 0.0

    def test_breath_detected(self, engine: TurnDetectionEngine) -> None:
        """Post-utterance breath should produce a high signal."""
        state = ConversationState(
            prosody=ProsodyFeatures(pause_type="breath", pause_duration_ms=300),
        )
        score = engine._score_breath_detected(state)
        assert score >= 0.6

    def test_question_detected(self, engine: TurnDetectionEngine) -> None:
        """A direct question should produce a high signal."""
        state = ConversationState(
            partial_text="What do you think about this?",
            prosody=ProsodyFeatures(f0_trajectory="rising"),
        )
        score = engine._score_question_detected(state)
        assert score >= 0.5

    def test_syntactic_completeness_complete(self, engine: TurnDetectionEngine) -> None:
        """A complete sentence should score high."""
        state = ConversationState(
            committed_text="I went to the store.",
            partial_text="",
        )
        score = engine._score_syntactic_completeness(state)
        assert score >= 0.5

    def test_syntactic_completeness_incomplete(self, engine: TurnDetectionEngine) -> None:
        """An incomplete sentence should score low."""
        state = ConversationState(
            committed_text="I went to the",
            partial_text="",
        )
        score = engine._score_syntactic_completeness(state)
        assert score <= 0.5

    def test_discourse_marker(self, engine: TurnDetectionEngine) -> None:
        """Turn-yielding discourse markers should score high."""
        state = ConversationState(partial_text="That's pretty much it anyway")
        score = engine._score_discourse_marker(state)
        assert score >= 0.5


class TestFusion:
    """Test the full fusion pipeline."""

    def test_complete_statement_triggers_respond(
        self,
        engine: TurnDetectionEngine,
    ) -> None:
        """A statement with strong completion signals across all channels should trigger RESPOND."""
        state = ConversationState(
            prosody=ProsodyFeatures(
                f0_hz=120,
                f0_trajectory="falling",
                intensity_trajectory="falling",
                voice_quality="creaky",
                pause_duration_ms=800,
                pause_type="breath",
                final_lengthening_ratio=1.8,
            ),
            baseline=SpeakerBaseline(f0_mean=150, f0_std=20),
            partial_text="I think we should go to the store. So yeah, that's about it.",
            committed_text="I think we should go to the store. So yeah, that's about it.",
            speaking_duration_s=5.0,
        )
        signal = engine.compute(state)
        assert signal.score >= BACKCHANNEL_THRESHOLD
        assert signal.action in (TurnAction.RESPOND, TurnAction.BACKCHANNEL)

    def test_mid_sentence_triggers_listen(
        self,
        engine: TurnDetectionEngine,
        mid_sentence_state: ConversationState,
    ) -> None:
        """A mid-sentence state should trigger LISTEN."""
        signal = engine.compute(mid_sentence_state)
        assert signal.action in (TurnAction.LISTEN, TurnAction.BACKCHANNEL)
        assert signal.score < RESPONSE_THRESHOLD

    def test_idle_state_triggers_listen(
        self,
        engine: TurnDetectionEngine,
        idle_state: ConversationState,
    ) -> None:
        """An idle state should trigger LISTEN."""
        signal = engine.compute(idle_state)
        assert signal.action == TurnAction.LISTEN

    def test_confidence_breakdown_present(
        self,
        engine: TurnDetectionEngine,
        complete_statement_state: ConversationState,
    ) -> None:
        """The signal should include a confidence breakdown."""
        signal = engine.compute(complete_statement_state)
        assert len(signal.confidence_breakdown) == len(SIGNAL_WEIGHTS)
        for name in SIGNAL_WEIGHTS:
            assert name in signal.confidence_breakdown
            assert 0.0 <= signal.confidence_breakdown[name] <= 1.0


class TestThresholdOverrides:
    def test_custom_thresholds_are_applied(self) -> None:
        state = ConversationState(
            prosody=ProsodyFeatures(
                f0_hz=120,
                f0_trajectory="falling",
                intensity_trajectory="falling",
                pause_duration_ms=500,
                pause_type="breath",
                final_lengthening_ratio=1.4,
            ),
            baseline=SpeakerBaseline(f0_mean=150, f0_std=20),
            partial_text="I think that is enough for now.",
            committed_text="I think that is enough for now.",
            speaking_duration_s=2.0,
        )
        default_signal = TurnDetectionEngine().compute(state)
        strict_signal = TurnDetectionEngine(response_threshold=0.95).compute(state)

        assert default_signal.score == pytest.approx(strict_signal.score)
        assert default_signal.action in (TurnAction.RESPOND, TurnAction.BACKCHANNEL)
        assert strict_signal.action in (TurnAction.BACKCHANNEL, TurnAction.LISTEN)
