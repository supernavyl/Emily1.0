"""Unit tests for memory/knowledge_store.py and memory/knowledge_models.py."""

from __future__ import annotations

import pytest
import pytest_asyncio

from memory.knowledge_models import (
    EntityRecord,
    EventRecord,
    FactRecord,
    PersonRecord,
    RelationshipRecord,
)
from memory.knowledge_store import KnowledgeStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path):
    """
    Provide a fresh KnowledgeStore backed by a temp file for each test.

    KnowledgeStore.connect() is self-bootstrapping — it applies the schema
    automatically, so no separate migration step is needed in tests.
    """
    db_path = str(tmp_path / "test_knowledge.db")
    ks = KnowledgeStore(db_path=db_path)
    await ks.connect()
    yield ks
    await ks.close()


@pytest_asyncio.fixture
async def alice_entity(store: KnowledgeStore) -> EntityRecord:
    """Insert and return a test entity."""
    entity = EntityRecord(
        canonical_name="Alice Nguyen",
        type="person",
        aliases=["Alice", "Ali"],
        confidence=0.95,
    )
    await store.upsert_entity(entity)
    return entity


@pytest_asyncio.fixture
async def alice_person(store: KnowledgeStore, alice_entity: EntityRecord) -> PersonRecord:
    """Insert and return a test person profile."""
    person = PersonRecord(
        entity_id=alice_entity.id,
        full_name="Alice Nguyen",
        relationship_to_user="colleague",
        employer="Acme Corp",
        important_dates={"birthday": "03-14"},
        preferences={"food": "vegan"},
    )
    await store.upsert_person(person)
    return person


# ---------------------------------------------------------------------------
# Entity tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_get_entity(store: KnowledgeStore) -> None:
    """Inserted entity can be retrieved by primary key."""
    entity = EntityRecord(canonical_name="Bob Smith", type="person")
    await store.upsert_entity(entity)

    fetched = await store.get_entity(entity.id)
    assert fetched is not None
    assert fetched.canonical_name == "Bob Smith"
    assert fetched.type == "person"


@pytest.mark.asyncio
async def test_get_entity_missing_returns_none(store: KnowledgeStore) -> None:
    """get_entity returns None for a non-existent ID."""
    result = await store.get_entity("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_find_entities_by_name(store: KnowledgeStore, alice_entity: EntityRecord) -> None:
    """find_entities returns partial name matches."""
    results = await store.find_entities("Alice")
    assert any(e.id == alice_entity.id for e in results)


@pytest.mark.asyncio
async def test_find_entities_by_type(store: KnowledgeStore, alice_entity: EntityRecord) -> None:
    """find_entities filters by type correctly."""
    person_results = await store.find_entities("Alice", entity_type="person")
    org_results = await store.find_entities("Alice", entity_type="org")
    assert any(e.id == alice_entity.id for e in person_results)
    assert not any(e.id == alice_entity.id for e in org_results)


@pytest.mark.asyncio
async def test_delete_entity(store: KnowledgeStore) -> None:
    """Deleted entity is no longer retrievable."""
    entity = EntityRecord(canonical_name="Temp Entity", type="object")
    await store.upsert_entity(entity)
    assert await store.get_entity(entity.id) is not None

    await store.delete_entity(entity.id)
    assert await store.get_entity(entity.id) is None


@pytest.mark.asyncio
async def test_entity_aliases_roundtrip(store: KnowledgeStore) -> None:
    """Aliases list survives JSON serialization roundtrip."""
    entity = EntityRecord(canonical_name="Carol", type="person", aliases=["Caz", "Caroline"])
    await store.upsert_entity(entity)
    fetched = await store.get_entity(entity.id)
    assert fetched is not None
    assert fetched.aliases == ["Caz", "Caroline"]


# ---------------------------------------------------------------------------
# Person tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_get_person(store: KnowledgeStore, alice_person: PersonRecord) -> None:
    """Person profile can be retrieved after insertion."""
    fetched = await store.get_person(alice_person.entity_id)
    assert fetched is not None
    assert fetched.full_name == "Alice Nguyen"
    assert fetched.employer == "Acme Corp"
    assert fetched.preferences == {"food": "vegan"}


@pytest.mark.asyncio
async def test_search_people_by_name(store: KnowledgeStore, alice_person: PersonRecord) -> None:
    """search_people matches on full_name substring."""
    results = await store.search_people(name_fragment="Alice")
    assert any(p.entity_id == alice_person.entity_id for p in results)


@pytest.mark.asyncio
async def test_search_people_by_employer(store: KnowledgeStore, alice_person: PersonRecord) -> None:
    """search_people filters by employer correctly."""
    results = await store.search_people(employer="Acme Corp")
    assert any(p.entity_id == alice_person.entity_id for p in results)

    no_results = await store.search_people(employer="Unknown Co")
    assert not any(p.entity_id == alice_person.entity_id for p in no_results)


@pytest.mark.asyncio
async def test_birthday_this_week(store: KnowledgeStore, alice_person: PersonRecord) -> None:
    """get_people_with_birthday_this_week returns person with today's birthday."""
    from datetime import date

    today_md = date.today().strftime("%m-%d")
    # Update Alice's birthday to today's MM-DD
    alice_person.important_dates = {"birthday": today_md}
    await store.upsert_person(alice_person)

    results = await store.get_people_with_birthday_this_week()
    assert any(p.entity_id == alice_person.entity_id for p in results)


# ---------------------------------------------------------------------------
# Relationship tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_get_relationship(
    store: KnowledgeStore, alice_entity: EntityRecord
) -> None:
    """Relationship can be stored and retrieved for both entities."""
    bob = EntityRecord(canonical_name="Bob", type="person")
    await store.upsert_entity(bob)

    rel = RelationshipRecord(
        from_entity_id=alice_entity.id,
        to_entity_id=bob.id,
        relationship_type="knows",
        strength=0.8,
    )
    await store.upsert_relationship(rel)

    rels = await store.get_relationships_for_entity(alice_entity.id, direction="outgoing")
    assert any(r.id == rel.id for r in rels)


