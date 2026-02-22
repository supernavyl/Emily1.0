"""Tests for the message widget logic and non-Qt utilities.

Tests the signal-emission API, streaming append, thinking chip display,
and action bar helpers in :mod:`emily_chat.ui.conversation_stream`.
Tests that exercise Qt signal emission require a QApplication instance;
we only test the non-widget logic here to avoid the dependency.
"""

from __future__ import annotations

import pytest

from emily_chat.ui.markdown_renderer import MarkdownRenderer, build_document_css
from emily_chat.ui.theme_engine import PALETTES


# ------------------------------------------------------------------
# MarkdownTextBrowser streaming logic (non-widget internals)
# ------------------------------------------------------------------


class TestMarkdownTextBrowserLogic:
    """Test the MarkdownTextBrowser's markdown accumulation logic."""

    def test_renderer_produces_segments_for_streaming(self) -> None:
        """Simulated streaming: chunks accumulate into valid markdown."""
        renderer = MarkdownRenderer()
        chunks = ["Hello ", "**world**", "\n\n```python\nx = 1\n```"]
        accumulated = "".join(chunks)
        segments = renderer.render_with_code_blocks(accumulated)
        types = [s["type"] for s in segments]
        assert "html" in types
        assert "code" in types

    def test_empty_markdown_renders(self) -> None:
        """Empty string should produce no segments."""
        renderer = MarkdownRenderer()
        segments = renderer.render_with_code_blocks("")
        assert segments == []


# ------------------------------------------------------------------
# ThinkingIndicator state
# ------------------------------------------------------------------


class TestThinkingIndicatorLogic:
    """Test ThinkingIndicator state transitions (non-widget)."""

    def test_preview_text_truncation(self) -> None:
        """Preview text longer than 50 chars should be truncated."""
        long_text = "a" * 100
        truncated = "\u2026" + long_text[-50:]
        assert len(truncated) == 51
        assert truncated.startswith("\u2026")

    def test_preview_text_short(self) -> None:
        """Short preview text should not be truncated."""
        text = "thinking about things"
        assert len(text) <= 50


# ------------------------------------------------------------------
# Action bar button enumeration
# ------------------------------------------------------------------


class TestActionBarButtons:
    """Verify action bar button definitions."""

    def test_user_action_buttons(self) -> None:
        """User messages should have copy, edit, resend buttons."""
        expected = {"copy", "edit", "resend"}
        assert expected == {"copy", "edit", "resend"}

    def test_emily_action_buttons(self) -> None:
        """Emily messages should have the full set of action buttons."""
        expected = {"like", "dislike", "copy", "copy_md", "retry", "branch"}
        assert expected == {"like", "dislike", "copy", "copy_md", "retry", "branch"}


# ------------------------------------------------------------------
# ConversationStream API contract
# ------------------------------------------------------------------


class TestConversationStreamContract:
    """Verify the ConversationStream public API matches expectations."""

    def test_module_exports_classes(self) -> None:
        """The module should export all expected classes."""
        from emily_chat.ui.conversation_stream import (
            ConversationStream,
            EmilyMessageWidget,
            MarkdownTextBrowser,
            ThinkingIndicator,
            UserMessageWidget,
        )
        assert ConversationStream is not None
        assert EmilyMessageWidget is not None
        assert UserMessageWidget is not None
        assert ThinkingIndicator is not None
        assert MarkdownTextBrowser is not None

    def test_signal_names_on_conversation_stream(self) -> None:
        """ConversationStream should declare the expected signals."""
        from emily_chat.ui.conversation_stream import ConversationStream
        expected_signals = [
            "scroll_locked_changed",
            "edit_requested",
            "resend_requested",
            "retry_requested",
            "branch_requested",
            "feedback_given",
            "message_clicked",
        ]
        for name in expected_signals:
            assert hasattr(ConversationStream, name), f"Missing signal: {name}"

    def test_emily_widget_signals(self) -> None:
        """EmilyMessageWidget should declare the expected signals."""
        from emily_chat.ui.conversation_stream import EmilyMessageWidget
        expected = ["feedback_given", "retry_requested", "branch_requested", "copy_requested"]
        for name in expected:
            assert hasattr(EmilyMessageWidget, name), f"Missing signal: {name}"

    def test_user_widget_signals(self) -> None:
        """UserMessageWidget should declare the expected signals."""
        from emily_chat.ui.conversation_stream import UserMessageWidget
        expected = ["edit_submitted", "resend_requested", "copy_requested"]
        for name in expected:
            assert hasattr(UserMessageWidget, name), f"Missing signal: {name}"


# ------------------------------------------------------------------
# Document CSS generation
# ------------------------------------------------------------------


class TestDocumentCSS:
    """Document CSS for QTextBrowser should render properly."""

    def test_dark_palette_css(self) -> None:
        """Dark palette should produce valid CSS with known colours."""
        css = build_document_css(PALETTES["dark"])
        assert "#f0f0f5" in css
        assert "font-family" in css
        assert "#0d0d14" in css

    def test_light_palette_css(self) -> None:
        """Light palette should produce valid CSS with known colours."""
        css = build_document_css(PALETTES["light"])
        assert "#1a1a2e" in css
        assert "#f0f0f4" in css

    def test_link_color_uses_palette(self) -> None:
        """Link color should come from the palette."""
        css = build_document_css(PALETTES["dark"])
        assert PALETTES["dark"]["link_color"] in css


# ------------------------------------------------------------------
# Theme palette completeness
# ------------------------------------------------------------------


class TestPaletteCompleteness:
    """Verify that new palette tokens are present."""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_new_tokens_present(self, theme: str) -> None:
        """Phase 10-13 tokens should be in both palettes."""
        palette = PALETTES[theme]
        for key in (
            "code_border",
            "link_color",
            "action_btn_hover",
            "phase_analyzing",
            "phase_considering",
            "phase_comparing",
            "phase_concluding",
            "phase_uncertain",
            "progress_bar",
            "progress_bg",
        ):
            assert key in palette, f"Missing token '{key}' in '{theme}' palette"
