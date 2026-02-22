"""Global search overlay triggered by Ctrl+K.

Provides FTS5-powered conversation search with filters, commands,
and keyboard navigation.  Results are populated asynchronously by
the controller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

COMMANDS: list[dict[str, str]] = [
    {"id": "new", "label": "New Conversation", "shortcut": "Ctrl+N"},
    {"id": "switch_model", "label": "Switch Model", "shortcut": ""},
    {"id": "export", "label": "Export Conversation", "shortcut": ""},
    {"id": "fork", "label": "Fork Conversation", "shortcut": ""},
    {"id": "settings", "label": "Settings", "shortcut": ""},
]

FILTER_OPTIONS = ("All", "Model", "Skill", "Date", "Cost")


def format_search_result(
    title: str,
    excerpt: str,
    model: str | None = None,
    message_count: int = 0,
    cost: float = 0.0,
    updated_at: datetime | None = None,
) -> dict[str, str]:
    """Format a search result for display in the overlay.

    Args:
        title: Conversation title.
        excerpt: Highlighted text excerpt.
        model: Model badge text.
        message_count: Number of messages.
        cost: Total conversation cost.
        updated_at: Last update time.

    Returns:
        Dict with ``title``, ``excerpt``, ``meta`` keys.
    """
    meta_parts: list[str] = []
    if model:
        meta_parts.append(model)
    if message_count:
        meta_parts.append(f"{message_count} msgs")
    if cost > 0:
        meta_parts.append(f"${cost:.3f}")
    if updated_at:
        now = datetime.now(timezone.utc)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        delta = now - updated_at
        if delta.days == 0:
            meta_parts.append("Today")
        elif delta.days == 1:
            meta_parts.append("Yesterday")
        elif delta.days < 7:
            meta_parts.append(f"{delta.days}d ago")
        else:
            meta_parts.append(updated_at.strftime("%b %d"))
    return {
        "title": title,
        "excerpt": excerpt,
        "meta": " \u2022 ".join(meta_parts),
    }


def filter_results(
    results: list[dict[str, Any]],
    active_filter: str,
    filter_value: str = "",
) -> list[dict[str, Any]]:
    """Apply a filter to search results.

    Args:
        results: List of result dicts.
        active_filter: Filter category from ``FILTER_OPTIONS``.
        filter_value: Value to filter on (model name, skill name, etc.).

    Returns:
        Filtered list.
    """
    if active_filter == "All" or not filter_value:
        return results
    key = active_filter.lower()
    return [r for r in results if filter_value.lower() in str(r.get(key, "")).lower()]


class _SearchResultWidget(QWidget):
    """A single search result row."""

    clicked = Signal(str)

    def __init__(
        self,
        conv_id: str,
        title: str,
        excerpt: str,
        meta: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("searchResultItem")
        self._conv_id = conv_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("searchResultTitle")
        title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(title_label)

        if excerpt:
            exc_label = QLabel(excerpt)
            exc_label.setObjectName("searchResultExcerpt")
            exc_label.setWordWrap(True)
            exc_label.setStyleSheet("font-size: 11px; opacity: 0.7;")
            layout.addWidget(exc_label)

        if meta:
            meta_label = QLabel(meta)
            meta_label.setObjectName("searchResultMeta")
            meta_label.setStyleSheet("font-size: 10px; opacity: 0.5;")
            layout.addWidget(meta_label)

    def mousePressEvent(self, event: Any) -> None:
        """Emit clicked on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._conv_id)
        super().mousePressEvent(event)


