"""Rich-powered terminal UI for the voice conversation loop."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class TerminalUI:
    """Provides a polished terminal interface for voice conversations.

    Uses ``rich`` for colour, panels, spinners, and live-updating markdown
    rendering of streaming LLM output.
    """

    def __init__(self) -> None:
        self._console = Console()

    # ── Status indicators ─────────────────────────────────────────

    def show_listening(self) -> None:
        """Display an animated 'Listening...' status line."""
        self._console.print(
            Text("  Listening ...", style="bold cyan"),
            highlight=False,
        )

    def show_processing(self) -> None:
        """Display a 'Thinking...' spinner-style status line."""
        self._console.print(
            Text("  Thinking ...", style="bold yellow"),
            highlight=False,
        )

    def show_status(self, msg: str) -> None:
        """Show a general dim status message."""
        self._console.print(Text(f"  {msg}", style="dim"), highlight=False)

    # ── Conversation display ──────────────────────────────────────

    def show_transcript(self, text: str) -> None:
        """Display the user's transcribed speech."""
        panel = Panel(
            Text(text, style="cyan"),
            title="[bold cyan]You[/bold cyan]",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        )
        self._console.print(panel)

    def show_response(self, text: str) -> None:
        """Display the assistant's complete response as rendered markdown."""
        panel = Panel(
            Markdown(text),
            title="[bold green]Assistant[/bold green]",
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )
        self._console.print(panel)

    async def show_response_stream(self, token_stream: AsyncIterator[str]) -> str:
        """Live-render the assistant's response as tokens arrive.

        Returns the complete response text once the stream is exhausted.
        """
        collected: list[str] = []

        with Live(
            Panel(
                Text("", style="green"),
                title="[bold green]Assistant[/bold green]",
                title_align="left",
                border_style="green",
                padding=(0, 1),
            ),
            console=self._console,
            refresh_per_second=12,
            transient=True,
        ) as live:
            async for token in token_stream:
                collected.append(token)
                current_text = "".join(collected)
                live.update(
                    Panel(
                        Markdown(current_text),
                        title="[bold green]Assistant[/bold green]",
                        title_align="left",
                        border_style="green",
                        padding=(0, 1),
                    )
                )

        full_text = "".join(collected)
        # Print the final, non-transient version
        self.show_response(full_text)
        return full_text

    # ── Errors ────────────────────────────────────────────────────

    def show_error(self, msg: str) -> None:
        """Display an error message."""
        panel = Panel(
            Text(msg, style="bold red"),
            title="[bold red]Error[/bold red]",
            title_align="left",
            border_style="red",
            padding=(0, 1),
        )
        self._console.print(panel)

    # ── Banner ────────────────────────────────────────────────────

    def show_welcome(self) -> None:
        """Display a startup banner."""
        self._console.print()
        self._console.print(
            Panel(
                Text.from_markup(
                    "[bold]Voice Engine[/bold] v0.1.0\n"
                    "[dim]Speak naturally. Press Ctrl+C to exit.[/dim]"
                ),
                border_style="bright_blue",
                padding=(1, 2),
            )
        )
        self._console.print()

    def show_goodbye(self) -> None:
        """Display a shutdown message."""
        self._console.print()
        self._console.print(
            Text("  Goodbye!", style="dim italic"),
            highlight=False,
        )
        self._console.print()
