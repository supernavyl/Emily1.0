"""Conversation stream — scrollable list of rich message widgets.

Renders user and Emily messages with full markdown rendering (via
:class:`~emily_chat.ui.markdown_renderer.MarkdownRenderer`), embedded
code blocks (via :class:`~emily_chat.ui.code_block_widget.CodeBlockWidget`),
collapsible thinking chips, and interactive action bars.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from emily_chat.ui.code_block_widget import CodeBlockWidget
from emily_chat.ui.markdown_renderer import MarkdownRenderer, build_document_css
from emily_chat.ui.theme_engine import PALETTES

_CHECKMARK_MS = 1500
_STREAM_DEBOUNCE_MS = 80

_renderer = MarkdownRenderer()


def _get_document_css() -> str:
    """Return theme-aware document CSS for QTextBrowser."""
    return build_document_css(PALETTES.get("dark", {}))


# ---------------------------------------------------------------------------
# MarkdownTextBrowser — interleaved prose + code blocks
# ---------------------------------------------------------------------------


class MarkdownTextBrowser(QWidget):
    """Widget that renders markdown as interleaved HTML prose and code blocks.

    For static content use :meth:`set_markdown`.  For streaming, call
    :meth:`append_markdown` repeatedly — the widget debounces re-renders
    to avoid jank.

    Args:
        parent: Parent widget.
    """

    anchor_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("markdownBrowser")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._raw_md = ""
        self._widgets: list[QWidget] = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_render)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

    def set_markdown(self, md: str) -> None:
        """Render full markdown content (non-streaming).

        Args:
            md: Raw markdown source.
        """
        self._raw_md = md
        self._do_render()

    def append_markdown(self, chunk: str) -> None:
        """Accumulate markdown and schedule a debounced re-render.

        Args:
            chunk: Raw markdown text fragment.
        """
        self._raw_md += chunk
        if not self._debounce_timer.isActive():
            self._debounce_timer.start(_STREAM_DEBOUNCE_MS)

    def full_markdown(self) -> str:
        """Return the accumulated raw markdown source.

        Returns:
            Raw markdown string.
        """
        return self._raw_md

    def full_text(self) -> str:
        """Return the accumulated raw markdown (alias for full_markdown).

        Returns:
            Raw markdown string.
        """
        return self._raw_md

    def _do_render(self) -> None:
        """Re-render the full markdown content into widgets."""
        for w in self._widgets:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._widgets.clear()

        segments = _renderer.render_with_code_blocks(self._raw_md)
        css = _get_document_css()

        for seg in segments:
            if seg["type"] == "html":
                browser = QTextBrowser()
                browser.setObjectName("markdownBrowserSegment")
                browser.setOpenExternalLinks(False)
                browser.setOpenLinks(False)
                browser.anchorClicked.connect(
                    lambda url: QDesktopServices.openUrl(url)
                )
                browser.setReadOnly(True)
                browser.setVerticalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                )
                browser.setHorizontalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                )
                doc = browser.document()
                if doc is not None:
                    doc.setDefaultStyleSheet(css)
                browser.setHtml(seg["content"])
                if doc is not None:
                    doc.adjustSize()
                    browser.setFixedHeight(int(doc.size().height()) + 4)
                browser.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                self._layout.addWidget(browser)
                self._widgets.append(browser)
            elif seg["type"] == "code":
                cb = CodeBlockWidget(seg["content"], seg.get("lang", ""))
                self._layout.addWidget(cb)
                self._widgets.append(cb)

    def clear(self) -> None:
        """Clear all content."""
        self._raw_md = ""
        for w in self._widgets:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._widgets.clear()


# ---------------------------------------------------------------------------
# Action bar helper
# ---------------------------------------------------------------------------


class _ActionBar(QWidget):
    """Row of action buttons below a message bubble."""

    def __init__(
        self,
        buttons: list[tuple[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("actionBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        self._buttons: dict[str, QPushButton] = {}
        for key, label in buttons:
            btn = QPushButton(label)
            btn.setObjectName("actionBtn" if key not in ("like", "dislike") else "feedbackBtn")
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

    def button(self, key: str) -> QPushButton | None:
        """Return the button for *key*, or ``None``.

        Args:
            key: Button identifier.

        Returns:
            The QPushButton, or None.
        """
        return self._buttons.get(key)


# ---------------------------------------------------------------------------
# UserMessageWidget
# ---------------------------------------------------------------------------


class UserMessageWidget(QFrame):
    """Right-aligned user message with markdown body and action bar.

    Signals:
        edit_submitted(str, str): ``(message_id, new_text)``
        resend_requested(str): ``(message_id,)``
        copy_requested(str): ``(message_id,)``
    """

    edit_submitted = Signal(str, str)
    resend_requested = Signal(str)
    copy_requested = Signal(str)

    def __init__(
        self,
        text: str,
        msg_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("userBubble")
        self._text = text
        self._msg_id = msg_id
        self._edit_mode = False
        self._versions: list[str] = [text]

        outer = QHBoxLayout(self)
        outer.setContentsMargins(60, 4, 8, 4)
        outer.addStretch()

        col = QVBoxLayout()
        col.setSpacing(2)

        self._header = QLabel(f"You  \u00b7  {datetime.now():%H:%M}")
        self._header.setObjectName("bubbleHeader")
        self._header.setAlignment(Qt.AlignmentFlag.AlignRight)
        col.addWidget(self._header)

        self._body = MarkdownTextBrowser()
        self._body.set_markdown(text)
        col.addWidget(self._body)

        self._edit_area = QTextEdit()
        self._edit_area.setObjectName("inputTextArea")
        self._edit_area.setVisible(False)
        self._edit_area.setMaximumHeight(150)
        col.addWidget(self._edit_area)

        self._edit_bar = QWidget()
        edit_bar_layout = QHBoxLayout(self._edit_bar)
        edit_bar_layout.setContentsMargins(0, 0, 0, 0)
        self._send_edit_btn = QPushButton("Send Edit")
        self._send_edit_btn.setObjectName("actionBtn")
        self._send_edit_btn.clicked.connect(self._on_send_edit)
        self._cancel_edit_btn = QPushButton("Cancel")
        self._cancel_edit_btn.setObjectName("actionBtn")
        self._cancel_edit_btn.clicked.connect(self._on_cancel_edit)
        edit_bar_layout.addStretch()
        edit_bar_layout.addWidget(self._cancel_edit_btn)
        edit_bar_layout.addWidget(self._send_edit_btn)
        self._edit_bar.setVisible(False)
        col.addWidget(self._edit_bar)

        self._version_label = QLabel("")
        self._version_label.setObjectName("bubbleHeader")
        self._version_label.setVisible(False)
        col.addWidget(self._version_label)

        self._action_bar = _ActionBar([
            ("copy", "\U0001f4cb Copy"),
            ("edit", "\u270f\ufe0f Edit"),
            ("resend", "\U0001f501 Resend"),
        ])
        bar_copy = self._action_bar.button("copy")
        if bar_copy:
            bar_copy.clicked.connect(self._on_copy)
        bar_edit = self._action_bar.button("edit")
        if bar_edit:
            bar_edit.clicked.connect(self._on_edit)
        bar_resend = self._action_bar.button("resend")
        if bar_resend:
            bar_resend.clicked.connect(lambda: self.resend_requested.emit(self._msg_id))
        col.addWidget(self._action_bar)

        outer.addLayout(col)

    @property
    def msg_id(self) -> str:
        """The message identifier."""
        return self._msg_id

    @property
    def raw_text(self) -> str:
        """The raw message text."""
        return self._text

    def _on_copy(self) -> None:
        """Copy raw text to clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._text)
        btn = self._action_bar.button("copy")
        if btn:
            btn.setText("\u2713 Copied")
            QTimer.singleShot(_CHECKMARK_MS, lambda: btn.setText("\U0001f4cb Copy"))
        self.copy_requested.emit(self._msg_id)

    def _on_edit(self) -> None:
        """Enter edit mode."""
        self._edit_mode = True
        self._body.setVisible(False)
        self._edit_area.setPlainText(self._text)
        self._edit_area.setVisible(True)
        self._edit_bar.setVisible(True)
        self._action_bar.setVisible(False)

    def _on_send_edit(self) -> None:
        """Submit the edited text."""
        new_text = self._edit_area.toPlainText()
        self._versions.append(new_text)
        self._text = new_text
        self._body.set_markdown(new_text)
        self._exit_edit_mode()
        self._version_label.setText(f"[edited \u00b7 v{len(self._versions)}]")
        self._version_label.setVisible(True)
        self.edit_submitted.emit(self._msg_id, new_text)

    def _on_cancel_edit(self) -> None:
        """Cancel editing."""
        self._exit_edit_mode()

    def _exit_edit_mode(self) -> None:
        """Return to display mode."""
        self._edit_mode = False
        self._edit_area.setVisible(False)
        self._edit_bar.setVisible(False)
        self._body.setVisible(True)
        self._action_bar.setVisible(True)


