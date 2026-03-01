"""
LLM-based named-entity extraction.

Sends text through the fast LLM model and parses the JSON array of entities
returned by the model. Every extracted entity receives:
- confidence score
- source_session_id linkage
- ISO8601 timestamp
- raw_excerpt from the source text

Facts with confidence < 0.4 are returned but flagged — they are not written
to the knowledge store without explicit user confirmation (enforced in the pipeline).
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
    from llm.base import LLMClientProtocol
from observability.logger import get_logger

log = get_logger(__name__)

_PROMPT_BUILDER = PromptBuilder()


@dataclass
class ExtractedEntity:
    """
    An entity extracted from raw text by the LLM.

    Not yet persisted — pipeline.py merges these into EntityRecord/PersonRecord
    after deduplication.
    """

    canonical_name: str
    type: str
    aliases: list[str] = field(default_factory=list)
    confidence: float = 1.0
    raw_excerpt: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    source_session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    temp_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def needs_confirmation(self) -> bool:
        """True if confidence is below the auto-store threshold (0.4)."""
        return self.confidence < 0.4


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    """
    Extract the first JSON array from a raw LLM response string.

    The model sometimes wraps JSON in markdown code fences; this handles that.

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed list of dicts, or empty list on failure.
    """
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Find first [ ... ]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        log.warning("entity_json_parse_failed", error=str(exc), raw_snippet=raw[:200])
        return []


class EntityExtractor:
    """
    Extracts named entities from text using the fast LLM tier.

    Calls the local LLM with a structured extraction prompt and
    parses the JSON response into ExtractedEntity objects.
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        model: str = "Qwen2.5-14B-Instruct-abliterated",
    ) -> None:
        """
        Args:
            llm_client: LLM client satisfying LLMClientProtocol.
            model: Model identifier to use for extraction.
        """
        self._llm = llm_client
        self._model = model

    async def extract(
        self,
        text: str,
        source_session_id: str = "",
    ) -> list[ExtractedEntity]:
        """
        Extract entities from arbitrary text.

        Args:
            text: Raw text to process.
            source_session_id: Session UUID to tag each entity with.

        Returns:
            List of ExtractedEntity objects (unsaved, not deduplicated).
        """
        if not text.strip():
            return []

        prompt = _PROMPT_BUILDER.build_entity_extraction_prompt(text)
        messages = [ChatMessage(role="user", content=prompt)]

        try:
            result = await self._llm.chat(
                model=self._model,
                messages=messages,
                temperature=0.1,  # low temp for structured extraction
                max_tokens=2048,
                model_tier="fast",
            )
        except Exception as exc:
            log.error("entity_extraction_llm_error", error=str(exc))
            return []

        raw_items = _extract_json_array(result.content)
        entities: list[ExtractedEntity] = []

        for item in raw_items:
            name = item.get("canonical_name", "").strip()
            if not name:
                continue

            confidence = float(item.get("confidence", 0.5))
            entity = ExtractedEntity(
                canonical_name=name,
                type=item.get("type", "person"),
                aliases=item.get("aliases", []),
                confidence=confidence,
                raw_excerpt=item.get("raw_excerpt", ""),
                attributes=item.get("attributes", {}),
                source_session_id=source_session_id,
            )
            entities.append(entity)

            if entity.needs_confirmation:
                log.warning(
                    "low_confidence_entity",
                    name=name,
                    confidence=confidence,
                )

        log.info(
            "entities_extracted",
            count=len(entities),
            session=source_session_id,
        )
        return entities
