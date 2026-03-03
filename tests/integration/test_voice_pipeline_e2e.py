"""Integration test: Voice pipeline components.

Tests STT → LLM → TTS chain with mocked audio devices.
Verifies that each component can be instantiated and produces
expected output types.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.mark.asyncio
async def test_prosody_controller_produces_valid_params():
    """ProsodyController.compute() should return bounded ProsodyParams."""
    from voice.prosody import ProsodyController

    pc = ProsodyController()

    # Test with various emotional states
    states = [
        {"engagement": 0.9, "confidence": 0.9, "concern": 0.0, "enthusiasm": 0.9},
        {"engagement": 0.1, "confidence": 0.1, "concern": 0.9, "enthusiasm": 0.1},
        {},  # Default
    ]

    for state in states:
        pc.reset_position()
        params = pc.compute("Hello, how are you?", state)
        assert 0.7 <= params.speed <= 1.8, f"Speed out of range: {params.speed}"
        assert 0.8 <= params.pitch <= 1.3, f"Pitch out of range: {params.pitch}"
        assert 0.6 <= params.energy <= 1.4, f"Energy out of range: {params.energy}"
        assert params.pause_after_ms >= 0
        assert params.pause_before_ms >= 0


@pytest.mark.asyncio
async def test_expressive_engine_detects_patterns():
    """ExpressiveEngine.process() should detect laugh and hesitation patterns."""
    from voice.expressive_engine import ExpressiveEngine, TextSegment

    engine = ExpressiveEngine(voice_pitch_hz=210.0)

    # "haha" should produce an audio segment
    segments = engine.process("That's so funny haha")
    types = [type(s).__name__ for s in segments]
    assert "AudioSegment" in types, f"Expected AudioSegment in {types}"

    # Pure text should produce only TextSegment
    segments = engine.process("Hello there")
    assert all(isinstance(s, TextSegment) for s in segments)


@pytest.mark.asyncio
async def test_sentence_splitter():
    """ProsodyController.split_into_sentences handles abbreviations."""
    from voice.prosody import ProsodyController

    sentences = ProsodyController.split_into_sentences(
        "Dr. Smith went to the store. He bought 3.5 kg of flour. That's a lot... isn't it?"
    )
    assert len(sentences) >= 3
    assert any("Dr." in s for s in sentences)
    assert any("..." in s for s in sentences)


@pytest.mark.asyncio
async def test_emily_tts_provider_empty_text():
    """EmilyTTSProvider.synthesize('') should return empty array."""
    from voice_engine.providers.tts.emily_tts import EmilyTTSProvider

    mock_manager = MagicMock()
    provider = EmilyTTSProvider(mock_manager)

    result = await provider.synthesize("")
    assert isinstance(result, np.ndarray)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_breath_injector_synthetic_generation():
    """BreathInjector should generate synthetic breaths when no WAV files exist."""
    from voice.breath_injector import BreathInjector, BreathType

    injector = BreathInjector()
    await injector.load()

    # Should have synthetic breaths for each type
    for bt in BreathType:
        assert len(injector._library[bt]) > 0, f"No breaths for {bt.name}"
