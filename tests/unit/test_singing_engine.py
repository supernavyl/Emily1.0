"""Unit tests for voice.singing — SingingManager and engine selection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import numpy as np
import pytest

from config import SingingConfig


@pytest.fixture()
def singing_config() -> SingingConfig:
    """Return a default SingingConfig for testing."""
    return SingingConfig()


@pytest.fixture()
def disabled_config() -> SingingConfig:
    """Return a SingingConfig with all engines disabled."""
    return SingingConfig(
        enabled=False,
        rvc={"enabled": False},
        musicgen={"enabled": False},
        suno={"enabled": False},
    )


def test_singing_config_defaults(singing_config: SingingConfig) -> None:
    """SingingConfig instantiates with expected defaults."""
    assert singing_config.enabled is True
    assert singing_config.primary == "musicgen"
    assert singing_config.fallback == "suno"
    assert singing_config.rvc.f0_method == "rmvpe"
    assert singing_config.musicgen.model_size == "small"
    assert singing_config.suno.timeout_seconds == 120


def test_singing_config_invalid_engine() -> None:
    """Invalid engine name in primary/fallback raises validation error."""
    with pytest.raises(Exception):
        SingingConfig(primary="nonexistent")


def test_singing_config_invalid_f0_method() -> None:
    """Invalid f0_method raises validation error."""
    with pytest.raises(Exception):
        SingingConfig(rvc={"f0_method": "invalid"})


def test_singing_config_invalid_model_size() -> None:
    """Invalid musicgen model_size raises validation error."""
    with pytest.raises(Exception):
        SingingConfig(musicgen={"model_size": "huge"})


def test_manager_builds_engine_list(singing_config: SingingConfig) -> None:
    """SingingManager creates engines in config-driven priority order."""
    from voice.singing import SingingManager

    manager = SingingManager(singing_config)
    names = [e.name for e in manager._engine_list]
    assert names[0] == "musicgen"
    assert names[1] == "suno"
    assert "rvc" in names


@pytest.mark.asyncio
async def test_manager_load_all_engines(singing_config: SingingConfig) -> None:
    """SingingManager.load() calls load() on every engine without crashing."""
    from voice.singing import SingingManager

    manager = SingingManager(singing_config)
    for eng in manager._engine_list:
        eng.load = AsyncMock()

    await manager.load()
    for eng in manager._engine_list:
        eng.load.assert_awaited_once()


def test_select_engine_by_mode(singing_config: SingingConfig) -> None:
    """_select_engine maps mode strings to the correct engine type."""
    from voice.singing import SingingManager

    manager = SingingManager(singing_config)
    for eng in manager._engine_list:
        eng._available = True

    assert manager._select_engine("generate").name == "musicgen"
    assert manager._select_engine("voice_convert").name == "rvc"
    assert manager._select_engine("full_song").name == "suno"


def test_select_engine_falls_back_when_preferred_unavailable(
    singing_config: SingingConfig,
) -> None:
    """When the preferred engine is not available, the first available is used."""
    from voice.singing import SingingManager

    manager = SingingManager(singing_config)
    for eng in manager._engine_list:
        eng._available = eng.name == "suno"

    selected = manager._select_engine("generate")
    assert selected.name == "suno"


def test_select_engine_raises_when_none_available(
    singing_config: SingingConfig,
) -> None:
    """RuntimeError when no engine is available."""
    from voice.singing import SingingManager

    manager = SingingManager(singing_config)
    with pytest.raises(RuntimeError, match="No singing engine available"):
        manager._select_engine()


def test_resample_passthrough() -> None:
    """_resample_to_target is a no-op when source_sr == target."""
    from voice.singing import TARGET_SR, _resample_to_target

    audio = np.ones(1000, dtype=np.float32)
    result = _resample_to_target(audio, TARGET_SR)
    assert len(result) == 1000


def test_resample_changes_length() -> None:
    """_resample_to_target changes the number of samples when sr differs."""
    from voice.singing import TARGET_SR, _resample_to_target

    audio = np.ones(48_000, dtype=np.float32)
    result = _resample_to_target(audio, 48_000)
    assert abs(len(result) - TARGET_SR) < 2
