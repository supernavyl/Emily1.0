"""Tests for the Orpheus TTS provider (llama-cpp-python + SNAC)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_engine.providers.tts.orpheus_tts import OrpheusTTS


def _fake_orpheus_stream_chunks() -> list[dict]:
    """Mimic llama-cpp-python streaming output: 7 audio-code tokens + EOS."""
    codes = [1234, 2345, 3456, 987, 654, 321, 1111]
    chunks = [{"choices": [{"text": f"<|audio_code:{c}|>"}]} for c in codes]
    chunks.append({"choices": [{"text": "<|eot|>"}]})
    return chunks


@pytest.mark.asyncio
async def test_synthesize_empty_text_returns_empty_array() -> None:
    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls,
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_llama_cls.return_value.create_completion.return_value = iter(
            _fake_orpheus_stream_chunks()
        )
        mock_decoder_cls.return_value.decode_frame.return_value = np.zeros(512, dtype=np.float32)
        mock_decoder_cls.return_value.sample_rate = 24000

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audio = await tts.synthesize("   ")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.size == 0


@pytest.mark.asyncio
async def test_synthesize_returns_float32_pcm_24khz() -> None:
    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls,
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_llama_cls.return_value.create_completion.return_value = iter(
            _fake_orpheus_stream_chunks()
        )
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

    def _new_stream(*_a, **_kw):
        return iter(_fake_orpheus_stream_chunks())

    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls,
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_llama_cls.return_value = MagicMock(create_completion=_new_stream)
        mock_decoder_cls.return_value.decode_frame.return_value = (
            np.ones(1024, dtype=np.float32) * 0.1
        )
        mock_decoder_cls.return_value.sample_rate = 24000

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audios: list[np.ndarray] = []
        async for chunk in tts.synthesize_stream(_text_chunks()):
            audios.append(chunk)

    assert len(audios) == 2
    for a in audios:
        assert a.dtype == np.float32
        assert a.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_honors_cancellation() -> None:
    async def _text_chunks() -> AsyncIterator[str]:
        yield "this should be cancelled"
        await asyncio.sleep(1.0)
        yield "never reached"

    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls,
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls,
    ):
        mock_llama_cls.return_value.create_completion.return_value = iter(
            _fake_orpheus_stream_chunks()
        )
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

    # pylint: disable=protected-access  — reading state for test
    assert tts._voice == "tara"
