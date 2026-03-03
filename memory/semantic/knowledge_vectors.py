"""
Knowledge OS vector store — manages 4 Qdrant collections for the personal
knowledge system alongside the existing emily_semantic RAG collection.

Collections:
  emily_entities  — canonical entity descriptions (person, org, place…)
  emily_facts     — atomic facts about entities
  emily_events    — event descriptions
  emily_knowledge — chunks from ingested documents (PDF, email, vCard, etc.)

Each point payload follows the importance scoring schema so the query engine
can apply recency decay, access-frequency boosting, and explicit pinning.

Importance score formula (0–1):
    importance = 0.4·recency + 0.3·access_freq + 0.2·explicit_mark + 0.1·entity_centrality

All methods degrade gracefully when Qdrant is unavailable (offline mode).
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_DENSE_DIM = 1024  # BGE-M3 dense dimension
_DECAY_HALF_LIFE = 30 * 86400  # 30 days in seconds


# ---------------------------------------------------------------------------
# Payload dataclass
# ---------------------------------------------------------------------------


@dataclass
class KnowledgePoint:
    """
    A vector point to be stored in one of the knowledge collections.

    The `id` must be a deterministic UUID v5 derived from the entity/fact/event
    UUID so upserts are idempotent.
    """

    id: str
    text: str  # Human-readable text for the embedding
    record_type: str  # entity|fact|event|knowledge
    entity_ids: list[str] = field(default_factory=list)
    source_session: str = ""
    confidence: float = 1.0
    importance_score: float = 0.5
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Convert to Qdrant point payload dict."""
        return {
            "id": self.id,
            "text": self.text,
            "type": self.record_type,
            "entity_ids": self.entity_ids,
            "source_session": self.source_session,
            "confidence": self.confidence,
            "importance_score": self.importance_score,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "tags": self.tags,
            "timestamp": self.timestamp,
            **self.extra,
        }


# ---------------------------------------------------------------------------
# Importance scoring
# ---------------------------------------------------------------------------


def compute_importance(
    created_timestamp: float,
    access_count: int = 0,
    is_pinned: bool = False,
    entity_degree: int = 0,
) -> float:
    """
    Compute an importance score for a knowledge point.

    Uses exponential decay for recency, logarithmic growth for access
    frequency, a binary bonus for user-pinned items, and a small bonus
    for highly-connected entities.

    Args:
        created_timestamp: Unix timestamp when the item was created.
        access_count: Number of times the item was retrieved.
        is_pinned: True if the user explicitly marked this as important.
        entity_degree: Number of graph edges the related entity has.

    Returns:
        Importance score in [0.0, 1.0].
    """
    age_s = max(0.0, time.time() - created_timestamp)
    recency = math.exp(-age_s / _DECAY_HALF_LIFE)

    freq = math.log1p(access_count) / math.log1p(100)
    freq = min(freq, 1.0)

    pin_bonus = 1.0 if is_pinned else 0.0

    centrality = math.log1p(entity_degree) / math.log1p(50)
    centrality = min(centrality, 1.0)

    score = 0.4 * recency + 0.3 * freq + 0.2 * pin_bonus + 0.1 * centrality
    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Knowledge Vector Store
# ---------------------------------------------------------------------------


