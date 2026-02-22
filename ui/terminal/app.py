"""
Emily terminal user interface — built with Textual.

Provides a rich TUI with:
- Live conversation panel (chat history)
- System status panel (FSM state, active agents, resource usage)
- Memory panel (working memory entries, episodic session info)
- Capability gaps panel
- Log viewer

Run with:
    python -m ui.terminal.app
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Log,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from config import get_settings
from observability.logger import get_logger

log = get_logger(__name__)


class ConversationPanel(RichLog):
    """Scrollable chat log panel."""

    DEFAULT_CSS = """
    ConversationPanel {
        height: 100%;
        border: round $primary;
        padding: 0 1;
    }
    """

    def add_user_turn(self, text: str) -> None:
        """Add a user utterance."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.write(f"[bold cyan][{ts}] You:[/bold cyan] {text}")

    def add_emily_turn(self, text: str) -> None:
        """Add an Emily response."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.write(f"[bold magenta][{ts}] Emily:[/bold magenta] {text}")

    def add_system_event(self, text: str) -> None:
        """Add a system event (tool use, errors, etc.)."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.write(f"[dim][{ts}] ⚙  {text}[/dim]")


class StatusPanel(Static):
    """Live system status display."""

    DEFAULT_CSS = """
    StatusPanel {
        height: auto;
        border: round $secondary;
        padding: 1;
    }
    """

    fsm_state: reactive[str] = reactive("unknown")
    cpu_pct: reactive[float] = reactive(0.0)
    ram_pct: reactive[float] = reactive(0.0)
    vram_mb: reactive[float] = reactive(0.0)

    def render(self) -> str:  # type: ignore[override]
        state_color = {
            "IDLE": "green", "LISTENING": "blue", "PROCESSING": "yellow",
            "RESPONDING": "magenta", "TOOL_USE": "cyan", "REFLECTING": "dim",
            "ERROR": "red", "SHUTDOWN": "red",
        }.get(self.fsm_state, "white")

        return (
            f"[bold]Emily Status[/bold]\n"
            f"State: [{state_color}]{self.fsm_state}[/{state_color}]\n"
            f"CPU: {self.cpu_pct:.1f}%  "
            f"RAM: {self.ram_pct:.1f}%  "
            f"VRAM: {self.vram_mb:.0f}MB"
        )


class EmilyTUI(App[None]):
    """
    Main Emily terminal UI application.
    """

    TITLE = "Emily — Cognitive AI OS"
    SUB_TITLE = "v1.0"
    CSS_PATH = None

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_log", "Clear", show=True),
        Binding("f1", "show_tab('chat')", "Chat", show=True),
        Binding("f2", "show_tab('memory')", "Memory", show=True),
        Binding("f3", "show_tab('logs')", "Logs", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="main-content"):
                with TabbedContent(initial="chat"):
                    with TabPane("Chat [F1]", id="chat"):
                        yield ConversationPanel(id="conversation", markup=True)
                    with TabPane("Memory [F2]", id="memory"):
                        yield DataTable(id="memory-table")
                    with TabPane("Logs [F3]", id="logs"):
                        yield Log(id="system-log", highlight=True)
                yield Input(
                    placeholder="Type a message or command... (Enter to send)",
                    id="chat-input",
                )
            with Vertical(id="sidebar"):
                yield StatusPanel(id="status-panel")
                yield Static("", id="gap-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the UI components after mounting."""
        # Set up the memory table
        table = self.query_one("#memory-table", DataTable)
        table.add_columns("Type", "Content", "Importance", "Time")

        # Show a welcome message
        conv = self.query_one("#conversation", ConversationPanel)
        conv.add_system_event("Emily initialized. Voice pipeline ready.")
        conv.add_emily_turn(
            "Hello! I'm Emily. I'm online and listening. "
            "How can I help you today?"
        )

        # Start background polling
        self.set_interval(2.0, self._poll_status)

    async def _poll_status(self) -> None:
        """Poll system status and update the status panel."""
        try:
            import psutil
            panel = self.query_one("#status-panel", StatusPanel)
            panel.cpu_pct = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            panel.ram_pct = ram.percent
        except ImportError:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle chat input submission."""
        text = event.value.strip()
        if not text:
            return
        self.query_one("#chat-input", Input).clear()
        conv = self.query_one("#conversation", ConversationPanel)
        conv.add_user_turn(text)
        # In production, this would route to the ConversationAgent via the AgentBus
        conv.add_system_event(f"Processing: {text[:60]}...")

    def action_clear_log(self) -> None:
        """Clear the conversation panel."""
        conv = self.query_one("#conversation", ConversationPanel)
        conv.clear()

    def action_show_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        try:
            tabs = self.query_one(TabbedContent)
            tabs.active = tab_id
        except Exception:
            pass

    def add_emily_response(self, text: str) -> None:
        """
        Add an Emily response to the conversation panel.

        Called externally by the ConversationAgent.
        """
        conv = self.query_one("#conversation", ConversationPanel)
        conv.add_emily_turn(text)

    def update_fsm_state(self, state: str) -> None:
        """Update the FSM state display."""
        panel = self.query_one("#status-panel", StatusPanel)
        panel.fsm_state = state


def run_tui() -> None:
    """Entry point for the Textual TUI."""
    app = EmilyTUI()
    app.run()


if __name__ == "__main__":
    run_tui()
