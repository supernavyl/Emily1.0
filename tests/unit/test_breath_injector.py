"""Tests for the breath injector module."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from voice_engine.processing.breath_injector import BreathInjector

# ── Task 3: Types and Sample Loader ─────────────────────────────


def test_speech_segment_holds_text() -> None:
    from voice_engine.processing.breath_injector import SpeechSegment

    seg = SpeechSegment(text="Hello world")
    assert seg.text == "Hello world"


def test_breath_segment_holds_audio_and_duration() -> None:
    from voice_engine.processing.breath_injector import BreathSegment

    audio = np.zeros(2400, dtype=np.float32)
    seg = BreathSegment(audio=audio, duration_ms=100)
    assert seg.duration_ms == 100
    assert len(seg.audio) == 2400


def test_load_samples_from_directory(tmp_path: Path) -> None:
    from scipy.io import wavfile

    from voice_engine.processing.breath_injector import BreathSampleLibrary

    for name in ("inhale_short_1.wav", "inhale_medium_1.wav"):
        audio = np.random.randn(2400).astype(np.float32) * 0.1
        wavfile.write(str(tmp_path / name), 24000, audio)

    lib = BreathSampleLibrary(tmp_path)
    assert lib.has_samples()
    sample = lib.pick("short")
    assert isinstance(sample, np.ndarray)
    assert sample.dtype == np.float32


def test_load_samples_empty_dir(tmp_path: Path) -> None:
    from voice_engine.processing.breath_injector import BreathSampleLibrary

    lib = BreathSampleLibrary(tmp_path)
    assert not lib.has_samples()


def test_pick_falls_back_to_silence_when_no_samples(tmp_path: Path) -> None:
    from voice_engine.processing.breath_injector import BreathSampleLibrary

    lib = BreathSampleLibrary(tmp_path)
    sample = lib.pick("medium")
    assert isinstance(sample, np.ndarray)
    assert np.all(sample == 0.0)


# ── Task 4: Heuristic Scorer ────────────────────────────────────


def test_score_short_sentence_low() -> None:
    from voice_engine.processing.breath_injector import score_breath

    result = score_breath(prev_sentence_len=30, prev_end_char=".", cumulative_speech_s=0.0)
    assert 0.2 <= result <= 0.3


def test_score_long_sentence_high() -> None:
    from voice_engine.processing.breath_injector import score_breath

    result = score_breath(prev_sentence_len=120, prev_end_char=".", cumulative_speech_s=0.0)
    assert 0.9 <= result <= 1.1


def test_score_question_mark_bonus() -> None:
    from voice_engine.processing.breath_injector import score_breath

    base = score_breath(prev_sentence_len=60, prev_end_char=".", cumulative_speech_s=0.0)
    with_q = score_breath(prev_sentence_len=60, prev_end_char="?", cumulative_speech_s=0.0)
    assert with_q - base == pytest.approx(0.3, abs=0.01)


def test_score_cumulative_speech_bonus() -> None:
    from voice_engine.processing.breath_injector import score_breath

    no_cum = score_breath(prev_sentence_len=60, prev_end_char=".", cumulative_speech_s=1.0)
    with_cum = score_breath(prev_sentence_len=60, prev_end_char=".", cumulative_speech_s=4.0)
    assert with_cum - no_cum == pytest.approx(0.2, abs=0.01)


def test_should_breathe_density_zero_never() -> None:
    from voice_engine.processing.breath_injector import should_breathe

    assert not should_breathe(score=0.99, density=0.0)


def test_should_breathe_density_one_always() -> None:
    from voice_engine.processing.breath_injector import should_breathe

    assert should_breathe(score=0.01, density=1.0)


# ── Task 5: BreathInjector.process ──────────────────────────────


def _make_injector(
    density: float = 0.5,
    enabled: bool = True,
    respect_llm_tokens: bool = True,
    sample_dir: Path | None = None,
) -> BreathInjector:
    from unittest.mock import MagicMock

    from voice_engine.processing.breath_injector import BreathInjector

    config = MagicMock()
    config.enabled = enabled
    config.density = density
    config.min_silence_ms = 30
    config.max_breath_ms = 400
    config.respect_llm_tokens = respect_llm_tokens
    config.emotional_modulation = False
    return BreathInjector(config, sample_dir=sample_dir or Path("/nonexistent"))


def test_process_disabled_returns_single_speech_segment() -> None:
    from voice_engine.processing.breath_injector import SpeechSegment

    inj = _make_injector(enabled=False)
    segments = inj.process("Hello world.", prev_sentence_len=0, cumulative_speech_s=0.0)
    assert len(segments) == 1
    assert isinstance(segments[0], SpeechSegment)
    assert segments[0].text == "Hello world."


def test_process_inserts_breath_before_sentence_at_high_density() -> None:
    from voice_engine.processing.breath_injector import BreathSegment, SpeechSegment

    inj = _make_injector(density=1.0)
    segments = inj.process(
        "How are you today?",
        prev_sentence_len=80,
        cumulative_speech_s=2.0,
    )
    assert len(segments) >= 2
    assert isinstance(segments[0], BreathSegment)
    assert isinstance(segments[-1], SpeechSegment)
    assert segments[-1].text == "How are you today?"


def test_process_no_breath_at_zero_density() -> None:
    from voice_engine.processing.breath_injector import SpeechSegment

    inj = _make_injector(density=0.0)
    segments = inj.process(
        "Short sentence.",
        prev_sentence_len=100,
        cumulative_speech_s=5.0,
    )
    assert len(segments) == 1
    assert isinstance(segments[0], SpeechSegment)


def test_process_respects_breath_token() -> None:
    from voice_engine.processing.breath_injector import BreathSegment, SpeechSegment

    inj = _make_injector(density=0.0, respect_llm_tokens=True)
    segments = inj.process(
        "First part<breath>second part",
        prev_sentence_len=0,
        cumulative_speech_s=0.0,
    )
    assert len(segments) == 3
    assert isinstance(segments[0], SpeechSegment)
    assert segments[0].text == "First part"
    assert isinstance(segments[1], BreathSegment)
    assert isinstance(segments[2], SpeechSegment)
    assert segments[2].text == "second part"


def test_process_respects_pause_token() -> None:
    from voice_engine.processing.breath_injector import BreathSegment, SpeechSegment

    inj = _make_injector(density=0.0, respect_llm_tokens=True)
    segments = inj.process(
        "Wait<pause:500ms>okay",
        prev_sentence_len=0,
        cumulative_speech_s=0.0,
    )
    assert len(segments) == 3
    assert isinstance(segments[0], SpeechSegment)
    assert isinstance(segments[1], BreathSegment)
    assert segments[1].duration_ms == 500
    assert np.all(segments[1].audio == 0.0)
    assert isinstance(segments[2], SpeechSegment)


def test_process_first_sentence_no_breath() -> None:
    from voice_engine.processing.breath_injector import SpeechSegment

    inj = _make_injector(density=1.0)
    segments = inj.process("Hello!", prev_sentence_len=0, cumulative_speech_s=0.0)
    assert len(segments) == 1
    assert isinstance(segments[0], SpeechSegment)


# ── Task 6: SentenceCollector preserves breath/pause tokens ─────


def test_sentence_collector_preserves_breath_token() -> None:
    from voice_engine.processing.sentence_collector import SentenceCollector

    c = SentenceCollector()
    sentences = c.feed("Hello world. <breath>How are you? ")
    combined = " ".join(sentences)
    assert "<breath>" in combined


def test_sentence_collector_preserves_pause_token() -> None:
    from voice_engine.processing.sentence_collector import SentenceCollector

    c = SentenceCollector()
    sentences = c.feed("Wait here.<pause:300ms> Then go. ")
    combined = " ".join(sentences)
    assert "<pause:300ms>" in combined
