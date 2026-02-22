"""
People & Entity REST API routes.

GET  /knowledge/entities          - search entities
GET  /knowledge/entities/{id}     - get entity + person profile
POST /knowledge/entities          - create entity
GET  /knowledge/people/birthdays  - upcoming birthdays this week
GET  /knowledge/people/{id}/facts - get facts for a person
GET  /knowledge/people/{id}/relationships - get relationships

All responses are safe for LLM context and TTS — no credential secrets.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from memory.knowledge_models import EntityRecord, PersonRecord
from memory.knowledge_store import KnowledgeStore
from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Dependency: shared KnowledgeStore instance
# The real app wires this via app.state; tests can inject a mock.
# ---------------------------------------------------------------------------


def _get_store() -> KnowledgeStore:
    """Placeholder — overridden by app.state dependency injection."""
    raise RuntimeError("KnowledgeStore not wired into API dependencies")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class EntityCreate(BaseModel):
    """Request body for creating a new entity."""

    canonical_name: str
    type: str = "person"
    aliases: list[str] = []
    confidence: float = 1.0


class PersonUpdate(BaseModel):
    """Partial update for a person profile (all fields optional)."""

    relationship_to_user: str | None = None
    employer: str | None = None
    occupation: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/entities")
async def search_entities(
    q: str = Query(default="", description="Name fragment to search"),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """
    Search entities by name fragment and optional type filter.

    Returns a list of entity records (id, canonical_name, type, aliases).
    """
    entities = await store.find_entities(q, entity_type=entity_type, limit=limit)
    return {
        "entities": [
            {
                "id": e.id,
                "canonical_name": e.canonical_name,
                "type": e.type,
                "aliases": e.aliases,
                "confidence": e.confidence,
                "created_at": e.created_at,
            }
            for e in entities
        ],
        "count": len(entities),
    }


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """
    Retrieve full entity record plus person profile if available.
    """
    entity = await store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    result: dict[str, Any] = {
        "id": entity.id,
        "canonical_name": entity.canonical_name,
        "type": entity.type,
        "aliases": entity.aliases,
        "confidence": entity.confidence,
        "created_at": entity.created_at,
    }

    if entity.type == "person":
        person = await store.get_person(entity_id)
        if person:
            result["person"] = {
                "full_name": person.full_name,
                "relationship_to_user": person.relationship_to_user,
                "employer": person.employer,
                "occupation": person.occupation,
                "email_addresses": person.email_addresses,
                "last_contact": person.last_contact,
                "important_dates": person.important_dates,
                "preferences": person.preferences,
                "notes": person.notes,
                "tags": person.tags,
            }

    return result


@router.post("/entities", status_code=201)
async def create_entity(
    body: EntityCreate,
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, str]:
    """Create a new entity (person, org, place, etc.)."""
    entity = EntityRecord(
        canonical_name=body.canonical_name,
        type=body.type,
        aliases=body.aliases,
        confidence=body.confidence,
    )
    await store.upsert_entity(entity)

    if body.type == "person":
        person = PersonRecord(entity_id=entity.id, full_name=body.canonical_name)
        await store.upsert_person(person)

    return {"id": entity.id, "canonical_name": entity.canonical_name}


@router.get("/people/birthdays")
async def upcoming_birthdays(
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """Return people with birthdays in the next 7 days."""
    people = await store.get_people_with_birthday_this_week()
    return {
        "people": [
            {
                "entity_id": p.entity_id,
                "full_name": p.full_name,
                "birthday": p.important_dates.get("birthday"),
                "relationship": p.relationship_to_user,
            }
            for p in people
        ]
    }


@router.get("/people/{entity_id}/facts")
async def get_person_facts(
    entity_id: str,
    fact_type: str | None = Query(default=None),
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """Retrieve all active facts about a person."""
    facts = await store.get_facts_for_entity(entity_id, fact_type=fact_type)
    return {
        "entity_id": entity_id,
        "facts": [
            {
                "id": f.id,
                "type": f.fact_type,
                "text": f.fact_text,
                "confidence": f.confidence,
                "timestamp": f.timestamp,
            }
            for f in facts
        ],
    }


@router.get("/people/{entity_id}/relationships")
async def get_person_relationships(
    entity_id: str,
    direction: str = Query(default="both", enum=["both", "outgoing", "incoming"]),
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """Retrieve relationships for an entity."""
    rels = await store.get_relationships_for_entity(entity_id, direction=direction)
    return {
        "entity_id": entity_id,
        "relationships": [
            {
                "id": r.id,
                "from": r.from_entity_id,
                "to": r.to_entity_id,
                "type": r.relationship_type,
                "label": r.relationship_label,
                "strength": r.strength,
            }
            for r in rels
        ],
    }
