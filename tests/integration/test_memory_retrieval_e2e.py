"""Integration test: Memory retrieval pipeline.

Verify that the memory system can store and retrieve context chunks,
and that the RAG pipeline returns results when queried.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_memory_manager_retrieve_returns_list():
    """MemoryManager.retrieve_context returns a list even with no retriever."""
    from memory.manager import MemoryManager

    config = MagicMock()
    config.memory.sensory_buffer_size = 100
    config.memory.working_memory_max_tokens = 4000
    config.memory.episodic.db_path = ":memory:"

    mm = MemoryManager(config)
    # Without startup, retriever is None → should return empty list
    result = await mm.retrieve_context("test query")
    assert isinstance(result, list)
    assert result == []


@pytest.mark.asyncio
async def test_episodic_memory_roundtrip():
    """Save and retrieve an episode from SQLite."""
    from memory.episodic import Episode, EpisodicMemory

    config = MagicMock()
    config.db_path = ":memory:"

    em = EpisodicMemory(config)
    await em.connect()

    episode = Episode(
        topics=["test", "integration"],
        summary="Test episode for integration test",
        emotional_tone="neutral",
    )
    await em.save_episode(episode)

    retrieved = await em.get_episode(episode.id)
    assert retrieved is not None
    assert retrieved.summary == "Test episode for integration test"
    assert "test" in retrieved.topics

    count = await em.count()
    assert count == 1

    await em.close()


@pytest.mark.asyncio
async def test_cross_session_recall_intent_detection():
    """has_recall_intent detects recall patterns."""
    from memory.manager import MemoryManager

    config = MagicMock()
    config.memory.sensory_buffer_size = 100
    config.memory.working_memory_max_tokens = 4000
    config.memory.episodic.db_path = ":memory:"

    mm = MemoryManager(config)
    assert mm.has_recall_intent("Do you remember when we talked about Python?")
    assert mm.has_recall_intent("What did we discuss about the project?")
    assert not mm.has_recall_intent("What is the weather today?")
