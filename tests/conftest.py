"""Shared pytest fixtures for Emily test suite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fake result objects (matches patterns used across the test suite)
# ---------------------------------------------------------------------------


@dataclass
class FakeLLMResult:
    """Minimal stand-in for streaming_engine.LLMResult."""

    content: str
    model_id: str = "test-model"
    tokens_in: int = 10
    tokens_out: int = 20
    latency_ms: float = 100.0


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_config() -> dict[str, Any]:
    """Minimal Emily config dict for tests."""
    return {
        "llm": {
            "default_model": "test-model",
            "tier_backend": "ollama",
            "models": {},
        },
        "tools": {
            "allowed_paths": ["/tmp"],
        },
        "voice": {
            "stt_model": "base.en",
            "tts_engine": "kokoro",
        },
    }


@pytest.fixture()
def mock_llm_fleet() -> MagicMock:
    """AsyncMock LLMFleet with .chat() returning FakeLLMResult."""
    fleet = MagicMock()
    fleet.chat = AsyncMock(return_value=FakeLLMResult(content="Hello from mock"))
    fleet.available_models = ["test-model"]
    return fleet


@pytest.fixture()
def tmp_key_path(tmp_path: Path) -> Path:
    """Temp directory path for encryption key tests."""
    return tmp_path / ".test_key"
