"""Unit tests for the Emily configuration system."""

from __future__ import annotations

import pytest

from config import EmilySettings


def test_default_settings_instantiate() -> None:
    """EmilySettings can be instantiated with all defaults."""
    s = EmilySettings()
    assert s.name == "Emily"
    assert s.version == "1.0.0"
    assert s.log_level == "INFO"


def test_llm_model_tiers_defined() -> None:
    """All LLM model tiers have non-empty model identifiers."""
    s = EmilySettings()
    assert s.llm.models.nano
    assert s.llm.models.fast
    assert s.llm.models.smart
    assert s.llm.models.reasoning
    assert s.llm.models.vision
    assert s.llm.models.embedding


def test_invalid_log_level_raises() -> None:
    """An invalid log_level raises a validation error."""
    with pytest.raises(Exception):
        EmilySettings(log_level="VERBOSE")


def test_memory_defaults() -> None:
    """Memory configuration has sensible defaults."""
    s = EmilySettings()
    assert s.memory.working.max_tokens > 0
    assert s.memory.episodic.db_path
    assert 0 < s.memory.semantic.decay_factor <= 1.0


def test_persona_dimensions_in_range() -> None:
    """All persona dimensions are in [0, 1]."""
    s = EmilySettings()
    for dim in [
        s.persona.curiosity,
        s.persona.warmth,
        s.persona.directness,
        s.persona.humor,
        s.persona.formality,
    ]:
        assert 0.0 <= dim <= 1.0


def test_security_approval_tools_list() -> None:
    """Security config has a non-empty approval tools list."""
    s = EmilySettings()
    assert len(s.security.require_approval_tools) > 0
    assert "shell" in s.security.require_approval_tools
