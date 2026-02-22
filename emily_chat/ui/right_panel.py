"""Right panel — live thinking with reasoning phases, metadata, and session stats.

Streams thinking tokens character-by-character during generation,
automatically detects reasoning phases (ANALYZING, CONSIDERING,
COMPARING, CONCLUDING, UNCERTAIN), and shows per-message metadata
with context usage bar and cumulative session statistics with
per-model cost breakdown.
"""

from __future__ import annotations

import re
import time
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Reasoning phase detection
# ---------------------------------------------------------------------------

class ReasoningPhase:
    """Represents a detected reasoning phase with timing and content."""

    ANALYZING = "analyzing"
    CONSIDERING = "considering"
    COMPARING = "comparing"
    CONCLUDING = "concluding"
    UNCERTAIN = "uncertain"

    ALL_PHASES = (ANALYZING, CONSIDERING, COMPARING, CONCLUDING, UNCERTAIN)

    LABELS = {
        ANALYZING: "ANALYZING",
        CONSIDERING: "CONSIDERING",
        COMPARING: "COMPARING",
        CONCLUDING: "CONCLUDING",
        UNCERTAIN: "UNCERTAIN",
    }

    def __init__(self, phase: str, start_time: float) -> None:
        self.phase = phase
        self.start_time = start_time
        self.end_time: float | None = None
        self.content = ""

    @property
    def label(self) -> str:
        """Human-readable phase label."""
        return self.LABELS.get(self.phase, self.phase.upper())

    @property
    def time_range(self) -> str:
        """Formatted time range string."""
        end = self.end_time or time.monotonic()
        return f"[{self.start_time - self._t0:.1f}s\u2013{end - self._t0:.1f}s]"

    def format_time_range(self, t0: float) -> str:
        """Format the time range relative to a base time.

        Args:
            t0: The absolute start time of the generation.

        Returns:
            Formatted string like ``[0.0s\u20132.1s]``.
        """
        self._t0 = t0
        return self.time_range


_PHASE_PATTERNS: dict[str, re.Pattern[str]] = {
    ReasoningPhase.ANALYZING: re.compile(
        r"(?i)\b(break\s+down|understand|analy[sz]|looking\s+at|examin|inspect|read\s+through|parse|identify)"
    ),
    ReasoningPhase.CONSIDERING: re.compile(
        r"(?i)\b(consider|option|approach|alternativel|could\s+use|one\s+way|another\s+way|possible|might\s+try|let\s+me\s+think)"
    ),
    ReasoningPhase.COMPARING: re.compile(
        r"(?i)\b(compar|versus|vs\.?|trade.?off|better|worse|pro\b|con\b|advantage|disadvantage|prefer)"
    ),
    ReasoningPhase.CONCLUDING: re.compile(
        r"(?i)\b(therefore|thus|conclud|final\s+answer|best\s+approach|in\s+conclusion|so\s+the|the\s+answer|I'll\s+go\s+with)"
    ),
    ReasoningPhase.UNCERTAIN: re.compile(
        r"(?i)\b(unsure|not\s+certain|might|unclear|hard\s+to\s+say|I'm\s+not\s+sure|debatable|could\s+go\s+either)"
    ),
}


def detect_phase(text: str) -> str | None:
    """Detect which reasoning phase a text fragment belongs to.

    Args:
        text: A fragment of reasoning text.

    Returns:
        A phase identifier string, or ``None`` if no phase detected.
    """
    for phase, pattern in _PHASE_PATTERNS.items():
        if pattern.search(text):
            return phase
    return None


