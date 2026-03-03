"""
Dataclass models for the personal knowledge store.

These are plain Python dataclasses with JSON-serialisable fields that map
directly to the SQLite tables in data/knowledge.db.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


@dataclass
class EntityRecord:
    """A node in the knowledge graph (person, org, place, event, etc.)."""

    id: str = field(default_factory=_uuid)
    type: str = "person"  # person|org|place|event|object|concept
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    confidence: float = 1.0
    source_ids: list[str] = field(default_factory=list)

    def to_db_row(self) -> dict[str, Any]:
        """Serialize to SQLite-compatible dict."""
        return {
            "id": self.id,
            "type": self.type,
            "canonical_name": self.canonical_name,
            "aliases": json.dumps(self.aliases),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confidence": self.confidence,
            "source_ids": json.dumps(self.source_ids),
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> EntityRecord:
        """Deserialize from SQLite row dict."""
        return cls(
            id=row["id"],
            type=row["type"],
            canonical_name=row["canonical_name"],
            aliases=json.loads(row.get("aliases", "[]")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confidence=row["confidence"],
            source_ids=json.loads(row.get("source_ids", "[]")),
        )


# ---------------------------------------------------------------------------
# Person (extends Entity)
# ---------------------------------------------------------------------------


@dataclass
class PersonRecord:
    """Detailed profile for a person entity."""

    entity_id: str = ""
    full_name: str = ""
    nicknames: list[str] = field(default_factory=list)
    date_of_birth: str | None = None
    relationship_to_user: str | None = None
    relationship_strength: float = 0.5
    first_met: str | None = None
    first_met_context: str | None = None
    occupation: str | None = None
    employer: str | None = None
    email_addresses: list[str] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)
    physical_description: str | None = None
    personality_notes: str | None = None
    communication_style: str | None = None
    last_contact: str | None = None
    contact_frequency: str | None = None
    important_dates: dict[str, str] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    dislikes: dict[str, Any] = field(default_factory=dict)
    goals: str | None = None
    current_projects: list[str] = field(default_factory=list)
    social_profiles: dict[str, str] = field(default_factory=dict)
    home_location: str | None = None
    work_location: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_db_row(self) -> dict[str, Any]:
        """Serialize to SQLite-compatible dict."""
        return {
            "entity_id": self.entity_id,
            "full_name": self.full_name,
            "nicknames": json.dumps(self.nicknames),
            "date_of_birth": self.date_of_birth,
            "relationship_to_user": self.relationship_to_user,
            "relationship_strength": self.relationship_strength,
            "first_met": self.first_met,
            "first_met_context": self.first_met_context,
            "occupation": self.occupation,
            "employer": self.employer,
            "email_addresses": json.dumps(self.email_addresses),
            "phone_numbers": json.dumps(self.phone_numbers),
            "physical_description": self.physical_description,
            "personality_notes": self.personality_notes,
            "communication_style": self.communication_style,
            "last_contact": self.last_contact,
            "contact_frequency": self.contact_frequency,
            "important_dates": json.dumps(self.important_dates),
            "preferences": json.dumps(self.preferences),
            "dislikes": json.dumps(self.dislikes),
            "goals": self.goals,
            "current_projects": json.dumps(self.current_projects),
            "social_profiles": json.dumps(self.social_profiles),
            "home_location": self.home_location,
            "work_location": self.work_location,
            "notes": self.notes,
            "tags": json.dumps(self.tags),
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> PersonRecord:
        """Deserialize from SQLite row dict."""
        return cls(
            entity_id=row["entity_id"],
            full_name=row["full_name"],
            nicknames=json.loads(row.get("nicknames", "[]")),
            date_of_birth=row.get("date_of_birth"),
            relationship_to_user=row.get("relationship_to_user"),
            relationship_strength=row.get("relationship_strength", 0.5),
            first_met=row.get("first_met"),
            first_met_context=row.get("first_met_context"),
            occupation=row.get("occupation"),
            employer=row.get("employer"),
            email_addresses=json.loads(row.get("email_addresses", "[]")),
            phone_numbers=json.loads(row.get("phone_numbers", "[]")),
            physical_description=row.get("physical_description"),
            personality_notes=row.get("personality_notes"),
            communication_style=row.get("communication_style"),
            last_contact=row.get("last_contact"),
            contact_frequency=row.get("contact_frequency"),
            important_dates=json.loads(row.get("important_dates", "{}")),
            preferences=json.loads(row.get("preferences", "{}")),
            dislikes=json.loads(row.get("dislikes", "{}")),
            goals=row.get("goals"),
            current_projects=json.loads(row.get("current_projects", "[]")),
            social_profiles=json.loads(row.get("social_profiles", "{}")),
            home_location=row.get("home_location"),
            work_location=row.get("work_location"),
            notes=row.get("notes"),
            tags=json.loads(row.get("tags", "[]")),
        )


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------


@dataclass
class RelationshipRecord:
    """A typed edge between two entities."""

    id: str = field(default_factory=_uuid)
    from_entity_id: str = ""
    to_entity_id: str = ""
    relationship_type: str = ""
    relationship_label: str | None = None
    strength: float = 0.5
    since: str | None = None
    notes: str | None = None
    source_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_db_row(self) -> dict[str, Any]:
        """Serialize to SQLite-compatible dict."""
        return {
            "id": self.id,
            "from_entity_id": self.from_entity_id,
            "to_entity_id": self.to_entity_id,
            "relationship_type": self.relationship_type,
            "relationship_label": self.relationship_label,
            "strength": self.strength,
            "since": self.since,
            "notes": self.notes,
            "source_ids": json.dumps(self.source_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> RelationshipRecord:
        """Deserialize from SQLite row dict."""
        return cls(
            id=row["id"],
            from_entity_id=row["from_entity_id"],
            to_entity_id=row["to_entity_id"],
            relationship_type=row["relationship_type"],
            relationship_label=row.get("relationship_label"),
            strength=row.get("strength", 0.5),
            since=row.get("since"),
            notes=row.get("notes"),
            source_ids=json.loads(row.get("source_ids", "[]")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ---------------------------------------------------------------------------
# Fact
# ---------------------------------------------------------------------------


@dataclass
class FactRecord:
    """An atomic factual statement about an entity."""

    id: str = field(default_factory=_uuid)
    entity_id: str = ""
    fact_type: str = ""  # preference|belief|habit|skill|history|etc
    fact_text: str = ""
    confidence: float = 1.0
    contradicts_fact_id: str | None = None
    source_id: str | None = None
    timestamp: str = field(default_factory=_now_iso)
    is_superseded: bool = False

    def to_db_row(self) -> dict[str, Any]:
        """Serialize to SQLite-compatible dict."""
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "fact_type": self.fact_type,
            "fact_text": self.fact_text,
            "confidence": self.confidence,
            "contradicts_fact_id": self.contradicts_fact_id,
            "source_id": self.source_id,
            "timestamp": self.timestamp,
            "is_superseded": 1 if self.is_superseded else 0,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> FactRecord:
        """Deserialize from SQLite row dict."""
        return cls(
            id=row["id"],
            entity_id=row["entity_id"],
            fact_type=row["fact_type"],
            fact_text=row["fact_text"],
            confidence=row["confidence"],
            contradicts_fact_id=row.get("contradicts_fact_id"),
            source_id=row.get("source_id"),
            timestamp=row["timestamp"],
            is_superseded=bool(row.get("is_superseded", 0)),
        )


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


@dataclass
class EventRecord:
    """A time-anchored occurrence involving one or more entities."""

    id: str = field(default_factory=_uuid)
    title: str = ""
    event_type: str = ""  # meeting|call|birthday|deadline|etc
    datetime: str = ""  # ISO8601
    duration_minutes: int | None = None
    location: str | None = None
    participant_ids: list[str] = field(default_factory=list)
    description: str | None = None
    outcome: str | None = None
    action_items: list[str] = field(default_factory=list)
    follow_up_date: str | None = None
    source_id: str | None = None
    created_at: str = field(default_factory=_now_iso)

    def to_db_row(self) -> dict[str, Any]:
        """Serialize to SQLite-compatible dict."""
        return {
            "id": self.id,
            "title": self.title,
            "event_type": self.event_type,
            "datetime": self.datetime,
            "duration_minutes": self.duration_minutes,
            "location": self.location,
            "participant_ids": json.dumps(self.participant_ids),
            "description": self.description,
            "outcome": self.outcome,
            "action_items": json.dumps(self.action_items),
            "follow_up_date": self.follow_up_date,
            "source_id": self.source_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> EventRecord:
        """Deserialize from SQLite row dict."""
        return cls(
            id=row["id"],
            title=row["title"],
            event_type=row["event_type"],
            datetime=row["datetime"],
            duration_minutes=row.get("duration_minutes"),
            location=row.get("location"),
            participant_ids=json.loads(row.get("participant_ids", "[]")),
            description=row.get("description"),
            outcome=row.get("outcome"),
            action_items=json.loads(row.get("action_items", "[]")),
            follow_up_date=row.get("follow_up_date"),
            source_id=row.get("source_id"),
            created_at=row["created_at"],
        )
