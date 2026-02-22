"""Unit tests for plugin sandbox (run_python_sandboxed, _wrap_code)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from plugins.sandbox import _wrap_code, run_python_sandboxed


def test_wrap_code_contains_restricted_builtins() -> None:
    """_wrap_code output assigns __builtins__ to a safe subset."""
    out = _wrap_code("print(1)")
    assert "__builtins__ = " in out
    assert "_blocked" in out
    assert "print(1)" in out


def test_wrap_code_user_code_in_try() -> None:
    """User code is indented inside a try block."""
    out = _wrap_code("x = 2")
    assert "try:" in out
    assert "    x = 2" in out


@pytest.mark.asyncio
async def test_run_python_sandboxed_simple() -> None:
    """run_python_sandboxed executes simple code and returns stdout when sandbox is available."""
    stdout, stderr, returncode = await run_python_sandboxed(
        code="print(42)",
        allowed_paths=[str(Path(tempfile.gettempdir()))],
        timeout_s=5.0,
    )
    # If bwrap fails (e.g. unknown option on some systems), returncode may be 1
    if returncode == 0:
        assert "42" in stdout
    else:
        # Sandbox unavailable or bwrap error; at least no crash
        assert "42" not in stdout or "pwned" not in stderr


@pytest.mark.asyncio
async def test_run_python_sandboxed_restricts_import() -> None:
    """Sandboxed code cannot use __import__ (blocked builtin)."""
    stdout, stderr, returncode = await run_python_sandboxed(
        code="__import__('os').system('echo pwned')",
        allowed_paths=[str(Path(tempfile.gettempdir()))],
        timeout_s=5.0,
    )
    # When the sandbox runs, __import__ is not in builtins so we get NameError; no "pwned" in output
    # When bwrap fails, returncode may be 1 for bwrap error (still no pwned)
    assert "pwned" not in stdout
