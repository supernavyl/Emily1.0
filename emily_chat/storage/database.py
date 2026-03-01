"""Async SQLite database with FTS5 full-text search for Emily Chat.

All conversation and message persistence goes through this module.
Zero raw SQL elsewhere in the codebase.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from emily_chat.storage.models import ConversationSummary, Message, SearchResult

_DB_DIR = Path.home() / ".emily-chat"
_DB_PATH = _DB_DIR / "conversations.db"
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _utcnow() -> str:
    """ISO-8601 timestamp in UTC."""
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


class ConversationDatabase:
    """Async conversation store backed by SQLite + FTS5.

    Usage::

        db = ConversationDatabase()
        await db.init()
        # … use db …
        await db.close()
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._path = str(db_path) if db_path else str(_DB_PATH)
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Open the database and apply pending migrations."""
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._migrate()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Return the active connection, raising if not initialised."""
        if self._conn is None:
            raise RuntimeError("Database not initialised — call init() first")
        return self._conn

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    async def _migrate(self) -> None:
        """Run any migration scripts not yet applied."""
        await self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        cursor = await self.conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
        row = await cursor.fetchone()
        current = row[0] if row else 0

        for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = int(sql_file.stem.split("_")[0])
            if version <= current:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            await self.conn.executescript(sql)
            await self.conn.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)",
                (version, _utcnow()),
            )
            await self.conn.commit()

    # ------------------------------------------------------------------
    # Conversations — CRUD
    # ------------------------------------------------------------------

    async def create_conversation(
        self,
        title: str = "New conversation",
        *,
        model: str | None = None,
        provider: str | None = None,
        skill_id: str | None = None,
    ) -> ConversationSummary:
        """Insert a new conversation and return its summary."""
        cid = _new_id()
        now = _utcnow()
        await self.conn.execute(
            "INSERT INTO conversations "
            "(id, title, created_at, updated_at, model, provider, skill_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, title, now, now, model, provider, skill_id),
        )
        await self.conn.commit()
        return ConversationSummary(
            id=cid,
            title=title,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
            model=model,
            provider=provider,
            skill_id=skill_id,
        )

    async def get_conversation(self, conversation_id: str) -> ConversationSummary | None:
        """Return a single conversation summary or None."""
        cursor = await self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_summary(row)

    async def get_all_conversations(
        self, *, include_archived: bool = False
    ) -> list[ConversationSummary]:
        """Return all conversations ordered by updated_at descending."""
        if include_archived:
            sql = "SELECT * FROM conversations ORDER BY pinned DESC, updated_at DESC"
            cursor = await self.conn.execute(sql)
        else:
            sql = (
                "SELECT * FROM conversations WHERE archived = 0 "
                "ORDER BY pinned DESC, updated_at DESC"
            )
            cursor = await self.conn.execute(sql)
        rows = await cursor.fetchall()
        return [_row_to_summary(r) for r in rows]

    async def rename_conversation(self, conversation_id: str, title: str) -> None:
        """Update a conversation's title."""
        await self.conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _utcnow(), conversation_id),
        )
        await self.conn.commit()

    async def pin_conversation(self, conversation_id: str, pinned: bool = True) -> None:
        """Pin or unpin a conversation."""
        await self.conn.execute(
            "UPDATE conversations SET pinned = ?, updated_at = ? WHERE id = ?",
            (int(pinned), _utcnow(), conversation_id),
        )
        await self.conn.commit()

    async def archive_conversation(self, conversation_id: str, archived: bool = True) -> None:
        """Archive or unarchive a conversation."""
        await self.conn.execute(
            "UPDATE conversations SET archived = ?, updated_at = ? WHERE id = ?",
            (int(archived), _utcnow(), conversation_id),
        )
        await self.conn.commit()

    async def delete_conversation(self, conversation_id: str) -> None:
        """Permanently delete a conversation and its messages."""
        await self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        await self.conn.commit()

    async def duplicate_conversation(self, conversation_id: str) -> ConversationSummary | None:
        """Clone a conversation and all its messages, returning the new summary."""
        src = await self.get_conversation(conversation_id)
        if src is None:
            return None

        new_conv = await self.create_conversation(
            title=f"{src.title} (copy)",
            model=src.model,
            provider=src.provider,
            skill_id=src.skill_id,
        )

        cursor = await self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            new_mid = _new_id()
            await self.conn.execute(
                "INSERT INTO messages "
                "(id, conversation_id, role, content, content_raw, thinking_content, "
                "model, provider, tokens_in, tokens_out, tokens_thinking, cost_usd, "
                "latency_ms, first_token_ms, created_at, edited, stopped, rating, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_mid,
                    new_conv.id,
                    row["role"],
                    row["content"],
                    row["content_raw"],
                    row["thinking_content"],
                    row["model"],
                    row["provider"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["tokens_thinking"],
                    row["cost_usd"],
                    row["latency_ms"],
                    row["first_token_ms"],
                    row["created_at"],
                    row["edited"],
                    row["stopped"],
                    row["rating"],
                    row["version"],
                ),
            )

        # Sync aggregate counters
        await self._recount_conversation(new_conv.id)
        await self.conn.commit()
        return await self.get_conversation(new_conv.id)

    async def fork_conversation(
        self, conversation_id: str, from_message_id: str
    ) -> ConversationSummary | None:
        """Create a branch: copy messages up to (and including) *from_message_id*."""
        src = await self.get_conversation(conversation_id)
        if src is None:
            return None

        new_conv = await self.create_conversation(
            title=f"{src.title} (fork)",
            model=src.model,
            provider=src.provider,
            skill_id=src.skill_id,
        )
        await self.conn.execute(
            "UPDATE conversations SET parent_id = ?, branch_from_message_id = ? WHERE id = ?",
            (conversation_id, from_message_id, new_conv.id),
        )

        cursor = await self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            new_mid = _new_id()
            await self.conn.execute(
                "INSERT INTO messages "
                "(id, conversation_id, role, content, content_raw, thinking_content, "
                "model, provider, tokens_in, tokens_out, tokens_thinking, cost_usd, "
                "latency_ms, first_token_ms, created_at, edited, stopped, rating, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_mid,
                    new_conv.id,
                    row["role"],
                    row["content"],
                    row["content_raw"],
                    row["thinking_content"],
                    row["model"],
                    row["provider"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["tokens_thinking"],
                    row["cost_usd"],
                    row["latency_ms"],
                    row["first_token_ms"],
                    row["created_at"],
                    row["edited"],
                    row["stopped"],
                    row["rating"],
                    row["version"],
                ),
            )
            if row["id"] == from_message_id:
                break

        await self._recount_conversation(new_conv.id)
        await self.conn.commit()
        return await self.get_conversation(new_conv.id)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        content_raw: str | None = None,
        thinking_content: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_thinking: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int | None = None,
        first_token_ms: int | None = None,
    ) -> Message:
        """Append a message to a conversation and update aggregate counters."""
        mid = _new_id()
        now = _utcnow()
        await self.conn.execute(
            "INSERT INTO messages "
            "(id, conversation_id, role, content, content_raw, thinking_content, "
            "model, provider, tokens_in, tokens_out, tokens_thinking, "
            "cost_usd, latency_ms, first_token_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mid,
                conversation_id,
                role,
                content,
                content_raw,
                thinking_content,
                model,
                provider,
                tokens_in,
                tokens_out,
                tokens_thinking,
                cost_usd,
                latency_ms,
                first_token_ms,
                now,
            ),
        )
        # Update conversation aggregates
        await self.conn.execute(
            "UPDATE conversations SET "
            "total_messages = total_messages + 1, "
            "total_tokens_in = total_tokens_in + ?, "
            "total_tokens_out = total_tokens_out + ?, "
            "total_thinking_tokens = total_thinking_tokens + ?, "
            "total_cost_usd = total_cost_usd + ?, "
            "model = COALESCE(?, model), "
            "provider = COALESCE(?, provider), "
            "updated_at = ? "
            "WHERE id = ?",
            (
                tokens_in,
                tokens_out,
                tokens_thinking,
                cost_usd,
                model,
                provider,
                now,
                conversation_id,
            ),
        )
        await self.conn.commit()
        return Message(
            id=mid,
            conversation_id=conversation_id,
            role=role,
            content=content,
            content_raw=content_raw,
            thinking_content=thinking_content,
            model=model,
            provider=provider,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_thinking=tokens_thinking,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            first_token_ms=first_token_ms,
            created_at=datetime.fromisoformat(now),
        )

    async def get_messages(self, conversation_id: str) -> list[Message]:
        """Return all messages for a conversation in chronological order."""
        cursor = await self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_message(r) for r in rows]

    async def rate_message(self, message_id: str, rating: int) -> bool:
        """Set the rating on a message.

        Args:
            message_id: The message ID.
            rating: Rating value (-1, 0, or 1).

        Returns:
            ``True`` if the message existed and was updated.
        """
        cursor = await self.conn.execute(
            "UPDATE messages SET rating = ? WHERE id = ?",
            (rating, message_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def edit_message(self, message_id: str, content: str) -> bool:
        """Update the content of a message and mark it as edited.

        Args:
            message_id: The message ID.
            content: The new content.

        Returns:
            ``True`` if the message existed and was updated.
        """
        cursor = await self.conn.execute(
            "UPDATE messages SET content = ?, edited = 1 WHERE id = ?",
            (content, message_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_fulltext(self, query: str, *, limit: int = 20) -> list[SearchResult]:
        """FTS5 search across all message content.  Returns ranked results."""
        cursor = await self.conn.execute(
            "SELECT m.id AS message_id, m.conversation_id, c.title, "
            "snippet(messages_fts, 0, '«', '»', '…', 48) AS excerpt, "
            "rank "
            "FROM messages_fts "
            "JOIN messages m ON m.rowid = messages_fts.rowid "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE messages_fts MATCH ? "
            "ORDER BY rank "
            "LIMIT ?",
            (query, limit),
        )
        rows = await cursor.fetchall()
        return [
            SearchResult(
                conversation_id=r["conversation_id"],
                message_id=r["message_id"],
                title=r["title"],
                excerpt=r["excerpt"],
                match_rank=float(r["rank"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _recount_conversation(self, conversation_id: str) -> None:
        """Recompute aggregate counters from messages."""
        cursor = await self.conn.execute(
            "SELECT "
            "  COUNT(*) AS cnt, "
            "  COALESCE(SUM(tokens_in), 0) AS ti, "
            "  COALESCE(SUM(tokens_out), 0) AS to_, "
            "  COALESCE(SUM(tokens_thinking), 0) AS tt, "
            "  COALESCE(SUM(cost_usd), 0.0) AS cost "
            "FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return
        await self.conn.execute(
            "UPDATE conversations SET "
            "total_messages = ?, total_tokens_in = ?, total_tokens_out = ?, "
            "total_thinking_tokens = ?, total_cost_usd = ?, updated_at = ? "
            "WHERE id = ?",
            (row["cnt"], row["ti"], row["to_"], row["tt"], row["cost"], _utcnow(), conversation_id),
        )


# ------------------------------------------------------------------
# Row → model converters
# ------------------------------------------------------------------


def _row_to_summary(row: aiosqlite.Row) -> ConversationSummary:
    tags_raw = row["tags"]
    tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw or []

    return ConversationSummary(
        id=row["id"],
        title=row["title"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        model=row["model"],
        provider=row["provider"],
        skill_id=row["skill_id"],
        pinned=bool(row["pinned"]),
        archived=bool(row["archived"]),
        tags=tags,
        total_messages=row["total_messages"],
        total_tokens_in=row["total_tokens_in"],
        total_tokens_out=row["total_tokens_out"],
        total_thinking_tokens=row["total_thinking_tokens"],
        total_cost_usd=row["total_cost_usd"],
        parent_id=row["parent_id"],
        branch_from_message_id=row["branch_from_message_id"],
    )


def _row_to_message(row: aiosqlite.Row) -> Message:
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        content_raw=row["content_raw"],
        thinking_content=row["thinking_content"],
        model=row["model"],
        provider=row["provider"],
        tokens_in=row["tokens_in"],
        tokens_out=row["tokens_out"],
        tokens_thinking=row["tokens_thinking"],
        cost_usd=row["cost_usd"],
        latency_ms=row["latency_ms"],
        first_token_ms=row["first_token_ms"],
        created_at=datetime.fromisoformat(row["created_at"]),
        edited=bool(row["edited"]),
        stopped=bool(row["stopped"]),
        rating=row["rating"],
        version=row["version"],
        parent_message_id=row["parent_message_id"],
    )
