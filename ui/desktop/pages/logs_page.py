"""Logs page — real-time log viewer and audit trail."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme


class LogsPage(QWidget):
    """Log viewer — application logs + audit trail with live refresh."""

    def __init__(self, base_url: str = "http://localhost:8000", parent: QWidget | None = None):
        super().__init__(parent)
        self._base_url = base_url
        self._nam = QNetworkAccessManager(self)
        self._auto_scroll = True
        self._log_filter = ""
        self._log_level = "all"
        self._seen_count = 0

        self._build_ui()

        # Auto-refresh every 3s
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_logs)
        self._refresh_timer.start(3000)

        QTimer.singleShot(200, self._fetch_logs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()

        title = QLabel("LOGS")
        title.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 16px; font-weight: 700;")
        toolbar.addWidget(title)
        toolbar.addSpacing(20)

        # Log type selector
        self._log_type = QComboBox()
        self._log_type.addItems(["Application Logs", "Audit Trail"])
        self._log_type.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.TEXT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 8px;"
        )
        self._log_type.currentIndexChanged.connect(lambda _: self._fetch_logs())
        toolbar.addWidget(self._log_type)

        # Level filter
        self._level_combo = QComboBox()
        self._level_combo.addItems(["all", "info", "warning", "error", "debug"])
        self._level_combo.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.TEXT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 8px;"
        )
        self._level_combo.currentTextChanged.connect(self._on_level_change)
        toolbar.addWidget(QLabel("Level:"))
        toolbar.addWidget(self._level_combo)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter logs...")
        self._search.setStyleSheet(
            f"background-color: {theme.BG_INPUT}; color: {theme.TEXT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 6px 10px; font-size: 12px;"
        )
        self._search.textChanged.connect(self._on_filter_change)
        toolbar.addWidget(self._search, 1)

        toolbar.addStretch()

        # Buttons
        self._auto_scroll_btn = QPushButton("Auto-scroll: ON")
        self._auto_scroll_btn.setCheckable(True)
        self._auto_scroll_btn.setChecked(True)
        self._auto_scroll_btn.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.SUCCESS}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        self._auto_scroll_btn.toggled.connect(self._on_auto_scroll_toggle)
        toolbar.addWidget(self._auto_scroll_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.TEXT_SECONDARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        clear_btn.clicked.connect(self._clear_logs)
        toolbar.addWidget(clear_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.TEXT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        refresh_btn.clicked.connect(self._fetch_logs)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        # Log display
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setObjectName("logView")
        self._log_view.setStyleSheet(
            f"QPlainTextEdit {{ "
            f"  background-color: {theme.BG_PRIMARY}; "
            f"  color: {theme.TEXT_PRIMARY}; "
            f"  border: 1px solid {theme.BORDER}; "
            f"  border-radius: 8px; "
            f"  padding: 12px; "
            f"  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace; "
            f"  font-size: 12px; "
            f"  selection-background-color: {theme.USER_BUBBLE}; "
            f"}}"
        )
        layout.addWidget(self._log_view, 1)

        # Status bar
        status = QHBoxLayout()
        self._log_count = QLabel("0 entries")
        self._log_count.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        status.addWidget(self._log_count)
        status.addStretch()
        self._last_refresh = QLabel("")
        self._last_refresh.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        status.addWidget(self._last_refresh)
        layout.addLayout(status)

    def _on_level_change(self, level: str) -> None:
        self._log_level = level
        self._fetch_logs()

    def _on_filter_change(self, text: str) -> None:
        self._log_filter = text.lower()
        self._refilter()

    def _on_auto_scroll_toggle(self, checked: bool) -> None:
        self._auto_scroll = checked
        self._auto_scroll_btn.setText(f"Auto-scroll: {'ON' if checked else 'OFF'}")
        color = theme.SUCCESS if checked else theme.TEXT_MUTED
        self._auto_scroll_btn.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {color}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )

    def _fetch_logs(self) -> None:
        is_audit = self._log_type.currentIndex() == 1
        url = QUrl(f"{self._base_url}/logs/recent?n=200")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_logs(reply, is_audit))

    def _handle_logs(self, reply: QNetworkReply, is_audit: bool) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._log_view.setPlainText(f"Failed to fetch logs: {reply.errorString()}")
            reply.deleteLater()
            return

        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            entries = data.get("audit" if is_audit else "logs", [])
            self._render_entries(entries)
        except Exception as e:
            self._log_view.setPlainText(f"Error parsing logs: {e}")
        reply.deleteLater()

        from datetime import datetime

        self._last_refresh.setText(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

    def _render_entries(self, entries: list[dict[str, Any]]) -> None:
        lines: list[str] = []
        for entry in entries:
            line = self._format_entry(entry)
            if self._log_level != "all":
                level = entry.get("level", "info")
                if level != self._log_level:
                    continue
            if self._log_filter and self._log_filter not in line.lower():
                continue
            lines.append(line)

        self._log_view.setPlainText("\n".join(lines))
        self._log_count.setText(f"{len(lines)} entries")

        if self._auto_scroll:
            sb = self._log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _format_entry(self, entry: dict[str, Any]) -> str:
        if isinstance(entry, str):
            return entry
        # Structured log
        ts = entry.get("timestamp", entry.get("ts", ""))
        if isinstance(ts, int | float):
            from datetime import datetime

            ts = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        elif isinstance(ts, str) and len(ts) > 19:
            ts = ts[11:19]  # Extract HH:MM:SS

        level = entry.get("level", "info").upper()
        event = entry.get("event", "")

        # Color-code by level
        extra_parts = []
        for k, v in entry.items():
            if k not in ("timestamp", "ts", "level", "event", "logger"):
                extra_parts.append(f"{k}={v}")
        extra = "  ".join(extra_parts)

        parts = []
        if ts:
            parts.append(f"[{ts}]")
        parts.append(f"{level:7s}")
        if event:
            parts.append(event)
        if extra:
            parts.append(f"  {extra}")

        return " ".join(parts)

    def _refilter(self) -> None:
        """Re-apply current filter to displayed text."""
        self._fetch_logs()

    def _clear_logs(self) -> None:
        self._log_view.clear()
        self._log_count.setText("0 entries")
