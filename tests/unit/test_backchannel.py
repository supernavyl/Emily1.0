"""
Tests for the backchannel generation engine.

Verifies:
- Type selection logic (elicitors, emotion, surprise, word count)
- COMPLETION type triggered by high prediction score
- Token diversity and non-repetition
- 4-second cooldown enforcement
- Phrase-boundary safety (pause_type + stress_pattern)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

from conversation.backchannel import (
    BackchannelEngine,
    BackchannelEvent,
    BackchannelType,
)
from perception.audio.prosody_analyzer import ProsodyFeatures


@pytest.fixture
def engine() -> BackchannelEngine:
    """Create a fresh backchannel engine."""
    return BackchannelEngine()


class TestTypeSelection:
    """Test that the correct backchannel type is selected for each context."""

    @pytest.mark.asyncio
    async def test_elicitor_selects_continuer(self, engine: BackchannelEngine) -> None:
        """Backchannel elicitors like 'you know' should select CONTINUER."""
        event = await engine.should_backchannel(
            partial_text="it was really hard, you know",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is not None
        assert event.bc_type == BackchannelType.CONTINUER

    @pytest.mark.asyncio
    async def test_negative_emotion_selects_empathy(self, engine: BackchannelEngine) -> None:
        """Negative valence emotion should select EMPATHY."""

        @dataclass
        class FakeEmotion:
            valence: float = -0.5
            arousal: float = 0.3

        event = await engine.should_backchannel(
            partial_text="it was such a terrible day at work today",
            emotion=FakeEmotion(),
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is not None
        assert event.bc_type == BackchannelType.EMPATHY

    @pytest.mark.asyncio
    async def test_high_arousal_positive_selects_agreement(self, engine: BackchannelEngine) -> None:
        """High arousal + positive valence should select AGREEMENT."""

        @dataclass
        class FakeEmotion:
            valence: float = 0.6
            arousal: float = 0.7

        event = await engine.should_backchannel(
            partial_text="that was such a great thing they did for us",
            emotion=FakeEmotion(),
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is not None
        assert event.bc_type == BackchannelType.AGREEMENT

    @pytest.mark.asyncio
    async def test_surprise_indicators(self, engine: BackchannelEngine) -> None:
        """Surprise phrases like 'guess what' should select SURPRISE."""
        event = await engine.should_backchannel(
            partial_text="so guess what happened to me at the office today",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is not None
        assert event.bc_type == BackchannelType.SURPRISE

    @pytest.mark.asyncio
    async def test_long_text_selects_acknowledgment(self, engine: BackchannelEngine) -> None:
        """Partial text > 10 words should select ACKNOWLEDGMENT."""
        event = await engine.should_backchannel(
            partial_text="so I went to the store and then I picked up some groceries for dinner",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is not None
        assert event.bc_type == BackchannelType.ACKNOWLEDGMENT

    @pytest.mark.asyncio
    async def test_short_text_returns_none(self, engine: BackchannelEngine) -> None:
        """Text with <= 5 words and no other signal should return None."""
        event = await engine.should_backchannel(
            partial_text="hi there",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is None


class TestCompletionType:
    """Test COMPLETION backchannel triggered by high prediction score."""

    @pytest.mark.asyncio
    async def test_high_score_selects_completion(self, engine: BackchannelEngine) -> None:
        """Completion prediction > 0.90 should select COMPLETION."""
        event = await engine.should_backchannel(
            partial_text="I think we should",
            completion_prediction_score=0.95,
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert event is not None
        assert event.bc_type == BackchannelType.COMPLETION
        assert event.token != ""

    @pytest.mark.asyncio
    async def test_low_score_does_not_select_completion(self, engine: BackchannelEngine) -> None:
        """Completion prediction <= 0.90 should not select COMPLETION."""
        event = await engine.should_backchannel(
            partial_text="so I went to the store and picked up some items",
            completion_prediction_score=0.5,
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        if event is not None:
            assert event.bc_type != BackchannelType.COMPLETION


class TestCooldown:
    """Test the 4-second minimum interval between backchannels."""

    @pytest.mark.asyncio
    async def test_cooldown_blocks_rapid_fire(self, engine: BackchannelEngine) -> None:
        """A second backchannel within 4 seconds should be blocked."""
        first = await engine.should_backchannel(
            partial_text="it was such a long and terrible experience for everyone",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert first is not None

        second = await engine.should_backchannel(
            partial_text="and then something else happened right after that moment",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert second is None

    @pytest.mark.asyncio
    async def test_cooldown_expires(self, engine: BackchannelEngine) -> None:
        """After the cooldown, a new backchannel should be allowed."""
        first = await engine.should_backchannel(
            partial_text="it was such a long and terrible experience for everyone",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert first is not None

        engine._last_bc_time = time.monotonic() - 5.0

        second = await engine.should_backchannel(
            partial_text="and then something else happened right after that moment",
            prosody=ProsodyFeatures(pause_type="silence"),
        )
        assert second is not None


class TestTokenDiversity:
    """Test that tokens are not repeated consecutively."""

    @pytest.mark.asyncio
    async def test_no_immediate_repeat(self, engine: BackchannelEngine) -> None:
        """Consecutive backchannels should not use the same token."""
        tokens: list[str] = []
        for _ in range(10):
            engine._last_bc_time = 0.0
            event = await engine.should_backchannel(
                partial_text="it was such a terrible and awful thing that happened to us",
                prosody=ProsodyFeatures(pause_type="silence"),
            )
            if event is not None:
                tokens.append(event.token)

        for i in range(1, len(tokens)):
            if tokens[i - 1] == tokens[i]:
                pytest.fail(f"Token repeated consecutively: {tokens[i]}")


class TestPhraseBoundarySafety:
    """Test is_safe_to_insert with prosody data."""

    def test_safe_on_silence(self, engine: BackchannelEngine) -> None:
        """Silence pause type should be safe for insertion."""
        prosody = ProsodyFeatures(pause_type="silence", stress_pattern=[0.3])
        assert engine.is_safe_to_insert(prosody) is True

    def test_safe_on_breath(self, engine: BackchannelEngine) -> None:
        """Breath pause type should be safe."""
        prosody = ProsodyFeatures(pause_type="breath", stress_pattern=[0.2])
        assert engine.is_safe_to_insert(prosody) is True

    def test_safe_on_filled(self, engine: BackchannelEngine) -> None:
        """Filled pause should be safe."""
        prosody = ProsodyFeatures(pause_type="filled", stress_pattern=[])
        assert engine.is_safe_to_insert(prosody) is True

    def test_unsafe_mid_speech(self, engine: BackchannelEngine) -> None:
        """No pause (pause_type='none') should block insertion."""
        prosody = ProsodyFeatures(pause_type="none", stress_pattern=[0.3])
        assert engine.is_safe_to_insert(prosody) is False

    def test_unsafe_on_stressed_syllable(self, engine: BackchannelEngine) -> None:
        """High stress pattern value should block insertion."""
        prosody = ProsodyFeatures(pause_type="silence", stress_pattern=[0.9])
        assert engine.is_safe_to_insert(prosody) is False

    def test_none_prosody_is_safe(self, engine: BackchannelEngine) -> None:
        """None prosody should default to safe (backwards compatibility)."""
        assert engine.is_safe_to_insert(None) is True

    @pytest.mark.asyncio
    async def test_unsafe_prosody_blocks_backchannel(self, engine: BackchannelEngine) -> None:
        """should_backchannel returns None when prosody indicates mid-speech."""
        event = await engine.should_backchannel(
            partial_text="it was such a long and terrible experience for everyone",
            prosody=ProsodyFeatures(pause_type="none", stress_pattern=[0.3]),
        )
        assert event is None
