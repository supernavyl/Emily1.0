"""
Tier 4: Semantic Memory — Qdrant vector store client.

All semantic memories are stored as BGE-M3 embeddings in Qdrant.
The collection uses named vectors to support both dense and sparse
retrieval from a single collection (BGE-M3's hybrid output).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from config import SemanticMemoryConfig
from observability.logger import get_logger
from observability.metrics import MEMORY_READS_TOTAL, MEMORY_WRITES_TOTAL
from rag.chunker import Chunk

log = get_logger(__name__)

_COLLECTION_NAME = "emily_semantic"
_DENSE_DIM = 1024  # BGE-M3 dense embedding dimension


class QdrantVectorStore:
    """
    Async Qdrant client for Emily's semantic memory.

    Manages the collection lifecycle, upsert, and search operations.
    All heavy operations run in a thread pool to avoid blocking the event loop.
    """

    def __init__(self, config: SemanticMemoryConfig) -> None:
        """
        Args:
            config: Semantic memory configuration.
        """
        self._config = config
        self._client: object | None = None
        self._available = False

    async def connect(self) -> None:
        """Connect to Qdrant and create the collection if it doesn't exist."""
        try:
            from qdrant_client import AsyncQdrantClient  # type: ignore[import-untyped]
            from qdrant_client.models import (  # type: ignore[import-untyped]
                Distance,
                VectorParams,
            )

            self._client = AsyncQdrantClient(url=self._config.qdrant_url)
            client = self._client

            # Check if collection exists
            collections = await client.get_collections()
            existing = {c.name for c in collections.collections}

            if self._config.collection_name not in existing:
                await client.create_collection(
                    collection_name=self._config.collection_name,
                    vectors_config=VectorParams(
                        size=_DENSE_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                log.info(
                    "qdrant_collection_created",
                    collection=self._config.collection_name,
                )

            self._available = True
            log.info(
                "qdrant_connected",
                url=self._config.qdrant_url,
                collection=self._config.collection_name,
            )
        except ImportError:
            log.warning("qdrant_client_not_installed")
        except Exception as exc:
            log.error("qdrant_connection_failed", error=str(exc))

    async def ensure_collection(self) -> None:
        """Connect to Qdrant and ensure the collection exists.

        Alias for :meth:`connect` used by the bootstrap sequence.
        """
        await self.connect()

    async def upsert_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """
        Store chunks with their embeddings in Qdrant.

        Args:
            chunks: List of Chunk objects to store.
            embeddings: Pre-computed embeddings. If None, assumed to be
                        computed externally and stored in chunk.metadata["embedding"].
        """
        if not self._available or self._client is None:
            log.warning("qdrant_not_available_skipping_upsert")
            return

        from qdrant_client.models import PointStruct  # type: ignore[import-untyped]

        points = []
        for i, chunk in enumerate(chunks):
            embedding = (
                embeddings[i]
                if embeddings
                else chunk.metadata.get("embedding", [0.0] * _DENSE_DIM)
            )
            point = PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.id)),
                vector=embedding,
                payload={
                    "chunk_id": chunk.id,
                    "content": chunk.content,
                    "source": chunk.source,
                    "source_path": chunk.source_path,
                    "parent_id": chunk.parent_id,
                    "is_parent": chunk.is_parent,
                    "token_count": chunk.token_count,
                    "content_hash": chunk.content_hash,
                    "last_accessed": time.time(),
                    "access_count": 0,
                    "negative_feedback": 0,
                    **chunk.metadata,
                },
            )
            points.append(point)

        await self._client.upsert(  # type: ignore[union-attr]
            collection_name=self._config.collection_name,
            points=points,
        )
        MEMORY_WRITES_TOTAL.labels(tier="semantic").inc()
        log.debug("qdrant_upserted", n_chunks=len(chunks))

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        filter_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Perform a dense vector similarity search.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            filter_payload: Optional Qdrant filter dict.

        Returns:
            List of result dicts with content, score, and metadata.
        """
        if not self._available or self._client is None:
            return []

        from qdrant_client.models import Filter  # type: ignore[import-untyped]

        results = await self._client.search(  # type: ignore[union-attr]
            collection_name=self._config.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=filter_payload,
            with_payload=True,
        )

        MEMORY_READS_TOTAL.labels(tier="semantic").inc()

        return [
            {
                "id": str(hit.id),
                "content": hit.payload.get("content", ""),
                "score": hit.score,
                "source": hit.payload.get("source", ""),
                "source_path": hit.payload.get("source_path", ""),
                "parent_id": hit.payload.get("parent_id"),
                "chunk_id": hit.payload.get("chunk_id"),
                "metadata": hit.payload,
            }
            for hit in results
        ]

    async def get_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        """
        Retrieve a specific chunk by its chunk_id.

        Args:
            chunk_id: The chunk's ID string.

        Returns:
            Chunk payload dict or None.
        """
        if not self._available or self._client is None:
            return None

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
        results = await self._client.retrieve(  # type: ignore[union-attr]
            collection_name=self._config.collection_name,
            ids=[point_id],
            with_payload=True,
        )
        if results:
            return results[0].payload
        return None

    async def update_access_stats(self, chunk_ids: list[str]) -> None:
        """
        Increment access_count and update last_accessed for retrieved chunks.

        Implements the temporal decay model's "access tracking" component.

        Args:
            chunk_ids: List of chunk IDs that were accessed.
        """
        if not self._available or self._client is None:
            return
        from qdrant_client.models import SetPayload  # type: ignore[import-untyped]

        point_ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, cid)) for cid in chunk_ids]
        now = time.time()
        for point_id in point_ids:
            try:
                await self._client.set_payload(  # type: ignore[union-attr]
                    collection_name=self._config.collection_name,
                    payload={"last_accessed": now},
                    points=[point_id],
                )
            except Exception:
                pass

    async def record_negative_feedback(self, chunk_id: str) -> None:
        """
        Increment the negative_feedback counter for a chunk.

        Chunks with high negative feedback are down-weighted in retrieval.

        Args:
            chunk_id: The chunk's ID.
        """
        if not self._available or self._client is None:
            return
        from qdrant_client.models import SetPayload  # type: ignore[import-untyped]

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
        existing = await self.get_by_id(chunk_id)
        current = existing.get("negative_feedback", 0) if existing else 0
        try:
            await self._client.set_payload(  # type: ignore[union-attr]
                collection_name=self._config.collection_name,
                payload={"negative_feedback": current + 1},
                points=[point_id],
            )
        except Exception as exc:
            log.warning("feedback_update_failed", chunk_id=chunk_id, error=str(exc))

    @property
    def is_available(self) -> bool:
        """True if Qdrant is connected and available."""
        return self._available
