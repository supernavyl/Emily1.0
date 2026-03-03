"""
Tier 4: Personal Knowledge Store — entity/people/relationship/fact/event CRUD.

All operations are async via aiosqlite against data/knowledge.db.
Run scripts/migrations/001_knowledge_schema.py to initialise the database
before using this store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from memory.knowledge_models import (
    EntityRecord,
    EventRecord,
    FactRecord,
    PersonRecord,
    RelationshipRecord,
)
from observability.logger import get_logger

log = get_logger(__name__)

_DEFAULT_DB = "data/knowledge.db"

# DDL is mirrored from scripts/migrations/001_knowledge_schema.py.
# connect() runs it with CREATE IF NOT EXISTS so the store is self-bootstrapping.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('person','org','place','event','object','concept')),
    canonical_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
    source_ids TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_name);

CREATE TABLE IF NOT EXISTS people (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    nicknames TEXT NOT NULL DEFAULT '[]',
    date_of_birth TEXT,
    relationship_to_user TEXT,
    relationship_strength REAL DEFAULT 0.5 CHECK(relationship_strength >= 0 AND relationship_strength <= 1),
    first_met TEXT,
    first_met_context TEXT,
    occupation TEXT,
    employer TEXT,
    email_addresses TEXT NOT NULL DEFAULT '[]',
    phone_numbers TEXT NOT NULL DEFAULT '[]',
    physical_description TEXT,
    personality_notes TEXT,
    communication_style TEXT,
    last_contact TEXT,
    contact_frequency TEXT,
    important_dates TEXT NOT NULL DEFAULT '{}',
    preferences TEXT NOT NULL DEFAULT '{}',
    dislikes TEXT NOT NULL DEFAULT '{}',
    goals TEXT,
    current_projects TEXT NOT NULL DEFAULT '[]',
    social_profiles TEXT NOT NULL DEFAULT '{}',
    home_location TEXT,
    work_location TEXT,
    notes TEXT,
    tags TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    relationship_label TEXT,
    strength REAL DEFAULT 0.5 CHECK(strength >= 0 AND strength <= 1),
    since TEXT,
    notes TEXT,
    source_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    fact_type TEXT NOT NULL,
    fact_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
    contradicts_fact_id TEXT REFERENCES facts(id),
    source_id TEXT,
    timestamp TEXT NOT NULL,
    is_superseded INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity_id);
CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_facts_active ON facts(entity_id, is_superseded);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    datetime TEXT NOT NULL,
    duration_minutes INTEGER,
    location TEXT,
    participant_ids TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    outcome TEXT,
    action_items TEXT NOT NULL DEFAULT '[]',
    follow_up_date TEXT,
    source_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_datetime ON events(datetime);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class KnowledgeStore:
    """
    Async SQLite-backed store for entities, people, relationships, facts and events.

    Must be used as an async context manager or call connect()/close() manually.
    Foreign keys are enforced; WAL mode is enabled for concurrent read access.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        """
        Args:
            db_path: Path to the SQLite knowledge database.
        """
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the database connection, apply schema, and enable WAL + foreign keys."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        log.info("knowledge_store_connected", path=self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> KnowledgeStore:
        """Support async context manager usage."""
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Close on context manager exit."""
        await self.close()

    def _require_db(self) -> aiosqlite.Connection:
        """Return the active connection or raise RuntimeError."""
        if self._db is None:
            raise RuntimeError("KnowledgeStore not connected — call connect() first")
        return self._db

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    async def upsert_entity(self, entity: EntityRecord) -> None:
        """
        Insert or replace an entity record.

        Args:
            entity: The EntityRecord to persist.
        """
        db = self._require_db()
        row = entity.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(f"INSERT OR REPLACE INTO entities ({cols}) VALUES ({placeholders})", row)
        await db.commit()
        log.debug("entity_upserted", entity_id=entity.id, name=entity.canonical_name)

    async def get_entity(self, entity_id: str) -> EntityRecord | None:
        """
        Retrieve an entity by primary key.

        Args:
            entity_id: UUID of the entity.

        Returns:
            EntityRecord if found, else None.
        """
        db = self._require_db()
        async with db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)) as cur:
            row = await cur.fetchone()
            return EntityRecord.from_db_row(dict(row)) if row else None

    async def find_entities(
        self,
        name_fragment: str,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[EntityRecord]:
        """
        Search entities by canonical name (case-insensitive substring match).

        Args:
            name_fragment: Substring to search for in canonical_name or aliases.
            entity_type: Optional filter by entity type.
            limit: Maximum number of results.

        Returns:
            List of matching EntityRecords.
        """
        db = self._require_db()
        pattern = f"%{name_fragment}%"
        if entity_type:
            query = (
                "SELECT * FROM entities WHERE type = ? AND "
                "(canonical_name LIKE ? OR aliases LIKE ?) LIMIT ?"
            )
            args = (entity_type, pattern, pattern, limit)
        else:
            query = "SELECT * FROM entities WHERE canonical_name LIKE ? OR aliases LIKE ? LIMIT ?"
            args = (pattern, pattern, limit)

        async with db.execute(query, args) as cur:
            rows = await cur.fetchall()
            return [EntityRecord.from_db_row(dict(r)) for r in rows]

    async def delete_entity(self, entity_id: str) -> None:
        """
        Delete an entity and cascade to people, relationships, and facts.

        Args:
            entity_id: UUID of the entity to delete.
        """
        db = self._require_db()
        await db.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        await db.commit()
        log.info("entity_deleted", entity_id=entity_id)

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    async def upsert_person(self, person: PersonRecord) -> None:
        """
        Insert or replace a person profile.

        Args:
            person: The PersonRecord to persist (entity must already exist).
        """
        db = self._require_db()
        row = person.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(f"INSERT OR REPLACE INTO people ({cols}) VALUES ({placeholders})", row)
        await db.commit()
        log.debug("person_upserted", entity_id=person.entity_id, name=person.full_name)

    async def get_person(self, entity_id: str) -> PersonRecord | None:
        """
        Retrieve a person profile by entity_id.

        Args:
            entity_id: UUID of the entity.

        Returns:
            PersonRecord if found, else None.
        """
        db = self._require_db()
        async with db.execute("SELECT * FROM people WHERE entity_id = ?", (entity_id,)) as cur:
            row = await cur.fetchone()
            return PersonRecord.from_db_row(dict(row)) if row else None

    async def search_people(
        self,
        name_fragment: str = "",
        employer: str | None = None,
        relationship_to_user: str | None = None,
        limit: int = 20,
    ) -> list[PersonRecord]:
        """
        Search person profiles with optional filters.

        Args:
            name_fragment: Substring match on full_name.
            employer: Exact match on employer.
            relationship_to_user: Exact match on relationship type.
            limit: Maximum number of results.

        Returns:
            List of matching PersonRecords.
        """
        db = self._require_db()
        clauses = []
        args: list[Any] = []

        if name_fragment:
            clauses.append("full_name LIKE ?")
            args.append(f"%{name_fragment}%")
        if employer:
            clauses.append("employer = ?")
            args.append(employer)
        if relationship_to_user:
            clauses.append("relationship_to_user = ?")
            args.append(relationship_to_user)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(limit)
        async with db.execute(f"SELECT * FROM people {where} LIMIT ?", args) as cur:
            rows = await cur.fetchall()
            return [PersonRecord.from_db_row(dict(r)) for r in rows]

    async def get_people_with_birthday_this_week(self) -> list[PersonRecord]:
        """
        Return people whose birthday (MM-DD) falls within the next 7 days.

        Returns:
            List of PersonRecords with upcoming birthdays.
        """
        from datetime import date, timedelta

        db = self._require_db()
        today = date.today()
        upcoming = [(today + timedelta(days=i)).strftime("%m-%d") for i in range(7)]

        # important_dates is JSON: {"birthday": "MM-DD", ...}
        async with db.execute("SELECT * FROM people WHERE important_dates != '{}'") as cur:
            rows = await cur.fetchall()

        results = []
        import json

        for row in rows:
            dates = json.loads(row["important_dates"])
            bday = dates.get("birthday")
            if bday and bday in upcoming:
                results.append(PersonRecord.from_db_row(dict(row)))
        return results

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    async def upsert_relationship(self, rel: RelationshipRecord) -> None:
        """
        Insert or replace a relationship edge.

        Args:
            rel: The RelationshipRecord to persist.
        """
        db = self._require_db()
        row = rel.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(
            f"INSERT OR REPLACE INTO relationships ({cols}) VALUES ({placeholders})", row
        )
        await db.commit()
        log.debug(
            "relationship_upserted",
            rel_id=rel.id,
            rel_type=rel.relationship_type,
        )

    async def get_relationships_for_entity(
        self, entity_id: str, direction: str = "both"
    ) -> list[RelationshipRecord]:
        """
        Get all relationships involving the given entity.

        Args:
            entity_id: UUID of the entity.
            direction: "outgoing", "incoming", or "both".

        Returns:
            List of RelationshipRecords.
        """
        db = self._require_db()
        if direction == "outgoing":
            query = "SELECT * FROM relationships WHERE from_entity_id = ?"
        elif direction == "incoming":
            query = "SELECT * FROM relationships WHERE to_entity_id = ?"
        else:
            query = "SELECT * FROM relationships WHERE from_entity_id = ? OR to_entity_id = ?"
            async with db.execute(query, (entity_id, entity_id)) as cur:
                rows = await cur.fetchall()
                return [RelationshipRecord.from_db_row(dict(r)) for r in rows]

        async with db.execute(query, (entity_id,)) as cur:
            rows = await cur.fetchall()
            return [RelationshipRecord.from_db_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    async def add_fact(self, fact: FactRecord) -> None:
        """
        Insert a new fact. Raises ValueError if confidence < 0.4.

        Per system rules, facts with confidence below 0.4 must not be
        committed without explicit user confirmation.

        Args:
            fact: The FactRecord to store.

        Raises:
            ValueError: If confidence is below the minimum threshold.
        """
        if fact.confidence < 0.4:
            raise ValueError(
                f"Fact confidence {fact.confidence:.2f} is below 0.4 — "
                "confirm with user before storing."
            )
        db = self._require_db()
        row = fact.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(f"INSERT OR REPLACE INTO facts ({cols}) VALUES ({placeholders})", row)
        await db.commit()
        log.debug("fact_added", fact_id=fact.id, entity_id=fact.entity_id)

    async def get_facts_for_entity(
        self,
        entity_id: str,
        fact_type: str | None = None,
        include_superseded: bool = False,
    ) -> list[FactRecord]:
        """
        Retrieve facts about an entity.

        Args:
            entity_id: UUID of the entity.
            fact_type: Optional filter by fact type.
            include_superseded: If False (default), skip superseded facts.

        Returns:
            List of FactRecords.
        """
        db = self._require_db()
        clauses = ["entity_id = ?"]
        args: list[Any] = [entity_id]

        if not include_superseded:
            clauses.append("is_superseded = 0")
        if fact_type:
            clauses.append("fact_type = ?")
            args.append(fact_type)

        where = " AND ".join(clauses)
        async with db.execute(
            f"SELECT * FROM facts WHERE {where} ORDER BY timestamp DESC", args
        ) as cur:
            rows = await cur.fetchall()
            return [FactRecord.from_db_row(dict(r)) for r in rows]

    async def supersede_fact(self, old_fact_id: str, new_fact: FactRecord) -> None:
        """
        Mark an existing fact as superseded and insert the replacement.

        Args:
            old_fact_id: ID of the fact being replaced.
            new_fact: The new FactRecord (should reference old_fact_id via contradicts_fact_id).
        """
        db = self._require_db()
        await db.execute("UPDATE facts SET is_superseded = 1 WHERE id = ?", (old_fact_id,))
        new_fact.contradicts_fact_id = old_fact_id
        row = new_fact.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(f"INSERT INTO facts ({cols}) VALUES ({placeholders})", row)
        await db.commit()
        log.info("fact_superseded", old_id=old_fact_id, new_id=new_fact.id)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def upsert_event(self, event: EventRecord) -> None:
        """
        Insert or replace an event record.

        Args:
            event: The EventRecord to persist.
        """
        db = self._require_db()
        row = event.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(f"INSERT OR REPLACE INTO events ({cols}) VALUES ({placeholders})", row)
        await db.commit()
        log.debug("event_upserted", event_id=event.id, title=event.title)

    async def get_events_for_entity(self, entity_id: str, limit: int = 20) -> list[EventRecord]:
        """
        Return events where the given entity appears in participant_ids.

        Args:
            entity_id: UUID of the entity.
            limit: Maximum number of events.

        Returns:
            List of EventRecords, most recent first.
        """
        db = self._require_db()
        async with db.execute(
            "SELECT * FROM events WHERE participant_ids LIKE ? ORDER BY datetime DESC LIMIT ?",
            (f"%{entity_id}%", limit),
        ) as cur:
            rows = await cur.fetchall()
            return [EventRecord.from_db_row(dict(r)) for r in rows]

    async def get_upcoming_events(self, limit: int = 10) -> list[EventRecord]:
        """
        Return future events ordered by datetime ascending.

        Args:
            limit: Maximum number of events.

        Returns:
            List of upcoming EventRecords.
        """
        db = self._require_db()
        now = _now_iso()
        async with db.execute(
            "SELECT * FROM events WHERE datetime > ? ORDER BY datetime ASC LIMIT ?",
            (now, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [EventRecord.from_db_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def counts(self) -> dict[str, int]:
        """
        Return record counts for each table.

        Returns:
            Dict mapping table name to row count.
        """
        db = self._require_db()
        result: dict[str, int] = {}
        for table in ("entities", "people", "relationships", "facts", "events"):
            async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:  # noqa: S608
                row = await cur.fetchone()
                result[table] = row[0] if row else 0
        return result
