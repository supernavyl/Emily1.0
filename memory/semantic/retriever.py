"""
Hybrid retriever: BM25 + dense vector search fused via Reciprocal Rank Fusion.

Retrieval pipeline:
1. Query expansion: LLM generates 3 alternative phrasings
2. BM25 sparse search on child chunks
3. Dense vector search on child chunks (BGE-M3)
4. RRF fusion of BM25 + dense results
5. Parent chunk promotion (replace child results with their parents)
6. Cross-encoder reranking (reranker.py)
7. Temporal decay weighting
"""

from __future__ import annotations

import asyncio
from typing import Any

from config import RAGConfig
from memory.semantic.bm25 import BM25Index
from memory.semantic.vector_store import QdrantVectorStore
from observability.logger import get_logger
from observability.metrics import RAG_RETRIEVAL_LATENCY

log = get_logger(__name__)


def _reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """
    Fuse multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = sum over lists of 1 / (k + rank)

    Args:
        ranked_lists: List of ranked result lists. Each item must have "chunk_id".
        k: RRF constant (60 is a well-tested default).

    Returns:
        Fused and re-ranked list of unique chunks.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, 1):
            chunk_id = item.get("chunk_id") or item.get("id", f"unknown_{rank}")
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            items[chunk_id] = item

    fused = sorted(
        items.values(), key=lambda x: scores.get(x.get("chunk_id", ""), 0.0), reverse=True
    )
    for item in fused:
        cid = item.get("chunk_id") or item.get("id", "")
        item["rrf_score"] = scores.get(cid, 0.0)
    return fused


class HybridRetriever:
    """
    Combines BM25 and dense vector search with RRF fusion.

    The retriever handles the full pipeline from raw query to ranked chunks
    ready for the LLM context window.
    """

    def __init__(
        self,
        config: RAGConfig,
        vector_store: QdrantVectorStore | None,
        bm25: BM25Index,
        embedder: Any,
        reranker: Any | None = None,
    ) -> None:
        """
        Args:
            config: RAG configuration.
            vector_store: Qdrant vector store, or None for BM25-only mode.
            bm25: BM25 index instance.
            embedder: Embedding function: async (text: str) -> list[float].
            reranker: Optional CrossEncoderReranker for final re-scoring.
        """
        self._config = config
        self._vector_store = vector_store
        self._bm25 = bm25
        self._embedder = embedder
        self._reranker = reranker

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        expand_queries: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Perform hybrid retrieval for a query.

        Args:
            query: The user's query.
            top_k: Number of final results. Defaults to config value.
            expand_queries: Whether to expand the query with LLM alternatives.

        Returns:
            Ranked list of chunk dicts ready for LLM context.
        """
        import time

        t0 = time.monotonic()
        final_k = top_k or self._config.final_top_k

        # Query expansion (requires LLM — skipped if embedder is not a fleet)
        # Full expansion implemented in Phase 9 when fleet is available to retriever

        # BM25 sparse search (always available)
        bm25_results = await asyncio.to_thread(self._bm25.search, query, self._config.rerank_top_k)

        # Dense vector search (only when Qdrant is wired)
        dense_results: list[dict[str, Any]] = []
        if self._vector_store is not None:
            query_vector = await self._embedder(query)
            dense_results = await self._vector_store.search(
                query_vector, top_k=self._config.rerank_top_k
            )

        # Normalize BM25 scores to [0, 1]
        if bm25_results:
            max_score = max(r.get("bm25_score", 1.0) for r in bm25_results) or 1.0
            for r in bm25_results:
                r["score"] = r.get("bm25_score", 0.0) / max_score

        # RRF fusion (works with one or both result lists)
        ranked_lists = [r for r in [bm25_results, dense_results] if r]
        fused = _reciprocal_rank_fusion(ranked_lists) if ranked_lists else []

        # Parent chunk promotion: replace children with their parents
        promoted = await self._promote_parents(fused[: self._config.rerank_top_k])

        # Cross-encoder reranking (if available)
        if self._reranker is not None:
            result = await self._reranker.rerank(query, promoted, top_k=final_k)
        else:
            result = promoted[:final_k]

        elapsed = (time.monotonic() - t0) * 1000
        RAG_RETRIEVAL_LATENCY.observe(elapsed / 1000.0)
        log.info(
            "hybrid_retrieval_complete",
            query_len=len(query),
            n_bm25=len(bm25_results),
            n_dense=len(dense_results),
            n_fused=len(fused),
            n_returned=len(result),
            elapsed_ms=f"{elapsed:.0f}",
        )

        return result

    async def _promote_parents(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Replace child chunks with their parent chunks for richer LLM context.

        Args:
            results: Ranked list of child chunk results.

        Returns:
            Results with children replaced by their parent chunks where available.
        """
        promoted: list[dict[str, Any]] = []
        seen_parents: set[str] = set()
        seen_chunks: set[str] = set()

        for result in results:
            parent_id = result.get("parent_id")
            chunk_id = result.get("chunk_id", "")

            if parent_id and parent_id not in seen_parents and self._vector_store is not None:
                # Try to fetch the parent chunk
                parent = await self._vector_store.get_by_id(parent_id)
                if parent:
                    parent["score"] = result.get("rrf_score", result.get("score", 0.5))
                    parent["retrieved_via_child"] = chunk_id
                    promoted.append(parent)
                    seen_parents.add(parent_id)
                    continue

            # No parent or already seen — use the child itself
            if chunk_id not in seen_chunks:
                promoted.append(result)
                seen_chunks.add(chunk_id)

        return promoted
