"""Tests for Orpheus-related voice config defaults.

Tests bypass the .env file via `_env_file=None` to assert the CODE defaults.
The .env file is expected to also be updated in production to match.
"""

from __future__ import annotations

from voice_engine.config import VoiceEngineConfig


def _pure_defaults() -> VoiceEngineConfig:
    return VoiceEngineConfig(_env_file=None)


def test_default_tts_provider_is_orpheus() -> None:
    cfg = _pure_defaults()

    assert cfg.tts_provider == "orpheus"
    assert cfg.tts_fallback == "kokoro"
    assert cfg.tts_voice == "tara"


def test_default_orpheus_model_path_points_to_shipped_gguf() -> None:
    cfg = _pure_defaults()

    assert cfg.orpheus_model_path.endswith("orpheus-3b-0.1-ft-q4_k_m.gguf")
    assert cfg.orpheus_main_gpu == 1
    assert cfg.orpheus_snac_device == "cuda:1"


def test_stt_defaults_pin_whisper_to_cuda1_int8() -> None:
    cfg = _pure_defaults()

    assert cfg.stt_device == "cuda"
    assert cfg.stt_device_index == 1
    assert cfg.stt_compute_type == "int8"
