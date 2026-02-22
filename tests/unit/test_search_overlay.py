"""Tests for the GlobalSearchOverlay — filters, formatting, commands."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from emily_chat.ui.search_overlay import (
    COMMANDS,
    FILTER_OPTIONS,
    filter_results,
    format_search_result,
)


class TestFormatSearchResult:
    """Tests for format_search_result."""

    def test_basic(self) -> None:
        result = format_search_result("Title", "excerpt text")
        assert result["title"] == "Title"
        assert result["excerpt"] == "excerpt text"

    def test_with_model(self) -> None:
        result = format_search_result("T", "e", model="GPT-5")
        assert "GPT-5" in result["meta"]

    def test_with_cost(self) -> None:
        result = format_search_result("T", "e", cost=0.123)
        assert "$0.123" in result["meta"]

    def test_with_message_count(self) -> None:
        result = format_search_result("T", "e", message_count=42)
        assert "42 msgs" in result["meta"]

    def test_today_relative(self) -> None:
        now = datetime.now(timezone.utc)
        result = format_search_result("T", "e", updated_at=now)
        assert "Today" in result["meta"]

    def test_yesterday_relative(self) -> None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        result = format_search_result("T", "e", updated_at=yesterday)
        assert "Yesterday" in result["meta"]

    def test_days_ago_relative(self) -> None:
        three_days = datetime.now(timezone.utc) - timedelta(days=3)
        result = format_search_result("T", "e", updated_at=three_days)
        assert "3d ago" in result["meta"]

    def test_old_date_formatted(self) -> None:
        old = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = format_search_result("T", "e", updated_at=old)
        assert "Jan" in result["meta"]

    def test_zero_cost_excluded(self) -> None:
        result = format_search_result("T", "e", cost=0.0)
        assert "$" not in result["meta"]

    def test_all_metadata(self) -> None:
        result = format_search_result(
            "T", "e", model="GPT-5", message_count=10,
            cost=0.05, updated_at=datetime.now(timezone.utc),
        )
        assert "GPT-5" in result["meta"]
        assert "10 msgs" in result["meta"]
        assert "$0.050" in result["meta"]
        assert "Today" in result["meta"]


class TestFilterResults:
    """Tests for filter_results."""

    def test_all_filter_returns_everything(self) -> None:
        results = [{"title": "A"}, {"title": "B"}]
        assert len(filter_results(results, "All")) == 2

    def test_filter_by_model(self) -> None:
        results = [
            {"title": "A", "model": "GPT-5"},
            {"title": "B", "model": "Gemini"},
        ]
        filtered = filter_results(results, "Model", "GPT")
        assert len(filtered) == 1
        assert filtered[0]["title"] == "A"

    def test_filter_case_insensitive(self) -> None:
        results = [{"title": "A", "skill": "Code"}]
        filtered = filter_results(results, "Skill", "code")
        assert len(filtered) == 1

    def test_filter_no_value_returns_all(self) -> None:
        results = [{"title": "A"}, {"title": "B"}]
        assert len(filter_results(results, "Model", "")) == 2

    def test_filter_no_match(self) -> None:
        results = [{"title": "A", "model": "GPT-5"}]
        assert len(filter_results(results, "Model", "Gemini")) == 0


class TestCommands:
    """Tests for command definitions."""

    def test_commands_defined(self) -> None:
        assert len(COMMANDS) >= 5

    def test_command_has_id(self) -> None:
        for cmd in COMMANDS:
            assert "id" in cmd
            assert "label" in cmd

    def test_new_command_exists(self) -> None:
        ids = [cmd["id"] for cmd in COMMANDS]
        assert "new" in ids

    def test_export_command_exists(self) -> None:
        ids = [cmd["id"] for cmd in COMMANDS]
        assert "export" in ids


class TestFilterOptions:
    """Tests for filter option definitions."""

    def test_all_included(self) -> None:
        assert "All" in FILTER_OPTIONS

    def test_model_included(self) -> None:
        assert "Model" in FILTER_OPTIONS

    def test_at_least_three(self) -> None:
        assert len(FILTER_OPTIONS) >= 3


class TestOverlaySignals:
    """Tests for signal declarations on GlobalSearchOverlay."""

    @pytest.fixture(autouse=True)
    def _skip_no_display(self) -> None:
        pytest.importorskip("PySide6.QtWidgets")

    def test_has_conversation_opened(self) -> None:
        from emily_chat.ui.search_overlay import GlobalSearchOverlay
        assert hasattr(GlobalSearchOverlay, "conversation_opened")

    def test_has_command_executed(self) -> None:
        from emily_chat.ui.search_overlay import GlobalSearchOverlay
        assert hasattr(GlobalSearchOverlay, "command_executed")

    def test_has_search_query(self) -> None:
        from emily_chat.ui.search_overlay import GlobalSearchOverlay
        assert hasattr(GlobalSearchOverlay, "search_query")
