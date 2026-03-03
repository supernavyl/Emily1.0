"""Tests for temporal awareness in the PromptBuilder system prompt."""

from __future__ import annotations

import pytest

from llm.prompt_builder import PromptBuilder


@pytest.fixture
def builder() -> PromptBuilder:
    return PromptBuilder()


def test_system_prompt_contains_current_date_auto(builder: PromptBuilder) -> None:
    """When no datetime is supplied, the prompt should contain today's UTC date."""
    prompt = builder.get_system_prompt()
    assert "Current date/time:" in prompt
    assert "UTC" in prompt


def test_system_prompt_contains_explicit_datetime(builder: PromptBuilder) -> None:
    """An explicit datetime string must appear verbatim in the prompt."""
    dt = "2026-02-20 15:30 UTC"
    prompt = builder.get_system_prompt(current_datetime=dt)
    assert dt in prompt


def test_temporal_awareness_section_present(builder: PromptBuilder) -> None:
    """The TEMPORAL AWARENESS section must be injected."""
    prompt = builder.get_system_prompt()
    assert "TEMPORAL AWARENESS" in prompt
    assert "knowledge cutoff" in prompt
    assert "web search" in prompt


def test_format_placeholder_not_leaking(builder: PromptBuilder) -> None:
    """The raw {current_datetime} placeholder must never appear."""
    prompt = builder.get_system_prompt()
    assert "{current_datetime}" not in prompt


def test_persona_and_datetime_coexist(builder: PromptBuilder) -> None:
    """Persona injection and datetime injection must not interfere."""
    prompt = builder.get_system_prompt(
        persona={"curiosity": 0.9, "warmth": 0.9},
        current_datetime="2026-06-01 00:00 UTC",
    )
    assert "2026-06-01 00:00 UTC" in prompt
    assert "STYLE GUIDANCE" in prompt
