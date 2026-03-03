"""
Emily Terminal Interface — Professional Textual TUI

Real-time streaming chat, GPU monitoring, voice control,
and Emily API integration.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Log,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

try:
    from observability.logger import get_logger

    log = get_logger(__name__)
except ImportError:
    import logging

    log = logging.getLogger(__name__)

import contextlib

from .commands import execute_command
from .widgets.dashboard import DashboardPanel
from .widgets.prompt import PromptWidget
from .widgets.status_bar import StatusBar

API_BASE = "http://localhost:8001"


class ConversationPanel(RichLog):
    """Chat log panel — completed turns only."""

    DEFAULT_CSS = """
    ConversationPanel {
        height: 1fr;
        border: round $primary;
        background: $surface;
        padding: 0 1;
    }
    """

    def add_user_turn(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.write(f"[bold cyan][{ts}] you »[/bold cyan] [cyan]{text}[/cyan]")

    def add_emily_turn(self, text: str, model: str = "") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        model_tag = f" [dim]({model})[/dim]" if model else ""
        self.write(f"[bold blue][{ts}] emily «[/bold blue]{model_tag}")
        # Write content lines individually so they wrap properly
        for line in text.split("\n"):
            self.write(f"[blue]  {line}[/blue]" if line.strip() else "")

    def add_system(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.write(f"[dim][{ts}] • {text}[/dim]")

    def add_command_output(self, text: str) -> None:
        for line in text.split("\n"):
            self.write(f"[green]  {line}[/green]" if line.strip() else "")


class StreamingPanel(Static):
    """Live streaming response display — updated token by token."""

    DEFAULT_CSS = """
    StreamingPanel {
        height: auto;
        min-height: 1;
        border: solid $secondary;
        background: $surface;
        padding: 0 1;
        display: none;
    }

    StreamingPanel.active {
        display: block;
    }
    """

    def show_stream(self, text: str, model: str = "") -> None:
        model_tag = f"[dim] ({model})[/dim]" if model else ""
        cursor = "[bold blue]▋[/bold blue]"
        preview = text[-400:] if len(text) > 400 else text
        self.update(f"[bold blue]emily «[/bold blue]{model_tag}\n[blue]{preview}[/blue]{cursor}")
        self.add_class("active")

    def hide(self) -> None:
        self.update("")
        self.remove_class("active")


class EmilyTUIImproved(App[None]):
    """Emily professional terminal interface with live streaming chat."""

    TITLE = "Emily — Cognitive AI OS"
    SUB_TITLE = "v1.0 · local"
    CSS_PATH = None

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_log", "Clear", show=True),
        Binding("ctrl+n", "new_conversation", "New conv", show=True),
        Binding("f1", "show_tab('chat')", "Chat", show=True),
        Binding("f2", "show_tab('dashboard')", "Dashboard", show=True),
        Binding("f3", "show_tab('memory')", "Memory", show=True),
        Binding("f4", "show_tab('logs')", "Logs", show=True),
        Binding("f5", "refresh_all", "Refresh", show=True),
        Binding("f6", "toggle_voice", "Voice", show=True),
        Binding("tab", "focus_next", "Next", show=False),
        Binding("shift+tab", "focus_previous", "Previous", show=False),
    ]

    CSS = """
    Screen {
        background: #0a0a0a;
        color: #e0e0e0;
    }

    Header {
        background: #1a1a2e;
        color: #00d4ff;
        text-style: bold;
        border-bottom: solid #00d4ff;
    }

    Footer {
        background: #1a1a2e;
        color: #00d4ff;
        border-top: solid #00d4ff;
    }

    Footer > .footer--key {
        background: #16213e;
        color: #00d4ff;
        border: solid #00a8cc;
    }

    Footer > .footer--description {
        color: #00a8cc;
    }

    PromptWidget {
        background: #16213e;
        border: solid #00d4ff;
        margin: 0;
    }

    #prompt-label {
        color: #00d4ff;
        text-style: bold;
        background: #0f3460;
    }

    #prompt-input {
        background: #16213e;
        color: #e0e0e0;
        border: none;
    }

    #prompt-input:focus {
        background: #0f3460;
        border: solid #00d4ff;
    }

    ConversationPanel {
        background: #0a0a0a;
        border: solid #00d4ff;
        color: #e0e0e0;
    }

    StreamingPanel {
        background: #050d1a;
        border: solid #0050a0;
        color: #b0c8ff;
        margin: 0;
    }

    DashboardPanel {
        background: #16213e;
        border: solid #00d4ff;
        color: #e0e0e0;
    }

    StatusBar {
        background: #1a1a2e;
        border: solid #00d4ff;
        color: #e0e0e0;
    }

    DataTable {
        background: #0a0a0a;
        border: solid #00d4ff;
        color: #e0e0e0;
    }

    DataTable > .datatable--header {
        background: #16213e;
        color: #00d4ff;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: #0f3460;
        color: #00d4ff;
    }

    Log {
        background: #0a0a0a;
        border: solid #00d4ff;
        color: #e0e0e0;
    }

    TabbedContent {
        background: #0a0a0a;
    }

    Tabs {
        background: #16213e;
        border: solid #00d4ff;
    }

    Tab {
        background: #1a1a2e;
        color: #00a8cc;
        text-style: bold;
    }

    Tab.-active {
        background: #0f3460;
        color: #00d4ff;
        text-style: bold;
    }

    TabPane {
        background: #0a0a0a;
        border: solid #00d4ff;
    }

    #sidebar {
        background: #16213e;
        width: 36;
        border: solid #00d4ff;
        padding: 1;
    }

    $primary: #00d4ff;
    $secondary: #00a8cc;
    $accent: #ff00ff;
    $success: #00ff88;
    $warning: #ffaa00;
    $error: #ff4444;
    $surface: #0a0a0a;
    $panel: #16213e;
    $text: #e0e0e0;
    $text-muted: #888888;
    """

    def __init__(self) -> None:
        super().__init__()
        self._active_conv_id: str | None = None
        self._is_streaming: bool = False
        self._stream_model: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-content"):
            with Vertical(id="content-area"):
                with TabbedContent(initial="chat"):
                    with TabPane("💬 Chat [F1]", id="chat"), Vertical():
                        yield ConversationPanel(id="conversation", markup=True)
                        yield StreamingPanel(id="stream-panel", markup=True)
                    with TabPane("📊 Dashboard [F2]", id="dashboard"):
                        yield DashboardPanel()
                    with TabPane("🧠 Memory [F3]", id="memory"):
                        yield DataTable(id="memory-table")
                    with TabPane("📋 Logs [F4]", id="logs"):
                        yield Log(id="system-log", highlight=True)

                yield PromptWidget(id="prompt")

            with Vertical(id="sidebar"):
                yield StatusBar()

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#memory-table", DataTable)
        table.add_columns("Type", "Content", "Importance", "Time")

        conv = self.query_one("#conversation", ConversationPanel)
        conv.add_system("Emily terminal ready · type a message to chat")
        conv.add_system("Commands: /help  /model  /gpu  /health  /new  /voice")
        conv.add_system("Shortcuts: F1-F4 tabs · F6 voice · Ctrl+N new conversation")

        self.query_one("#prompt", PromptWidget).query_one("#prompt-input").focus()

    # ── Prompt handler ──────────────────────────────────────────────────────

    async def on_prompt_submitted(self, event) -> None:
        text = getattr(event, "value", str(event)).strip()
        if not text:
            return

        prompt = self.query_one("#prompt", PromptWidget)
        conv = self.query_one("#conversation", ConversationPanel)

        prompt.add_to_history(text)
        prompt.clear()

        if text.startswith("/"):
            conv.add_user_turn(text)
            result = await execute_command(text)
            if result.success:
                if result.message == "CLEAR_SCREEN":
                    conv.clear()
                    conv.add_system("Terminal cleared")
                elif result.message == "NEW_CONVERSATION":
                    self._active_conv_id = None
                    conv.clear()
                    conv.add_system("New conversation started")
                else:
                    conv.add_command_output(result.message)
            else:
                conv.add_system(f"✗ {result.message}")
        else:
            if self._is_streaming:
                conv.add_system("Busy — wait for current response to finish")
                return
            conv.add_user_turn(text)
            await self._stream_response(text)

    # ── Streaming chat ──────────────────────────────────────────────────────

    async def _stream_response(self, text: str) -> None:
        """Stream a chat response from the Emily API via SSE."""
        conv = self.query_one("#conversation", ConversationPanel)
        stream_panel = self.query_one("#stream-panel", StreamingPanel)

        self._is_streaming = True
        accumulated = ""
        model_display = ""

        try:
            import httpx

            body: dict = {
                "message": text,
                "model_id": "auto",
                "skill_id": "normal",
            }
            if self._active_conv_id:
                body["conversation_id"] = self._active_conv_id

            stream_panel.show_stream("", "connecting...")

            async with (
                httpx.AsyncClient(timeout=120.0) as client,
                client.stream(
                    "POST",
                    f"{API_BASE}/api/v1/chat/stream",
                    json=body,
                    headers={"Accept": "text/event-stream"},
                ) as resp,
            ):
                if not resp.is_success:
                    conv.add_system(f"API error {resp.status_code} — is the server running?")
                    return

                event_type = ""
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        raw = line[6:]
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue

                        if event_type == "meta":
                            model_display = data.get("display", "")
                            conv_id = data.get("conversation_id")
                            if conv_id:
                                self._active_conv_id = conv_id
                            stream_panel.show_stream("", model_display)

                        elif event_type == "text":
                            chunk = data.get("text", "")
                            accumulated += chunk
                            stream_panel.show_stream(accumulated, model_display)

                        elif event_type == "done":
                            break

                        elif event_type == "error":
                            conv.add_system(f"Stream error: {data.get('message', '?')}")
                            break

                        event_type = ""

        except ImportError:
            conv.add_system("httpx not available — run: uv add httpx")
        except Exception as exc:
            err = str(exc)
            if "connect" in err.lower() or "connection" in err.lower():
                conv.add_system(f"Cannot reach Emily API at {API_BASE} — start it first")
            else:
                conv.add_system(f"Stream error: {err[:120]}")
        finally:
            stream_panel.hide()
            if accumulated:
                conv.add_emily_turn(accumulated, model_display)
            self._is_streaming = False

    # ── Actions ─────────────────────────────────────────────────────────────

    def action_clear_log(self) -> None:
        conv = self.query_one("#conversation", ConversationPanel)
        conv.clear()
        conv.add_system("Terminal cleared")

    def action_new_conversation(self) -> None:
        self._active_conv_id = None
        conv = self.query_one("#conversation", ConversationPanel)
        conv.clear()
        conv.add_system("New conversation — no history context")

    def action_show_tab(self, tab_id: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one(TabbedContent).active = tab_id

    def action_refresh_all(self) -> None:
        for cls in (DashboardPanel, StatusBar):
            with contextlib.suppress(Exception):
                self.query_one(cls).action_refresh()

    async def action_toggle_voice(self) -> None:
        """Toggle voice mode via the API."""
        conv = self.query_one("#conversation", ConversationPanel)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                status = (await client.get(f"{API_BASE}/api/audio/voice/status")).json()
                if status.get("active"):
                    await client.post(f"{API_BASE}/api/audio/voice/stop")
                    conv.add_system("Voice mode stopped")
                else:
                    await client.post(f"{API_BASE}/api/audio/voice/start")
                    conv.add_system("Voice mode started — say something!")
        except Exception as e:
            conv.add_system(f"Voice toggle failed: {e}")


def run_improved_tui() -> None:
    """Entry point for the improved Textual TUI."""
    EmilyTUIImproved().run()


if __name__ == "__main__":
    run_improved_tui()
