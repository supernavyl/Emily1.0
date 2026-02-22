"""Enhanced input panel — attachments, toolbar, slash commands, message history.

Enter sends, Shift+Enter inserts a newline, Ctrl+Enter force-sends.
Up/Down in empty textarea cycles through message history.
Slash commands are triggered by ``/`` at start of line.
"""

from __future__ import annotations

import os
import re
from collections import deque
from typing import Any

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_MIN_HEIGHT = 38
_MAX_HEIGHT = 220
_HISTORY_SIZE = 50
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

SLASH_COMMANDS: dict[str, str] = {
    "/new": "Start a new conversation",
    "/clear": "Clear the current conversation",
    "/model": "Switch model (e.g. /model gpt-5)",
    "/search": "Search conversations",
    "/export": "Export current conversation",
    "/branch": "Branch the conversation from here",
    "/retry": "Retry the last Emily response",
    "/edit": "Edit the last user message",
    "/cost": "Show cost breakdown",
    "/summarize": "Summarize the conversation",
}


def parse_slash_command(text: str) -> tuple[str, str] | None:
    """Parse a slash command from input text.

    Args:
        text: The input text to parse.

    Returns:
        ``(command, argument)`` tuple if a slash command is detected,
        ``None`` otherwise.
    """
    m = re.match(r"^(/\w+)\s*(.*)", text.strip())
    if m and m.group(1) in SLASH_COMMANDS:
        return m.group(1), m.group(2)
    return None


def format_file_size(size_bytes: int) -> str:
    """Format a file size in human-readable form.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string like ``"1.2 MB"`` or ``"3.4 KB"``.
    """
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def validate_attachments(paths: list[str]) -> tuple[list[str], list[str]]:
    """Validate attachment file paths.

    Args:
        paths: List of file paths.

    Returns:
        ``(valid, errors)`` where ``valid`` is the accepted paths
        and ``errors`` is a list of error messages for rejected files.
    """
    valid: list[str] = []
    errors: list[str] = []
    for path in paths:
        if not os.path.isfile(path):
            errors.append(f"Not a file: {os.path.basename(path)}")
            continue
        size = os.path.getsize(path)
        if size > _MAX_ATTACHMENT_BYTES:
            errors.append(
                f"Too large ({format_file_size(size)}): {os.path.basename(path)}"
            )
            continue
        valid.append(path)
    return valid, errors


class _AttachmentChip(QFrame):
    """Dismissible chip for an attached file."""

    removed = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("attachmentChip")
        self._path = path

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        name = os.path.basename(path)
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        label = QLabel(f"{name} ({format_file_size(size)})")
        label.setObjectName("attachmentChipLabel")
        layout.addWidget(label)

        close_btn = QPushButton("\u2715")
        close_btn.setObjectName("attachmentChipClose")
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(lambda: self.removed.emit(self._path))
        layout.addWidget(close_btn)

    @property
    def file_path(self) -> str:
        """The file path this chip represents."""
        return self._path


