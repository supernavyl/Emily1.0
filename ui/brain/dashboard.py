"""
Emily Brain Dashboard — main window.

A PySide6 QMainWindow that displays live internal events from every Emily
subsystem.  Designed to run in-process with ``main.py`` so all data is
delivered via direct Qt signals with zero serialization overhead.

Layout:
    +------------------------------------------------------------------+
    | EMILY BRAIN DASHBOARD                              [pause] [clear]|
    +-------------------+----------------------------------------------+
    | FSM STATE         |  LLM THINKING (raw token stream)             |
    +-------------------+----------------------------------------------+
    | AGENT BUS         | PERCEPTION FEED                              |
    +-------------------+-------------------+--------------------------+
    | MEMORY OPS        | REACT REASONING   | METRICS                  |
    +-------------------+-------------------+--------------------------+
    | FULL EVENT LOG (all events, color-coded, filterable, searchable) |
    +------------------------------------------------------------------+
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.brain.widgets import (
    AgentBusWidget,
    EventLogWidget,
    FSMStateWidget,
    LLMStreamWidget,
    MemoryOpsWidget,
    MetricsWidget,
    PerceptionWidget,
    ReActWidget,
)

if TYPE_CHECKING:
    from core.brain_hub import BrainEventHub

_DARK_STYLESHEET = """
QMainWindow {
    background: #181825;
}
QWidget {
    background: #181825;
    color: #cdd6f4;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 12px;
}
QSplitter::handle {
    background: #313244;
}
QPushButton {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton:hover {
    background: #45475a;
}
QPushButton:pressed {
    background: #585b70;
}
"""


class _BrainSignals(QObject):
    """Qt signals emitted by BrainEventHub for cross-thread delivery.

    Each signal carries a ``dict`` (the event envelope).
    """

    event_emitted = Signal(dict)
    llm_event = Signal(dict)
    react_event = Signal(dict)
    agent_event = Signal(dict)
    perception_event = Signal(dict)
    fsm_event = Signal(dict)
    memory_event = Signal(dict)
    log_event = Signal(dict)
    metric_event = Signal(dict)


class BrainDashboard(QMainWindow):
    """
    Main Brain Dashboard window.

    Connects to BrainEventHub signals and distributes events to panel widgets.

    Args:
        hub: The BrainEventHub to listen to.
        parent: Optional parent widget.
    """

    def __init__(self, hub: BrainEventHub, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hub = hub
        self.setWindowTitle("Emily Brain Dashboard")
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)

        self._signals = _BrainSignals()
        hub.attach_signals(self._signals)

        self.setStyleSheet(_DARK_STYLESHEET)

        self._build_ui()
        self._connect_signals()
        self._backfill()

    def _build_ui(self) -> None:
        """Construct the panel layout."""
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Title bar
        title_row = QHBoxLayout()
        title_label = QLabel("EMILY BRAIN DASHBOARD")
        title_label.setStyleSheet(
            "color: #cba6f7; font-size: 16px; font-weight: bold; letter-spacing: 2px;"
        )
        title_row.addWidget(title_label)
        title_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_all)
        title_row.addWidget(clear_btn)
        root.addLayout(title_row)

        # Main content splitter (vertical)
        main_split = QSplitter(Qt.Orientation.Vertical)

        # Top section: FSM + LLM
        top_split = QSplitter(Qt.Orientation.Horizontal)
        self._fsm_widget = FSMStateWidget()
        self._fsm_widget.setMaximumWidth(220)
        top_split.addWidget(self._fsm_widget)
        self._llm_widget = LLMStreamWidget()
        top_split.addWidget(self._llm_widget)
        top_split.setStretchFactor(0, 0)
        top_split.setStretchFactor(1, 1)
        main_split.addWidget(top_split)

        # Middle section: Agent Bus + Perception
        mid_split = QSplitter(Qt.Orientation.Horizontal)
        self._agent_widget = AgentBusWidget()
        mid_split.addWidget(self._agent_widget)
        self._perception_widget = PerceptionWidget()
        mid_split.addWidget(self._perception_widget)
        mid_split.setStretchFactor(0, 1)
        mid_split.setStretchFactor(1, 1)
        main_split.addWidget(mid_split)

        # Lower-middle: Memory + ReAct + Metrics
        lower_split = QSplitter(Qt.Orientation.Horizontal)
        self._memory_widget = MemoryOpsWidget()
        lower_split.addWidget(self._memory_widget)
        self._react_widget = ReActWidget()
        lower_split.addWidget(self._react_widget)
        self._metrics_widget = MetricsWidget()
        self._metrics_widget.setMaximumWidth(240)
        lower_split.addWidget(self._metrics_widget)
        lower_split.setStretchFactor(0, 1)
        lower_split.setStretchFactor(1, 1)
        lower_split.setStretchFactor(2, 0)
        main_split.addWidget(lower_split)

        # Bottom: full event log
        self._event_log = EventLogWidget()
        main_split.addWidget(self._event_log)

        main_split.setStretchFactor(0, 2)
        main_split.setStretchFactor(1, 2)
        main_split.setStretchFactor(2, 1)
        main_split.setStretchFactor(3, 3)

        root.addWidget(main_split)

    def _connect_signals(self) -> None:
        """Wire hub signals to the appropriate panel widgets."""
        self._signals.event_emitted.connect(self._on_any_event)
        self._signals.fsm_event.connect(self._fsm_widget.on_event)
        self._signals.llm_event.connect(self._llm_widget.on_event)
        self._signals.react_event.connect(self._react_widget.on_event)
        self._signals.agent_event.connect(self._agent_widget.on_event)
        self._signals.perception_event.connect(self._perception_widget.on_event)
        self._signals.memory_event.connect(self._memory_widget.on_event)

    @Slot(dict)
    def _on_any_event(self, event: dict[str, Any]) -> None:
        """Route every event to the full event log."""
        self._event_log.on_event(event)

    def _backfill(self) -> None:
        """Replay ring buffer events for panels that missed startup."""
        for event in self._hub.backfill():
            cat = event.get("cat", "")
            sig = getattr(self._signals, f"{cat}_event", None)
            if sig is not None:
                sig.emit(event)
            self._event_log.on_event(event)

    def _clear_all(self) -> None:
        """Clear all panel contents."""
        for widget in (
            self._llm_widget._text,
            self._react_widget._text,
            self._agent_widget._text,
            self._perception_widget._text,
            self._memory_widget._text,
            self._event_log._text,
        ):
            widget.clear()