@pytest.mark.asyncio
async def test_relationship_bidirectional_lookup(
    store: KnowledgeStore, alice_entity: EntityRecord
) -> None:
    """direction='both' returns edges in either direction."""
    bob = EntityRecord(canonical_name="Bob2", type="person")
    await store.upsert_entity(bob)

    rel = RelationshipRecord(
        from_entity_id=bob.id,
        to_entity_id=alice_entity.id,
        relationship_type="works_with",
    )
    await store.upsert_relationship(rel)

    rels = await store.get_relationships_for_entity(alice_entity.id, direction="both")
    assert any(r.id == rel.id for r in rels)


# ---------------------------------------------------------------------------
# Fact tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_retrieve_fact(store: KnowledgeStore, alice_entity: EntityRecord) -> None:
    """Facts can be stored and retrieved for an entity."""
    fact = FactRecord(
        entity_id=alice_entity.id,
        fact_type="preference",
        fact_text="Alice prefers async communication",
        confidence=0.9,
    )
    await store.add_fact(fact)

    facts = await store.get_facts_for_entity(alice_entity.id)
    assert any(f.id == fact.id for f in facts)


@pytest.mark.asyncio
async def test_add_fact_low_confidence_raises(
    store: KnowledgeStore, alice_entity: EntityRecord
) -> None:
    """Facts with confidence < 0.4 raise ValueError."""
    fact = FactRecord(
        entity_id=alice_entity.id,
        fact_type="habit",
        fact_text="Maybe Alice jogs",
        confidence=0.3,
    )
    with pytest.raises(ValueError, match="0.4"):
        await store.add_fact(fact)


@pytest.mark.asyncio
async def test_supersede_fact(store: KnowledgeStore, alice_entity: EntityRecord) -> None:
    """supersede_fact marks old fact inactive and stores the new one."""
    old = FactRecord(
        entity_id=alice_entity.id,
        fact_type="employment",
        fact_text="Alice works at Acme",
        confidence=0.95,
    )
    await store.add_fact(old)

    new = FactRecord(
        entity_id=alice_entity.id,
        fact_type="employment",
        fact_text="Alice works at Meta",
        confidence=0.95,
    )
    await store.supersede_fact(old.id, new)

    active = await store.get_facts_for_entity(alice_entity.id)
    assert all(f.id != old.id for f in active)
    assert any(f.id == new.id for f in active)


# ---------------------------------------------------------------------------
# Event tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_get_event(store: KnowledgeStore, alice_entity: EntityRecord) -> None:
    """Events can be stored and retrieved by participant."""
    event = EventRecord(
        title="Q1 Planning",
        event_type="meeting",
        datetime="2026-03-01T10:00:00Z",
        participant_ids=[alice_entity.id],
        description="Quarterly planning session",
    )
    await store.upsert_event(event)

    events = await store.get_events_for_entity(alice_entity.id)
    assert any(e.id == event.id for e in events)


@pytest.mark.asyncio
async def test_get_upcoming_events(store: KnowledgeStore) -> None:
    """get_upcoming_events returns only future events."""
    future_event = EventRecord(
        title="Future Meeting",
        event_type="meeting",
        datetime="2099-01-01T10:00:00Z",
    )
    past_event = EventRecord(
        title="Past Meeting",
        event_type="meeting",
        datetime="2000-01-01T10:00:00Z",
    )
    await store.upsert_event(future_event)
    await store.upsert_event(past_event)

    upcoming = await store.get_upcoming_events()
    upcoming_ids = [e.id for e in upcoming]
    assert future_event.id in upcoming_ids
    assert past_event.id not in upcoming_ids


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counts(
    store: KnowledgeStore, alice_entity: EntityRecord, alice_person: PersonRecord
) -> None:
    """counts() returns accurate row counts for all tables."""
    c = await store.counts()
    assert c["entities"] >= 1
    assert c["people"] >= 1
    assert c["relationships"] >= 0
    assert c["facts"] >= 0
    assert c["events"] >= 0
