"""
Textual TUI for Emily's Agent Replay Debugger.

Provides a terminal-based viewer for recorded session JSONL files with:
- Left pane:  scrollable event timeline, color-coded by category
- Right pane: full JSON payload of the selected event
- Bottom bar:  filter controls and navigation status

Keybindings:
    n / Down   — next event
    p / Up     — previous event
    f          — open filter bar
    t          — trace task_id of selected event
    a          — trace agent (sender/recipient) of selected event
    r          — reset filters, show all events
    Home       — jump to first event
    End        — jump to last event
    q          — quit

Run:
    python -m ui.replay_tui data/replay/<session>.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from observability.replay_engine import ReplayEngine, ReplayEvent

# Category → color mapping for the timeline
_CAT_COLORS = {
    "agent": "dodger_blue1",
    "bus": "cyan",
    "fsm": "green",
    "llm": "yellow",
    "memory": "magenta",
    "perception": "orange1",
    "log": "grey70",
    "react": "red",
    "proactive": "plum2",
}

_AGENT_COLORS = {
    "ConversationAgent": "dodger_blue1",
    "PlannerAgent": "green",
    "MemoryAgent": "magenta",
    "ReflectionAgent": "plum2",
    "ResearchAgent": "orange1",
    "CodeAgent": "yellow",
    "MonitorAgent": "cyan",
    "ToolBuilderAgent": "red",
    "OnboardingAgent": "grey70",
}


def _color_for_event(event: ReplayEvent) -> str:
    """Pick the best color for an event — prefer agent color, fall back to category."""
    sender = event.data.get("sender", "")
    if sender in _AGENT_COLORS:
        return _AGENT_COLORS[sender]
    return _CAT_COLORS.get(event.cat, "white")


def _format_ts(ts: float, base_ts: float) -> str:
    """Format timestamp as +seconds from session start."""
    delta = ts - base_ts
    minutes, seconds = divmod(delta, 60)
    return f"+{int(minutes):02d}:{seconds:05.2f}"


class EventItem(ListItem):
    """A single event row in the timeline list."""

    def __init__(self, event: ReplayEvent, base_ts: float, index: int) -> None:
        super().__init__()
        self.event = event
        self._base_ts = base_ts
        self._index = index

    def compose(self) -> ComposeResult:
        color = _color_for_event(self.event)
        ts_str = _format_ts(self.event.ts, self._base_ts)
        text = f"[{color}]{ts_str}  #{self.event.seq:<5d} {self.event.summary()}[/]"
        yield Label(text, markup=True)


class ReplayTUI(App[None]):
    """Main TUI application for replaying session events."""

    CSS = """
    #timeline {
        width: 1fr;
        min-width: 40;
        border: solid $primary;
    }
    #detail {
        width: 1fr;
        min-width: 40;
        border: solid $accent;
        overflow-y: auto;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    #filter-bar {
        height: 3;
        dock: bottom;
        display: none;
    }
    #filter-input {
        width: 100%;
    }
    #main-panes {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("n", "next_event", "Next", show=True),
        Binding("down", "next_event", "Next", show=False),
        Binding("p", "prev_event", "Prev", show=True),
        Binding("up", "prev_event", "Prev", show=False),
        Binding("f", "toggle_filter", "Filter", show=True),
        Binding("t", "trace_task", "Task trace", show=True),
        Binding("a", "trace_agent", "Agent trace", show=True),
        Binding("r", "reset_filter", "Reset", show=True),
        Binding("home", "jump_start", "Start", show=False),
        Binding("end", "jump_end", "End", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    TITLE = "Emily Replay Debugger"

    filter_description: reactive[str] = reactive("all events")

    def __init__(self, engine: ReplayEngine) -> None:
        super().__init__()
        self._engine = engine
        self._visible_events: list[ReplayEvent] = list(engine)
        self._base_ts = engine.time_range()[0] if len(engine) > 0 else 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-panes"):
            yield ListView(id="timeline")
            yield Static("Select an event to view details.", id="detail")
        with Vertical(id="filter-bar"):
            yield Input(
                placeholder="Filter: cat:agent kind:message agent:ConversationAgent",
                id="filter-input",
            )
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._populate_timeline(self._visible_events)
        self._update_status()

    def _populate_timeline(self, events: list[ReplayEvent]) -> None:
        timeline = self.query_one("#timeline", ListView)
        timeline.clear()
        for i, event in enumerate(events):
            timeline.append(EventItem(event, self._base_ts, i))

    def _update_status(self) -> None:
        bar = self.query_one("#status-bar", Static)
        total = len(self._engine)
        visible = len(self._visible_events)
        cats = ", ".join(self._engine.categories())
        bar.update(
            f" Events: {visible}/{total} | Filter: {self.filter_description} | Categories: {cats}"
        )

    def _show_event_detail(self, event: ReplayEvent) -> None:
        detail = self.query_one("#detail", Static)
        color = _color_for_event(event)

        header = (
            f"[bold {color}]#{event.seq}[/] [{color}]{event.cat}.{event.kind}[/]\n"
            f"Timestamp: {event.ts:.6f}  "
            f"(session {_format_ts(event.ts, self._base_ts)})\n"
        )

        payload = json.dumps(event.data, indent=2, default=str)
        detail.update(header + "\n" + payload, markup=True)  # type: ignore[call-arg]

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(ListView.Highlighted, "#timeline")
    def on_timeline_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is not None and isinstance(event.item, EventItem):
            self._show_event_detail(event.item.event)

    @on(Input.Submitted, "#filter-input")
    def on_filter_submitted(self, event: Input.Submitted) -> None:
        self._apply_text_filter(event.value)
        self.query_one("#filter-bar").styles.display = "none"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_next_event(self) -> None:
        timeline = self.query_one("#timeline", ListView)
        if timeline.index is not None and timeline.index < len(self._visible_events) - 1:
            timeline.index += 1

    def action_prev_event(self) -> None:
        timeline = self.query_one("#timeline", ListView)
        if timeline.index is not None and timeline.index > 0:
            timeline.index -= 1

    def action_jump_start(self) -> None:
        timeline = self.query_one("#timeline", ListView)
        if self._visible_events:
            timeline.index = 0

    def action_jump_end(self) -> None:
        timeline = self.query_one("#timeline", ListView)
        if self._visible_events:
            timeline.index = len(self._visible_events) - 1

    def action_toggle_filter(self) -> None:
        bar = self.query_one("#filter-bar")
        bar.styles.display = "block" if bar.styles.display == "none" else "none"
        if bar.styles.display == "block":
            self.query_one("#filter-input", Input).focus()

    def action_trace_task(self) -> None:
        timeline = self.query_one("#timeline", ListView)
        if timeline.index is None:
            return
        item = timeline.highlighted_child
        if not isinstance(item, EventItem):
            return
        task_id = item.event.data.get("task_id")
        if not task_id:
            self.notify("No task_id on selected event", severity="warning")
            return
        traced = self._engine.task_trace(task_id)
        self._visible_events = traced
        self._populate_timeline(traced)
        self.filter_description = f"task:{task_id[:12]}"
        self._update_status()
        self.notify(f"Tracing task {task_id[:12]}... ({len(traced)} events)")

    def action_trace_agent(self) -> None:
        timeline = self.query_one("#timeline", ListView)
        if timeline.index is None:
            return
        item = timeline.highlighted_child
        if not isinstance(item, EventItem):
            return
        agent = item.event.data.get("sender") or item.event.data.get("recipient")
        if not agent:
            self.notify("No agent on selected event", severity="warning")
            return
        traced = self._engine.agent_trace(agent)
        self._visible_events = traced
        self._populate_timeline(traced)
        self.filter_description = f"agent:{agent}"
        self._update_status()
        self.notify(f"Tracing {agent} ({len(traced)} events)")

    def action_reset_filter(self) -> None:
        self._visible_events = list(self._engine)
        self._populate_timeline(self._visible_events)
        self.filter_description = "all events"
        self._update_status()
        self.notify("Filters reset")

    def _apply_text_filter(self, text: str) -> None:
        """Parse filter string like ``cat:agent kind:message agent:Planner``."""
        filters: dict[str, str] = {}
        for token in text.split():
            if ":" in token:
                key, val = token.split(":", 1)
                filters[key] = val

        result = self._engine.filter(
            cat=filters.get("cat"),
            kind=filters.get("kind"),
            agent=filters.get("agent"),
            msg_type=filters.get("type"),
        )
        self._visible_events = result
        self._populate_timeline(result)
        self.filter_description = text or "all events"
        self._update_status()


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        # List available sessions
        replay_dir = Path("data/replay")
        if replay_dir.exists():
            sessions = sorted(
                replay_dir.glob("*.jsonl*"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            if sessions:
                print("Available sessions:")
                for s in sessions[:20]:
                    print(f"  {s}")
                print("\nUsage: python -m ui.replay_tui <session_file>")
            else:
                print("No session files found in data/replay/")
        else:
            print("No replay directory found. Start Emily and have a conversation first.")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    engine = ReplayEngine.load(path)
    print(f"Loaded {len(engine)} events from {path}")

    app = ReplayTUI(engine)
    app.run()


if __name__ == "__main__":
    main()
