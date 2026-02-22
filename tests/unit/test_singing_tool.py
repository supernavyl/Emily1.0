"""Unit tests for plugins.builtin.singing — SingingTool plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import SingingConfig
from plugins.base import ExecutionContext


@pytest.fixture()
def singing_config() -> SingingConfig:
    return SingingConfig()


@pytest.fixture()
def tool(singing_config: SingingConfig):
    from plugins.builtin.singing import SingingTool
    return SingingTool(singing_config=singing_config)


@pytest.fixture()
def context() -> ExecutionContext:
    return ExecutionContext(session_id="test-session", user_id="test-user")


def test_tool_name_and_schema(tool) -> None:
    """SingingTool has the expected name and JSON schema structure."""
    assert tool.name == "sing"
    schema = tool.to_schema()
    assert schema["name"] == "sing"
    assert "prompt" in schema["parameters"]["properties"]
    assert "mode" in schema["parameters"]["properties"]
    assert "prompt" in schema["parameters"]["required"]


@pytest.mark.asyncio
async def test_dry_run_generate(tool) -> None:
    """dry_run returns a readable description for generate mode."""
    result = await tool.dry_run({"prompt": "chill lo-fi beat", "mode": "generate"})
    assert "lo-fi" in result
    assert "instrumental" in result.lower() or "Generate" in result


@pytest.mark.asyncio
async def test_dry_run_voice_convert(tool) -> None:
    """dry_run describes voice conversion."""
    result = await tool.dry_run({"prompt": "my song", "mode": "voice_convert"})
    assert "voice" in result.lower()


@pytest.mark.asyncio
async def test_dry_run_full_song(tool) -> None:
    """dry_run describes full song generation."""
    result = await tool.dry_run({
        "prompt": "love ballad",
        "mode": "full_song",
        "style": "jazz",
    })
    assert "song" in result.lower()
    assert "jazz" in result


@pytest.mark.asyncio
async def test_validate_missing_prompt(tool) -> None:
    """Validation fails when prompt is missing."""
    result = await tool.validate({})
    assert not result.valid


@pytest.mark.asyncio
async def test_validate_invalid_mode(tool) -> None:
    """Validation fails for an unknown mode."""
    result = await tool.validate({"prompt": "test", "mode": "explode"})
    assert not result.valid
    assert "mode" in result.errors[0].lower() or "Invalid" in result.errors[0]


@pytest.mark.asyncio
async def test_validate_voice_convert_needs_audio(tool) -> None:
    """voice_convert mode requires input_audio_path."""
    result = await tool.validate({"prompt": "test", "mode": "voice_convert"})
    assert not result.valid
    assert "input_audio_path" in result.errors[0]


@pytest.mark.asyncio
async def test_validate_voice_convert_file_must_exist(tool) -> None:
    """voice_convert validation fails if the audio file doesn't exist."""
    result = await tool.validate({
        "prompt": "test",
        "mode": "voice_convert",
        "input_audio_path": "/nonexistent/song.wav",
    })
    assert not result.valid


@pytest.mark.asyncio
async def test_validate_voice_convert_valid(tool) -> None:
    """voice_convert passes when a valid file exists."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        result = await tool.validate({
            "prompt": "test",
            "mode": "voice_convert",
            "input_audio_path": f.name,
        })
        assert result.valid


@pytest.mark.asyncio
async def test_validate_duration_out_of_range(tool) -> None:
    """Duration outside 1-300 range fails validation."""
    result = await tool.validate({
        "prompt": "test",
        "duration_seconds": 500,
    })
    assert not result.valid


@pytest.mark.asyncio
async def test_validate_happy_path(tool) -> None:
    """Standard generate request passes validation."""
    result = await tool.validate({"prompt": "a calm piano melody"})
    assert result.valid


@pytest.mark.asyncio
async def test_execute_returns_result(tool, context) -> None:
    """execute returns a ToolResult with audio metadata."""
    fake_pcm = b"\x00" * 48_000  # 1 second of silence at 24 kHz (int16)

    async def fake_sing(*args, **kwargs):
        yield fake_pcm

    mock_manager = MagicMock()
    mock_manager.sing = fake_sing
    mock_manager.load = AsyncMock()

    tool._manager = mock_manager
    tool._loaded = True

    with tempfile.TemporaryDirectory() as tmpdir:
        tool._config = SingingConfig(output_dir=tmpdir)
        result = await tool.execute(
            {"prompt": "test beat", "mode": "generate"},
            context,
        )

    assert result.success
    assert result.output["status"] == "completed"
    assert result.output["mode"] == "generate"
    assert result.output["sample_rate"] == 24_000


@pytest.mark.asyncio
async def test_execute_handles_engine_failure(tool, context) -> None:
    """execute returns a failed ToolResult when the engine crashes."""
    mock_manager = MagicMock()

    async def exploding_sing(*args, **kwargs):
        raise RuntimeError("GPU exploded")
        yield  # noqa: unreachable — makes this an async generator

    mock_manager.sing = exploding_sing
    mock_manager.load = AsyncMock()

    tool._manager = mock_manager
    tool._loaded = True

    result = await tool.execute(
        {"prompt": "crash test", "mode": "generate"},
        context,
    )
    assert not result.success
    assert "GPU exploded" in (result.error or "")
