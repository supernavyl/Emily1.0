"""
LLM-based relationship extraction between known entities.

Takes the list of ExtractedEntity objects from entity_extractor.py and the
original text, asks the LLM to identify typed edges between them, and returns
ExtractedRelationship objects for the pipeline to persist.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from extraction.entity_extractor import ExtractedEntity
    from llm.base import LLMClientProtocol
from observability.logger import get_logger

log = get_logger(__name__)

_PROMPT_BUILDER = PromptBuilder()


@dataclass
class ExtractedRelationship:
    """
    A typed relationship between two extracted entities (not yet persisted).

    from_temp_id and to_temp_id reference ExtractedEntity.temp_id values so
    the pipeline can remap them to real entity UUIDs after deduplication.
    """

    from_temp_id: str
    to_temp_id: str
    relationship_type: str
    relationship_label: str = ""
    strength: float = 0.5
    since: str | None = None
    confidence: float = 1.0
    raw_excerpt: str = ""
    source_session_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    """
    Extract the first JSON array from a raw LLM response string.

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed list of dicts, or empty list on failure.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        log.warning("relation_json_parse_failed", error=str(exc))
        return []


class RelationExtractor:
    """
    Extracts typed relationships between already-identified entities.

    Uses the fast LLM tier with a structured JSON prompt. Relationship objects
    reference entity temp_ids so the pipeline can map them to real UUIDs once
    deduplication is complete.
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        model: str = "Qwen2.5-14B-Instruct-abliterated",
    ) -> None:
        """
        Args:
            llm_client: LLM client satisfying LLMClientProtocol.
            model: Model identifier.
        """
        self._llm = llm_client
        self._model = model

    async def extract(
        self,
        text: str,
        entities: list[ExtractedEntity],
        source_session_id: str = "",
    ) -> list[ExtractedRelationship]:
        """
        Extract relationships between the given entities within the text.

        Args:
            text: Raw source text.
            entities: Already extracted entities (must have temp_id set).
            source_session_id: Session UUID for provenance tracking.

        Returns:
            List of ExtractedRelationship objects (unsaved).
        """
        if len(entities) < 2:
            return []  # No pairs to relate

        entity_dicts = [{"canonical_name": e.canonical_name, "id": e.temp_id} for e in entities]
        prompt = _PROMPT_BUILDER.build_relation_extraction_prompt(text, entity_dicts)
        messages = [ChatMessage(role="user", content=prompt)]

        try:
            result = await self._llm.chat(
                model=self._model,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
                model_tier="fast",
            )
        except Exception as exc:
            log.error("relation_extraction_llm_error", error=str(exc))
            return []

        raw_items = _extract_json_array(result.content)

        # Build a lookup from temp_id to entity for validation
        known_ids = {e.temp_id for e in entities}
        relationships: list[ExtractedRelationship] = []

        for item in raw_items:
            from_id = item.get("from_entity_id", "")
            to_id = item.get("to_entity_id", "")

            if from_id not in known_ids or to_id not in known_ids:
                log.warning(
                    "relation_unknown_entity_id",
                    from_id=from_id,
                    to_id=to_id,
                )
                continue

            rel = ExtractedRelationship(
                from_temp_id=from_id,
                to_temp_id=to_id,
                relationship_type=item.get("relationship_type", "knows"),
                relationship_label=item.get("relationship_label", ""),
                strength=float(item.get("strength", 0.5)),
                since=item.get("since"),
                confidence=float(item.get("confidence", 0.8)),
                raw_excerpt=item.get("raw_excerpt", ""),
                source_session_id=source_session_id,
            )
            relationships.append(rel)

        log.info(
            "relationships_extracted",
            count=len(relationships),
            session=source_session_id,
        )
        return relationships
