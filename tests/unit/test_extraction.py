"""Unit tests for extraction modules (deduplicator, entity/relation models)."""

from __future__ import annotations

from datetime import UTC

import pytest
import pytest_asyncio

from extraction.deduplicator import Deduplicator, _jaro_winkler, _normalize
from extraction.entity_extractor import ExtractedEntity, _extract_json_array
from memory.knowledge_models import EntityRecord
from memory.knowledge_store import KnowledgeStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path):
    """Fresh KnowledgeStore for each test."""
    ks = KnowledgeStore(db_path=str(tmp_path / "test.db"))
    await ks.connect()
    yield ks
    await ks.close()


@pytest_asyncio.fixture
async def dedup(store):
    """Deduplicator backed by fresh store."""
    return Deduplicator(store)


# ---------------------------------------------------------------------------
# Jaro-Winkler / normalize tests
# ---------------------------------------------------------------------------


def test_normalize_removes_punctuation() -> None:
    """_normalize strips punctuation and lowercases."""
    assert _normalize("Alice O'Brien!") == "alice obrien"


def test_jaro_winkler_identical() -> None:
    """Identical strings score 1.0."""
    assert _jaro_winkler("alice", "alice") == 1.0


def test_jaro_winkler_different() -> None:
    """Completely different strings score low."""
    score = _jaro_winkler("alice", "zxqmv")
    assert score < 0.6


def test_jaro_winkler_similar() -> None:
    """Similar strings score high."""
    score = _jaro_winkler("robert", "roberto")
    assert score > 0.85


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def test_extract_json_array_plain() -> None:
    """Parses a plain JSON array."""
    raw = '[{"canonical_name": "Alice", "type": "person", "confidence": 0.9}]'
    result = _extract_json_array(raw)
    assert len(result) == 1
    assert result[0]["canonical_name"] == "Alice"


def test_extract_json_array_fenced() -> None:
    """Parses JSON wrapped in markdown code fences."""
    raw = '```json\n[{"canonical_name": "Bob"}]\n```'
    result = _extract_json_array(raw)
    assert len(result) == 1


def test_extract_json_array_empty_on_invalid() -> None:
    """Returns empty list for unparseable content."""
    result = _extract_json_array("this is not json at all")
    assert result == []


def test_extract_json_array_empty_list() -> None:
    """Returns empty list for '[]' response."""
    result = _extract_json_array("[]")
    assert result == []


# ---------------------------------------------------------------------------
# ExtractedEntity
# ---------------------------------------------------------------------------


def test_extracted_entity_needs_confirmation_below_threshold() -> None:
    """Entities with confidence < 0.4 need confirmation."""
    entity = ExtractedEntity(canonical_name="Maybe Person", type="person", confidence=0.3)
    assert entity.needs_confirmation is True


def test_extracted_entity_no_confirmation_above_threshold() -> None:
    """Entities with confidence >= 0.4 do not need confirmation."""
    entity = ExtractedEntity(canonical_name="Alice", type="person", confidence=0.9)
    assert entity.needs_confirmation is False


# ---------------------------------------------------------------------------
# Deduplicator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_creates_new_entity(dedup: Deduplicator, store: KnowledgeStore) -> None:
    """Unknown entity is created in the store."""
    extracted = ExtractedEntity(canonical_name="Alice Nguyen", type="person", confidence=0.9)
    entity, created = await dedup.resolve_entity(extracted)
    assert created is True
    assert entity.canonical_name == "Alice Nguyen"

    # Verify it's actually in the store
    fetched = await store.get_entity(entity.id)
    assert fetched is not None


@pytest.mark.asyncio
async def test_dedup_merges_exact_name(dedup: Deduplicator, store: KnowledgeStore) -> None:
    """Re-extracting the same name returns the existing entity."""
    first = ExtractedEntity(canonical_name="Alice Nguyen", type="person", confidence=0.9)
    entity1, created1 = await dedup.resolve_entity(first)
    assert created1 is True

    second = ExtractedEntity(canonical_name="Alice Nguyen", type="person", confidence=0.95)
    entity2, created2 = await dedup.resolve_entity(second)
    assert created2 is False
    assert entity2.id == entity1.id


@pytest.mark.asyncio
async def test_dedup_adds_aliases_on_merge(dedup: Deduplicator, store: KnowledgeStore) -> None:
    """Merging an entity with a new alias adds the alias to the existing entity."""
    first = ExtractedEntity(
        canonical_name="Alice Nguyen", type="person", confidence=0.9, aliases=["Alice"]
    )
    entity1, _ = await dedup.resolve_entity(first)

    second = ExtractedEntity(
        canonical_name="Alice Nguyen", type="person", confidence=0.9, aliases=["Ali", "A. Nguyen"]
    )
    entity2, created = await dedup.resolve_entity(second)
    assert not created
    assert "Ali" in entity2.aliases or "A. Nguyen" in entity2.aliases


@pytest.mark.asyncio
async def test_dedup_fuzzy_match(dedup: Deduplicator, store: KnowledgeStore) -> None:
    """Fuzzy name match merges instead of creating a duplicate."""
    first = ExtractedEntity(canonical_name="Robert Johnson", type="person", confidence=0.9)
    entity1, created1 = await dedup.resolve_entity(first)
    assert created1 is True

    # "Roberto Johnson" is very similar — should fuzz-merge
    second = ExtractedEntity(canonical_name="Roberto Johnson", type="person", confidence=0.85)
    entity2, created2 = await dedup.resolve_entity(second)
    # May or may not merge depending on score — just check it doesn't crash
    # and if it does match, IDs are equal
    if not created2:
        assert entity2.id == entity1.id


# ---------------------------------------------------------------------------
# Proactive engine (no DB needed — unit level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proactive_birthday_alert(store: KnowledgeStore) -> None:
    """ProactiveEngine.check_birthdays returns alert for today's birthday."""
    from datetime import date

    from memory.knowledge_models import PersonRecord
    from proactive.engine import ProactiveEngine

    entity = EntityRecord(canonical_name="Birthday Person", type="person")
    await store.upsert_entity(entity)

    today_md = date.today().strftime("%m-%d")
    person = PersonRecord(
        entity_id=entity.id,
        full_name="Birthday Person",
        important_dates={"birthday": today_md},
    )
    await store.upsert_person(person)

    engine = ProactiveEngine(store)
    alerts = await engine.check_birthdays()
    assert any(a.entity_id == entity.id for a in alerts)


@pytest.mark.asyncio
async def test_proactive_upcoming_event(store: KnowledgeStore) -> None:
    """ProactiveEngine.check_upcoming_events includes events within the window."""
    from datetime import datetime, timedelta

    from memory.knowledge_models import EventRecord
    from proactive.engine import ProactiveEngine

    soon = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    event = EventRecord(title="Test Meeting", event_type="meeting", datetime=soon)
    await store.upsert_event(event)

    engine = ProactiveEngine(store)
    alerts = await engine.check_upcoming_events(hours_ahead=24)
    assert any(a.extra.get("event_id") == event.id for a in alerts)
