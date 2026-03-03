"""
Entity deduplication and merging.

After LLM extraction, the same real-world entity may appear multiple times
across sessions with slightly different names (e.g., "Alice", "Alice Nguyen",
"A. Nguyen"). The Deduplicator finds these overlaps and merges them into the
canonical EntityRecord, updating all foreign keys in relationships and facts.

Strategy:
1. Exact alias match: if any alias of an incoming entity matches any alias
   or canonical name of an existing entity → merge immediately.
2. Fuzzy match: Levenshtein distance below threshold on canonical_name → flag
   for merge (reported as candidates, confirmed by pipeline with >0.85 score).
"""

from __future__ import annotations

import re
from datetime import UTC

from extraction.entity_extractor import ExtractedEntity
from memory.knowledge_models import EntityRecord
from memory.knowledge_store import KnowledgeStore
from observability.logger import get_logger

log = get_logger(__name__)

_FUZZY_THRESHOLD = 0.85  # Jaro-Winkler similarity threshold


def _normalize(name: str) -> str:
    """Lower-case and strip punctuation for comparison."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _jaro_winkler(s1: str, s2: str) -> float:
    """
    Compute Jaro-Winkler similarity between two strings.

    Returns a score in [0.0, 1.0]; 1.0 means identical.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Jaro-Winkler similarity score.
    """
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_dist = max(len1, len2) // 2 - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = transpositions = 0

    for i, c1 in enumerate(s1):
        lo = max(0, i - match_dist)
        hi = min(len2, i + match_dist + 1)
        for j in range(lo, hi):
            if s2_matches[j] or c1 != s2[j]:
                continue
            s1_matches[i] = s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3

    # Winkler prefix bonus
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1 - jaro)


class Deduplicator:
    """
    Identifies and merges duplicate entities in the KnowledgeStore.

    Called by ExtractionPipeline after each extraction batch. Merging means:
    - Adding new aliases to the canonical entity
    - Updating source_ids with provenance from the duplicate
    - Returning the canonical entity_id for use in relationship/fact writes
    """

    def __init__(self, store: KnowledgeStore) -> None:
        """
        Args:
            store: Connected KnowledgeStore to perform lookups and writes against.
        """
        self._store = store

    async def resolve_entity(
        self,
        extracted: ExtractedEntity,
    ) -> tuple[EntityRecord, bool]:
        """
        Find the canonical EntityRecord for an extracted entity, creating it if new.

        Resolution order:
        1. Exact alias / canonical name match in the store.
        2. Fuzzy Jaro-Winkler match above threshold.
        3. Create new entity if no match found.

        Args:
            extracted: Freshly extracted entity to resolve.

        Returns:
            Tuple of (resolved_or_created EntityRecord, was_created: bool).
        """
        candidates = await self._store.find_entities(
            extracted.canonical_name, entity_type=extracted.type, limit=10
        )

        # 1. Exact name match
        norm_incoming = _normalize(extracted.canonical_name)
        for candidate in candidates:
            norm_canon = _normalize(candidate.canonical_name)
            if norm_canon == norm_incoming:
                return await self._merge(candidate, extracted), False

            # Check all stored aliases
            for alias in candidate.aliases:
                if _normalize(alias) == norm_incoming:
                    return await self._merge(candidate, extracted), False

        # 2. Fuzzy match
        for candidate in candidates:
            score = _jaro_winkler(norm_incoming, _normalize(candidate.canonical_name))
            if score >= _FUZZY_THRESHOLD:
                log.info(
                    "entity_fuzzy_merge",
                    incoming=extracted.canonical_name,
                    existing=candidate.canonical_name,
                    score=f"{score:.3f}",
                )
                return await self._merge(candidate, extracted), False

        # 3. New entity
        entity = EntityRecord(
            canonical_name=extracted.canonical_name,
            type=extracted.type,
            aliases=extracted.aliases,
            confidence=extracted.confidence,
            source_ids=[extracted.source_session_id] if extracted.source_session_id else [],
        )
        await self._store.upsert_entity(entity)
        log.info("entity_created", name=entity.canonical_name, id=entity.id)
        return entity, True

    async def _merge(
        self,
        existing: EntityRecord,
        incoming: ExtractedEntity,
    ) -> EntityRecord:
        """
        Merge new aliases and source provenance into an existing entity.

        Args:
            existing: The canonical EntityRecord already in the store.
            incoming: The newly extracted entity to absorb.

        Returns:
            Updated EntityRecord after merge.
        """
        changed = False

        new_aliases = set(existing.aliases)
        for alias in incoming.aliases + [incoming.canonical_name]:
            if (
                _normalize(alias) != _normalize(existing.canonical_name)
                and alias not in new_aliases
            ):
                new_aliases.add(alias)
                changed = True

        if incoming.source_session_id and incoming.source_session_id not in existing.source_ids:
            existing.source_ids.append(incoming.source_session_id)
            changed = True

        # Take higher confidence
        if incoming.confidence > existing.confidence:
            existing.confidence = incoming.confidence
            changed = True

        if changed:
            existing.aliases = sorted(new_aliases)
            from datetime import datetime

            existing.updated_at = datetime.now(UTC).isoformat()
            await self._store.upsert_entity(existing)
            log.debug("entity_merged", id=existing.id, name=existing.canonical_name)

        return existing
