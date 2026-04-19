"""Tests for the SNAC streaming decoder used by Orpheus TTS."""

from __future__ import annotations

import numpy as np
import pytest

from voice_engine.providers.tts.snac_stream_decoder import SNACStreamDecoder

SNAC_SAMPLE_RATE = 24000


def _fake_codes() -> list[list[int]]:
    """Return one Orpheus frame: 7 code positions, values inside SNAC codebook."""
    return [[100 + i * 13 for i in range(7)]]


def test_decoder_initializes_on_cpu() -> None:
    decoder = SNACStreamDecoder(device="cpu")

    assert decoder.sample_rate == SNAC_SAMPLE_RATE
    assert decoder.device == "cpu"


def test_decode_frame_returns_nonempty_float32_pcm() -> None:
    decoder = SNACStreamDecoder(device="cpu")

    pcm = decoder.decode_frame(_fake_codes())

    assert isinstance(pcm, np.ndarray)
    assert pcm.dtype == np.float32
    assert pcm.ndim == 1
    assert pcm.size > 0
    assert np.all(np.abs(pcm) <= 1.5)


def test_reset_clears_state_without_error() -> None:
    decoder = SNACStreamDecoder(device="cpu")
    decoder.decode_frame(_fake_codes())

    decoder.reset()

    pcm2 = decoder.decode_frame(_fake_codes())
    assert pcm2.size > 0


def test_decode_empty_codes_returns_empty() -> None:
    decoder = SNACStreamDecoder(device="cpu")

    pcm = decoder.decode_frame([])

    assert pcm.size == 0
    assert pcm.dtype == np.float32


def test_decode_wrong_frame_size_raises() -> None:
    decoder = SNACStreamDecoder(device="cpu")

    with pytest.raises(ValueError, match="7 codes"):
        decoder.decode_frame([[1, 2, 3]])  # 3 codes, not 7


@pytest.mark.integration
def test_decoder_on_cuda1_if_available() -> None:
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
        pytest.skip("CUDA:1 not available")

    decoder = SNACStreamDecoder(device="cuda:1")
    pcm = decoder.decode_frame(_fake_codes())

    assert pcm.dtype == np.float32
    assert pcm.size > 0
