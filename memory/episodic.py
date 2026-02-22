"""
Tier 3: Episodic Memory — session-level memory with SQLite persistence.

Every conversation session produces a structured episode record containing:
- Full transcript reference
- LLM-generated summary
- Key decisions, action items, topics
- Emotional tone trajectory
- Embedding ID for semantic search

Episodes are stored in SQLite (`data/episodes.db`) and embedded in Qdrant
for cross-session semantic retrieval.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from config import EpisodicMemoryConfig
from observability.logger import get_logger
from observability.metrics import MEMORY_READS_TOTAL, MEMORY_WRITES_TOTAL

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    duration_seconds REAL NOT NULL,
    topics TEXT NOT NULL,           -- JSON array
    emotional_tone TEXT NOT NULL,
    key_decisions TEXT NOT NULL,    -- JSON array
    action_items TEXT NOT NULL,     -- JSON array
    summary TEXT NOT NULL,
    full_transcript_path TEXT,
    embedding_id TEXT,
    metadata TEXT NOT NULL,         -- JSON object
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp);
CREATE INDEX IF NOT EXISTS idx_episodes_topics ON episodes(topics);
"""


@dataclass
class Episode:
    """A structured record of a single conversation session."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    duration_seconds: float = 0.0
    topics: list[str] = field(default_factory=list)
    emotional_tone: str = "neutral"
    key_decisions: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    summary: str = ""
    full_transcript_path: str | None = None
    embedding_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_db_row(self) -> dict[str, Any]:
        """Serialize for SQLite storage."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "topics": json.dumps(self.topics),
            "emotional_tone": self.emotional_tone,
            "key_decisions": json.dumps(self.key_decisions),
            "action_items": json.dumps(self.action_items),
            "summary": self.summary,
            "full_transcript_path": self.full_transcript_path,
            "embedding_id": self.embedding_id,
            "metadata": json.dumps(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Episode":
        """Deserialize from SQLite row."""
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            duration_seconds=row["duration_seconds"],
            topics=json.loads(row["topics"]),
            emotional_tone=row["emotional_tone"],
            key_decisions=json.loads(row["key_decisions"]),
            action_items=json.loads(row["action_items"]),
            summary=row["summary"],
            full_transcript_path=row.get("full_transcript_path"),
            embedding_id=row.get("embedding_id"),
            metadata=json.loads(row.get("metadata", "{}")),
            created_at=row["created_at"],
        )


class EpisodicMemory:
    """
    SQLite-backed episodic memory store.

    All database operations are async via aiosqlite.
    """

    def __init__(self, config: EpisodicMemoryConfig) -> None:
        """
        Args:
            config: Episodic memory configuration.
        """
        self._config = config
        self._db_path = config.db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the SQLite database and create the schema if needed."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        log.info("episodic_memory_connected", path=self._db_path)

    async def save_episode(self, episode: Episode) -> None:
        """
        Persist an episode to SQLite.

        Args:
            episode: The Episode to store.
        """
        if self._db is None:
            raise RuntimeError("EpisodicMemory not connected")

        row = episode.to_db_row()
        placeholders = ", ".join(f":{k}" for k in row)
        cols = ", ".join(row.keys())
        await self._db.execute(
            f"INSERT OR REPLACE INTO episodes ({cols}) VALUES ({placeholders})",
            row,
        )
        await self._db.commit()
        MEMORY_WRITES_TOTAL.labels(tier="episodic").inc()
        log.info(
            "episode_saved",
            episode_id=episode.id,
            topics=episode.topics,
            duration_s=f"{episode.duration_seconds:.0f}",
        )

    async def get_episode(self, episode_id: str) -> Episode | None:
        """
        Retrieve an episode by ID.

        Args:
            episode_id: The episode's UUID.

        Returns:
            Episode if found, else None.
        """
        if self._db is None:
            raise RuntimeError("EpisodicMemory not connected")

        async with self._db.execute(
            "SELECT * FROM episodes WHERE id = ?", (episode_id,)
        ) as cursor:
            row = await cursor.fetchone()
            MEMORY_READS_TOTAL.labels(tier="episodic").inc()
            if row:
                return Episode.from_db_row(dict(row))
            return None

    async def get_recent_episodes(self, n: int = 10) -> list[Episode]:
        """
        Retrieve the N most recent episodes.

        Args:
            n: Number of episodes to return.

        Returns:
            List of Episode objects, most recent first.
        """
        if self._db is None:
            raise RuntimeError("EpisodicMemory not connected")

        async with self._db.execute(
            "SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?", (n,)
        ) as cursor:
            rows = await cursor.fetchall()
            MEMORY_READS_TOTAL.labels(tier="episodic").inc()
            return [Episode.from_db_row(dict(row)) for row in rows]

    async def search_by_topic(self, topic: str, limit: int = 10) -> list[Episode]:
        """
        Find episodes containing the given topic keyword.

        Args:
            topic: Topic keyword to search for.
            limit: Maximum results.

        Returns:
            List of matching Episodes.
        """
        if self._db is None:
            raise RuntimeError("EpisodicMemory not connected")

        async with self._db.execute(
            "SELECT * FROM episodes WHERE topics LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{topic}%", limit),
        ) as cursor:
            rows = await cursor.fetchall()
            MEMORY_READS_TOTAL.labels(tier="episodic").inc()
            return [Episode.from_db_row(dict(row)) for row in rows]

    async def save_transcript(self, session_id: str, transcript: str) -> str:
        """
        Save a full conversation transcript to disk and return the file path.

        Args:
            session_id: Session UUID.
            transcript: The full conversation text.

        Returns:
            Path to the saved transcript file.
        """
        transcripts_dir = Path("data/transcripts")
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        path = transcripts_dir / f"{session_id}.txt"
        path.write_text(transcript, encoding="utf-8")
        return str(path)

    async def count(self) -> int:
        """Return the total number of stored episodes."""
        if self._db is None:
            return 0
        async with self._db.execute("SELECT COUNT(*) FROM episodes") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
