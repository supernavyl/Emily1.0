"""
Brain Dashboard panel widgets.

Each widget connects to a specific BrainEventHub signal category and renders
live data from Emily's internals.  All widgets are designed for a dark theme.
"""

from __future__ import annotations

import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_MONO = QFont("JetBrains Mono", 10)
_MONO.setStyleHint(QFont.StyleHint.Monospace)

_CAT_COLORS: dict[str, str] = {
    "llm": "#60a5fa",
    "react": "#c084fc",
    "agent": "#34d399",
    "perception": "#fbbf24",
    "fsm": "#f87171",
    "memory": "#2dd4bf",
    "log": "#94a3b8",
    "metric": "#fb923c",
}

_MAX_LOG_LINES = 2000


def _ts_str(ts: float) -> str:
    """Format a timestamp as HH:MM:SS.mmm."""
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def _section_frame(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Create a dark-bordered frame with a header label."""
    frame = QFrame()
    frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
    frame.setStyleSheet(
        "QFrame { background: #1e1e2e; border: 1px solid #313244; border-radius: 6px; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(4)
    header = QLabel(title)
    header.setStyleSheet("color: #cdd6f4; font-weight: bold; font-size: 11px; border: none;")
    layout.addWidget(header)
    return frame, layout


class FSMStateWidget(QWidget):
    """Shows the current FSM state with colored indicator and transition history."""

    _STATE_COLORS: dict[str, str] = {
        "IDLE": "#94a3b8",
        "LISTENING": "#60a5fa",
        "PROCESSING": "#c084fc",
        "RESPONDING": "#34d399",
        "TOOL_USE": "#fbbf24",
        "REFLECTING": "#2dd4bf",
        "ERROR": "#f87171",
        "SHUTDOWN": "#6b7280",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("FSM STATE")

        self._current = QLabel("IDLE")
        self._current.setStyleSheet(
            "color: #94a3b8; font-size: 22px; font-weight: bold; border: none;"
        )
        self._layout.addWidget(self._current)

        self._history_label = QLabel("")
        self._history_label.setWordWrap(True)
        self._history_label.setStyleSheet("color: #6c7086; font-size: 10px; border: none;")
        self._layout.addWidget(self._history_label)
        self._layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self._transitions: list[str] = []

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle an fsm event."""
        if event.get("kind") != "state_change":
            return
        data = event.get("data", {})
        new_state = data.get("new", "IDLE")
        color = self._STATE_COLORS.get(new_state, "#cdd6f4")
        self._current.setText(new_state)
        self._current.setStyleSheet(
            f"color: {color}; font-size: 22px; font-weight: bold; border: none;"
        )
        self._transitions.append(new_state)
        if len(self._transitions) > 20:
            self._transitions = self._transitions[-20:]
        self._history_label.setText(" → ".join(self._transitions[-8:]))


class LLMStreamWidget(QWidget):
    """Displays raw LLM token stream with model info and blinking cursor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("LLM THINKING")

        self._model_label = QLabel("Waiting...")
        self._model_label.setStyleSheet("color: #6c7086; font-size: 10px; border: none;")
        self._layout.addWidget(self._model_label)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            "QTextEdit { background: #11111b; color: #cdd6f4; border: 1px solid #313244; "
            "border-radius: 4px; padding: 6px; }"
        )
        self._text.setMinimumHeight(80)
        self._layout.addWidget(self._text)

        self._token_count = QLabel("")
        self._token_count.setStyleSheet("color: #6c7086; font-size: 10px; border: none;")
        self._layout.addWidget(self._token_count)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self._current_model = ""
        self._n_tokens = 0

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle llm events."""
        kind = event.get("kind", "")
        data = event.get("data", {})

        if kind == "token_start":
            self._text.clear()
            self._current_model = data.get("model", "")
            self._n_tokens = 0
            tier = data.get("tier", "")
            self._model_label.setText(f"Model: {self._current_model}  |  Tier: {tier}")
            self._token_count.setText("")
        elif kind == "token":
            self._text.moveCursor(QTextCursor.MoveOperation.End)
            self._text.insertPlainText(data.get("text", ""))
            self._text.moveCursor(QTextCursor.MoveOperation.End)
            self._n_tokens = data.get("n", self._n_tokens + 1)
        elif kind == "token_end":
            total = data.get("total_tokens", self._n_tokens)
            self._token_count.setText(f"Tokens: {total}")
        elif kind == "request":
            self._current_model = data.get("model", "")
            self._model_label.setText(f"Model: {self._current_model} (non-streaming)")
            self._text.clear()
            self._text.setPlainText("Processing...")
        elif kind == "response":
            latency = data.get("latency_ms", 0)
            length = data.get("content_len", 0)
            self._token_count.setText(f"Response: {length} chars  |  {latency}ms")
            self._text.setPlainText(f"[Non-streaming response: {length} characters in {latency}ms]")


class ReActWidget(QWidget):
    """Displays ReAct reasoning steps as they happen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("REACT REASONING")

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            "QTextEdit { background: #11111b; color: #cba6f7; border: 1px solid #313244; "
            "border-radius: 4px; padding: 6px; }"
        )
        self._text.setMaximumHeight(120)
        self._layout.addWidget(self._text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle react events."""
        kind = event.get("kind", "")
        data = event.get("data", {})
        ts = _ts_str(event.get("ts", 0))

        if kind == "iteration_start":
            self._text.append(f"[{ts}] ── Iteration {data.get('iteration', '?')} ──")
        elif kind == "thought":
            self._text.append(f"[{ts}] THOUGHT: {data.get('thought', '')[:200]}")
        elif kind == "action":
            self._text.append(
                f"[{ts}] ACTION: {data.get('tool', '')}({data.get('input', '')[:100]})"
            )
        elif kind == "observation":
            self._text.append(f"[{ts}] OBSERVE: {data.get('observation', '')[:200]}")
        elif kind == "final_answer":
            self._text.append(f"[{ts}] FINAL ({data.get('iterations', '?')} iters)")

        self._text.moveCursor(QTextCursor.MoveOperation.End)


class AgentBusWidget(QWidget):
    """Scrolling feed of inter-agent messages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("AGENT BUS")

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            "QTextEdit { background: #11111b; color: #a6e3a1; border: 1px solid #313244; "
            "border-radius: 4px; padding: 6px; }"
        )
        self._layout.addWidget(self._text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle agent events."""
        data = event.get("data", {})
        ts = _ts_str(event.get("ts", 0))
        sender = data.get("sender", "?")
        recipient = data.get("recipient", "?")
        msg_type = data.get("type", "?")
        self._text.append(f"[{ts}] {sender} → {recipient}: {msg_type}")

        if self._text.document().blockCount() > 200:
            cursor = self._text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 50)
            cursor.removeSelectedText()

        self._text.moveCursor(QTextCursor.MoveOperation.End)


