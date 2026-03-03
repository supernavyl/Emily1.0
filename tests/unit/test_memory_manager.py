"""Unit tests for memory.manager.MemoryManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def _mock_settings():
    """Build a minimal EmilySettings mock."""
    settings = MagicMock()
    settings.memory.sensory_buffer_size = 100
    settings.memory.working.max_tokens = 4096
    settings.memory.working.pin_important_threshold = 0.8
    settings.memory.episodic.db_path = ":memory:"
    settings.memory.episodic.auto_summarize = False
    settings.memory.procedural.path = "/tmp/test_proc.json"
    settings.memory.semantic.qdrant_url = "http://localhost:6333"
    settings.memory.semantic.collection_name = "test"
    settings.memory.semantic.bm25_index_path = "/tmp/test_bm25"
    settings.memory.consolidation.idle_trigger_minutes = 10
    return settings


@pytest.fixture()
def manager(_mock_settings):
    with (
        patch("memory.manager.EpisodicMemory"),
        patch("memory.manager.ProceduralMemory"),
        patch("memory.manager.WorkingMemory") as wm_cls,
    ):
        wm_instance = MagicMock()
        wm_instance.session_id = "test-session"
        wm_instance.to_dict_list.return_value = []
        wm_instance.total_tokens = 0
        wm_instance.get_transcript.return_value = "test transcript"
        wm_cls.return_value = wm_instance

        from memory.manager import MemoryManager

        mgr = MemoryManager(_mock_settings)
        yield mgr


@pytest.mark.asyncio
async def test_startup(manager):
    manager.episodic.connect = AsyncMock()
    manager.procedural.load = AsyncMock()
    await manager.startup()
    manager.episodic.connect.assert_awaited_once()
    manager.procedural.load.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_user_turn(manager):
    await manager.add_user_turn("hello", importance=0.7)
    manager.working.add.assert_called_once_with(
        role="user",
        content="hello",
        importance=0.7,
        metadata={},
    )


@pytest.mark.asyncio
async def test_add_assistant_turn(manager):
    await manager.add_assistant_turn("hi there", importance=0.5, metadata={"model": "phi4"})
    manager.working.add.assert_called_once_with(
        role="assistant",
        content="hi there",
        importance=0.5,
        metadata={"model": "phi4"},
    )


@pytest.mark.asyncio
async def test_retrieve_context_no_retriever(manager):
    result = await manager.retrieve_context("what is the meaning of life")
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_context_with_retriever(manager):
    retriever = AsyncMock()
    retriever.retrieve.return_value = [{"content": "42", "score": 0.9}]
    manager.set_retriever(retriever)
    result = await manager.retrieve_context("meaning of life", top_k=3)
    assert len(result) == 1
    retriever.retrieve.assert_awaited_once_with("meaning of life", top_k=3)


@pytest.mark.asyncio
async def test_retrieve_context_handles_error(manager):
    retriever = AsyncMock()
    retriever.retrieve.side_effect = RuntimeError("connection lost")
    manager.set_retriever(retriever)
    result = await manager.retrieve_context("query")
    assert result == []


@pytest.mark.asyncio
async def test_push_perception(manager):
    initial_len = len(manager.sensory._buffer)
    manager.push_perception("audio.speech", {"text": "hi"})
    assert len(manager.sensory._buffer) == initial_len + 1


@pytest.mark.asyncio
async def test_get_context_for_llm(manager):
    manager.procedural.user_profile = {"name": "Test"}
    manager.procedural.self_model = {"warmth": 0.8}
    ctx = await manager.get_context_for_llm()
    assert "messages" in ctx
    assert "session_id" in ctx
