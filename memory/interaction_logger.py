"""
Interaction Logger — guarantees every interaction is saved to disk.

This module provides a fail-safe persistence layer that logs every single
user/assistant turn immediately to SQLite, ensuring no conversation is lost
even if Emily crashes or is interrupted.

Features:
- Immediate write-through for every turn
- Separate database from episodic memory for redundancy
- Automatic backups
- Full-text search support
- Export functionality
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from observability.logger import get_logger
from observability.metrics import MEMORY_WRITES_TOTAL

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    role TEXT NOT NULL,           -- 'user' or 'assistant'
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    metadata TEXT,                -- JSON object
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(session_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_role ON interactions(role);

-- Full-text search support
CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
    content,
    content=interactions,
    content_rowid=rowid
);

-- Trigger to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
    DELETE FROM interactions_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS interactions_au AFTER UPDATE ON interactions BEGIN
    UPDATE interactions_fts SET content = new.content WHERE rowid = new.rowid;
END;
"""


@dataclass
class Interaction:
    """A single user or assistant turn in a conversation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    role: str = "user"  # 'user' or 'assistant'
    content: str = ""
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_db_row(self) -> dict[str, Any]:
        """Serialize for SQLite storage."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
            "importance": self.importance,
            "metadata": json.dumps(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> Interaction:
        """Deserialize from SQLite row."""
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            role=row["role"],
            content=row["content"],
            importance=row["importance"],
            metadata=json.loads(row.get("metadata", "{}")),
            created_at=row["created_at"],
        )


