"""
Tab completion engine for Emily terminal commands.
"""

from __future__ import annotations

from .commands import registry


class CompletionEngine:
    """Provides tab completion for commands and paths."""

    def __init__(self) -> None:
        self.commands = list(registry.list_all_names())
        self.applications = ["brain", "voice", "chat", "terminal", "api", "web", "core", "all"]

    def get_completion(self, text: str) -> str:
        """Get completion hint for current input."""
        if not text.startswith("/"):
            return ""

        # Remove the leading slash for completion
        cmd_text = text[1:]

        # Find matching commands
        matches = [cmd for cmd in self.commands if cmd.startswith(cmd_text)]

        if len(matches) == 1:
            return f"/{matches[0]}"
        elif len(matches) > 1:
            # Find common prefix
            prefix = self._common_prefix(list(matches))
            if prefix != cmd_text:
                return f"/{prefix}"
        return ""

    def complete(self, text: str) -> str:
        """Perform tab completion."""
        if not text.startswith("/"):
            return text

        cmd_text = text[1:]
        matches = [cmd for cmd in self.commands if cmd.startswith(cmd_text)]

        if len(matches) == 1:
            return f"/{matches[0]}"
        elif len(matches) > 1:
            # Find common prefix
            prefix = self._common_prefix(matches)
            if prefix != cmd_text:
                return f"/{prefix}"
            else:
                # Show all matches (this would be displayed in a completion widget)
                return text

        return text

    def _common_prefix(self, strings: list[str]) -> str:
        """Find common prefix among strings."""
        if not strings:
            return ""

        shortest = min(strings, key=len)
        for i, char in enumerate(shortest):
            for other in strings:
                if other[i] != char:
                    return shortest[:i]
        return shortest

    def get_command_help(self, command: str) -> str:
        """Get help for a specific command."""
        cmd_func = registry.get_command(command)
        if cmd_func and cmd_func.__doc__:
            return cmd_func.__doc__.strip()
        return "No help available"

    def get_app_completions(self, partial: str) -> list[str]:
        """Get completions for application names."""
        return [app for app in self.applications if app.startswith(partial)]