class _AutoTextEdit(QTextEdit):
    """QTextEdit that grows vertically and supports input shortcuts."""

    submit_requested = Signal()
    history_up = Signal()
    history_down = Signal()
    slash_triggered = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputTextArea")
        self.setPlaceholderText("Ask Emily anything\u2026")
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumHeight(_MIN_HEIGHT)
        self.setMaximumHeight(_MAX_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAcceptDrops(True)
        self.textChanged.connect(self._resize)
        self.textChanged.connect(self._check_slash)

    def _resize(self) -> None:
        """Auto-resize to fit content."""
        doc = self.document()
        if doc is None:
            return
        margins = self.contentsMargins()
        doc_height = int(doc.size().height()) + margins.top() + margins.bottom() + 4
        target = max(_MIN_HEIGHT, min(doc_height, _MAX_HEIGHT))
        if self.height() != target:
            self.setFixedHeight(target)

    def _check_slash(self) -> None:
        """Emit slash_triggered when ``/`` is typed at start of line."""
        text = self.toPlainText()
        if text.startswith("/") and "\n" not in text:
            self.slash_triggered.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Enter/Ctrl+Enter/Up/Down."""
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if mods & Qt.KeyboardModifier.ControlModifier:
                self.submit_requested.emit()
                event.accept()
                return
            if not mods & Qt.KeyboardModifier.ShiftModifier:
                self.submit_requested.emit()
                event.accept()
                return

        if key == Qt.Key.Key_Up and not self.toPlainText().strip():
            self.history_up.emit()
            event.accept()
            return

        if key == Qt.Key.Key_Down and not self.toPlainText().strip():
            self.history_down.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class InputPanel(QWidget):
    """Enhanced message input area with attachments, toolbar, and slash commands.

    Signals:
        message_submitted(str): User pressed Enter or clicked Send.
        stop_requested(): User clicked Stop during generation.
        web_search_toggled(bool): Web search toggle state changed.
        quick_skill_override(str): One-shot skill override selected.
        slash_command(str, str): Slash command with command name and argument.
        files_attached(list): List of attached file paths.
    """

    message_submitted = Signal(str)
    stop_requested = Signal()
    web_search_toggled = Signal(bool)
    quick_skill_override = Signal(str)
    slash_command = Signal(str, str)
    files_attached = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputPanel")
        self.setAcceptDrops(True)

        self._attachments: list[str] = []
        self._history: deque[str] = deque(maxlen=_HISTORY_SIZE)
        self._history_index: int = -1
        self._web_search_on = False
        self._generating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 8)
        root.setSpacing(4)

        self._attachment_row = QHBoxLayout()
        self._attachment_row.setSpacing(4)
        self._attachment_container = QWidget()
        self._attachment_container.setLayout(self._attachment_row)
        self._attachment_container.setVisible(False)
        root.addWidget(self._attachment_container)

        self._text_edit = _AutoTextEdit()
        self._text_edit.submit_requested.connect(self._on_submit)
        self._text_edit.history_up.connect(self._history_prev)
        self._text_edit.history_down.connect(self._history_next)
        self._text_edit.slash_triggered.connect(self._show_slash_popup)
        root.addWidget(self._text_edit)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._attach_btn = QPushButton("\U0001f4ce")
        self._attach_btn.setObjectName("toolbarBtn")
        self._attach_btn.setToolTip("Attach files")
        self._attach_btn.setFixedSize(30, 30)
        self._attach_btn.clicked.connect(self._open_file_picker)
        toolbar.addWidget(self._attach_btn)

        self._search_btn = QPushButton("\U0001f310")
        self._search_btn.setObjectName("toolbarBtn")
        self._search_btn.setToolTip("Web search")
        self._search_btn.setFixedSize(30, 30)
        self._search_btn.clicked.connect(self._toggle_web_search)
        toolbar.addWidget(self._search_btn)

        self._quick_btn = QPushButton("\u26a1")
        self._quick_btn.setObjectName("toolbarBtn")
        self._quick_btn.setToolTip("Quick mode")
        self._quick_btn.setFixedSize(30, 30)
        self._quick_btn.clicked.connect(self._show_quick_menu)
        toolbar.addWidget(self._quick_btn)

        self._slash_btn = QPushButton("/")
        self._slash_btn.setObjectName("toolbarBtn")
        self._slash_btn.setToolTip("Commands")
        self._slash_btn.setFixedSize(30, 30)
        self._slash_btn.clicked.connect(self._show_slash_popup)
        toolbar.addWidget(self._slash_btn)

        toolbar.addStretch()

        self._send_btn = QPushButton("\u2191")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setToolTip("Send (Enter)")
        self._send_btn.clicked.connect(self._on_submit)
        toolbar.addWidget(self._send_btn)

        self._stop_btn = QPushButton("\u25a0")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setFixedSize(36, 36)
        self._stop_btn.setToolTip("Stop generation (Esc)")
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        toolbar.addWidget(self._stop_btn)

        root.addLayout(toolbar)

        self._update_send_enabled()
        self._text_edit.textChanged.connect(self._update_send_enabled)

    def _update_send_enabled(self) -> None:
        """Enable send button when text is present and not generating."""
        has_text = bool(self._text_edit.toPlainText().strip())
        self._send_btn.setEnabled(has_text and not self._generating)

    def _on_submit(self) -> None:
        """Handle message submission."""
        text = self._text_edit.toPlainText().strip()
        if not text or self._generating:
            return

        parsed = parse_slash_command(text)
        if parsed:
            self.slash_command.emit(parsed[0], parsed[1])
            self._text_edit.clear()
            return

        self._history.append(text)
        self._history_index = -1
        self.message_submitted.emit(text)
        self._text_edit.clear()

    def _history_prev(self) -> None:
        """Navigate to the previous message in history."""
        if not self._history:
            return
        if self._history_index == -1:
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self._text_edit.setPlainText(self._history[self._history_index])

    def _history_next(self) -> None:
        """Navigate to the next message in history."""
        if self._history_index == -1:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._text_edit.setPlainText(self._history[self._history_index])
        else:
            self._history_index = -1
            self._text_edit.clear()

    def _toggle_web_search(self) -> None:
        """Toggle web search mode."""
        self._web_search_on = not self._web_search_on
        obj_name = "toolbarBtnActive" if self._web_search_on else "toolbarBtn"
        self._search_btn.setObjectName(obj_name)
        self._search_btn.style().unpolish(self._search_btn)
        self._search_btn.style().polish(self._search_btn)
        self.web_search_toggled.emit(self._web_search_on)

    def _show_quick_menu(self) -> None:
        """Show the quick skill override popup."""
        menu = QMenu(self)
        for mode in ("Normal", "Deep Think", "Concise", "Code", "Research"):
            action = menu.addAction(mode)
            action.triggered.connect(
                lambda checked=False, m=mode.lower().replace(" ", "_"): self.quick_skill_override.emit(m)
            )
        menu.exec(self._quick_btn.mapToGlobal(self._quick_btn.rect().topLeft()))

    def _show_slash_popup(self) -> None:
        """Show the slash command popup."""
        menu = QMenu(self)
        menu.setObjectName("slashCommandPopup")
        for cmd, desc in SLASH_COMMANDS.items():
            action = menu.addAction(f"{cmd}  \u2014  {desc}")
            action.triggered.connect(
                lambda checked=False, c=cmd: self._insert_slash_command(c)
            )
        menu.exec(self._slash_btn.mapToGlobal(self._slash_btn.rect().topLeft()))

    def _insert_slash_command(self, command: str) -> None:
        """Insert a slash command into the text area.

        Args:
            command: The command string (e.g. ``"/new"``).
        """
        self._text_edit.setPlainText(command + " ")
        cursor = self._text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._text_edit.setTextCursor(cursor)
        self._text_edit.setFocus()

    def _open_file_picker(self) -> None:
        """Open a file picker and attach selected files."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach Files", "", "All Files (*)"
        )
        if paths:
            self._add_attachments(paths)

    def _add_attachments(self, paths: list[str]) -> None:
        """Add file attachments with validation.

        Args:
            paths: List of file paths to attach.
        """
        valid, errors = validate_attachments(paths)
        for path in valid:
            if path not in self._attachments:
                self._attachments.append(path)
                chip = _AttachmentChip(path)
                chip.removed.connect(self._remove_attachment)
                self._attachment_row.addWidget(chip)
        self._attachment_container.setVisible(bool(self._attachments))
        if valid:
            self.files_attached.emit(list(self._attachments))

    def _remove_attachment(self, path: str) -> None:
        """Remove an attachment chip.

        Args:
            path: The file path to remove.
        """
        if path in self._attachments:
            self._attachments.remove(path)
        for i in range(self._attachment_row.count()):
            widget = self._attachment_row.itemAt(i)
            if widget and isinstance(widget.widget(), _AttachmentChip):
                if widget.widget().file_path == path:
                    w = widget.widget()
                    self._attachment_row.removeWidget(w)
                    w.deleteLater()
                    break
        self._attachment_container.setVisible(bool(self._attachments))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept file drag events."""
        if event.mimeData() and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle file drops."""
        if event.mimeData() and event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self._add_attachments(paths)
                event.acceptProposedAction()

    # --- public API -------------------------------------------------

    def set_generating(self, active: bool) -> None:
        """Toggle between generating and idle states.

        Args:
            active: ``True`` during generation.
        """
        self._generating = active
        self._send_btn.setVisible(not active)
        self._stop_btn.setVisible(active)
        self._text_edit.setReadOnly(active)
        self._update_send_enabled()

    def focus_input(self) -> None:
        """Give keyboard focus to the text area."""
        self._text_edit.setFocus()

    def set_placeholder(self, text: str) -> None:
        """Update the placeholder text (e.g. based on active skill).

        Args:
            text: Placeholder text to display.
        """
        self._text_edit.setPlaceholderText(text)

    def get_text(self) -> str:
        """Return the current text in the input area."""
        return self._text_edit.toPlainText()

    def get_attachments(self) -> list[str]:
        """Return the list of attached file paths."""
        return list(self._attachments)

    def clear_attachments(self) -> None:
        """Remove all attachments."""
        self._attachments.clear()
        while self._attachment_row.count():
            item = self._attachment_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._attachment_container.setVisible(False)
