"""Tests for the Emily Chat conversation database (SQLite + FTS5)."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from emily_chat.storage.database import ConversationDatabase


@pytest_asyncio.fixture
async def db():
    """In-memory database initialised with the migration schema."""
    database = ConversationDatabase(db_path=":memory:")
    await database.init()
    yield database
    await database.close()


# ------------------------------------------------------------------
# Conversation CRUD
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_conversation(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Test conversation", model="gpt-5", provider="openai")
    assert conv.title == "Test conversation"
    assert conv.model == "gpt-5"

    fetched = await db.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.id == conv.id
    assert fetched.title == "Test conversation"


@pytest.mark.asyncio
async def test_get_all_conversations_excludes_archived(db: ConversationDatabase) -> None:
    c1 = await db.create_conversation("Visible")
    c2 = await db.create_conversation("Archived")
    await db.archive_conversation(c2.id)

    all_convs = await db.get_all_conversations()
    ids = [c.id for c in all_convs]
    assert c1.id in ids
    assert c2.id not in ids

    all_incl = await db.get_all_conversations(include_archived=True)
    ids_incl = [c.id for c in all_incl]
    assert c2.id in ids_incl


@pytest.mark.asyncio
async def test_rename_conversation(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Old title")
    await db.rename_conversation(conv.id, "New title")
    fetched = await db.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.title == "New title"


@pytest.mark.asyncio
async def test_pin_unpin(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Pin me")
    assert not conv.pinned

    await db.pin_conversation(conv.id, True)
    fetched = await db.get_conversation(conv.id)
    assert fetched is not None and fetched.pinned

    await db.pin_conversation(conv.id, False)
    fetched = await db.get_conversation(conv.id)
    assert fetched is not None and not fetched.pinned


@pytest.mark.asyncio
async def test_delete_conversation(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Doomed")
    await db.delete_conversation(conv.id)
    assert await db.get_conversation(conv.id) is None


# ------------------------------------------------------------------
# Messages
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get_messages(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Chat")
    m1 = await db.add_message(conv.id, "user", "Hello Emily")
    m2 = await db.add_message(
        conv.id, "assistant", "Hi there!",
        model="claude-sonnet", provider="anthropic",
        tokens_in=10, tokens_out=5, cost_usd=0.001,
    )

    msgs = await db.get_messages(conv.id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "assistant"
    assert msgs[1].tokens_out == 5

    # Aggregates updated
    updated = await db.get_conversation(conv.id)
    assert updated is not None
    assert updated.total_messages == 2
    assert updated.total_tokens_in == 10
    assert updated.total_cost_usd == pytest.approx(0.001)


# ------------------------------------------------------------------
# FTS5 Search
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fulltext_search(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Python chat")
    await db.add_message(conv.id, "user", "How do I use async generators in Python?")
    await db.add_message(conv.id, "assistant", "You can use 'async for' with yield.")

    results = await db.search_fulltext("async generators")
    assert len(results) >= 1
    assert results[0].conversation_id == conv.id
    assert "async" in results[0].excerpt.lower() or "generator" in results[0].excerpt.lower()


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_match(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Unrelated")
    await db.add_message(conv.id, "user", "What is the capital of France?")

    results = await db.search_fulltext("quantum entanglement")
    assert len(results) == 0


# ------------------------------------------------------------------
# Duplicate & Fork
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_conversation(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Original", model="gpt-5", provider="openai")
    await db.add_message(conv.id, "user", "Hello")
    await db.add_message(conv.id, "assistant", "Hi")

    dup = await db.duplicate_conversation(conv.id)
    assert dup is not None
    assert dup.id != conv.id
    assert dup.title == "Original (copy)"
    assert dup.total_messages == 2

    dup_msgs = await db.get_messages(dup.id)
    assert len(dup_msgs) == 2
    assert dup_msgs[0].content == "Hello"


@pytest.mark.asyncio
async def test_fork_conversation(db: ConversationDatabase) -> None:
    conv = await db.create_conversation("Long chat")
    m1 = await db.add_message(conv.id, "user", "First")
    m2 = await db.add_message(conv.id, "assistant", "Second")
    m3 = await db.add_message(conv.id, "user", "Third")

    fork = await db.fork_conversation(conv.id, m2.id)
    assert fork is not None
    assert fork.title == "Long chat (fork)"

    fork_msgs = await db.get_messages(fork.id)
    assert len(fork_msgs) == 2
    assert fork_msgs[0].content == "First"
    assert fork_msgs[1].content == "Second"


@pytest.mark.asyncio
async def test_duplicate_nonexistent_returns_none(db: ConversationDatabase) -> None:
    assert await db.duplicate_conversation("nonexistent") is None


@pytest.mark.asyncio
async def test_fork_nonexistent_returns_none(db: ConversationDatabase) -> None:
    assert await db.fork_conversation("nonexistent", "whatever") is None
