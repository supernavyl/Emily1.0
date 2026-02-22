"""
Migration 001 — Knowledge Schema.

Creates data/knowledge.db with the entity, people, relationship, fact,
and event tables used by the personal knowledge OS.

Run:
    python scripts/migrations/001_knowledge_schema.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiosqlite

_DB_PATH = Path("data/knowledge.db")

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


async def run_migration() -> None:
    """Create knowledge.db and apply the schema."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    existed = _DB_PATH.exists()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(_SCHEMA)
        await db.commit()

    action = "already existed — schema applied" if existed else "created fresh"
    print(f"[001_knowledge_schema] {_DB_PATH} {action}")
    print("[001_knowledge_schema] Tables: entities, people, relationships, facts, events")


if __name__ == "__main__":
    asyncio.run(run_migration())
    sys.exit(0)
