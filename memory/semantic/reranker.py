"""
Cross-encoder reranker for Emily's RAG retrieval pipeline.

After BM25 + dense RRF fusion, a cross-encoder model (BGE-reranker-v2-m3)
re-scores the top-K results by computing a relevance score for each
(query, passage) pair. This significantly improves retrieval precision.

Uses the ``rerankers`` library for a lightweight, backend-agnostic API.
Falls back to ``sentence_transformers.CrossEncoder`` if ``rerankers`` is
not installed, and to score passthrough if neither is available.
"""

from __future__ import annotations

import asyncio
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class CrossEncoderReranker:
    """
    Cross-encoder reranker using the ``rerankers`` library (preferred) or
    ``sentence_transformers`` (fallback).

    Falls back to score passthrough when no reranker backend is available.
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._available = False
        self._backend: str = "none"

    async def load(self) -> None:
        """Load the cross-encoder model."""
        # Try rerankers library first (lightweight, unified API)
        try:
            from rerankers import Reranker  # type: ignore[import-untyped]

            self._model = await asyncio.to_thread(Reranker, _RERANKER_MODEL)
            self._available = True
            self._backend = "rerankers"
            log.info("reranker_loaded", model=_RERANKER_MODEL, backend="rerankers")
            return
        except ImportError:
            pass
        except Exception as exc:
            log.warning("rerankers_load_failed", error=str(exc))

        # Fallback: sentence-transformers CrossEncoder
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

            self._model = await asyncio.to_thread(CrossEncoder, _RERANKER_MODEL)
            self._available = True
            self._backend = "sentence_transformers"
            log.info("reranker_loaded", model=_RERANKER_MODEL, backend="sentence_transformers")
            return
        except ImportError:
            log.warning(
                "reranker_no_backend_available (install rerankers or sentence-transformers)"
            )
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

        if self._backend == "rerankers":
            return await self._rerank_rerankers(query, results, top_k)
        return await self._rerank_sentence_transformers(query, results, top_k)

    async def _rerank_rerankers(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Rerank using the rerankers library."""
        docs = [r.get("content", "") for r in results]

        def _score() -> object:
            return self._model.rank(query=query, docs=docs)  # type: ignore[union-attr]

        ranked = await asyncio.to_thread(_score)

        # rerankers returns RankedResults with .results list of Result objects
        for r in ranked.results:  # type: ignore[union-attr]
            idx = r.doc_id
            if 0 <= idx < len(results):
                results[idx]["rerank_score"] = float(r.score)

        reranked = sorted(results, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        log.debug(
            "reranker_complete",
            backend="rerankers",
            input_n=len(results),
            top_k=top_k,
            top_score=f"{reranked[0].get('rerank_score', 0.0):.3f}" if reranked else "n/a",
        )
        return reranked[:top_k]

    async def _rerank_sentence_transformers(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Rerank using sentence-transformers CrossEncoder."""
        pairs = [(query, r.get("content", "")) for r in results]

        def _score() -> list[float]:
            return list(self._model.predict(pairs))  # type: ignore[union-attr]

        scores = await asyncio.to_thread(_score)

        for result, score in zip(results, scores, strict=False):
            result["rerank_score"] = float(score)

        reranked = sorted(results, key=lambda r: r.get("rerank_score", 0.0), reverse=True)
        log.debug(
            "reranker_complete",
            backend="sentence_transformers",
            input_n=len(results),
            top_k=top_k,
            top_score=f"{reranked[0].get('rerank_score', 0.0):.3f}" if reranked else "n/a",
        )
        return reranked[:top_k]