# ---------------------------------------------------------------------------
# EmilyMessageWidget
# ---------------------------------------------------------------------------


class EmilyMessageWidget(QFrame):
    """Left-aligned Emily response with markdown body, thinking, and action bar.

    Signals:
        feedback_given(str, bool): ``(message_id, positive)``
        retry_requested(str): ``(message_id,)``
        branch_requested(str): ``(message_id,)``
        copy_requested(str): ``(message_id,)``
    """

    feedback_given = Signal(str, bool)
    retry_requested = Signal(str)
    branch_requested = Signal(str)
    copy_requested = Signal(str)

    def __init__(
        self,
        msg_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emilyBubble")
        self._msg_id = msg_id
        self._thinking_text = ""

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 4, 60, 4)

        col = QVBoxLayout()
        col.setSpacing(2)

        self._header = QLabel("Emily")
        self._header.setObjectName("bubbleHeader")
        col.addWidget(self._header)

        # --- collapsible thinking block ---
        self._thinking_frame = QFrame()
        self._thinking_frame.setObjectName("inlineThinkingBlock")
        thinking_layout = QVBoxLayout(self._thinking_frame)
        thinking_layout.setContentsMargins(0, 0, 0, 0)
        thinking_layout.setSpacing(0)

        self._thinking_toggle = QPushButton("")
        self._thinking_toggle.setObjectName("inlineThinkingToggle")
        self._thinking_toggle.clicked.connect(self._toggle_thinking)
        thinking_layout.addWidget(self._thinking_toggle)

        self._thinking_content = QLabel("")
        self._thinking_content.setObjectName("inlineThinkingContent")
        self._thinking_content.setWordWrap(True)
        self._thinking_content.setVisible(False)
        self._thinking_content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        thinking_layout.addWidget(self._thinking_content)

        self._thinking_frame.setVisible(False)
        col.addWidget(self._thinking_frame)

        # --- markdown body ---
        self._body = MarkdownTextBrowser()
        col.addWidget(self._body)

        # --- action bar ---
        self._action_bar = _ActionBar([
            ("like", "\U0001f44d"),
            ("dislike", "\U0001f44e"),
            ("copy", "\U0001f4cb Copy"),
            ("copy_md", "\U0001f4cb MD"),
            ("retry", "\U0001f501 Retry"),
            ("branch", "\u2702\ufe0f Branch"),
        ])

        bar_like = self._action_bar.button("like")
        if bar_like:
            bar_like.clicked.connect(lambda: self._on_feedback(True))
        bar_dislike = self._action_bar.button("dislike")
        if bar_dislike:
            bar_dislike.clicked.connect(lambda: self._on_feedback(False))
        bar_copy = self._action_bar.button("copy")
        if bar_copy:
            bar_copy.clicked.connect(self._on_copy)
        bar_copy_md = self._action_bar.button("copy_md")
        if bar_copy_md:
            bar_copy_md.clicked.connect(self._on_copy_md)
        bar_retry = self._action_bar.button("retry")
        if bar_retry:
            bar_retry.clicked.connect(lambda: self.retry_requested.emit(self._msg_id))
        bar_branch = self._action_bar.button("branch")
        if bar_branch:
            bar_branch.clicked.connect(lambda: self.branch_requested.emit(self._msg_id))

        col.addWidget(self._action_bar)

        outer.addLayout(col)
        outer.addStretch()

    @property
    def msg_id(self) -> str:
        """The message identifier."""
        return self._msg_id

    # --- streaming API ------------------------------------------------

    def append_text(self, chunk: str) -> None:
        """Append a text chunk during streaming.

        Args:
            chunk: Raw markdown text fragment.
        """
        self._body.append_markdown(chunk)

    def set_thinking_text(self, text: str) -> None:
        """Set thinking content (used when loading stored messages).

        Args:
            text: Full thinking text.
        """
        self._thinking_text = text
        if text:
            self._thinking_content.setText(text)

    def set_thinking_chip(self, label: str) -> None:
        """Show the collapsed thinking summary chip.

        Args:
            label: Chip text like ``"Thought for 8.2s"``.
        """
        self._thinking_toggle.setText(label)
        self._thinking_frame.setVisible(True)

    def set_header(self, model_badge: str) -> None:
        """Update the header with a model badge.

        Args:
            model_badge: Text to display after ``"Emily"``.
        """
        self._header.setText(f"Emily  \u00b7  {model_badge}")

    def finish(self, metadata: dict | None = None) -> None:
        """Finalise the bubble after streaming ends.

        Args:
            metadata: Generation metadata dict.
        """
        self._body._debounce_timer.stop()
        self._body._do_render()

        if metadata:
            latency = metadata.get("latency_ms", "")
            tokens = metadata.get("output_tokens", "")
            parts: list[str] = []
            if latency:
                parts.append(f"{latency / 1000:.1f}s")
            if tokens:
                parts.append(f"{tokens:,} tokens")
            if parts:
                self._header.setText(
                    f"Emily  \u00b7  {' \u00b7 '.join(parts)}"
                )

    def full_text(self) -> str:
        """Return the accumulated response text.

        Returns:
            Raw markdown string.
        """
        return self._body.full_markdown()

    # --- thinking toggle ----------------------------------------------

    def _toggle_thinking(self) -> None:
        """Toggle inline thinking content visibility."""
        visible = not self._thinking_content.isVisible()
        self._thinking_content.setVisible(visible)

    # --- action handlers ----------------------------------------------

    def _on_feedback(self, positive: bool) -> None:
        """Handle like/dislike feedback.

        Args:
            positive: ``True`` for like, ``False`` for dislike.
        """
        btn_key = "like" if positive else "dislike"
        btn = self._action_bar.button(btn_key)
        if btn:
            btn.setProperty("active", "true")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        other_key = "dislike" if positive else "like"
        other = self._action_bar.button(other_key)
        if other:
            other.setProperty("active", "false")
            other.style().unpolish(other)
            other.style().polish(other)
        self.feedback_given.emit(self._msg_id, positive)

    def _on_copy(self) -> None:
        """Copy plain text to clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._body.full_text())
        btn = self._action_bar.button("copy")
        if btn:
            btn.setText("\u2713 Copied")
            QTimer.singleShot(_CHECKMARK_MS, lambda: btn.setText("\U0001f4cb Copy"))
        self.copy_requested.emit(self._msg_id)

    def _on_copy_md(self) -> None:
        """Copy raw markdown to clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._body.full_markdown())
        btn = self._action_bar.button("copy_md")
        if btn:
            btn.setText("\u2713 Copied")
            QTimer.singleShot(_CHECKMARK_MS, lambda: btn.setText("\U0001f4cb MD"))