def compute_session_stats(
    messages: list[dict[str, Any]],
    session_start: float | None = None,
) -> dict[str, Any]:
    """Compute cumulative session statistics from message history.

    Args:
        messages: List of message metadata dicts, each containing
            optional keys: ``model``, ``tokens_in``, ``tokens_out``,
            ``tokens_thinking``, ``cost_usd``, ``latency_ms``.
        session_start: Absolute time when the session started.

    Returns:
        Dict with session-level aggregated stats.
    """
    total_in = 0
    total_out = 0
    total_thinking = 0
    total_cost = 0.0
    total_latency = 0
    msg_count = len(messages)
    cost_by_model: dict[str, float] = {}
    models_used: set[str] = set()

    for msg in messages:
        total_in += msg.get("tokens_in", 0) or 0
        total_out += msg.get("tokens_out", 0) or 0
        total_thinking += msg.get("tokens_thinking", 0) or 0
        total_cost += msg.get("cost_usd", 0.0) or 0.0
        total_latency += msg.get("latency_ms", 0) or 0
        model = msg.get("model", "")
        if model:
            models_used.add(model)
            cost_by_model[model] = cost_by_model.get(model, 0.0) + (
                msg.get("cost_usd", 0.0) or 0.0
            )

    avg_latency = total_latency / msg_count if msg_count > 0 else 0

    breakdown = sorted(
        [
            {
                "model": model,
                "cost": cost,
                "pct": (cost / total_cost * 100) if total_cost > 0 else 0,
            }
            for model, cost in cost_by_model.items()
        ],
        key=lambda x: x["cost"],
        reverse=True,
    )

    return {
        "messages": msg_count,
        "total_tokens": total_in + total_out + total_thinking,
        "total_cost": total_cost,
        "avg_latency": avg_latency,
        "models_used": len(models_used),
        "cost_breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# _PhaseCard — individual reasoning phase widget
# ---------------------------------------------------------------------------


class _PhaseCard(QFrame):
    """Collapsible card displaying a single reasoning phase."""

    def __init__(
        self,
        phase: str,
        time_range: str,
        content: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("phaseCard")
        self.setProperty("phase", phase)

        self._expanded = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        header_row = QHBoxLayout()
        self._header = QLabel(f"\u25b8 {ReasoningPhase.LABELS.get(phase, phase.upper())}")
        self._header.setObjectName("phaseCardHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_row.addWidget(self._header)
        header_row.addStretch()

        self._time_label = QLabel(time_range)
        self._time_label.setObjectName("phaseCardTime")
        header_row.addWidget(self._time_label)
        layout.addLayout(header_row)

        self._body = QLabel(content)
        self._body.setObjectName("phaseCardBody")
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._body)

    def mousePressEvent(self, event: Any) -> None:
        """Toggle expand/collapse on click."""
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        phase_label = ReasoningPhase.LABELS.get(
            self.property("phase"), ""
        )
        arrow = "\u25b8" if not self._expanded else "\u25be"
        self._header.setText(f"{arrow} {phase_label}")
        super().mousePressEvent(event)

    def collapse(self) -> None:
        """Collapse this card."""
        self._expanded = False
        self._body.setVisible(False)
        phase_label = ReasoningPhase.LABELS.get(
            self.property("phase"), ""
        )
        self._header.setText(f"\u25b8 {phase_label}")


# ---------------------------------------------------------------------------
# _ThinkingSection — with reasoning phase detection
# ---------------------------------------------------------------------------


class _ThinkingSection(QWidget):
    """Scrollable thinking area with auto-detected reasoning phases."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("thinkingSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self._header_label = QLabel("\U0001f9e0  REASONING")
        self._header_label.setObjectName("thinkingSectionHeader")
        header.addWidget(self._header_label)
        header.addStretch()

        self._copy_btn = QPushButton("\U0001f4cb")
        self._copy_btn.setObjectName("codeBlockCopyBtn")
        self._copy_btn.setFixedSize(24, 24)
        self._copy_btn.setToolTip("Copy reasoning")
        self._copy_btn.clicked.connect(self._on_copy)
        header.addWidget(self._copy_btn)

        self._clear_btn = QPushButton("\U0001f5d1\ufe0f")
        self._clear_btn.setObjectName("codeBlockCopyBtn")
        self._clear_btn.setFixedSize(24, 24)
        self._clear_btn.setToolTip("Clear")
        self._clear_btn.clicked.connect(self.clear)
        header.addWidget(self._clear_btn)

        self._timer_label = QLabel("")
        self._timer_label.setObjectName("thinkingTimer")
        header.addWidget(self._timer_label)
        layout.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._phases_container = QWidget()
        self._phases_layout = QVBoxLayout(self._phases_container)
        self._phases_layout.setContentsMargins(0, 0, 0, 0)
        self._phases_layout.setSpacing(2)
        self._phases_layout.addStretch()
        self._scroll.setWidget(self._phases_container)
        layout.addWidget(self._scroll)

        self._summary_label = QLabel("")
        self._summary_label.setObjectName("thinkingTimer")
        self._summary_label.setVisible(False)
        layout.addWidget(self._summary_label)

        self._start_time: float | None = None
        self._total_text = ""
        self._current_phase: str | None = None
        self._phase_cards: list[_PhaseCard] = []
        self._pending_text = ""
        self._total_tokens = 0

    def _on_copy(self) -> None:
        """Copy all reasoning text to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._total_text)

    @Slot(str)
    def append_thinking(self, text: str) -> None:
        """Append thinking tokens with phase detection.

        Args:
            text: Raw thinking text fragment.
        """
        if self._start_time is None:
            self._start_time = time.monotonic()
        self._total_text += text
        self._total_tokens += max(1, len(text) // 4)
        self._pending_text += text

        detected = detect_phase(self._pending_text)

        if detected and detected != self._current_phase:
            if self._phase_cards:
                self._phase_cards[-1].collapse()

            now = time.monotonic()
            time_range = f"[{now - self._start_time:.1f}s\u2013...]"
            card = _PhaseCard(detected, time_range, self._pending_text)
            idx = self._phases_layout.count() - 1
            self._phases_layout.insertWidget(idx, card)
            self._phase_cards.append(card)
            self._current_phase = detected
            self._pending_text = ""
        elif self._phase_cards:
            current_card = self._phase_cards[-1]
            current_card._body.setText(
                current_card._body.text() + text
            )

        elapsed = time.monotonic() - self._start_time
        self._timer_label.setText(f"{elapsed:.1f}s")

        sb = self._scroll.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def finish(self) -> None:
        """Transition to summary state after generation completes."""
        if self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
            self._timer_label.setText(f"Thought for {elapsed:.1f}s")
            self._summary_label.setText(
                f"Total reasoning time: {elapsed:.1f}s  \u00b7  "
                f"Thinking tokens used: {self._total_tokens:,}"
            )
            self._summary_label.setVisible(True)
        if not self._total_text:
            self._header_label.setText("\U0001f9e0  No reasoning trace")

    def get_thinking_text(self) -> str:
        """Return all accumulated thinking text.

        Returns:
            The full thinking content.
        """
        return self._total_text

    def clear(self) -> None:
        """Reset for a new message."""
        for card in self._phase_cards:
            self._phases_layout.removeWidget(card)
            card.deleteLater()
        self._phase_cards.clear()
        self._total_text = ""
        self._pending_text = ""
        self._current_phase = None
        self._start_time = None
        self._total_tokens = 0
        self._timer_label.setText("")
        self._summary_label.setVisible(False)
        self._header_label.setText("\U0001f9e0  REASONING")


# ---------------------------------------------------------------------------
# _MetadataSection — with context usage bar
# ---------------------------------------------------------------------------


class _MetadataSection(QWidget):
    """Displays per-message metadata with context usage progress bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metadataSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(2)

        header = QLabel("\U0001f4ca  LAST MESSAGE")
        header.setObjectName("metadataSectionHeader")
        layout.addWidget(header)

        self._rows: dict[str, QLabel] = {}
        for key, label in (
            ("model", "Model"),
            ("provider", "Provider"),
            ("tokens_in", "Tokens in"),
            ("tokens_out", "Tokens out"),
            ("tokens_thinking", "Think tokens"),
            ("cost", "Cost"),
            ("latency", "Latency"),
            ("first_token", "First token"),
        ):
            row = QHBoxLayout()
            key_label = QLabel(label)
            key_label.setObjectName("metadataKey")
            key_label.setFixedWidth(90)
            val_label = QLabel("\u2014")
            val_label.setObjectName("metadataValue")
            row.addWidget(key_label)
            row.addWidget(val_label)
            row.addStretch()
            layout.addLayout(row)
            self._rows[key] = val_label

        ctx_row = QHBoxLayout()
        ctx_key = QLabel("Context used")
        ctx_key.setObjectName("metadataKey")
        ctx_key.setFixedWidth(90)
        ctx_row.addWidget(ctx_key)

        self._context_bar = QProgressBar()
        self._context_bar.setObjectName("contextBar")
        self._context_bar.setFixedHeight(6)
        self._context_bar.setRange(0, 100)
        self._context_bar.setValue(0)
        self._context_bar.setTextVisible(False)
        ctx_row.addWidget(self._context_bar)

        self._context_pct_label = QLabel("\u2014")
        self._context_pct_label.setObjectName("metadataValue")
        self._context_pct_label.setFixedWidth(40)
        ctx_row.addWidget(self._context_pct_label)
        layout.addLayout(ctx_row)

        layout.addStretch()

    @Slot(dict)
    def set_metadata(self, data: dict) -> None:
        """Update all metadata fields from a dict.

        Args:
            data: Dict with metadata values.
        """
        _set = self._rows
        if "model" in data:
            _set["model"].setText(str(data["model"]))
        if "provider" in data:
            _set["provider"].setText(str(data["provider"]))
        if "input_tokens" in data:
            _set["tokens_in"].setText(f"{data['input_tokens']:,}")
        if "output_tokens" in data:
            _set["tokens_out"].setText(f"{data['output_tokens']:,}")
        if "tokens_thinking" in data:
            _set["tokens_thinking"].setText(f"{data['tokens_thinking']:,}")
        if "cost_usd" in data:
            _set["cost"].setText(f"${data['cost_usd']:.4f}")
        if "latency_ms" in data:
            _set["latency"].setText(f"{data['latency_ms']:,}ms")
        if "first_token_ms" in data:
            _set["first_token"].setText(f"{data['first_token_ms']:,}ms")

        if "context_pct" in data:
            pct = int(data["context_pct"])
            self._context_bar.setValue(min(pct, 100))
            self._context_pct_label.setText(f"{pct}%")

    def clear(self) -> None:
        """Reset all values to dashes."""
        for label in self._rows.values():
            label.setText("\u2014")
        self._context_bar.setValue(0)
        self._context_pct_label.setText("\u2014")


# ---------------------------------------------------------------------------
# _SessionStatsSection — cumulative session statistics
# ---------------------------------------------------------------------------


class _SessionStatsSection(QWidget):
    """Cumulative session statistics with expandable cost breakdown."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionStatsSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(2)

        header = QLabel("\U0001f4c8  SESSION")
        header.setObjectName("sessionStatsHeader")
        layout.addWidget(header)

        self._rows: dict[str, QLabel] = {}
        for key, label in (
            ("messages", "Messages"),
            ("total_tokens", "Total tokens"),
            ("total_cost", "Total cost"),
            ("avg_latency", "Avg latency"),
            ("models_used", "Models used"),
        ):
            row = QHBoxLayout()
            key_label = QLabel(label)
            key_label.setObjectName("sessionStatsKey")
            key_label.setFixedWidth(90)
            val_label = QLabel("\u2014")
            val_label.setObjectName("sessionStatsValue")
            row.addWidget(key_label)
            row.addWidget(val_label)
            row.addStretch()
            layout.addLayout(row)
            self._rows[key] = val_label

        self._breakdown_toggle = QPushButton("\U0001f4b0 Cost breakdown \u25bc")
        self._breakdown_toggle.setObjectName("actionBtn")
        self._breakdown_toggle.clicked.connect(self._toggle_breakdown)
        layout.addWidget(self._breakdown_toggle)

        self._breakdown_container = QWidget()
        self._breakdown_layout = QVBoxLayout(self._breakdown_container)
        self._breakdown_layout.setContentsMargins(8, 0, 0, 0)
        self._breakdown_layout.setSpacing(1)
        self._breakdown_container.setVisible(False)
        layout.addWidget(self._breakdown_container)

        layout.addStretch()
        self._breakdown_expanded = False

    def _toggle_breakdown(self) -> None:
        """Toggle cost breakdown visibility."""
        self._breakdown_expanded = not self._breakdown_expanded
        self._breakdown_container.setVisible(self._breakdown_expanded)
        arrow = "\u25b2" if self._breakdown_expanded else "\u25bc"
        self._breakdown_toggle.setText(f"\U0001f4b0 Cost breakdown {arrow}")

    @Slot(dict)
    def set_session_stats(self, data: dict) -> None:
        """Update session statistics.

        Args:
            data: Dict from :func:`compute_session_stats`.
        """
        if "messages" in data:
            self._rows["messages"].setText(str(data["messages"]))
        if "total_tokens" in data:
            self._rows["total_tokens"].setText(f"{data['total_tokens']:,}")
        if "total_cost" in data:
            self._rows["total_cost"].setText(f"${data['total_cost']:.4f}")
        if "avg_latency" in data:
            self._rows["avg_latency"].setText(f"{data['avg_latency']:.0f}ms")
        if "models_used" in data:
            self._rows["models_used"].setText(str(data["models_used"]))

        while self._breakdown_layout.count() > 0:
            item = self._breakdown_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for entry in data.get("cost_breakdown", []):
            lbl = QLabel(
                f"{entry['model']}  ${entry['cost']:.4f}  ({entry['pct']:.0f}%)"
            )
            lbl.setObjectName("costBreakdownItem")
            self._breakdown_layout.addWidget(lbl)

    def clear(self) -> None:
        """Reset all session stats."""
        for label in self._rows.values():
            label.setText("\u2014")
        while self._breakdown_layout.count() > 0:
            item = self._breakdown_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()


# ---------------------------------------------------------------------------
# RightPanel — combined thinking + metadata + session stats
# ---------------------------------------------------------------------------


class RightPanel(QWidget):
    """Combined thinking + metadata + session stats panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rightPanel")
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._thinking = _ThinkingSection()

        divider1 = QFrame()
        divider1.setObjectName("rightPanelDivider")
        divider1.setFrameShape(QFrame.Shape.HLine)
        divider1.setFixedHeight(1)

        self._metadata = _MetadataSection()

        divider2 = QFrame()
        divider2.setObjectName("rightPanelDivider")
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setFixedHeight(1)

        self._session = _SessionStatsSection()

        layout.addWidget(self._thinking, stretch=3)
        layout.addWidget(divider1)
        layout.addWidget(self._metadata, stretch=2)
        layout.addWidget(divider2)
        layout.addWidget(self._session, stretch=1)

    # --- public API used by the controller --------------------------

    @Slot(str)
    def append_thinking(self, text: str) -> None:
        """Forward a thinking chunk to the thinking section.

        Args:
            text: Raw thinking text fragment.
        """
        self._thinking.append_thinking(text)

    @Slot(dict)
    def set_metadata(self, data: dict) -> None:
        """Forward metadata to the metadata section.

        Args:
            data: Per-message metadata dict.
        """
        self._metadata.set_metadata(data)

    @Slot(dict)
    def set_session_stats(self, data: dict) -> None:
        """Forward session stats to the session stats section.

        Args:
            data: Dict from :func:`compute_session_stats`.
        """
        self._session.set_session_stats(data)

    def finish_thinking(self) -> None:
        """Mark thinking as complete (summary mode)."""
        self._thinking.finish()

    def get_thinking_text(self) -> str:
        """Return all accumulated thinking text.

        Returns:
            The full thinking content.
        """
        return self._thinking.get_thinking_text()

    def load_thinking(self, text: str) -> None:
        """Load stored thinking content for a past message.

        Args:
            text: Previously stored thinking text.
        """
        self._thinking.clear()
        if text:
            self._thinking.append_thinking(text)
            self._thinking.finish()

    def clear(self) -> None:
        """Reset all sections for a new generation."""
        self._thinking.clear()
        self._metadata.clear()
