from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from config import STTConfig
from perception.audio.streaming_stt import StreamingSTTEngine


class _FakeModel:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] | None = None

    def transcribe(self, _audio: np.ndarray, **kwargs: object):
        self.last_kwargs = kwargs
        segment = SimpleNamespace(text="hello", no_speech_prob=0.1, words=[])
        info = SimpleNamespace(language="en", language_probability=1.0)
        return iter([segment]), info


@pytest.mark.asyncio
async def test_streaming_stt_uses_configured_vad_and_no_speech_threshold() -> None:
    config = STTConfig(
        language="en",
        use_whisper_vad=False,
        whisper_vad_threshold=0.2,
        whisper_vad_min_speech_ms=50,
        whisper_vad_min_silence_ms=450,
        no_speech_threshold=0.6,
    )
    engine = StreamingSTTEngine(config)
    fake_model = _FakeModel()
    engine._model = fake_model
    engine._audio_buffer = [np.ones(16000, dtype=np.float32) * 0.05]

    result = await engine._transcribe_buffer()

    assert result is not None
    assert fake_model.last_kwargs is not None
    assert fake_model.last_kwargs["vad_filter"] is False
    assert fake_model.last_kwargs["no_speech_threshold"] == 0.6
    assert fake_model.last_kwargs["vad_parameters"] == {
        "threshold": 0.2,
        "min_speech_duration_ms": 50,
        "min_silence_duration_ms": 450,
    }


def test_streaming_stt_profile_selects_accuracy_beam_size() -> None:
    fast = StreamingSTTEngine(
        STTConfig(profile="fast", voice_fast_beam_size=1, voice_accurate_beam_size=4)
    )
    accurate = StreamingSTTEngine(
        STTConfig(profile="accurate", voice_fast_beam_size=1, voice_accurate_beam_size=4)
    )
    assert fast._streaming_beam_size == 1
    assert accurate._streaming_beam_size == 4


def test_streaming_stt_resample_handles_44100_input() -> None:
    audio = np.random.randn(44100).astype(np.float32)
    out = StreamingSTTEngine._downsample(audio, 44100)
    assert out.dtype == np.float32
    assert len(out) == pytest.approx(16000, abs=10)


@pytest.mark.asyncio
async def test_streaming_stt_uses_configured_low_confidence_reject_threshold() -> None:
    engine = StreamingSTTEngine(
        STTConfig(streaming_reject_low_confidence=0.8, streaming_commit_confidence=0.7)
    )
    engine._committed_words = [SimpleNamespace(text="quiet", confidence=0.75, is_committed=False)]
    engine._speculative_words = []
    engine._buffer_duration_s = 1.0

    final = await engine.commit_utterance()
    assert final.text == ""
    assert final.confidence == 0.0


@pytest.mark.asyncio
async def test_streaming_stt_rejects_repetitive_fragmented_transcript() -> None:
    engine = StreamingSTTEngine(
        STTConfig(
            streaming_min_final_words=3,
            streaming_min_unique_ratio=0.45,
            streaming_max_repeat_ratio=0.5,
            streaming_short_utterance_confidence=0.8,
        )
    )
    engine._committed_words = [
        SimpleNamespace(text="we'll", confidence=0.62, is_committed=False),
        SimpleNamespace(text="be", confidence=0.61, is_committed=False),
        SimpleNamespace(text="right", confidence=0.64, is_committed=False),
        SimpleNamespace(text="back", confidence=0.63, is_committed=False),
        SimpleNamespace(text="we'll", confidence=0.61, is_committed=False),
        SimpleNamespace(text="we'll", confidence=0.6, is_committed=False),
    ]
    engine._speculative_words = []
    engine._buffer_duration_s = 1.2

    final = await engine.commit_utterance()
    assert final.text == ""
    assert final.words == []


@pytest.mark.asyncio
async def test_streaming_stt_keeps_short_high_confidence_utterance() -> None:
    engine = StreamingSTTEngine(
        STTConfig(
            streaming_min_final_words=3,
            streaming_short_utterance_confidence=0.8,
        )
    )
    engine._committed_words = [
        SimpleNamespace(text="hi", confidence=0.92, is_committed=False),
        SimpleNamespace(text="emily", confidence=0.9, is_committed=False),
    ]
    engine._speculative_words = []
    engine._buffer_duration_s = 0.7

    final = await engine.commit_utterance()
    assert final.text.lower() == "hi emily"
    assert final.confidence > 0.85