# ---------------------------------------------------------------------------
# ThinkingIndicator
# ---------------------------------------------------------------------------


class ThinkingIndicator(QWidget):
    """Animated indicator shown while Emily is generating.

    In normal mode shows ``"Emily is thinking"`` with pulsing dots.
    In deep-think mode shows elapsed time and a preview of current
    thoughts.

    Args:
        parent: Parent widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("thinkingIndicator")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self._label = QLabel("Emily is thinking")
        self._label.setObjectName("bubbleHeader")
        layout.addWidget(self._label)

        self._dots = QLabel("")
        self._dots.setObjectName("thinkingDots")
        layout.addWidget(self._dots)

        layout.addStretch()

        self._elapsed_label = QLabel("")
        self._elapsed_label.setObjectName("thinkingElapsed")
        self._elapsed_label.setVisible(False)
        layout.addWidget(self._elapsed_label)

        self._preview_label = QLabel("")
        self._preview_label.setObjectName("thinkingPreview")
        self._preview_label.setVisible(False)
        self._preview_label.setMaximumWidth(200)
        layout.addWidget(self._preview_label)

        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._animate_dots)
        self._dot_state = 0
        self._deep_mode = False
        self._elapsed: float = 0.0

    def start(self, deep: bool = False) -> None:
        """Start the animation.

        Args:
            deep: If ``True``, show deep-think mode with timer.
        """
        self._deep_mode = deep
        self._dot_state = 0
        self._elapsed = 0.0
        self.setVisible(True)

        if deep:
            self._label.setText("Emily is reasoning...")
            self._elapsed_label.setVisible(True)
            self._preview_label.setVisible(True)
        else:
            self._label.setText("Emily is thinking")
            self._elapsed_label.setVisible(False)
            self._preview_label.setVisible(False)

        self._dot_timer.start(400)

    def stop(self) -> None:
        """Stop the animation and hide."""
        self._dot_timer.stop()
        self.setVisible(False)

    def set_preview(self, text: str) -> None:
        """Update the thought preview text.

        Args:
            text: Last ~50 chars of thinking stream.
        """
        if len(text) > 50:
            text = "\u2026" + text[-50:]
        self._preview_label.setText(text)

    def set_elapsed(self, seconds: float) -> None:
        """Update the elapsed timer.

        Args:
            seconds: Elapsed time in seconds.
        """
        self._elapsed = seconds
        self._elapsed_label.setText(f"[{seconds:.1f}s]")

    def _animate_dots(self) -> None:
        """Cycle the dot animation."""
        self._dot_state = (self._dot_state + 1) % 4
        self._dots.setText("\u00b7 " * self._dot_state)


# ---------------------------------------------------------------------------
# _EmptyState
# ---------------------------------------------------------------------------


class _EmptyState(QWidget):
    """Shown when there are no messages in the conversation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        avatar = QLabel("E")
        avatar.setObjectName("emptyStateAvatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(64, 64)
        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignCenter)

        prompt = QLabel("What would you like to explore?")
        prompt.setObjectName("emptyStatePrompt")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt)


