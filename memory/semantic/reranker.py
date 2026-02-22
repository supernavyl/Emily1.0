"""
Cross-encoder reranker for Emily's RAG retrieval pipeline.

After BM25 + dense RRF fusion, a cross-encoder model (BGE-reranker-v2-m3)
re-scores the top-K results by computing a relevance score for each
(query, passage) pair. This significantly improves retrieval precision.
"""

from __future__ import annotations

import asyncio
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class CrossEncoderReranker:
    """
    Cross-encoder reranker using sentence-transformers.

    Falls back to score passthrough when the model is not available.
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._available = False

    async def load(self) -> None:
        """Load the cross-encoder model."""
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]
            self._model = await asyncio.to_thread(CrossEncoder, _RERANKER_MODEL)
            self._available = True
            log.info("reranker_loaded", model=_RERANKER_MODEL)
        except ImportError:
            log.warning("sentence_transformers_not_installed_reranker_disabled")
        except Exception as exc:
            log.error("reranker_load_failed", error=str(exc))

    async def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Rerank results using the cross-encoder.

        Args:
            query: The original query string.
            results: List of chunk dicts (must have "content" key).
            top_k: Number of top results to return after reranking.

        Returns:
            Reranked list of chunk dicts with "rerank_score" added.
        """
        if not self._available or self._model is None or not results:
            return results[:top_k]

        pairs = [(query, r.get("content", "")) for r in results]

        def _score() -> list[float]:
            return list(self._model.predict(pairs))  # type: ignore[union-attr]

        scores = await asyncio.to_thread(_score)

        for result, score in zip(results, scores):
            result["rerank_score"] = float(score)

        reranked = sorted(results, key=lambda r: r.get("rerank_score", 0.0), reverse=True)
        log.debug(
            "reranker_complete",
            input_n=len(results),
            top_k=top_k,
            top_score=f"{reranked[0].get('rerank_score', 0.0):.3f}" if reranked else "n/a",
        )
        return reranked[:top_k]
