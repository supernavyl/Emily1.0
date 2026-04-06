"""Tests that ConversationAgent uses ExtractionPipeline instead of _extract_user_facts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_extract_user_facts_removed() -> None:
    """The old _extract_user_facts method should no longer exist."""
    from agents.conversation import ConversationAgent

    assert not hasattr(ConversationAgent, "_extract_user_facts"), \
        "_extract_user_facts should be removed — replaced by _extract_knowledge"


async def test_extract_knowledge_method_exists() -> None:
    """The new _extract_knowledge method should exist."""
    from agents.conversation import ConversationAgent

    assert hasattr(ConversationAgent, "_extract_knowledge"), \
        "_extract_knowledge method must exist on ConversationAgent"


async def test_extraction_pipeline_used_in_extract_knowledge() -> None:
    """_extract_knowledge should reference ExtractionPipeline."""
    import inspect
    from agents.conversation import ConversationAgent

    source = inspect.getsource(ConversationAgent._extract_knowledge)
    assert "ExtractionPipeline" in source or "extraction_pipeline" in source.lower(), \
        "_extract_knowledge must use ExtractionPipeline"


async def test_supersede_fact_called_on_contradiction() -> None:
    """When a new fact contradicts an existing one, supersede_fact should be called."""
    from extraction.entity_extractor import ExtractedEntity
    from extraction.pipeline import ExtractionPipeline
    from memory.knowledge_models import EntityRecord, FactRecord

    store = MagicMock()
    # Simulate existing fact for the entity
    existing_fact = MagicMock()
    existing_fact.id = "fact-old-1"
    existing_fact.fact_text = "preference: likes Python"

    store.get_facts_for_entity = AsyncMock(return_value=[existing_fact])
    store.supersede_fact = AsyncMock()
    store.add_fact = AsyncMock()

    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)
    pipeline._store = store

    entity = EntityRecord(
        id="ent-1",
        type="person",
        canonical_name="User",
    )
    extracted = ExtractedEntity(
        canonical_name="User",
        type="person",
        attributes={"preference": "hates Python"},
        confidence=0.8,
    )

    count = await pipeline._store_attributes_as_facts(entity, extracted, "session-new")

    # supersede_fact should have been called for the contradicting preference
    store.supersede_fact.assert_called_once()
    args = store.supersede_fact.call_args[0]
    assert args[0] == "fact-old-1"  # old fact ID
    assert count == 1


async def test_same_fact_skipped() -> None:
    """When a fact already exists with the same text, don't re-add it."""
    from extraction.entity_extractor import ExtractedEntity
    from extraction.pipeline import ExtractionPipeline
    from memory.knowledge_models import EntityRecord

    store = MagicMock()
    existing_fact = MagicMock()
    existing_fact.id = "fact-1"
    existing_fact.fact_text = "preference: likes Python"

    store.get_facts_for_entity = AsyncMock(return_value=[existing_fact])
    store.supersede_fact = AsyncMock()
    store.add_fact = AsyncMock()

    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)
    pipeline._store = store

    entity = EntityRecord(id="ent-1", type="person", canonical_name="User")
    extracted = ExtractedEntity(
        canonical_name="User",
        type="person",
        attributes={"preference": "likes Python"},
        confidence=0.8,
    )

    count = await pipeline._store_attributes_as_facts(entity, extracted, "session-new")

    # Neither supersede_fact nor add_fact should be called — same fact
    store.supersede_fact.assert_not_called()
    store.add_fact.assert_not_called()
    assert count == 0