class KnowledgeVectorStore:
    """
    Manages the four knowledge OS Qdrant collections.

    Can be used independently of the main QdrantVectorStore — the two
    share the same Qdrant server but operate on separate collections.
    Degrades gracefully when Qdrant is unreachable.
    """

    COLLECTIONS = {
        "entities": "emily_entities",
        "facts": "emily_facts",
        "events": "emily_events",
        "knowledge": "emily_knowledge",
    }

    def __init__(self, qdrant_url: str = "http://localhost:6333") -> None:
        """
        Args:
            qdrant_url: Qdrant server URL.
        """
        self._url = qdrant_url
        self._client: Any = None
        self._available = False

    async def connect(self) -> None:
        """Connect to Qdrant and create all four collections if needed."""
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = AsyncQdrantClient(url=self._url)
            existing = {c.name for c in (await self._client.get_collections()).collections}

            for col_name in self.COLLECTIONS.values():
                if col_name not in existing:
                    await self._client.create_collection(
                        collection_name=col_name,
                        vectors_config=VectorParams(
                            size=_DENSE_DIM,
                            distance=Distance.COSINE,
                        ),
                    )
                    log.info("knowledge_collection_created", collection=col_name)

            self._available = True
            log.info("knowledge_vector_store_connected", url=self._url)
        except Exception as exc:
            log.warning("knowledge_vector_store_unavailable", error=str(exc))
            self._available = False

    @property
    def is_available(self) -> bool:
        """True if Qdrant is reachable."""
        return self._available

    def _collection_for(self, record_type: str) -> str:
        """Map record_type to Qdrant collection name."""
        mapping = {
            "entity": "emily_entities",
            "fact": "emily_facts",
            "event": "emily_events",
            "knowledge": "emily_knowledge",
        }
        return mapping.get(record_type, "emily_knowledge")

    @staticmethod
    def make_point_id(namespace: str, record_id: str) -> str:
        """
        Generate a deterministic UUID v5 for a Qdrant point.

        Using UUID v5 ensures the same record always maps to the same
        point ID, making upserts idempotent.

        Args:
            namespace: Collection namespace string (e.g., "emily_facts").
            record_id: The source record's UUID.

        Returns:
            UUID string for Qdrant.
        """
        ns = uuid.uuid5(uuid.NAMESPACE_URL, namespace)
        return str(uuid.uuid5(ns, record_id))

    async def upsert(
        self,
        point: KnowledgePoint,
        embedding: list[float],
    ) -> None:
        """
        Upsert a single knowledge point into the appropriate collection.

        Args:
            point: KnowledgePoint with metadata payload.
            embedding: Dense embedding vector (BGE-M3, 1024-dim).
        """
        if not self._available or self._client is None:
            return

        from qdrant_client.models import PointStruct

        collection = self._collection_for(point.record_type)
        qdrant_id = self.make_point_id(collection, point.id)

        qdrant_point = PointStruct(
            id=qdrant_id,
            vector=embedding,
            payload=point.to_payload(),
        )

        await self._client.upsert(collection_name=collection, points=[qdrant_point])
        log.debug("knowledge_point_upserted", type=point.record_type, id=point.id)

    async def upsert_batch(
        self,
        points: list[KnowledgePoint],
        embeddings: list[list[float]],
    ) -> None:
        """
        Upsert a batch of knowledge points (mixed types allowed).

        Args:
            points: List of KnowledgePoint objects.
            embeddings: Corresponding embedding vectors (same order).
        """
        if not self._available or self._client is None:
            return

        from qdrant_client.models import PointStruct

        # Group by collection to minimise round trips
        batches: dict[str, list[PointStruct]] = {}
        for point, emb in zip(points, embeddings, strict=False):
            col = self._collection_for(point.record_type)
            qdrant_id = self.make_point_id(col, point.id)
            p = PointStruct(id=qdrant_id, vector=emb, payload=point.to_payload())
            batches.setdefault(col, []).append(p)

        for col, batch_points in batches.items():
            await self._client.upsert(collection_name=col, points=batch_points)
            log.debug("knowledge_batch_upserted", collection=col, n=len(batch_points))

    async def search(
        self,
        query_vector: list[float],
        record_type: str,
        top_k: int = 10,
        entity_id_filter: str | None = None,
        min_importance: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search within a single knowledge collection.

        Args:
            query_vector: Dense query embedding (1024-dim).
            record_type: "entity"|"fact"|"event"|"knowledge".
            top_k: Maximum results.
            entity_id_filter: Restrict to facts/events for this entity UUID.
            min_importance: Only return points above this importance score.

        Returns:
            List of result dicts with text, score, and payload.
        """
        if not self._available or self._client is None:
            return []

        collection = self._collection_for(record_type)

        # Build filter conditions
        filter_conditions: list[dict[str, Any]] = []
        if entity_id_filter:
            filter_conditions.append(
                {
                    "key": "entity_ids",
                    "match": {"any": [entity_id_filter]},
                }
            )
        if min_importance is not None:
            filter_conditions.append(
                {
                    "key": "importance_score",
                    "range": {"gte": min_importance},
                }
            )

        qdrant_filter = None
        if filter_conditions:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            qdrant_filter = Filter(
                must=[
                    FieldCondition(**c)
                    if "match" not in c
                    else FieldCondition(key=c["key"], match=MatchAny(any=c["match"]["any"]))
                    for c in filter_conditions
                ]
            )

        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "id": hit.payload.get("id", str(hit.id)),
                "text": hit.payload.get("text", ""),
                "score": hit.score,
                "type": hit.payload.get("type", record_type),
                "entity_ids": hit.payload.get("entity_ids", []),
                "importance_score": hit.payload.get("importance_score", 0.0),
                "timestamp": hit.payload.get("timestamp", ""),
                "payload": hit.payload,
            }
            for hit in results
        ]

    async def update_access(self, record_type: str, record_id: str) -> None:
        """
        Increment access_count and update last_accessed for a point.

        Args:
            record_type: Collection type.
            record_id: The record's UUID.
        """
        if not self._available or self._client is None:
            return

        collection = self._collection_for(record_type)
        qdrant_id = self.make_point_id(collection, record_id)

        try:
            points = await self._client.retrieve(
                collection_name=collection, ids=[qdrant_id], with_payload=True
            )
            if not points:
                return

            payload = points[0].payload
            new_count = payload.get("access_count", 0) + 1
            new_importance = compute_importance(
                created_timestamp=payload.get("last_accessed", time.time()) - 86400,
                access_count=new_count,
                is_pinned=payload.get("is_pinned", False),
            )
            await self._client.set_payload(
                collection_name=collection,
                payload={
                    "access_count": new_count,
                    "last_accessed": time.time(),
                    "importance_score": new_importance,
                },
                points=[qdrant_id],
            )
        except Exception as exc:
            log.warning("knowledge_access_update_failed", error=str(exc))

    async def delete_by_entity(self, entity_id: str, record_type: str) -> None:
        """
        Delete all points associated with a given entity_id.

        Args:
            entity_id: UUID of the entity whose vectors should be removed.
            record_type: Collection to delete from.
        """
        if not self._available or self._client is None:
            return

        from qdrant_client.models import FieldCondition, Filter, MatchAny

        collection = self._collection_for(record_type)
        await self._client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="entity_ids",
                        match=MatchAny(any=[entity_id]),
                    )
                ]
            ),
        )
        log.info("knowledge_vectors_deleted", entity_id=entity_id, collection=collection)