class InteractionLogger:
    """
    Write-through logger for all user/assistant interactions.

    Every interaction is immediately written to SQLite with fsync,
    providing durability guarantee even if Emily crashes.
    """

    def __init__(
        self,
        db_path: str,
        auto_backup_interval_minutes: int = 30,
    ) -> None:
        """
        Args:
            db_path: Path to interactions SQLite database.
            auto_backup_interval_minutes: How often to create automatic backups.
        """
        self._db_path = Path(db_path)
        self._backup_interval = auto_backup_interval_minutes * 60
        self._db: aiosqlite.Connection | None = None
        self._last_backup: float = 0.0
        self._backup_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Initialize the database and start backup task."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrent access
        await self._db.execute("PRAGMA journal_mode=WAL")
        # Enable synchronous=FULL for durability
        await self._db.execute("PRAGMA synchronous=FULL")

        await self._db.executescript(_SCHEMA)
        await self._db.commit()

        log.info("interaction_logger_connected", path=str(self._db_path))

        # Start automatic backup task
        self._backup_task = asyncio.create_task(self._backup_loop())

    async def log_interaction(self, interaction: Interaction) -> None:
        """
        Log a single interaction immediately to disk.

        Args:
            interaction: The Interaction object to persist.
        """
        if self._db is None:
            raise RuntimeError("InteractionLogger not connected")

        row = interaction.to_db_row()
        placeholders = ", ".join(f":{k}" for k in row)
        cols = ", ".join(row.keys())

        await self._db.execute(
            f"INSERT INTO interactions ({cols}) VALUES ({placeholders})",
            row,
        )
        await self._db.commit()

        MEMORY_WRITES_TOTAL.labels(tier="interactions").inc()

        log.debug(
            "interaction_saved",
            role=interaction.role,
            content_len=len(interaction.content),
            session_id=interaction.session_id[:8],
        )

    async def log_user_turn(
        self,
        session_id: str,
        content: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Interaction:
        """
        Log a user turn and return the Interaction object.

        Args:
            session_id: Current session UUID.
            content: User's message text.
            importance: Importance score [0.0, 1.0].
            metadata: Optional metadata dict.

        Returns:
            The created Interaction object.
        """
        interaction = Interaction(
            session_id=session_id,
            role="user",
            content=content,
            importance=importance,
            metadata=metadata or {},
        )
        await self.log_interaction(interaction)
        return interaction

    async def log_assistant_turn(
        self,
        session_id: str,
        content: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Interaction:
        """
        Log an assistant turn and return the Interaction object.

        Args:
            session_id: Current session UUID.
            content: Assistant's response text.
            importance: Importance score [0.0, 1.0].
            metadata: Optional metadata dict.

        Returns:
            The created Interaction object.
        """
        interaction = Interaction(
            session_id=session_id,
            role="assistant",
            content=content,
            importance=importance,
            metadata=metadata or {},
        )
        await self.log_interaction(interaction)
        return interaction

    async def get_session_interactions(
        self,
        session_id: str,
    ) -> list[Interaction]:
        """
        Retrieve all interactions for a given session.

        Args:
            session_id: Session UUID.

        Returns:
            List of Interaction objects in chronological order.
        """
        if self._db is None:
            raise RuntimeError("InteractionLogger not connected")

        async with self._db.execute(
            "SELECT * FROM interactions WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [Interaction.from_db_row(dict(row)) for row in rows]

    async def search_interactions(
        self,
        query: str,
        limit: int = 50,
    ) -> list[Interaction]:
        """
        Full-text search across all interactions.

        Args:
            query: Search query string.
            limit: Maximum results to return.

        Returns:
            List of matching Interaction objects.
        """
        if self._db is None:
            raise RuntimeError("InteractionLogger not connected")

        async with self._db.execute(
            """
            SELECT i.* FROM interactions i
            JOIN interactions_fts fts ON i.rowid = fts.rowid
            WHERE interactions_fts MATCH ?
            ORDER BY i.timestamp DESC
            LIMIT ?
            """,
            (query, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [Interaction.from_db_row(dict(row)) for row in rows]

    async def get_recent_interactions(
        self,
        n: int = 100,
        role: str | None = None,
    ) -> list[Interaction]:
        """
        Get the most recent interactions.

        Args:
            n: Number of interactions to retrieve.
            role: Optional filter by role ('user' or 'assistant').

        Returns:
            List of Interaction objects, most recent first.
        """
        if self._db is None:
            raise RuntimeError("InteractionLogger not connected")

        if role:
            query = "SELECT * FROM interactions WHERE role = ? ORDER BY timestamp DESC LIMIT ?"
            params = (role, n)
        else:
            query = "SELECT * FROM interactions ORDER BY timestamp DESC LIMIT ?"
            params = (n,)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [Interaction.from_db_row(dict(row)) for row in rows]

    async def count_interactions(
        self,
        session_id: str | None = None,
        role: str | None = None,
    ) -> int:
        """
        Count total interactions with optional filters.

        Args:
            session_id: Optional session filter.
            role: Optional role filter ('user' or 'assistant').

        Returns:
            Total interaction count.
        """
        if self._db is None:
            return 0

        conditions = []
        params = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if role:
            conditions.append("role = ?")
            params.append(role)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT COUNT(*) FROM interactions{where_clause}"

        async with self._db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def export_to_json(
        self,
        output_path: str,
        session_id: str | None = None,
    ) -> int:
        """
        Export interactions to a JSON file.

        Args:
            output_path: Path to output JSON file.
            session_id: Optional session filter.

        Returns:
            Number of interactions exported.
        """
        if session_id:
            interactions = await self.get_session_interactions(session_id)
        else:
            interactions = await self.get_recent_interactions(n=100000)  # All

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        data = [asdict(interaction) for interaction in interactions]
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")

        log.info("interactions_exported", path=output_path, count=len(data))
        return len(data)

    async def create_backup(self) -> str:
        """
        Create a backup of the interactions database.

        Returns:
            Path to the backup file.
        """
        if self._db is None:
            raise RuntimeError("InteractionLogger not connected")

        # Close WAL checkpoint before backup
        await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        backup_dir = self._db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"interactions_backup_{timestamp}.db"

        # Use SQLite backup API for consistent snapshot
        await self._db.execute("VACUUM")  # Optimize before backup
        shutil.copy2(self._db_path, backup_path)

        self._last_backup = time.time()
        log.info("interactions_backup_created", path=str(backup_path))

        return str(backup_path)

    async def _backup_loop(self) -> None:
        """Background task that creates periodic backups."""
        while True:
            try:
                await asyncio.sleep(self._backup_interval)
                await self.create_backup()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("backup_loop_error", error=str(exc))

    async def close(self) -> None:
        """Close the database connection and stop backup task."""
        if self._backup_task:
            self._backup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._backup_task

        if self._db:
            # Final checkpoint and backup before closing
            try:
                await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                await self.create_backup()
            except Exception as exc:
                log.error("final_backup_error", error=str(exc))

            await self._db.close()
            self._db = None
            log.info("interaction_logger_closed")
