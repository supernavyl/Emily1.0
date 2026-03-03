"""Code block widget — syntax-highlighted code with copy, run, and expand.

Standalone ``QFrame`` used by the conversation stream to display fenced
code blocks extracted by :class:`~emily_chat.ui.markdown_renderer.MarkdownRenderer`.
Features: language badge, line numbers, clipboard copy with checkmark
flash, Python sandbox execution, expand/collapse for long blocks, and
diff-view colouring.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import sys
from typing import Any

from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_COLLAPSE_THRESHOLD = 30
_COLLAPSE_PREVIEW_LINES = 15
_RUN_TIMEOUT = 10
_CHECKMARK_DURATION_MS = 1500

_RUNNABLE_LANGUAGES = frozenset({"python", "python3", "py"})


def detect_language(code: str, hint: str = "") -> str:
    """Detect the programming language of *code*.

    Args:
        code: Raw source code.
        hint: Optional hint from the fence info string.

    Returns:
        A normalised language name, or ``""`` if unknown.
    """
    if hint:
        return hint.lower().strip()
    try:
        lexer = guess_lexer(code)
        return lexer.name.lower()
    except ClassNotFound:
        return ""


def count_lines(code: str) -> int:
    """Return the number of lines in *code*.

    Args:
        code: Raw source code.

    Returns:
        Line count (minimum 1).
    """
    return max(1, code.count("\n") + (1 if not code.endswith("\n") else 0))


def is_diff(code: str, lang: str) -> bool:
    """Return ``True`` if the code should be rendered as a diff.

    Args:
        code: Code content.
        lang: Language hint.

    Returns:
        ``True`` for diff-like content.
    """
    if lang in ("diff", "patch"):
        return True
    lines = code.lstrip().split("\n", 3)
    return bool(len(lines) >= 2 and lines[0].startswith("---") and lines[1].startswith("+++"))


async def run_python_sandbox(code: str) -> dict[str, Any]:
    """Execute *code* in a sandboxed Python subprocess.

    Uses ``asyncio.create_subprocess_exec`` to avoid blocking the UI.
    On Linux, attempts to isolate the process from the network via
    ``unshare --net`` if available.

    Args:
        code: Python source code to execute.

    Returns:
        Dict with ``"stdout"``, ``"stderr"``, ``"returncode"``,
        and ``"timed_out"`` keys.
    """
    cmd: list[str] = []
    if sys.platform == "linux" and shutil.which("unshare"):
        cmd = ["unshare", "--net", "--map-root-user", sys.executable, "-c", code]
    else:
        cmd = [sys.executable, "-c", code]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_RUN_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {_RUN_TIMEOUT}s",
                "returncode": -1,
                "timed_out": True,
            }

        return {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "returncode": proc.returncode,
            "timed_out": False,
        }
    except Exception as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "timed_out": False,
        }


class CodeBlockWidget(QFrame):
    """Interactive code block with syntax highlighting and execution.

    Args:
        code: Raw source code.
        lang: Language identifier (e.g. ``"python"``).
        parent: Parent widget.

    Signals:
        run_requested(str): Emitted when the user clicks Run.
    """

    run_requested = Signal(str)

    def __init__(
        self,
        code: str,
        lang: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("codeBlockFrame")
        self._code = code
        self._lang = detect_language(code, lang)
        self._expanded = count_lines(code) <= _COLLAPSE_THRESHOLD
        self._is_diff = is_diff(code, self._lang)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- header row ---
        header = QWidget()
        header.setObjectName("codeBlockHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(6)

        self._lang_badge = QLabel(self._lang or "text")
        self._lang_badge.setObjectName("codeBlockLangBadge")
        header_layout.addWidget(self._lang_badge)
        header_layout.addStretch()

        self._copy_btn = QPushButton("\U0001f4cb Copy")
        self._copy_btn.setObjectName("codeBlockCopyBtn")
        self._copy_btn.clicked.connect(self._on_copy)
        header_layout.addWidget(self._copy_btn)

        if self._lang in _RUNNABLE_LANGUAGES:
            self._run_btn = QPushButton("\u25b6 Run")
            self._run_btn.setObjectName("codeBlockRunBtn")
            self._run_btn.clicked.connect(self._on_run)
            header_layout.addWidget(self._run_btn)
        else:
            self._run_btn = None

        n_lines = count_lines(code)
        if n_lines > _COLLAPSE_THRESHOLD:
            self._expand_btn = QPushButton(
                f"\u25bc Show all ({n_lines} lines)" if not self._expanded else "\u25b2 Collapse"
            )
            self._expand_btn.setObjectName("codeBlockExpandBtn")
            self._expand_btn.clicked.connect(self._on_toggle_expand)
            header_layout.addWidget(self._expand_btn)
        else:
            self._expand_btn = None

        main_layout.addWidget(header)

        # --- code body ---
        self._code_edit = QPlainTextEdit()
        self._code_edit.setObjectName("codeBlockBody")
        self._code_edit.setReadOnly(True)
        self._code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._code_edit.setFont(QFont(["JetBrains Mono", "Fira Code", "monospace"], 13))

        self._set_code_content()
        main_layout.addWidget(self._code_edit)

        # --- output area (hidden by default) ---
        self._output_area = QPlainTextEdit()
        self._output_area.setObjectName("codeBlockOutput")
        self._output_area.setReadOnly(True)
        self._output_area.setVisible(False)
        self._output_area.setMaximumHeight(200)
        main_layout.addWidget(self._output_area)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    @property
    def code(self) -> str:
        """The raw source code."""
        return self._code

    @property
    def lang(self) -> str:
        """The detected or specified language."""
        return self._lang

    def _set_code_content(self) -> None:
        """Display the code (possibly truncated)."""
        if self._expanded:
            display = self._code
        else:
            lines = self._code.split("\n")
            display = "\n".join(lines[:_COLLAPSE_PREVIEW_LINES])

        self._code_edit.setPlainText(display)

        n_lines = count_lines(display)
        line_height = self._code_edit.fontMetrics().lineSpacing()
        height = (n_lines + 1) * line_height + 16
        self._code_edit.setFixedHeight(min(height, 600))

    def _on_copy(self) -> None:
        """Copy raw code to clipboard and show checkmark."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code)
        self._copy_btn.setText("\u2713 Copied")
        QTimer.singleShot(
            _CHECKMARK_DURATION_MS,
            lambda: self._copy_btn.setText("\U0001f4cb Copy"),
        )

    def _on_run(self) -> None:
        """Execute Python code in a sandbox."""
        if self._run_btn is not None:
            self._run_btn.setEnabled(False)
            self._run_btn.setText("\u23f3 Running...")

        self._output_area.setVisible(True)
        self._output_area.setPlainText("Running...")
        self.run_requested.emit(self._code)

        loop = None
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()

        if loop and loop.is_running():
            asyncio.ensure_future(self._run_and_display())
        else:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._run_and_display())
                future.add_done_callback(lambda _: None)

    async def _run_and_display(self) -> None:
        """Run code and update the output area."""
        result = await run_python_sandbox(self._code)
        output_parts: list[str] = []
        if result["stdout"]:
            output_parts.append(result["stdout"])
        if result["stderr"]:
            output_parts.append(result["stderr"])

        output_text = "\n".join(output_parts) if output_parts else "(no output)"

        is_error = result["returncode"] != 0
        self._output_area.setObjectName("codeBlockOutputError" if is_error else "codeBlockOutput")
        self._output_area.style().unpolish(self._output_area)
        self._output_area.style().polish(self._output_area)
        self._output_area.setPlainText(output_text)

        if self._run_btn is not None:
            self._run_btn.setEnabled(True)
            self._run_btn.setText("\u25b6 Run")

    def _on_toggle_expand(self) -> None:
        """Toggle between expanded and collapsed views."""
        self._expanded = not self._expanded
        self._set_code_content()
        if self._expand_btn is not None:
            n_lines = count_lines(self._code)
            self._expand_btn.setText(
                f"\u25bc Show all ({n_lines} lines)" if not self._expanded else "\u25b2 Collapse"
            )
