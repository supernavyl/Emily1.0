"""Tests for the ConversationTopBar widget and helper functions."""

from __future__ import annotations

import pytest

from emily_chat.ui.top_bar import (
    ConversationTopBar,
    context_warning_level,
    cost_warning_level,
    format_cost,
    format_tokens,
    group_models,
)


class TestFormatCost:
    """Tests for the format_cost helper."""

    def test_zero(self) -> None:
        assert format_cost(0.0) == "$0.00"

    def test_tiny(self) -> None:
        assert format_cost(0.0001) == "$0.00"

    def test_normal(self) -> None:
        assert format_cost(0.0124) == "$0.0124"

    def test_large(self) -> None:
        assert format_cost(1.5678) == "$1.5678"


class TestFormatTokens:
    """Tests for the format_tokens helper."""

    def test_small(self) -> None:
        assert format_tokens(42) == "42"

    def test_thousands(self) -> None:
        assert format_tokens(4_247) == "4,247"

    def test_millions(self) -> None:
        assert format_tokens(1_234_567) == "1,234,567"


class TestCostWarningLevel:
    """Tests for the cost_warning_level thresholds."""

    def test_none(self) -> None:
        assert cost_warning_level(0.01) == "none"

    def test_yellow(self) -> None:
        assert cost_warning_level(0.05) == "yellow"

    def test_yellow_above(self) -> None:
        assert cost_warning_level(0.10) == "yellow"

    def test_red(self) -> None:
        assert cost_warning_level(0.20) == "red"

    def test_red_above(self) -> None:
        assert cost_warning_level(1.0) == "red"

    def test_below_threshold(self) -> None:
        assert cost_warning_level(0.049) == "none"


class TestContextWarningLevel:
    """Tests for the context_warning_level thresholds."""

    def test_none(self) -> None:
        assert context_warning_level(50) == "none"

    def test_yellow(self) -> None:
        assert context_warning_level(75) == "yellow"

    def test_red(self) -> None:
        assert context_warning_level(90) == "red"

    def test_red_above(self) -> None:
        assert context_warning_level(99) == "red"

    def test_below_yellow(self) -> None:
        assert context_warning_level(74.9) == "none"


class TestGroupModels:
    """Tests for model grouping logic."""

    def test_returns_non_empty(self) -> None:
        groups = group_models()
        assert len(groups) > 0

    def test_categories_have_items(self) -> None:
        for label, items in group_models():
            assert len(items) > 0, f"Category '{label}' is empty"

    def test_no_duplicate_keys(self) -> None:
        seen: set[str] = set()
        for _, items in group_models():
            for key, _ in items:
                assert key not in seen, f"Duplicate key: {key}"
                seen.add(key)

    def test_thinking_category_first(self) -> None:
        groups = group_models()
        assert "THINKING" in groups[0][0].upper()

    def test_all_registry_models_included(self) -> None:
        from emily_chat.models.registry import EMILY_MODEL_REGISTRY

        grouped_keys: set[str] = set()
        for _, items in group_models():
            for key, _ in items:
                grouped_keys.add(key)
        for key in EMILY_MODEL_REGISTRY:
            assert key in grouped_keys, f"Registry key '{key}' not grouped"


class TestConversationTopBarSignals:
    """Tests for signal declarations on ConversationTopBar."""

    @pytest.fixture(autouse=True)
    def _skip_no_display(self) -> None:
        pytest.importorskip("PySide6.QtWidgets")

    def test_has_model_changed_signal(self) -> None:
        assert hasattr(ConversationTopBar, "model_changed")

    def test_has_skill_changed_signal(self) -> None:
        assert hasattr(ConversationTopBar, "skill_changed")

    def test_has_clear_requested_signal(self) -> None:
        assert hasattr(ConversationTopBar, "clear_requested")

    def test_has_fork_requested_signal(self) -> None:
        assert hasattr(ConversationTopBar, "fork_requested")

    def test_has_export_requested_signal(self) -> None:
        assert hasattr(ConversationTopBar, "export_requested")

    def test_has_system_prompt_edit_signal(self) -> None:
        assert hasattr(ConversationTopBar, "system_prompt_edit_requested")
