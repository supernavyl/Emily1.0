"""
Extraction pipeline — orchestrates entity + relationship extraction and storage.

Flow:
    raw text
        → EntityExtractor     (LLM → ExtractedEntity list)
        → Deduplicator        (match against store, create/merge)
        → RelationExtractor   (LLM → ExtractedRelationship list)
        → KnowledgeStore      (persist entities, people, relationships, facts)

Every call to process() is idempotent: running the same text twice will
merge/update existing entities rather than creating duplicates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from extraction.deduplicator import Deduplicator
from extraction.entity_extractor import EntityExtractor, ExtractedEntity
from extraction.relation_extractor import RelationExtractor
from memory.knowledge_models import (
    EntityRecord,
    FactRecord,
    PersonRecord,
    RelationshipRecord,
)
from observability.logger import get_logger

if TYPE_CHECKING:
    from llm.base import LLMClientProtocol
    from memory.knowledge_store import KnowledgeStore

log = get_logger(__name__)


@dataclass
class ExtractionResult:
    """Summary of a completed extraction pipeline run."""

    session_id: str
    entities_created: int = 0
    entities_merged: int = 0
    relationships_created: int = 0
    facts_created: int = 0
    low_confidence_entities: list[str] = field(default_factory=list)


class ExtractionPipeline:
    """
    End-to-end extraction pipeline from raw text to knowledge store.

    Usage::

        pipeline = ExtractionPipeline(llm_client, knowledge_store)
        result = await pipeline.process(text, session_id="session-uuid")
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        store: KnowledgeStore,
        model: str = "Qwen2.5-14B-Instruct-abliterated",
    ) -> None:
        """
        Args:
            llm_client: LLM client satisfying LLMClientProtocol.
            store: Connected KnowledgeStore for persistence.
            model: LLM model to use for extraction tasks.
        """
        self._entity_extractor = EntityExtractor(llm_client, model=model)
        self._relation_extractor = RelationExtractor(llm_client, model=model)
        self._dedup = Deduplicator(store)
        self._store = store

    async def process(
        self,
        text: str,
        session_id: str = "",
        auto_confirm_low_confidence: bool = False,
    ) -> ExtractionResult:
        """
        Run the full extraction pipeline on raw text.

        Args:
            text: Text to extract knowledge from.
            session_id: Source session UUID for provenance.
            auto_confirm_low_confidence: If True, store low-confidence entities
                without user confirmation (use only in batch import scenarios).

        Returns:
            ExtractionResult summarising what was created/merged.
        """
        session_id = session_id or str(uuid.uuid4())
        result = ExtractionResult(session_id=session_id)

        if not text.strip():
            return result

        # ── Step 1: Extract entities ──────────────────────────────────────
        extracted = await self._entity_extractor.extract(text, source_session_id=session_id)

        # ── Step 2: Deduplicate and persist entities ──────────────────────
        # Maps temp_id → real EntityRecord
        temp_id_to_entity: dict[str, EntityRecord] = {}

        for ext in extracted:
            if ext.needs_confirmation and not auto_confirm_low_confidence:
                result.low_confidence_entities.append(ext.canonical_name)
                log.warning(
                    "entity_skipped_low_confidence",
                    name=ext.canonical_name,
                    confidence=ext.confidence,
                )
                continue

            entity, created = await self._dedup.resolve_entity(ext)
            temp_id_to_entity[ext.temp_id] = entity

            if created:
                result.entities_created += 1
                # Auto-create PersonRecord for person entities
                if entity.type == "person":
                    await self._create_person_profile(entity, ext)
            else:
                result.entities_merged += 1

            # Store attributes as facts
            facts_added = await self._store_attributes_as_facts(entity, ext, session_id)
            result.facts_created += facts_added

        # ── Step 3: Extract and persist relationships ─────────────────────
        if len(temp_id_to_entity) >= 2:
            resolved_entities = [
                _entity_as_extracted(e, tid) for tid, e in temp_id_to_entity.items()
            ]
            relationships = await self._relation_extractor.extract(
                text, resolved_entities, source_session_id=session_id
            )

            for rel in relationships:
                from_entity = temp_id_to_entity.get(rel.from_temp_id)
                to_entity = temp_id_to_entity.get(rel.to_temp_id)
                if not from_entity or not to_entity:
                    continue

                record = RelationshipRecord(
                    from_entity_id=from_entity.id,
                    to_entity_id=to_entity.id,
                    relationship_type=rel.relationship_type,
                    relationship_label=rel.relationship_label,
                    strength=rel.strength,
                    since=rel.since,
                    source_ids=[session_id],
                )
                await self._store.upsert_relationship(record)
                result.relationships_created += 1

        log.info(
            "extraction_complete",
            session_id=session_id,
            entities_created=result.entities_created,
            entities_merged=result.entities_merged,
            relationships=result.relationships_created,
            facts=result.facts_created,
            skipped_low_confidence=len(result.low_confidence_entities),
        )
        return result

    async def _create_person_profile(
        self,
        entity: EntityRecord,
        extracted: ExtractedEntity,
    ) -> None:
        """
        Create a minimal PersonRecord from extraction attributes.

        Args:
            entity: The canonical EntityRecord already in the store.
            extracted: The ExtractedEntity with attribute hints.
        """
        attrs = extracted.attributes
        person = PersonRecord(
            entity_id=entity.id,
            full_name=entity.canonical_name,
            nicknames=entity.aliases,
            occupation=attrs.get("occupation"),
            employer=attrs.get("employer"),
            relationship_to_user=attrs.get("relationship_to_user"),
        )
        await self._store.upsert_person(person)

    async def _store_attributes_as_facts(
        self,
        entity: EntityRecord,
        extracted: ExtractedEntity,
        session_id: str,
    ) -> int:
        """
        Convert extracted attribute key-value pairs into FactRecords.

        Skips attributes that are already handled by the people schema
        (occupation, employer, relationship_to_user) to avoid duplication.

        When a fact of the same type already exists for this entity,
        supersedes the old fact instead of creating a duplicate.

        Args:
            entity: The canonical entity to attach facts to.
            extracted: Source of attribute data.
            session_id: Provenance session.

        Returns:
            Number of facts stored.
        """
        _SCHEMA_ATTRS = {"occupation", "employer", "relationship_to_user"}
        count = 0

        for key, value in extracted.attributes.items():
            if key in _SCHEMA_ATTRS or not value:
                continue

            new_fact = FactRecord(
                entity_id=entity.id,
                fact_type=key,
                fact_text=f"{key}: {value}",
                confidence=extracted.confidence,
                source_id=session_id,
            )

            # Check for existing facts of the same type for this entity
            try:
                existing = await self._store.get_facts_for_entity(
                    entity.id, fact_type=key,
                )
                if existing:
                    # Supersede the most recent existing fact
                    old = existing[0]  # sorted by timestamp DESC
                    if old.fact_text != new_fact.fact_text:
                        await self._store.supersede_fact(old.id, new_fact)
                        count += 1
                        continue
                    else:
                        continue  # Same fact, skip
            except Exception as exc:
                log.debug("contradiction_check_failed", error=str(exc))

            try:
                await self._store.add_fact(new_fact)
                count += 1
            except ValueError:
                pass  # Below confidence threshold — already logged in store

        return count


def _entity_as_extracted(entity: EntityRecord, temp_id: str) -> ExtractedEntity:
    """
    Wrap an EntityRecord as an ExtractedEntity for RelationExtractor input.

    Args:
        entity: The persisted EntityRecord.
        temp_id: The temp_id to assign (so RelationExtractor can reference it).

    Returns:
        A minimal ExtractedEntity pointing at this entity.
    """
    ext = ExtractedEntity(
        canonical_name=entity.canonical_name,
        type=entity.type,
        aliases=entity.aliases,
    )
    ext.temp_id = temp_id
    return ext