class PerceptionWidget(QWidget):
    """Feed of perception events: STT, VAD, presence, vision."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("PERCEPTION FEED")

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            "QTextEdit { background: #11111b; color: #f9e2af; border: 1px solid #313244; "
            "border-radius: 4px; padding: 6px; }"
        )
        self._layout.addWidget(self._text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle perception events."""
        kind = event.get("kind", "")
        data = event.get("data", {})
        ts = _ts_str(event.get("ts", 0))

        text_preview = data.get("text", data.get("transcript", ""))
        if text_preview:
            self._text.append(f'[{ts}] [{kind}] "{text_preview[:120]}"')
        else:
            summary = str(data)[:150] if data else ""
            self._text.append(f"[{ts}] [{kind}] {summary}")

        if self._text.document().blockCount() > 200:
            cursor = self._text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 50)
            cursor.removeSelectedText()

        self._text.moveCursor(QTextCursor.MoveOperation.End)


class MemoryOpsWidget(QWidget):
    """Recent memory read/write operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("MEMORY OPS")

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            "QTextEdit { background: #11111b; color: #94e2d5; border: 1px solid #313244; "
            "border-radius: 4px; padding: 6px; }"
        )
        self._text.setMaximumHeight(120)
        self._layout.addWidget(self._text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle memory events."""
        kind = event.get("kind", "")
        data = event.get("data", {})
        ts = _ts_str(event.get("ts", 0))

        if kind == "user_turn":
            self._text.append(f"[{ts}] [write] user turn ({data.get('text_len', 0)} chars)")
        elif kind == "assistant_turn":
            self._text.append(f"[{ts}] [write] assistant turn ({data.get('text_len', 0)} chars)")
        elif kind == "context_retrieved":
            self._text.append(
                f"[{ts}] [read] semantic: {data.get('results', 0)} results "
                f'for "{data.get("query", "")[:60]}"'
            )
        else:
            self._text.append(f"[{ts}] [{kind}] {str(data)[:120]}")

        self._text.moveCursor(QTextCursor.MoveOperation.End)


