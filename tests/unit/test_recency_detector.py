"""Tests for the recency detection heuristic."""

from __future__ import annotations

import pytest

from llm.recency_detector import needs_web_search, needs_web_search_voice


# ── positive cases (should trigger web search) ──────────────────


@pytest.mark.parametrize(
    "query",
    [
        "What's the latest news?",
        "Who won the 2026 election?",
        "search for Python 3.14 changes",
        "What happened in Ukraine today?",
        "Tell me about the recently released GPT-6",
        "What's trending right now?",
        "Look up the current price of Bitcoin",
        "Has anything been announced about the new iPhone?",
        "What launched this week in AI?",
        "Google the weather for tomorrow",
        "What's the score of tonight's game?",
        "Any breaking news?",
    ],
)
def test_positive_recency_queries(query: str) -> None:
    """Queries about recent or time-sensitive topics must trigger."""
    assert needs_web_search(query) is True


# ── negative cases (should NOT trigger web search) ──────────────


@pytest.mark.parametrize(
    "query",
    [
        "What is 2+2?",
        "Tell me about ancient Rome",
        "How does photosynthesis work?",
        "Explain the Pythagorean theorem",
        "Write a Python function that sorts a list",
        "What is the capital of France?",
        "Summarize the plot of Hamlet",
        "How do I tie a bowline knot?",
    ],
)
def test_negative_non_recency_queries(query: str) -> None:
    """Timeless factual queries must NOT trigger."""
    assert needs_web_search(query) is False


def test_old_year_does_not_trigger() -> None:
    """References to years well in the past should not trigger."""
    assert needs_web_search("What happened in 2010?") is False


def test_current_year_triggers() -> None:
    """A reference to the current year should trigger."""
    from datetime import datetime, timezone

    year = datetime.now(timezone.utc).year
    assert needs_web_search(f"events in {year}") is True


# ── voice-mode variant ──────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "search for Python 3.14 changes",
        "Look up the current price of Bitcoin",
        "Google the weather for tomorrow",
        "Can you find out who directed Inception?",
        "check online for the best pizza near me",
    ],
)
def test_voice_positive_explicit_search(query: str) -> None:
    """Explicit search intent must trigger even in voice mode."""
    assert needs_web_search_voice(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "What's the latest news?",
        "What happened in Ukraine today?",
        "Any breaking news?",
        "What's trending right now?",
        "Has anything been announced about the new iPhone?",
        "What launched this week in AI?",
        "Tell me a joke",
        "How does photosynthesis work?",
    ],
)
def test_voice_negative_passive_recency(query: str) -> None:
    """Passive recency/news keywords must NOT trigger in voice mode."""
    assert needs_web_search_voice(query) is False
