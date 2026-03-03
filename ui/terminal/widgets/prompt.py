"""
Advanced prompt widget with tab completion and history.
"""

from __future__ import annotations

from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.events import Event
from textual.reactive import reactive
from textual.widgets import Input, Static

from ..completions import CompletionEngine


class Submitted(Event):
    """Event emitted when prompt is submitted."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__()


class PromptWidget(Horizontal):
    """Advanced input prompt with completion and history."""

    DEFAULT_CSS = """
    PromptWidget {
        height: auto;
        padding: 0 1;
        background: $primary;
    }

    #prompt-label {
        width: 8;
        content-align: left middle;
        color: $accent;
        text-style: bold;
    }

    #prompt-input {
        width: 1fr;
        background: $primary;
        border: none;
        color: $text;
    }

    #prompt-input:focus {
        border: none;
        background: $primary;
    }

    #completion-hint {
        width: auto;
        color: $text-muted;
        content-align: left middle;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("tab", "complete", "Complete", show=False),
        Binding("up", "history_up", "Previous", show=False),
        Binding("down", "history_down", "Next", show=False),
        Binding("escape", "clear_input", "Clear", show=False),
    ]

    current_text: reactive[str] = reactive("")
    completion_hint: reactive[str] = reactive("")
    history_index: reactive[int] = reactive(-1)
    history: list[str] = []

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.completion_engine = CompletionEngine()

    def compose(self):
        yield Static("emily >", id="prompt-label")
        yield Input(placeholder="Enter command or message...", id="prompt-input")
        yield Static("", id="completion-hint")

    def on_mount(self) -> None:
        """Initialize the prompt."""
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes and update completion hint."""
        self.current_text = event.value
        self.history_index = -1  # Reset history when typing

        # Update completion hint
        if event.value:
            completion = self.completion_engine.get_completion(event.value)
            self.completion_hint = completion
        else:
            self.completion_hint = ""

    def action_complete(self) -> None:
        """Handle tab completion."""
        input_widget = self.query_one("#prompt-input", Input)
        current = input_widget.value

        if current:
            completed = self.completion_engine.complete(current)
            if completed != current:
                input_widget.value = completed
                input_widget.cursor_position = len(completed)

    def action_history_up(self) -> None:
        """Navigate up through history."""
        if not self.history:
            return

        input_widget = self.query_one("#prompt-input", Input)

        # Save current text if we're at the bottom
        if self.history_index == -1:
            self.current_text = input_widget.value

        # Move up in history
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            input_widget.value = self.history[-(self.history_index + 1)]
            input_widget.cursor_position = len(input_widget.value)

    def action_history_down(self) -> None:
        """Navigate down through history."""
        if not self.history:
            return

        input_widget = self.query_one("#prompt-input", Input)

        if self.history_index > 0:
            self.history_index -= 1
            input_widget.value = self.history[-(self.history_index + 1)]
            input_widget.cursor_position = len(input_widget.value)
        elif self.history_index == 0:
            self.history_index = -1
            input_widget.value = self.current_text
            input_widget.cursor_position = len(input_widget.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission and emit custom event."""
        self.post_message(Submitted(event.value))

    def action_clear_input(self) -> None:
        """Clear the input field."""
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.value = ""
        input_widget.focus()

    def add_to_history(self, command: str) -> None:
        """Add a command to history."""
        if command.strip() and (not self.history or self.history[-1] != command):
            self.history.append(command)
            # Keep history manageable
            if len(self.history) > 1000:
                self.history = self.history[-500:]

    def get_value(self) -> str:
        """Get the current input value."""
        return self.query_one("#prompt-input", Input).value

    def clear(self) -> None:
        """Clear the input field."""
        self.action_clear_input()
        self.query_one("#prompt-input", Input).focus()
