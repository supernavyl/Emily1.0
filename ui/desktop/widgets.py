"""Reusable widgets for Emily Desktop."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme


class MessageBubble(QFrame):
    """A single chat message bubble."""

    def __init__(self, text: str, role: str = "user", parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QLabel("You" if role == "user" else "Emily")
        header.setStyleSheet(
            f"color: {'#58a6ff' if role == 'user' else '#c9a0dc'}; "
            f"font-size: 12px; font-weight: 600; padding: 0; margin: 0;"
        )
        layout.addWidget(header)

        # Content
        self.content_label = QLabel(text)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.content_label.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 14px; padding: 0; margin: 0;"
        )
        layout.addWidget(self.content_label)

        # Bubble styling
        bg = theme.USER_BUBBLE if role == "user" else theme.EMILY_BUBBLE
        self.setStyleSheet(
            f"MessageBubble {{ background-color: {bg}; border-radius: 12px; padding: 12px 16px; }}"
        )

    def append_text(self, text: str) -> None:
        current = self.content_label.text()
        self.content_label.setText(current + text)


class ThinkingBubble(QFrame):
    """Collapsible thinking/reasoning display."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._toggle = QPushButton("Thinking...")
        self._toggle.setStyleSheet(
            f"color: {theme.THINKING_BORDER}; background: transparent; "
            f"border: none; font-size: 12px; font-style: italic; text-align: left; padding: 0;"
        )
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle)

        self._content = QLabel("")
        self._content.setWordWrap(True)
        self._content.setVisible(False)
        self._content.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 13px; padding: 4px 0 0 0;"
        )
        layout.addWidget(self._content)

        self.setStyleSheet(
            f"ThinkingBubble {{ background-color: {theme.THINKING_BG}; "
            f"border-left: 3px solid {theme.THINKING_BORDER}; "
            f"border-radius: 8px; padding: 10px 14px; }}"
        )
        self._expanded = False
        self._text = ""

    def append_text(self, text: str) -> None:
        self._text += text
        word_count = len(self._text.split())
        self._toggle.setText(f"Thinking... ({word_count} words)")
        if self._expanded:
            self._content.setText(self._text)

    def finalize(self) -> None:
        word_count = len(self._text.split())
        self._toggle.setText(f"Thought for {word_count} words")

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        if self._expanded:
            self._content.setText(self._text)


class ChatInput(QPlainTextEdit):
    """Multi-line input that sends on Enter (Shift+Enter for newline)."""

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("messageInput")
        self.setPlaceholderText("Message Emily...")
        self.setMaximumHeight(150)
        self.setMinimumHeight(44)
        font = QFont("Inter", 14)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)
        self.setTabChangesFocus(True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                text = self.toPlainText().strip()
                if text:
                    self.submitted.emit(text)
                    self.clear()
        else:
            super().keyPressEvent(event)


class StatRow(QWidget):
    """A label + value stat display."""

    def __init__(self, label: str, value: str = "--", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self._label = QLabel(label)
        self._label.setProperty("class", "statLabel")
        self._label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")

        self._value = QLabel(value)
        self._value.setProperty("class", "statValue")
        self._value.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
        )
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self._label)
        layout.addStretch()
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value)