class _CommandWidget(QWidget):
    """A single command row."""

    clicked = Signal(str)

    def __init__(
        self,
        cmd_id: str,
        label: str,
        shortcut: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("searchCommandItem")
        self._cmd_id = cmd_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        name = QLabel(label)
        layout.addWidget(name)
        layout.addStretch()

        if shortcut:
            sc = QLabel(shortcut)
            sc.setStyleSheet("font-size: 10px; opacity: 0.5;")
            layout.addWidget(sc)

    def mousePressEvent(self, event: Any) -> None:
        """Emit clicked on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._cmd_id)
        super().mousePressEvent(event)


class GlobalSearchOverlay(QWidget):
    """Ctrl+K search overlay with results, filters, and commands.

    Signals:
        conversation_opened(str): Emitted with conversation ID.
        command_executed(str): Emitted with command ID.
        search_query(str): Emitted when the user types a search query.
    """

    conversation_opened = Signal(str)
    command_executed = Signal(str)
    search_query = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchOverlay")
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._panel = QWidget()
        self._panel.setObjectName("searchOverlayPanel")
        self._panel.setFixedWidth(560)
        self._panel.setMaximumHeight(500)

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchOverlayInput")
        self._search_input.setPlaceholderText("Search conversations, type a command\u2026")
        panel_layout.addWidget(self._search_input)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        self._filter_btns: dict[str, QPushButton] = {}
        for f in FILTER_OPTIONS:
            btn = QPushButton(f)
            btn.setObjectName("toolbarBtn")
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked=False, name=f: self._set_filter(name))
            filter_row.addWidget(btn)
            self._filter_btns[f] = btn
        filter_row.addStretch()
        panel_layout.addLayout(filter_row)
        self._active_filter = "All"

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(2)
        self._results_layout.addStretch()
        self._scroll.setWidget(self._results_container)

        panel_layout.addWidget(self._scroll, stretch=1)

        outer.addWidget(self._panel)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(100)
        self._debounce.timeout.connect(
            lambda: self.search_query.emit(self._search_input.text())
        )
        self._search_input.textChanged.connect(lambda _: self._debounce.start())

        self._populate_commands()

    def toggle(self) -> None:
        """Show or hide the overlay."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self._search_input.clear()
            self._search_input.setFocus()
            self._populate_commands()

    def set_results(
        self,
        results: list[dict[str, Any]],
    ) -> None:
        """Populate the overlay with search results.

        Args:
            results: List of dicts with ``conv_id``, ``title``, ``excerpt``,
                and optional ``meta`` keys.
        """
        self._clear_results()
        for r in results:
            widget = _SearchResultWidget(
                conv_id=r.get("conv_id", ""),
                title=r.get("title", ""),
                excerpt=r.get("excerpt", ""),
                meta=r.get("meta", ""),
            )
            widget.clicked.connect(self._on_result_clicked)
            self._results_layout.insertWidget(
                self._results_layout.count() - 1, widget
            )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Escape to close."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _populate_commands(self) -> None:
        """Show default command entries."""
        self._clear_results()

        section_label = QLabel("COMMANDS")
        section_label.setStyleSheet("font-size: 10px; font-weight: 600; opacity: 0.5; padding: 4px 8px;")
        self._results_layout.insertWidget(0, section_label)

        for cmd in COMMANDS:
            widget = _CommandWidget(
                cmd_id=cmd["id"],
                label=cmd["label"],
                shortcut=cmd.get("shortcut", ""),
            )
            widget.clicked.connect(self._on_command_clicked)
            self._results_layout.insertWidget(
                self._results_layout.count() - 1, widget
            )

    def _clear_results(self) -> None:
        """Remove all result widgets."""
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _set_filter(self, name: str) -> None:
        """Set the active filter.

        Args:
            name: Filter name from ``FILTER_OPTIONS``.
        """
        self._active_filter = name
        for fname, btn in self._filter_btns.items():
            btn.setObjectName("toolbarBtnActive" if fname == name else "toolbarBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_result_clicked(self, conv_id: str) -> None:
        """Handle a search result click.

        Args:
            conv_id: The conversation ID to open.
        """
        self.conversation_opened.emit(conv_id)
        self.hide()

    def _on_command_clicked(self, cmd_id: str) -> None:
        """Handle a command click.

        Args:
            cmd_id: The command ID to execute.
        """
        self.command_executed.emit(cmd_id)
        self.hide()