# ---------------------------------------------------------------------------
# ConversationStream
# ---------------------------------------------------------------------------


class ConversationStream(QScrollArea):
    """Scrollable area containing message bubbles.

    Signals:
        scroll_locked_changed(bool): Emitted when auto-scroll state changes.
        edit_requested(str, str): ``(msg_id, new_text)``
        resend_requested(str): ``(msg_id,)``
        retry_requested(str): ``(msg_id,)``
        branch_requested(str): ``(msg_id,)``
        feedback_given(str, bool): ``(msg_id, positive)``
        message_clicked(str): ``(msg_id,)`` — for loading thinking in right panel
    """

    scroll_locked_changed = Signal(bool)
    edit_requested = Signal(str, str)
    resend_requested = Signal(str)
    retry_requested = Signal(str)
    branch_requested = Signal(str)
    feedback_given = Signal(str, bool)
    message_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("conversationStream")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._container = QWidget()
        self._container.setObjectName("conversationContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(4)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._empty_state = _EmptyState()
        self._layout.insertWidget(0, self._empty_state)
        self._messages: list[QWidget] = []
        self._active_emily_bubble: EmilyMessageWidget | None = None
        self._thinking_indicator: ThinkingIndicator | None = None
        self._auto_scroll = True
        self._msg_counter = 0

        vbar = self.verticalScrollBar()
        if vbar is not None:
            vbar.rangeChanged.connect(self._on_range_changed)
            vbar.valueChanged.connect(self._on_value_changed)

    def _hide_empty_state(self) -> None:
        """Hide the empty state widget."""
        if self._empty_state.isVisible():
            self._empty_state.setVisible(False)

    def _on_range_changed(self, _min: int, _max: int) -> None:
        """Auto-scroll when content grows."""
        if self._auto_scroll:
            vbar = self.verticalScrollBar()
            if vbar is not None:
                vbar.setValue(_max)

    def _on_value_changed(self, value: int) -> None:
        """Track whether the user has scrolled away from bottom."""
        vbar = self.verticalScrollBar()
        if vbar is None:
            return
        at_bottom = value >= vbar.maximum() - 20
        if at_bottom != self._auto_scroll:
            self._auto_scroll = at_bottom
            self.scroll_locked_changed.emit(not at_bottom)

    def _next_msg_id(self) -> str:
        """Generate a sequential message ID.

        Returns:
            A string message ID.
        """
        self._msg_counter += 1
        return f"msg-{self._msg_counter}"

    def _wire_emily_signals(self, bubble: EmilyMessageWidget) -> None:
        """Connect Emily bubble signals to stream-level signals.

        Args:
            bubble: The Emily message widget.
        """
        bubble.feedback_given.connect(self.feedback_given.emit)
        bubble.retry_requested.connect(self.retry_requested.emit)
        bubble.branch_requested.connect(self.branch_requested.emit)

    def _wire_user_signals(self, bubble: UserMessageWidget) -> None:
        """Connect user bubble signals to stream-level signals.

        Args:
            bubble: The user message widget.
        """
        bubble.edit_submitted.connect(self.edit_requested.emit)
        bubble.resend_requested.connect(self.resend_requested.emit)

    # --- public API -------------------------------------------------

    def append_user_message(self, text: str) -> None:
        """Add a user message bubble.

        Args:
            text: The user's message text.
        """
        self._hide_empty_state()
        msg_id = self._next_msg_id()
        bubble = UserMessageWidget(text, msg_id=msg_id)
        self._wire_user_signals(bubble)
        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, bubble)
        self._messages.append(bubble)
        self._auto_scroll = True

    def start_emily_message(self, deep_think: bool = False) -> None:
        """Begin a new Emily response bubble (streaming mode).

        Args:
            deep_think: If ``True``, show the deep-think indicator.
        """
        self._hide_empty_state()

        indicator = ThinkingIndicator()
        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, indicator)
        indicator.start(deep=deep_think)
        self._thinking_indicator = indicator

        msg_id = self._next_msg_id()
        bubble = EmilyMessageWidget(msg_id=msg_id)
        self._wire_emily_signals(bubble)
        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, bubble)
        self._messages.append(bubble)
        self._active_emily_bubble = bubble
        self._auto_scroll = True

    @Slot(str)
    def append_emily_text(self, chunk: str) -> None:
        """Append a text chunk to the active Emily bubble.

        Args:
            chunk: Raw markdown text fragment.
        """
        if self._active_emily_bubble is not None:
            self._active_emily_bubble.append_text(chunk)

    def finish_emily_message(
        self,
        metadata: dict | None = None,
        thinking_seconds: float | None = None,
    ) -> None:
        """Finalise the active Emily bubble after streaming completes.

        Args:
            metadata: Generation metadata dict.
            thinking_seconds: Time spent on thinking (for the chip).
        """
        if self._thinking_indicator is not None:
            self._thinking_indicator.stop()
            self._layout.removeWidget(self._thinking_indicator)
            self._thinking_indicator.deleteLater()
            self._thinking_indicator = None

        if self._active_emily_bubble is not None:
            self._active_emily_bubble.finish(metadata)
            if thinking_seconds is not None and thinking_seconds > 0:
                self._active_emily_bubble.set_thinking_chip(
                    f"\U0001f9e0 Thought for {thinking_seconds:.1f}s"
                )
            self._active_emily_bubble = None

    def get_active_response_text(self) -> str:
        """Return the text accumulated so far in the active Emily bubble.

        Returns:
            Raw markdown string, or empty string.
        """
        if self._active_emily_bubble is not None:
            return self._active_emily_bubble.full_text()
        return ""

    def clear_messages(self) -> None:
        """Remove all messages and show the empty state."""
        for w in self._messages:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._messages.clear()
        self._active_emily_bubble = None
        if self._thinking_indicator is not None:
            self._thinking_indicator.stop()
            self._layout.removeWidget(self._thinking_indicator)
            self._thinking_indicator.deleteLater()
            self._thinking_indicator = None
        self._empty_state.setVisible(True)

    def load_messages(self, messages: list[dict]) -> None:
        """Populate from stored messages (dicts with *role* and *content*).

        Args:
            messages: List of dicts with ``role`` and ``content`` keys,
                and optionally ``thinking_content``.
        """
        self.clear_messages()
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                self.append_user_message(content)
            elif role == "assistant":
                self.start_emily_message()
                self.append_emily_text(content)
                thinking = msg.get("thinking_content", "")
                if thinking and self._active_emily_bubble:
                    self._active_emily_bubble.set_thinking_text(thinking)
                self.finish_emily_message()