class MetricsWidget(QWidget):
    """Live metric gauges for latency, VRAM, agent count."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("METRICS")

        self._labels: dict[str, QLabel] = {}
        for name in ["STT", "LLM-1st", "TTS", "VRAM", "Agents", "Queue"]:
            row = QHBoxLayout()
            name_lbl = QLabel(f"{name}:")
            name_lbl.setStyleSheet("color: #6c7086; font-size: 11px; border: none;")
            name_lbl.setFixedWidth(60)
            val_lbl = QLabel("--")
            val_lbl.setStyleSheet(
                "color: #fab387; font-size: 11px; font-weight: bold; border: none;"
            )
            self._labels[name] = val_lbl
            row.addWidget(name_lbl)
            row.addWidget(val_lbl)
            row.addStretch()
            self._layout.addLayout(row)
        self._layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

    def update_metrics(self, data: dict[str, Any]) -> None:
        """Update displayed metric values."""
        for key, label in self._labels.items():
            value = data.get(key)
            if value is not None:
                label.setText(str(value))


class EventLogWidget(QWidget):
    """
    Full scrolling event log with category filters, search, and pause.

    Shows ALL events from every category, color-coded and filterable.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame, self._layout = _section_frame("FULL EVENT LOG")
        self._paused = False
        self._pending: list[dict[str, Any]] = []

        controls = QHBoxLayout()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter...")
        self._search.setStyleSheet(
            "QLineEdit { background: #11111b; color: #cdd6f4; border: 1px solid #313244; "
            "border-radius: 3px; padding: 2px 6px; font-size: 11px; }"
        )
        self._search.setFixedWidth(160)
        controls.addWidget(self._search)

        self._filters: dict[str, QCheckBox] = {}
        for cat, color in _CAT_COLORS.items():
            cb = QCheckBox(cat)
            cb.setChecked(True)
            cb.setStyleSheet(f"QCheckBox {{ color: {color}; font-size: 10px; border: none; }}")
            self._filters[cat] = cb
            controls.addWidget(cb)

        self._pause_btn = QLabel("[▶ Live]")
        self._pause_btn.setStyleSheet(
            "color: #a6e3a1; font-size: 11px; font-weight: bold; border: none; cursor: pointer;"
        )
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.mousePressEvent = self._toggle_pause  # type: ignore[assignment]
        controls.addStretch()
        controls.addWidget(self._pause_btn)

        self._layout.addLayout(controls)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            "QTextEdit { background: #11111b; color: #cdd6f4; border: 1px solid #313244; "
            "border-radius: 4px; padding: 6px; }"
        )
        self._layout.addWidget(self._text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

    def _toggle_pause(self, _event: Any = None) -> None:
        """Toggle pause/resume of the event log."""
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.setText("[⏸ Paused]")
            self._pause_btn.setStyleSheet(
                "color: #f87171; font-size: 11px; font-weight: bold; border: none;"
            )
        else:
            self._pause_btn.setText("[▶ Live]")
            self._pause_btn.setStyleSheet(
                "color: #a6e3a1; font-size: 11px; font-weight: bold; border: none;"
            )
            for ev in self._pending:
                self._append_event(ev)
            self._pending.clear()

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle any brain event for the full log."""
        if self._paused:
            if len(self._pending) < 500:
                self._pending.append(event)
            return
        self._append_event(event)

    def _append_event(self, event: dict[str, Any]) -> None:
        """Append a single event line to the log."""
        cat = event.get("cat", "log")
        kind = event.get("kind", "")
        data = event.get("data", {})
        ts = _ts_str(event.get("ts", 0))

        cb = self._filters.get(cat)
        if cb is not None and not cb.isChecked():
            return

        search_text = self._search.text().strip().lower()
        line = f"[{ts}] [{cat}] {kind}: {self._summarize(data)}"
        if search_text and search_text not in line.lower():
            return

        color = _CAT_COLORS.get(cat, "#cdd6f4")
        self._text.append(f'<span style="color:{color}">{line}</span>')

        if self._text.document().blockCount() > _MAX_LOG_LINES:
            cursor = self._text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 500
            )
            cursor.removeSelectedText()

        self._text.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _summarize(data: dict[str, Any]) -> str:
        """Create a short text summary of event data."""
        if not data:
            return ""
        if "text" in data:
            return f'"{data["text"][:80]}"'
        if "event" in data:
            parts = [data["event"]]
            for key in ("error", "model", "sender", "recipient"):
                if key in data:
                    parts.append(f"{key}={data[key]}")
            return " ".join(parts[:4])
        parts = []
        for k, v in list(data.items())[:4]:
            parts.append(f"{k}={str(v)[:40]}")
        return " ".join(parts)
