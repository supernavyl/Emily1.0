"""
Proactive Intelligence Engine.

Runs periodic checks via Emily's Scheduler (P4 Idle priority) and emits
alert events on the AgentBus. Checks include:

- Birthday alerts (upcoming in the next 7 days)
- Upcoming calendar events (within the next 24 hours)
- Credential health (expiring, weak, reused passwords)
- Relationship drift (people you usually contact but haven't recently)
- Contradiction detection (facts in conflict with each other)

Alerts are plain dicts so they can be serialized to JSON or passed to
the TTS/notification system. Credential health alerts NEVER contain secret
material.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from observability.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from memory.knowledge_store import KnowledgeStore

log = get_logger(__name__)


@dataclass
class Alert:
    """A single proactive alert from the engine."""

    alert_type: str  # birthday|event|credential_health|relationship_drift|contradiction
    severity: str  # info|warning|critical
    title: str
    message: str
    entity_id: str = ""
    credential_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict safe for JSON/TTS."""
        d: dict[str, Any] = {
            "type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "entity_id": self.entity_id,
            "credential_id": self.credential_id,
        }
        if self.extra:
            d["extra"] = dict(self.extra)
        return d


class ProactiveEngine:
    """
    Runs background checks and emits Alert objects.

    Designed to be scheduled via Emily's Scheduler at P4 (idle) priority
    so proactive checks never delay user-facing interactions.

    Usage::

        engine = ProactiveEngine(knowledge_store, vault=vault)
        alerts = await engine.run_all_checks()
    """

    def __init__(
        self,
        store: KnowledgeStore,
        vault: Any | None = None,
        relationship_drift_days: int = 14,
    ) -> None:
        """
        Args:
            store: Connected KnowledgeStore.
            vault: Optional unlocked CredentialVault for health checks.
            relationship_drift_days: Days without contact before flagging drift.
        """
        self._store = store
        self._vault = vault
        self._drift_days = relationship_drift_days

    async def run_all_checks(self) -> list[Alert]:
        """
        Run all proactive checks in parallel and return aggregated alerts.

        Returns:
            Combined list of Alert objects, all severities.
        """
        birthday_task = self.check_birthdays()
        event_task = self.check_upcoming_events()
        drift_task = self.check_relationship_drift()
        contradiction_task = self.check_contradictions()

        tasks = [birthday_task, event_task, drift_task, contradiction_task]

        if self._vault and self._vault.is_unlocked():
            tasks.append(self.check_credential_health())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_alerts: list[Alert] = []
        for result in results:
            if isinstance(result, Exception):
                log.error("proactive_check_error", error=str(result))
            elif isinstance(result, list):
                all_alerts.extend(result)

        log.info("proactive_checks_complete", alerts=len(all_alerts))
        return all_alerts

    async def check_birthdays(self) -> list[Alert]:
        """
        Return alerts for people whose birthday falls in the next 7 days.

        Returns:
            List of birthday Alerts.
        """
        people = await self._store.get_people_with_birthday_this_week()
        alerts: list[Alert] = []

        today_md = datetime.now(UTC).strftime("%m-%d")

        for person in people:
            bday = person.important_dates.get("birthday", "")
            if not bday:
                continue

            is_today = bday == today_md
            name = person.full_name

            alerts.append(
                Alert(
                    alert_type="birthday",
                    severity="info",
                    title=f"{'Today is' if is_today else 'Upcoming birthday:'} {name}'s birthday",
                    message=(
                        f"{name}'s birthday is {'today' if is_today else 'this week'} ({bday}). "
                        + (
                            f"Relationship: {person.relationship_to_user}."
                            if person.relationship_to_user
                            else ""
                        )
                    ),
                    entity_id=person.entity_id,
                )
            )

        return alerts

    async def check_upcoming_events(self, hours_ahead: int = 24) -> list[Alert]:
        """
        Return alerts for events starting within the next `hours_ahead` hours.

        Args:
            hours_ahead: Look-ahead window in hours.

        Returns:
            List of event Alerts.
        """
        events = await self._store.get_upcoming_events(limit=20)
        alerts: list[Alert] = []

        now = datetime.now(UTC)
        window_end = now + timedelta(hours=hours_ahead)

        for event in events:
            try:
                event_dt = datetime.fromisoformat(event.datetime)
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=UTC)
            except ValueError:
                continue

            if now <= event_dt <= window_end:
                delta_minutes = int((event_dt - now).total_seconds() / 60)
                alerts.append(
                    Alert(
                        alert_type="event",
                        severity="warning" if delta_minutes <= 30 else "info",
                        title=f"Upcoming: {event.title}",
                        message=(
                            f"'{event.title}' starts in {delta_minutes} minutes"
                            + (f" at {event.location}" if event.location else "")
                        ),
                        entity_id="",
                        extra={"event_id": event.id, "datetime": event.datetime},
                    )
                )

        return alerts

    async def check_credential_health(self) -> list[Alert]:
        """
        Check vault credential health and return alerts.

        Requires vault to be unlocked. Returns NO secret material.

        Returns:
            List of credential health Alerts.
        """
        if not self._vault or not self._vault.is_unlocked():
            return []

        health_report = await self._vault.health_report()
        return [
            Alert(
                alert_type="credential_health",
                severity=item["severity"],
                title=f"Credential issue: {item['name']}",
                message=item["message"],
                credential_id=item["id"],
            )
            for item in health_report
        ]

    async def check_relationship_drift(self) -> list[Alert]:
        """
        Detect people the user usually contacts but hasn't recently.

        Returns:
            List of relationship drift Alerts.
        """
        alerts: list[Alert] = []
        now = datetime.now(UTC)

        people = await self._store.search_people(limit=50)
        for person in people:
            if not person.last_contact:
                continue
            if not person.contact_frequency:
                continue

            try:
                last_dt = datetime.fromisoformat(person.last_contact)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
            except ValueError:
                continue

            days_since = (now - last_dt).days
            if days_since >= self._drift_days:
                alerts.append(
                    Alert(
                        alert_type="relationship_drift",
                        severity="info",
                        title=f"Haven't contacted {person.full_name} recently",
                        message=(
                            f"You last contacted {person.full_name} {days_since} days ago "
                            f"(usual frequency: {person.contact_frequency})."
                        ),
                        entity_id=person.entity_id,
                    )
                )

        return alerts

    async def check_contradictions(self) -> list[Alert]:
        """
        Detect facts that contradict superseded facts without a replacement.

        Returns:
            List of contradiction Alerts.
        """
        alerts: list[Alert] = []

        entities = await self._store.find_entities("", limit=100)

        for entity in entities:
            facts = await self._store.get_facts_for_entity(entity.id, include_superseded=False)
            by_type: dict[str, list[Any]] = {}
            for fact in facts:
                by_type.setdefault(fact.fact_type, []).append(fact)

            for fact_type, type_facts in by_type.items():
                if len(type_facts) > 1:
                    texts: list[str] = [f.fact_text for f in type_facts]
                    alerts.append(
                        Alert(
                            alert_type="contradiction",
                            severity="warning",
                            title=f"Conflicting facts about {entity.canonical_name}",
                            message=(
                                f"Multiple active facts of type '{fact_type}' for "
                                f"{entity.canonical_name}: {' | '.join(texts[:2])}"
                            ),
                            entity_id=entity.id,
                        )
                    )

        return alerts


