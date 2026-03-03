"""Tests for proactive.engine — Alert, ProactiveEngine, ProactiveScheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from proactive.engine import Alert, ProactiveEngine, ProactiveScheduler

# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakePerson:
    full_name: str = "Alice"
    entity_id: str = "ent-1"
    relationship_to_user: str = ""
    important_dates: dict[str, str] = field(default_factory=dict)
    last_contact: str = ""
    contact_frequency: str = ""


@dataclass
class _FakeEvent:
    id: str = "ev-1"
    title: str = "Meeting"
    datetime: str = ""
    location: str = ""


@dataclass
class _FakeEntity:
    id: str = "entity-1"
    canonical_name: str = "Alice"


@dataclass
class _FakeFact:
    fact_type: str = "hobby"
    fact_text: str = "reading"


def _make_store(**overrides: Any) -> MagicMock:
    store = MagicMock()
    store.get_people_with_birthday_this_week = AsyncMock(
        return_value=overrides.get("birthday_people", []),
    )
    store.get_upcoming_events = AsyncMock(
        return_value=overrides.get("events", []),
    )
    store.search_people = AsyncMock(
        return_value=overrides.get("drift_people", []),
    )
    store.find_entities = AsyncMock(
        return_value=overrides.get("entities", []),
    )
    store.get_facts_for_entity = AsyncMock(
        return_value=overrides.get("facts", []),
    )
    return store


# ---------------------------------------------------------------------------
# Alert tests
# ---------------------------------------------------------------------------


class TestAlert:
    """Tests for Alert dataclass."""

    def test_to_dict_basic(self) -> None:
        alert = Alert(
            alert_type="birthday",
            severity="info",
            title="Test",
            message="Hello",
        )
        d = alert.to_dict()
        assert d["type"] == "birthday"
        assert d["severity"] == "info"
        assert d["title"] == "Test"
        assert d["message"] == "Hello"
        assert d["entity_id"] == ""
        assert d["credential_id"] == ""
        assert "extra" not in d

    def test_to_dict_includes_extra(self) -> None:
        alert = Alert(
            alert_type="event",
            severity="warning",
            title="Upcoming",
            message="Soon",
            extra={"event_id": "ev-1", "datetime": "2026-01-01"},
        )
        d = alert.to_dict()
        assert d["extra"] == {"event_id": "ev-1", "datetime": "2026-01-01"}

    def test_to_dict_with_entity_and_credential(self) -> None:
        alert = Alert(
            alert_type="credential_health",
            severity="critical",
            title="Weak",
            message="Password weak",
            entity_id="ent-1",
            credential_id="cred-1",
        )
        d = alert.to_dict()
        assert d["entity_id"] == "ent-1"
        assert d["credential_id"] == "cred-1"


# ---------------------------------------------------------------------------
# ProactiveEngine.check_birthdays
# ---------------------------------------------------------------------------


class TestCheckBirthdays:
    """Tests for ProactiveEngine.check_birthdays."""

    async def test_no_people(self) -> None:
        store = _make_store()
        engine = ProactiveEngine(store)
        alerts = await engine.check_birthdays()
        assert alerts == []

    async def test_birthday_today(self) -> None:
        today = datetime.now(UTC).strftime("%m-%d")
        person = _FakePerson(
            full_name="Bob",
            entity_id="ent-bob",
            important_dates={"birthday": today},
            relationship_to_user="friend",
        )
        store = _make_store(birthday_people=[person])
        engine = ProactiveEngine(store)
        alerts = await engine.check_birthdays()
        assert len(alerts) == 1
        assert "Today is" in alerts[0].title
        assert alerts[0].alert_type == "birthday"
        assert alerts[0].entity_id == "ent-bob"

    async def test_birthday_this_week(self) -> None:
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%m-%d")
        person = _FakePerson(
            full_name="Carol",
            important_dates={"birthday": tomorrow},
        )
        store = _make_store(birthday_people=[person])
        engine = ProactiveEngine(store)
        alerts = await engine.check_birthdays()
        assert len(alerts) == 1
        assert "Upcoming birthday:" in alerts[0].title

    async def test_skips_person_without_birthday(self) -> None:
        person = _FakePerson(important_dates={})
        store = _make_store(birthday_people=[person])
        engine = ProactiveEngine(store)
        alerts = await engine.check_birthdays()
        assert alerts == []


# ---------------------------------------------------------------------------
# ProactiveEngine.check_upcoming_events
# ---------------------------------------------------------------------------


class TestCheckUpcomingEvents:
    """Tests for ProactiveEngine.check_upcoming_events."""

    async def test_no_events(self) -> None:
        store = _make_store()
        engine = ProactiveEngine(store)
        alerts = await engine.check_upcoming_events()
        assert alerts == []

    async def test_event_within_window(self) -> None:
        soon = (datetime.now(UTC) + timedelta(minutes=60)).isoformat()
        event = _FakeEvent(title="Standup", datetime=soon, location="Room A")
        store = _make_store(events=[event])
        engine = ProactiveEngine(store)
        alerts = await engine.check_upcoming_events()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "event"
        assert alerts[0].severity == "info"
        assert "Room A" in alerts[0].message
        assert alerts[0].extra["event_id"] == "ev-1"

    async def test_event_within_30_minutes_is_warning(self) -> None:
        soon = (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
        event = _FakeEvent(title="Urgent", datetime=soon)
        store = _make_store(events=[event])
        engine = ProactiveEngine(store)
        alerts = await engine.check_upcoming_events()
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"

    async def test_event_outside_window_ignored(self) -> None:
        far = (datetime.now(UTC) + timedelta(hours=48)).isoformat()
        event = _FakeEvent(datetime=far)
        store = _make_store(events=[event])
        engine = ProactiveEngine(store)
        alerts = await engine.check_upcoming_events()
        assert alerts == []

    async def test_bad_datetime_skipped(self) -> None:
        event = _FakeEvent(datetime="not-a-date")
        store = _make_store(events=[event])
        engine = ProactiveEngine(store)
        alerts = await engine.check_upcoming_events()
        assert alerts == []


# ---------------------------------------------------------------------------
# ProactiveEngine.check_credential_health
# ---------------------------------------------------------------------------


class TestCheckCredentialHealth:
    """Tests for ProactiveEngine.check_credential_health."""

    async def test_no_vault(self) -> None:
        store = _make_store()
        engine = ProactiveEngine(store, vault=None)
        alerts = await engine.check_credential_health()
        assert alerts == []

    async def test_vault_locked(self) -> None:
        vault = MagicMock()
        vault.is_unlocked.return_value = False
        store = _make_store()
        engine = ProactiveEngine(store, vault=vault)
        alerts = await engine.check_credential_health()
        assert alerts == []

    async def test_vault_with_issues(self) -> None:
        vault = MagicMock()
        vault.is_unlocked.return_value = True
        vault.health_report = AsyncMock(
            return_value=[
                {"severity": "warning", "name": "gmail", "message": "Weak pw", "id": "c1"},
            ]
        )
        store = _make_store()
        engine = ProactiveEngine(store, vault=vault)
        alerts = await engine.check_credential_health()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "credential_health"
        assert alerts[0].credential_id == "c1"


# ---------------------------------------------------------------------------
# ProactiveEngine.check_relationship_drift
# ---------------------------------------------------------------------------


class TestCheckRelationshipDrift:
    """Tests for ProactiveEngine.check_relationship_drift."""

    async def test_no_drift(self) -> None:
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        person = _FakePerson(
            last_contact=recent,
            contact_frequency="weekly",
        )
        store = _make_store(drift_people=[person])
        engine = ProactiveEngine(store, relationship_drift_days=14)
        alerts = await engine.check_relationship_drift()
        assert alerts == []

    async def test_drift_detected(self) -> None:
        old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        person = _FakePerson(
            full_name="Dave",
            entity_id="ent-dave",
            last_contact=old,
            contact_frequency="weekly",
        )
        store = _make_store(drift_people=[person])
        engine = ProactiveEngine(store, relationship_drift_days=14)
        alerts = await engine.check_relationship_drift()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "relationship_drift"
        assert "Dave" in alerts[0].title

    async def test_skips_no_last_contact(self) -> None:
        person = _FakePerson(contact_frequency="weekly")
        store = _make_store(drift_people=[person])
        engine = ProactiveEngine(store)
        alerts = await engine.check_relationship_drift()
        assert alerts == []

    async def test_skips_no_frequency(self) -> None:
        person = _FakePerson(
            last_contact=(datetime.now(UTC) - timedelta(days=30)).isoformat(),
        )
        store = _make_store(drift_people=[person])
        engine = ProactiveEngine(store)
        alerts = await engine.check_relationship_drift()
        assert alerts == []


# ---------------------------------------------------------------------------
# ProactiveEngine.check_contradictions
# ---------------------------------------------------------------------------


class TestCheckContradictions:
    """Tests for ProactiveEngine.check_contradictions."""

    async def test_no_entities(self) -> None:
        store = _make_store()
        engine = ProactiveEngine(store)
        alerts = await engine.check_contradictions()
        assert alerts == []

    async def test_single_fact_no_contradiction(self) -> None:
        entity = _FakeEntity()
        store = _make_store(entities=[entity], facts=[_FakeFact()])
        engine = ProactiveEngine(store)
        alerts = await engine.check_contradictions()
        assert alerts == []

    async def test_duplicate_fact_type_flagged(self) -> None:
        entity = _FakeEntity(canonical_name="Bob")
        facts = [
            _FakeFact(fact_type="location", fact_text="NYC"),
            _FakeFact(fact_type="location", fact_text="LA"),
        ]
        store = _make_store(entities=[entity])
        store.get_facts_for_entity = AsyncMock(return_value=facts)
        engine = ProactiveEngine(store)
        alerts = await engine.check_contradictions()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "contradiction"
        assert "Bob" in alerts[0].title


# ---------------------------------------------------------------------------
# ProactiveEngine.run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    """Tests for ProactiveEngine.run_all_checks."""

    async def test_aggregates_all_check_results(self) -> None:
        today = datetime.now(UTC).strftime("%m-%d")
        person = _FakePerson(important_dates={"birthday": today})
        store = _make_store(birthday_people=[person])
        engine = ProactiveEngine(store)
        alerts = await engine.run_all_checks()
        assert len(alerts) >= 1
        assert any(a.alert_type == "birthday" for a in alerts)

    async def test_handles_check_exceptions(self) -> None:
        store = _make_store()
        store.get_people_with_birthday_this_week = AsyncMock(
            side_effect=RuntimeError("DB down"),
        )
        engine = ProactiveEngine(store)
        alerts = await engine.run_all_checks()
        assert isinstance(alerts, list)

    async def test_includes_credential_check_when_vault_unlocked(self) -> None:
        vault = MagicMock()
        vault.is_unlocked.return_value = True
        vault.health_report = AsyncMock(
            return_value=[
                {"severity": "info", "name": "test", "message": "ok", "id": "c0"},
            ]
        )
        store = _make_store()
        engine = ProactiveEngine(store, vault=vault)
        alerts = await engine.run_all_checks()
        assert any(a.alert_type == "credential_health" for a in alerts)


# ---------------------------------------------------------------------------
# ProactiveScheduler
# ---------------------------------------------------------------------------


class TestProactiveScheduler:
    """Tests for ProactiveScheduler."""

    async def test_on_alert_registers_callback(self) -> None:
        engine = MagicMock(spec=ProactiveEngine)
        scheduler = ProactiveScheduler(engine)
        cb = MagicMock()
        scheduler.on_alert(cb)
        assert cb in scheduler._alert_callbacks

    async def test_start_creates_task(self) -> None:
        engine = MagicMock(spec=ProactiveEngine)
        engine.run_all_checks = AsyncMock(return_value=[])
        scheduler = ProactiveScheduler(engine, check_interval_minutes=1)
        await scheduler.start()
        assert scheduler._task is not None
        assert not scheduler._task.done()
        await scheduler.stop()

    async def test_double_start_is_noop(self) -> None:
        engine = MagicMock(spec=ProactiveEngine)
        engine.run_all_checks = AsyncMock(return_value=[])
        scheduler = ProactiveScheduler(engine, check_interval_minutes=1)
        await scheduler.start()
        first_task = scheduler._task
        await scheduler.start()
        assert scheduler._task is first_task
        await scheduler.stop()

    async def test_stop_cancels_task(self) -> None:
        engine = MagicMock(spec=ProactiveEngine)
        engine.run_all_checks = AsyncMock(return_value=[])
        scheduler = ProactiveScheduler(engine, check_interval_minutes=1)
        await scheduler.start()
        await scheduler.stop()
        assert scheduler._task is not None
        assert scheduler._task.done()
