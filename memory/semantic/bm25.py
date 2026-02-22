"""BM25 sparse index for keyword-based RAG retrieval."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class BM25Index:
    """
    Rank-BM25 based sparse retrieval index.

    Maintains an in-memory BM25 index over all ingested chunks.
    Serialized to disk for persistence across restarts.
    """

    def __init__(self, index_path: str = "data/bm25_index") -> None:
        """
        Args:
            index_path: Directory path for persisting the index.
        """
        self._index_path = Path(index_path)
        self._model: object | None = None
        self._chunks: list[dict[str, Any]] = []
        self._available = False

    def load(self) -> None:
        """Load the index from disk if it exists, or initialize an empty one."""
        index_file = self._index_path / "bm25.pkl"
        chunks_file = self._index_path / "chunks.json"

        if index_file.exists() and chunks_file.exists():
            try:
                with index_file.open("rb") as f:
                    self._model = pickle.load(f)
                self._chunks = json.loads(chunks_file.read_text())
                self._available = bool(self._chunks)
                log.info("bm25_index_loaded", n_docs=len(self._chunks))
            except Exception as exc:
                log.warning("bm25_index_load_failed", error=str(exc))

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """
        Add new chunks to the BM25 index.

        Args:
            chunks: List of chunk dicts with "content" and "chunk_id" keys.
        """
        try:
            from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
        except ImportError:
            log.warning("rank_bm25_not_installed_bm25_disabled")
            return

        self._chunks.extend(chunks)
        tokenized = [doc["content"].lower().split() for doc in self._chunks]
        self._model = BM25Okapi(tokenized)
        self._available = True
        self._persist()
        log.debug("bm25_index_updated", n_docs=len(self._chunks))

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        """
        Search the BM25 index for the most relevant chunks.

        Args:
            query: Search query string.
            top_k: Number of results to return.

        Returns:
            List of chunk dicts sorted by BM25 score (descending).
        """
        if not self._available or self._model is None:
            return []

        tokenized_query = query.lower().split()
        scores = self._model.get_scores(tokenized_query)  # type: ignore[union-attr]

        results = []
        for i, score in enumerate(scores):
            if score > 0:
                results.append({
                    **self._chunks[i],
                    "bm25_score": float(score),
                })

        results.sort(key=lambda r: r["bm25_score"], reverse=True)
        return results[:top_k]

    def _persist(self) -> None:
        """Persist the index to disk."""
        try:
            self._index_path.mkdir(parents=True, exist_ok=True)
            with (self._index_path / "bm25.pkl").open("wb") as f:
                pickle.dump(self._model, f)
            (self._index_path / "chunks.json").write_text(
                json.dumps(self._chunks, ensure_ascii=False)
            )
        except Exception as exc:
            log.warning("bm25_persist_failed", error=str(exc))
