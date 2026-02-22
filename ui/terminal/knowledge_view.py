"""
Knowledge OS — Textual TUI panel.

Provides a read-only tabbed interface for browsing:
  Tab 1: People — searchable list of person entities with profiles
  Tab 2: Facts  — recent facts with entity names and confidence bars
  Tab 3: Events — upcoming events timeline
  Tab 4: Vault  — credential summaries (NO secrets rendered)
  Tab 5: Alerts — proactive intelligence alerts

Credential secrets are NEVER rendered in this panel. The vault tab shows
only name, service, and username. Accessing a secret requires a separate
CLI command or vault.get() call.

Usage (standalone):
    python -m ui.terminal.knowledge_view

Usage (as a Textual widget to embed in the main TUI):
    from ui.terminal.knowledge_view import KnowledgeScreen
    app.push_screen(KnowledgeScreen(store=store, vault=vault))
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from observability.logger import get_logger

log = get_logger(__name__)

_PANEL_TITLE = "Emily — Knowledge OS"
_NO_DATA = "[dim]No data — knowledge store may be empty or not connected.[/dim]"


class PeopleTab(TabPane):
    """Searchable list of person entities."""

    DEFAULT_CSS = """
    PeopleTab {
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Build the people search UI."""
        yield Label("Search people:", classes="label")
        yield Input(placeholder="Name, employer, or relationship…", id="people-search")
        yield DataTable(id="people-table", cursor_type="row")

    def on_mount(self) -> None:
        """Configure the people table columns."""
        table = self.query_one("#people-table", DataTable)
        table.add_columns("Name", "Relationship", "Employer", "Last Contact", "Birthday")

    async def load(self, store: Any) -> None:
        """Populate the table from the knowledge store."""
        table = self.query_one("#people-table", DataTable)
        table.clear()

        try:
            people = await store.search_people(limit=100)
            for person in people:
                bday = person.important_dates.get("birthday", "")
                table.add_row(
                    person.full_name,
                    person.relationship_to_user or "—",
                    person.employer or "—",
                    person.last_contact[:10] if person.last_contact else "—",
                    bday or "—",
                )
        except Exception as exc:
            log.error("people_tab_load_error", error=str(exc))
            table.add_row("[error]", str(exc), "", "", "")


class FactsTab(TabPane):
    """Recent facts with confidence indicators."""

    def compose(self) -> ComposeResult:
        """Build the facts table."""
        yield DataTable(id="facts-table", cursor_type="row")

    def on_mount(self) -> None:
        """Configure the facts table columns."""
        table = self.query_one("#facts-table", DataTable)
        table.add_columns("Entity", "Type", "Fact", "Confidence", "Timestamp")

    async def load(self, store: Any) -> None:
        """Populate facts from all entities (most confident first)."""
        table = self.query_one("#facts-table", DataTable)
        table.clear()

        try:
            entities = await store.find_entities("", limit=50)
            rows = []
            for entity in entities:
                facts = await store.get_facts_for_entity(entity.id)
                for fact in facts[:5]:  # max 5 per entity to avoid overflow
                    conf_bar = "█" * int(fact.confidence * 10)
                    rows.append((
                        entity.canonical_name,
                        fact.fact_type,
                        fact.fact_text[:80] + ("…" if len(fact.fact_text) > 80 else ""),
                        f"{conf_bar} {fact.confidence:.2f}",
                        fact.timestamp[:10] if fact.timestamp else "—",
                    ))

            rows.sort(key=lambda r: r[3], reverse=True)
            for row in rows[:50]:
                table.add_row(*row)

            if not rows:
                table.add_row(_NO_DATA, "", "", "", "")
        except Exception as exc:
            log.error("facts_tab_load_error", error=str(exc))


class EventsTab(TabPane):
    """Upcoming events timeline."""

    def compose(self) -> ComposeResult:
        """Build the events table."""
        yield Label("Upcoming Events:", classes="label")
        yield DataTable(id="events-table", cursor_type="row")

    def on_mount(self) -> None:
        """Configure the events table columns."""
        table = self.query_one("#events-table", DataTable)
        table.add_columns("Title", "Type", "When", "Location", "Description")

    async def load(self, store: Any) -> None:
        """Populate upcoming events."""
        table = self.query_one("#events-table", DataTable)
        table.clear()

        try:
            events = await store.get_upcoming_events(limit=30)
            for event in events:
                dt_str = event.datetime[:16].replace("T", " ") if event.datetime else "—"
                table.add_row(
                    event.title,
                    event.event_type,
                    dt_str,
                    event.location or "—",
                    (event.description or "")[:60],
                )
            if not events:
                table.add_row(_NO_DATA, "", "", "", "")
        except Exception as exc:
            log.error("events_tab_load_error", error=str(exc))


class VaultTab(TabPane):
    """Credential summaries — NO secrets displayed."""

    _VAULT_WARNING = (
        "[bold yellow]⚠ DISPLAY ONLY — secrets are never shown here.[/bold yellow]\n"
        "Unlock the vault to see credential summaries. "
        "Use the CLI to retrieve a secret."
    )

    def compose(self) -> ComposeResult:
        """Build the vault table."""
        yield Static(self._VAULT_WARNING, id="vault-warning")
        yield DataTable(id="vault-table", cursor_type="row")

    def on_mount(self) -> None:
        """Configure the vault table columns."""
        table = self.query_one("#vault-table", DataTable)
        table.add_columns("Name", "Service", "Username", "Type", "Strength", "Expires")

    async def load(self, vault: Any) -> None:
        """Populate vault credential summaries (no secrets)."""
        table = self.query_one("#vault-table", DataTable)
        table.clear()

        if vault is None:
            table.add_row("[dim]Vault not configured[/dim]", "", "", "", "", "")
            return

        if not vault.is_unlocked():
            table.add_row("[dim]Vault is locked — unlock via CLI[/dim]", "", "", "", "", "")
            return

        try:
            summaries = await vault.list_all()
            for s in summaries:
                strength_bar = "█" * int(s.password_strength * 10)
                table.add_row(
                    s.name,
                    s.service,
                    s.username,
                    s.type.value,
                    f"{strength_bar} {s.password_strength:.1f}",
                    s.expiry_date or "—",
                )
            if not summaries:
                table.add_row("[dim]No credentials stored[/dim]", "", "", "", "", "")
        except Exception as exc:
            log.error("vault_tab_load_error", error=str(exc))


class AlertsTab(TabPane):
    """Proactive intelligence alerts."""

    def compose(self) -> ComposeResult:
        """Build the alerts table."""
        yield DataTable(id="alerts-table", cursor_type="row")

    def on_mount(self) -> None:
        """Configure the alerts table columns."""
        table = self.query_one("#alerts-table", DataTable)
        table.add_columns("Severity", "Type", "Title", "Message")

    async def load(self, proactive: Any) -> None:
        """Populate alerts from the proactive engine."""
        table = self.query_one("#alerts-table", DataTable)
        table.clear()

        if proactive is None:
            table.add_row("—", "—", "[dim]Proactive engine not configured[/dim]", "")
            return

        try:
            alerts = await proactive.run_all_checks()
            severity_colors = {"critical": "red", "high": "yellow", "medium": "blue", "info": "green"}
            for alert in alerts:
                color = severity_colors.get(alert.severity, "white")
                table.add_row(
                    f"[{color}]{alert.severity.upper()}[/{color}]",
                    alert.alert_type,
                    alert.title[:60],
                    alert.message[:80],
                )
            if not alerts:
                table.add_row("[green]INFO[/green]", "status", "All clear", "No alerts at this time")
        except Exception as exc:
            log.error("alerts_tab_load_error", error=str(exc))


class KnowledgeScreen(Screen):
    """
    Full-screen Textual knowledge browser.

    Can be pushed as a screen in the main Emily TUI app or run standalone.
    Credential secrets are NEVER rendered anywhere in this screen.
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(
        self,
        store: Any = None,
        vault: Any = None,
        proactive: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            store: Connected KnowledgeStore (optional — shows empty state if None).
            vault: CredentialVault (optional).
            proactive: ProactiveEngine (optional).
        """
        super().__init__(**kwargs)
        self._store = store
        self._vault = vault
        self._proactive = proactive

    def compose(self) -> ComposeResult:
        """Assemble the tabbed knowledge interface."""
        yield Header(show_clock=True)
        with TabbedContent(initial="people-pane"):
            with PeopleTab("People", id="people-pane"):
                pass
            with FactsTab("Facts", id="facts-pane"):
                pass
            with EventsTab("Events", id="events-pane"):
                pass
            with VaultTab("Vault (display-only)", id="vault-pane"):
                pass
            with AlertsTab("Alerts", id="alerts-pane"):
                pass
        yield Footer()

    async def on_mount(self) -> None:
        """Load all tabs on mount."""
        await self._refresh_all()

    async def _refresh_all(self) -> None:
        """Reload data in all tabs."""
        if self._store:
            people_tab = self.query_one("#people-pane", PeopleTab)
            facts_tab = self.query_one("#facts-pane", FactsTab)
            events_tab = self.query_one("#events-pane", EventsTab)
            await asyncio.gather(
                people_tab.load(self._store),
                facts_tab.load(self._store),
                events_tab.load(self._store),
            )

        vault_tab = self.query_one("#vault-pane", VaultTab)
        await vault_tab.load(self._vault)

        alerts_tab = self.query_one("#alerts-pane", AlertsTab)
        await alerts_tab.load(self._proactive)

    async def action_refresh(self) -> None:
        """Refresh all tabs on 'r' keypress."""
        self.notify("Refreshing knowledge data…")
        await self._refresh_all()
        self.notify("Done.")


class KnowledgeApp(App):
    """
    Standalone Textual app for browsing Emily's knowledge store.

    Run with: python -m ui.terminal.knowledge_view
    """

    TITLE = _PANEL_TITLE
    CSS = """
    Screen { background: #0d0d1a; }
    Header { background: #1a1a2e; color: #a0a0c0; }
    Footer { background: #1a1a2e; color: #606080; }
    DataTable { height: 1fr; }
    .label { color: #8888aa; margin-bottom: 1; }
    #vault-warning { color: #c0a000; margin-bottom: 1; }
    """

    async def on_mount(self) -> None:
        """Push the KnowledgeScreen on startup."""
        await self.push_screen(KnowledgeScreen())


if __name__ == "__main__":
    KnowledgeApp().run()
