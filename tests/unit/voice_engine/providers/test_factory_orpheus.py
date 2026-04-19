"""Factory returns OrpheusTTS for orpheus config, falls back to Kokoro."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from voice_engine.config import VoiceEngineConfig
from voice_engine.providers.factory import ProviderFactory


def _cfg(**overrides: object) -> VoiceEngineConfig:
    return VoiceEngineConfig(_env_file=None, **overrides)


def test_factory_returns_orpheus_tts_for_orpheus_config() -> None:
    cfg = _cfg(tts_provider="orpheus")

    with (
        patch("voice_engine.providers.tts.orpheus_tts.Llama"),
        patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder"),
    ):
        provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "OrpheusTTS"


def test_factory_returns_kokoro_for_kokoro_config() -> None:
    cfg = _cfg(tts_provider="kokoro")

    provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "KokoroTTS"


def test_factory_falls_back_to_kokoro_when_orpheus_init_fails() -> None:
    cfg = _cfg(tts_provider="orpheus", tts_fallback="kokoro")

    with patch(
        "voice_engine.providers.tts.orpheus_tts.OrpheusTTS.__init__",
        side_effect=RuntimeError("simulated load failure"),
    ):
        provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "KokoroTTS"


def test_factory_raises_on_unknown_tts() -> None:
    cfg = _cfg(tts_provider="nonexistent_provider")

    with pytest.raises(ValueError, match="nonexistent_provider"):
        ProviderFactory.create_tts(cfg)
