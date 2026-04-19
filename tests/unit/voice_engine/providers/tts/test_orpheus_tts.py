"""Tests for the Orpheus TTS provider (llama-cpp-python + SNAC)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_engine.providers.tts.orpheus_tts import (
    _ORPHEUS_AUDIO_CODE_OFFSET,
    OrpheusTTS,
)


def _fake_audio_tokens(num_frames: int = 1) -> list[int]:
    """Build a valid stream of Orpheus token IDs that decode to `num_frames` SNAC frames."""
    tokens: list[int] = []
    for _ in range(num_frames):
        for pos in range(7):
            # Each position uses its own codebook offset. A valid code is in [0, 4095].
            code = 500  # safe mid-range value
            tokens.append(_ORPHEUS_AUDIO_CODE_OFFSET + (pos * 4096) + code)
    tokens.append(128258)  # stop token
    return tokens


@pytest.mark.asyncio
async def test_synthesize_empty_text_returns_empty_array() -> None:
    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama"),
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder"),
    ):
        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audio = await tts.synthesize("   ")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.size == 0


@pytest.mark.asyncio
async def test_synthesize_returns_float32_pcm() -> None:
    mock_llm = MagicMock()
    mock_llm.tokenize.return_value = [1, 2, 3]  # arbitrary body tokens
    mock_llm.generate.return_value = iter(_fake_audio_tokens(num_frames=2))

    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama", return_value=mock_llm),
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_decoder_cls.return_value.decode_frame.return_value = np.linspace(
            -0.5, 0.5, 2048, dtype=np.float32
        )
        mock_decoder_cls.return_value.sample_rate = 24000

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audio = await tts.synthesize("hello world")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert audio.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_yields_per_chunk() -> None:
    async def _text_chunks() -> AsyncIterator[str]:
        yield "First sentence."
        yield "Second one."

    mock_llm = MagicMock()
    mock_llm.tokenize.return_value = [1, 2, 3]
    mock_llm.generate.side_effect = lambda *_a, **_kw: iter(_fake_audio_tokens(num_frames=1))

    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama", return_value=mock_llm),
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_decoder_cls.return_value.decode_frame.return_value = (
            np.ones(1024, dtype=np.float32) * 0.1
        )
        mock_decoder_cls.return_value.sample_rate = 24000

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        out: list[np.ndarray] = []
        async for chunk in tts.synthesize_stream(_text_chunks()):
            out.append(chunk)

    assert len(out) == 2
    for a in out:
        assert a.dtype == np.float32
        assert a.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_honors_cancellation() -> None:
    async def _text_chunks() -> AsyncIterator[str]:
        yield "start"
        await asyncio.sleep(1.0)
        yield "never reached"

    mock_llm = MagicMock()
    mock_llm.tokenize.return_value = [1, 2, 3]
    mock_llm.generate.return_value = iter(_fake_audio_tokens(num_frames=1))

    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama", return_value=mock_llm),
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_decoder_cls.return_value.decode_frame.return_value = np.zeros(512, dtype=np.float32)
        mock_decoder_cls.return_value.sample_rate = 24000

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")

        async def _consume() -> None:
            async for _ in tts.synthesize_stream(_text_chunks()):
                pass

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


def test_unknown_voice_falls_back_to_tara() -> None:
    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama"),
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder"),
    ):
        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="not_a_real_voice")

    # pylint: disable=protected-access
    assert tts._voice == "tara"
