"""
Emily Terminal Help System - Comprehensive help content and formatting.

Provides structured help content for all terminal commands and applications
with search functionality and categorized organization.
"""

from __future__ import annotations


class HelpEntry:
    """A help entry for a command or topic."""

    def __init__(
        self,
        name: str,
        description: str,
        usage: str,
        examples: list[str] | None = None,
        aliases: list[str] | None = None,
        category: str = "general",
    ):
        self.name = name
        self.description = description
        self.usage = usage
        self.examples = examples or []
        self.aliases = aliases or []
        self.category = category

    def format_help(self) -> str:
        """Format the help entry for display."""
        lines = [f"/{self.name} - {self.description}"]
        lines.append(f"Usage: {self.usage}")

        if self.aliases:
            lines.append(f"Aliases: /{', /'.join(self.aliases)}")

        if self.examples:
            lines.append("Examples:")
            for example in self.examples:
                lines.append(f"  {example}")

        return "\n".join(lines)


class HelpSystem:
    """Comprehensive help system for Emily terminal."""

    def __init__(self):
        self._entries: dict[str, HelpEntry] = {}
        self._categories: dict[str, list[str]] = {}
        self._setup_help_content()

    def _setup_help_content(self) -> None:
        """Set up all help content."""
        # Command help entries
        self._add_command_help()

        # Application help entries
        self._add_application_help()

        # Category organization
        self._organize_categories()

    def _add_command_help(self) -> None:
        """Add help entries for all commands."""
        commands = [
            HelpEntry(
                name="help",
                description="Show help information",
                usage="/help [topic|command]",
                examples=["/help", "/help apps", "/help start", "/help commands"],
                aliases=["h", "?"],
                category="help",
            ),
            HelpEntry(
                name="start",
                description="Start an Emily application",
                usage="/start <app>",
                examples=["/start brain", "/start api", "/start all"],
                aliases=["run", "launch"],
                category="applications",
            ),
            HelpEntry(
                name="stop",
                description="Stop an Emily application",
                usage="/stop <app>",
                examples=["/stop brain", "/stop api"],
                aliases=["kill", "terminate"],
                category="applications",
            ),
            HelpEntry(
                name="restart",
                description="Restart an Emily application",
                usage="/restart <app>",
                examples=["/restart brain", "/restart api"],
                aliases=["reload", "reboot"],
                category="applications",
            ),
            HelpEntry(
                name="status",
                description="Show status of running applications",
                usage="/status",
                examples=["/status"],
                aliases=["ps", "list"],
                category="system",
            ),
            HelpEntry(
                name="logs",
                description="Show logs for an application",
                usage="/logs <app> [lines]",
                examples=["/logs api", "/logs brain 100"],
                aliases=["log"],
                category="system",
            ),
            HelpEntry(
                name="health",
                description="Check system health",
                usage="/health",
                examples=["/health"],
                aliases=["check"],
                category="system",
            ),
            HelpEntry(
                name="metrics",
                description="Show system metrics",
                usage="/metrics",
                examples=["/metrics"],
                aliases=["stats"],
                category="system",
            ),
            HelpEntry(
                name="clear",
                description="Clear the terminal screen",
                usage="/clear",
                examples=["/clear"],
                aliases=["cls", "clean"],
                category="terminal",
            ),
        ]

        for entry in commands:
            self._entries[entry.name] = entry
            for alias in entry.aliases:
                self._entries[alias] = entry

    def _add_application_help(self) -> None:
        """Add help entries for applications."""
        applications = [
            HelpEntry(
                name="brain",
                description="Brain Dashboard - Real-time cognitive monitoring",
                usage="/start brain",
                examples=["/start brain", "/stop brain"],
                category="applications",
            ),
            HelpEntry(
                name="voice",
                description="Voice Dashboard - Audio pipeline controls",
                usage="/start voice",
                examples=["/start voice", "/stop voice"],
                category="applications",
            ),
            HelpEntry(
                name="chat",
                description="Desktop Chat App - PySide6 chat interface",
                usage="/start chat",
                examples=["/start chat", "/stop chat"],
                category="applications",
            ),
            HelpEntry(
                name="terminal",
                description="Terminal UI - Textual-based interface",
                usage="/start terminal",
                examples=["/start terminal"],
                category="applications",
            ),
            HelpEntry(
                name="api",
                description="FastAPI Server - REST API and WebSocket server",
                usage="/start api",
                examples=["/start api", "/stop api"],
                category="applications",
            ),
            HelpEntry(
                name="web",
                description="Web Dashboard - React-based web interface",
                usage="/start web",
                examples=["/start web", "/stop web"],
                category="applications",
            ),
            HelpEntry(
                name="core",
                description="Emily Core - Main voice OS engine",
                usage="/start core",
                examples=["/start core", "/stop core"],
                category="applications",
            ),
            HelpEntry(
                name="all",
                description="Start complete Emily stack",
                usage="/start all",
                examples=["/start all"],
                category="applications",
            ),
        ]

        for entry in applications:
            self._entries[entry.name] = entry

    def _organize_categories(self) -> None:
        """Organize entries by category."""
        categories = {"help": [], "applications": [], "system": [], "terminal": [], "general": []}

        for entry in self._entries.values():
            if entry.category in categories:
                categories[entry.category].append(entry.name)

        self._categories = categories

    def get_help(self, topic: str | None = None) -> str:
        """Get help for a topic or general help."""
        if not topic:
            return self._get_main_help()

        topic_lower = topic.lower()

        # Check for category help
        if topic_lower in self._categories:
            return self._get_category_help(topic_lower)

        # Check for specific command/app help
        entry = self._entries.get(topic_lower)
        if entry:
            return entry.format_help()

        return f"Unknown help topic: {topic}. Type /help for available topics."

    def _get_main_help(self) -> str:
        """Get main help overview."""
        lines = [
            "Emily Terminal Commands - Help System",
            "=====================================",
            "",
            "Available Help Topics:",
            "  /help              - Show this help message",
            "  /help apps         - List all applications",
            "  /help commands     - List all commands",
            "  /help <category>   - Help for specific category",
            "  /help <command>    - Help for specific command",
            "",
            "Categories:",
        ]

        for category, entries in self._categories.items():
            if entries:
                lines.append(f"  {category:<12} - {len(entries)} entries")

        lines.extend(
            [
                "",
                "Quick Start:",
                "  /start brain       - Launch Brain Dashboard",
                "  /start api         - Start API server",
                "  /status            - Show running services",
                "  /help apps         - List all applications",
                "",
                "Examples:",
                "  /help start        - Help for start command",
                "  /start chat        - Launch Desktop Chat",
                "  /status            - Check what's running",
                "  /stop api          - Stop API server",
            ]
        )

        return "\n".join(lines)

    def _get_category_help(self, category: str) -> str:
        """Get help for a specific category."""
        if category not in self._categories:
            return f"Unknown category: {category}"

        entries = self._categories[category]
        if not entries:
            return f"No entries in category: {category}"

        lines = [f"{category.title()} Commands:"]

        for entry_name in sorted(entries):
            entry = self._entries[entry_name]
            lines.append(f"  /{entry_name:<12} - {entry.description}")

        return "\n".join(lines)

    def get_apps_help(self) -> str:
        """Get detailed help for all applications."""
        lines = [
            "Emily Applications",
            "==================",
            "",
        ]

        app_entries = [
            (
                "brain",
                "Brain Dashboard",
                "Real-time cognitive state monitoring, agent activity, memory operations, and system metrics visualization",
            ),
            (
                "voice",
                "Voice Dashboard",
                "Audio pipeline controls, conversation state, TTS/STT status, emotion detection, and speaker identification",
            ),
            (
                "chat",
                "Desktop Chat App",
                "PySide6-based chat interface with conversation history, profiles, and Emily persona customization",
            ),
            (
                "terminal",
                "Terminal UI",
                "Textual-based terminal interface with chat, memory view, system logs, and command access",
            ),
            (
                "api",
                "FastAPI Server",
                "REST API and WebSocket server for web interfaces and external integrations",
            ),
            (
                "web",
                "Web Dashboard",
                "React-based web interface with full Emily functionality accessible from browsers",
            ),
            (
                "core",
                "Emily Core",
                "Main voice OS with conversation engine, perception, memory, and agent coordination",
            ),
        ]

        for app_key, app_name, description in app_entries:
            lines.extend([f"{app_key:<10} - {app_name}", f"           {description}", ""])

        lines.extend(
            [
                "Usage:",
                "  /start <app>   - Launch the application",
                "  /stop <app>    - Stop the application",
                "  /restart <app> - Restart the application",
                "",
                "Special:",
                "  /start all     - Start complete Emily stack (api + core)",
            ]
        )

        return "\n".join(lines)

    def get_commands_help(self) -> str:
        """Get help for all commands."""
        lines = [
            "Available Commands",
            "==================",
            "",
        ]

        # Group commands by category
        for category, entries in self._categories.items():
            if not entries or category == "applications":
                continue

            lines.append(f"{category.title()} Commands:")
            for entry_name in sorted(entries):
                entry = self._entries[entry_name]
                aliases_str = f" (/{', /'.join(entry.aliases)})" if entry.aliases else ""
                lines.append(f"  /{entry_name:<12}{aliases_str} - {entry.description}")
            lines.append("")

        return "\n".join(lines)

    def search_help(self, query: str) -> list[str]:
        """Search help entries for a query."""
        query_lower = query.lower()
        results = []

        for entry in self._entries.values():
            if (
                query_lower in entry.name.lower()
                or query_lower in entry.description.lower()
                or any(query_lower in alias.lower() for alias in entry.aliases)
            ):
                results.append(entry.name)

        return results

    def get_command_suggestions(self, partial: str) -> list[str]:
        """Get command suggestions for partial input."""
        partial_lower = partial.lower()
        suggestions = []

        for name in self._entries:
            if name.startswith(partial_lower):
                suggestions.append(name)

        return sorted(suggestions)


# Global help system instance
help_system = HelpSystem()
