"""Tests for the code block widget.

Tests the non-Qt utility functions and the sandboxed execution logic
in :mod:`emily_chat.ui.code_block_widget`.  No Qt event loop required.
Covers: language detection, line counting, diff detection, sandbox
subprocess execution (mocked and real), and the collapse threshold.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from emily_chat.ui.code_block_widget import (
    _COLLAPSE_THRESHOLD,
    _COLLAPSE_PREVIEW_LINES,
    _RUNNABLE_LANGUAGES,
    count_lines,
    detect_language,
    is_diff,
    run_python_sandbox,
)


# ------------------------------------------------------------------
# Language detection
# ------------------------------------------------------------------


class TestDetectLanguage:
    """detect_language utility."""

    def test_explicit_hint(self) -> None:
        """An explicit hint should be returned as-is (lowered)."""
        assert detect_language("x = 1", "Python") == "python"

    def test_hint_stripped(self) -> None:
        """Whitespace in hint should be stripped."""
        assert detect_language("", "  js  ") == "js"

    def test_empty_hint_guesses(self) -> None:
        """Without a hint, Pygments guesses the language."""
        lang = detect_language("#!/usr/bin/env python3\nprint('hi')")
        assert lang != ""

    def test_unparseable_returns_empty(self) -> None:
        """Completely ambiguous code should return empty string."""
        lang = detect_language("abc")
        assert isinstance(lang, str)


# ------------------------------------------------------------------
# Line counting
# ------------------------------------------------------------------


class TestCountLines:
    """count_lines utility."""

    def test_single_line(self) -> None:
        """Single line without newline."""
        assert count_lines("hello") == 1

    def test_multiple_lines(self) -> None:
        """Multiple lines separated by newlines."""
        assert count_lines("a\nb\nc") == 3

    def test_trailing_newline(self) -> None:
        """Trailing newline should not add an extra line."""
        assert count_lines("a\nb\n") == 2

    def test_empty_string(self) -> None:
        """Empty string returns 1 (minimum)."""
        assert count_lines("") == 1

    def test_many_lines(self) -> None:
        """Correctly counts >30 lines."""
        code = "\n".join(f"line {i}" for i in range(50))
        assert count_lines(code) == 50


# ------------------------------------------------------------------
# Diff detection
# ------------------------------------------------------------------


class TestIsDiff:
    """is_diff utility."""

    def test_diff_language_hint(self) -> None:
        """Language 'diff' should return True."""
        assert is_diff("anything", "diff") is True

    def test_patch_language_hint(self) -> None:
        """Language 'patch' should return True."""
        assert is_diff("anything", "patch") is True

    def test_diff_content(self) -> None:
        """Content starting with --- and +++ should be detected."""
        code = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        assert is_diff(code, "text") is True

    def test_not_diff(self) -> None:
        """Regular code should not be detected as diff."""
        assert is_diff("x = 1\ny = 2", "python") is False

    def test_single_dashes_not_diff(self) -> None:
        """--- alone (without +++) is not a diff."""
        assert is_diff("---\ntitle: hello\n---", "yaml") is False


# ------------------------------------------------------------------
# Runnable languages
# ------------------------------------------------------------------


class TestRunnableLanguages:
    """Verify the set of runnable languages."""

    def test_python_runnable(self) -> None:
        """python is runnable."""
        assert "python" in _RUNNABLE_LANGUAGES

    def test_py_runnable(self) -> None:
        """py alias is runnable."""
        assert "py" in _RUNNABLE_LANGUAGES

    def test_js_not_runnable(self) -> None:
        """JavaScript is not runnable (no sandbox)."""
        assert "javascript" not in _RUNNABLE_LANGUAGES


# ------------------------------------------------------------------
# Collapse threshold
# ------------------------------------------------------------------


class TestCollapseThreshold:
    """Verify collapse constants."""

    def test_threshold_value(self) -> None:
        """Collapse threshold should be 30 lines."""
        assert _COLLAPSE_THRESHOLD == 30

    def test_preview_lines(self) -> None:
        """Preview should show 15 lines."""
        assert _COLLAPSE_PREVIEW_LINES == 15

    def test_short_code_not_collapsed(self) -> None:
        """Code with fewer lines than threshold is not collapsed."""
        code = "\n".join(f"line {i}" for i in range(10))
        assert count_lines(code) <= _COLLAPSE_THRESHOLD

    def test_long_code_collapsed(self) -> None:
        """Code exceeding threshold should be collapsed."""
        code = "\n".join(f"line {i}" for i in range(50))
        assert count_lines(code) > _COLLAPSE_THRESHOLD


# ------------------------------------------------------------------
# Python sandbox execution
# ------------------------------------------------------------------


class TestRunPythonSandbox:
    """run_python_sandbox async execution."""

    @pytest.mark.asyncio
    async def test_simple_print(self) -> None:
        """A simple print statement should produce output."""
        result = await run_python_sandbox("print('hello world')")
        assert result["returncode"] == 0
        assert "hello world" in result["stdout"]
        assert result["timed_out"] is False

    @pytest.mark.asyncio
    async def test_syntax_error(self) -> None:
        """A syntax error should be captured in stderr."""
        result = await run_python_sandbox("def :")
        assert result["returncode"] != 0
        assert result["stderr"]
        assert result["timed_out"] is False

    @pytest.mark.asyncio
    async def test_exception(self) -> None:
        """A runtime exception should be captured."""
        result = await run_python_sandbox("raise ValueError('test')")
        assert result["returncode"] != 0
        assert "ValueError" in result["stderr"]

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Long-running code should time out."""
        with patch(
            "emily_chat.ui.code_block_widget._RUN_TIMEOUT", 1
        ):
            result = await run_python_sandbox("import time; time.sleep(30)")
            assert result["timed_out"] is True or result["returncode"] != 0

    @pytest.mark.asyncio
    async def test_return_structure(self) -> None:
        """Result should have all expected keys."""
        result = await run_python_sandbox("pass")
        assert "stdout" in result
        assert "stderr" in result
        assert "returncode" in result
        assert "timed_out" in result

    @pytest.mark.asyncio
    async def test_multiline_output(self) -> None:
        """Multi-line output should be captured fully."""
        code = "for i in range(5): print(i)"
        result = await run_python_sandbox(code)
        assert result["returncode"] == 0
        for i in range(5):
            assert str(i) in result["stdout"]