class ProactiveScheduler:
    """
    Wraps ProactiveEngine to run checks on a recurring schedule.

    Submits check batches to Emily's Scheduler at P4 (idle) priority so
    proactive intelligence never competes with user interactions.
    """

    def __init__(
        self,
        engine: ProactiveEngine,
        check_interval_minutes: int = 30,
    ) -> None:
        """
        Args:
            engine: Configured ProactiveEngine.
            check_interval_minutes: How often to run all checks.
        """
        self._engine = engine
        self._interval = check_interval_minutes * 60
        self._task: asyncio.Task[None] | None = None
        self._alert_callbacks: list[Callable[[Alert], Any]] = []

    def on_alert(self, callback: Callable[[Alert], Any]) -> None:
        """Register a callback to be called with each Alert.

        Args:
            callback: Async or sync callable accepting an Alert.
        """
        self._alert_callbacks.append(callback)

    async def start(self) -> None:
        """Start the recurring check loop."""
        if self._task is not None and not self._task.done():
            log.warning("proactive_scheduler_already_running")
            return
        self._task = asyncio.create_task(self._loop())
        log.info("proactive_scheduler_started", interval_s=self._interval)

    async def stop(self) -> None:
        """Stop the recurring check loop."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        log.info("proactive_scheduler_stopped")

    async def _loop(self) -> None:
        """Main check loop — runs checks then sleeps for the interval."""
        while True:
            try:
                alerts = await self._engine.run_all_checks()
                for alert in alerts:
                    for cb in self._alert_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(alert)
                            else:
                                await asyncio.to_thread(cb, alert)
                        except Exception as exc:
                            log.error("alert_callback_error", error=str(exc))
            except Exception as exc:
                log.error("proactive_loop_error", error=str(exc))

            await asyncio.sleep(self._interval)
