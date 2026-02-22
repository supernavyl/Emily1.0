"""Tests for the enhanced InputPanel — slash commands, history, attachments."""

from __future__ import annotations

import os
import tempfile

import pytest

from emily_chat.ui.input_panel import (
    SLASH_COMMANDS,
    format_file_size,
    parse_slash_command,
    validate_attachments,
)


class TestParseSlashCommand:
    """Tests for parse_slash_command."""

    def test_new(self) -> None:
        assert parse_slash_command("/new") == ("/new", "")

    def test_model_with_arg(self) -> None:
        assert parse_slash_command("/model gpt-5") == ("/model", "gpt-5")

    def test_search_with_arg(self) -> None:
        assert parse_slash_command("/search hello world") == ("/search", "hello world")

    def test_export_no_arg(self) -> None:
        assert parse_slash_command("/export") == ("/export", "")

    def test_unknown_command(self) -> None:
        assert parse_slash_command("/foobar") is None

    def test_not_a_command(self) -> None:
        assert parse_slash_command("hello world") is None

    def test_slash_in_middle(self) -> None:
        assert parse_slash_command("hello /new") is None

    def test_whitespace_prefix(self) -> None:
        assert parse_slash_command("  /clear") == ("/clear", "")

    def test_all_commands_defined(self) -> None:
        expected = {"/new", "/clear", "/model", "/search", "/export",
                    "/branch", "/retry", "/edit", "/cost", "/summarize"}
        assert set(SLASH_COMMANDS.keys()) == expected


class TestFormatFileSize:
    """Tests for format_file_size."""

    def test_bytes(self) -> None:
        assert format_file_size(512) == "512 B"

    def test_kilobytes(self) -> None:
        assert format_file_size(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        assert format_file_size(3_145_728) == "3.0 MB"


class TestValidateAttachments:
    """Tests for validate_attachments."""

    def test_valid_file(self, tmp_path: object) -> None:
        p = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        p.write(b"hello")
        p.close()
        try:
            valid, errors = validate_attachments([p.name])
            assert len(valid) == 1
            assert len(errors) == 0
        finally:
            os.unlink(p.name)

    def test_nonexistent_file(self) -> None:
        valid, errors = validate_attachments(["/nonexistent/file.txt"])
        assert len(valid) == 0
        assert len(errors) == 1

    def test_too_large_file(self, tmp_path: object) -> None:
        p = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        p.write(b"x" * (11 * 1024 * 1024))
        p.close()
        try:
            valid, errors = validate_attachments([p.name])
            assert len(valid) == 0
            assert "Too large" in errors[0]
        finally:
            os.unlink(p.name)

    def test_mixed(self) -> None:
        p = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        p.write(b"ok")
        p.close()
        try:
            valid, errors = validate_attachments([p.name, "/no/such/file"])
            assert len(valid) == 1
            assert len(errors) == 1
        finally:
            os.unlink(p.name)


class TestInputPanelSignals:
    """Tests for InputPanel signal declarations."""

    @pytest.fixture(autouse=True)
    def _skip_no_display(self) -> None:
        pytest.importorskip("PySide6.QtWidgets")

    def test_has_web_search_toggled(self) -> None:
        from emily_chat.ui.input_panel import InputPanel
        assert hasattr(InputPanel, "web_search_toggled")

    def test_has_quick_skill_override(self) -> None:
        from emily_chat.ui.input_panel import InputPanel
        assert hasattr(InputPanel, "quick_skill_override")

    def test_has_slash_command(self) -> None:
        from emily_chat.ui.input_panel import InputPanel
        assert hasattr(InputPanel, "slash_command")

    def test_has_files_attached(self) -> None:
        from emily_chat.ui.input_panel import InputPanel
        assert hasattr(InputPanel, "files_attached")
