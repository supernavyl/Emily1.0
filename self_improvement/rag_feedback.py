"""
RAG feedback loop for Emily's self-improvement engine.

Tracks retrieval quality and user-signal feedback for retrieved chunks:
- Positive signals: user references retrieved content, says it was helpful
- Negative signals: user ignores retrieved content, says it was irrelevant
- Implicit signals: whether retrieved chunks contributed to the final response

This data is used to:
1. Penalize low-quality chunks in future retrieval (temporal decay weighting)
2. Identify documents that consistently fail to yield relevant results
3. Trigger re-ingestion of stale or poor-quality documents
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_FEEDBACK_LOG_PATH = Path("data/rag_feedback.jsonl")
_STATS_PATH = Path("data/rag_quality_stats.json")


@dataclass
class RAGFeedbackEvent:
    """A single RAG retrieval quality feedback event."""

    chunk_id: str
    document_source: str
    query: str
    relevance_score: float  # Retriever's relevance score (0-1)
    used_in_response: bool  # Whether this chunk was cited in the LLM response
    user_feedback: str = "none"  # "positive", "negative", "none"
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_source": self.document_source,
            "query": self.query,
            "relevance_score": self.relevance_score,
            "used_in_response": self.used_in_response,
            "user_feedback": self.user_feedback,
            "ts": self.ts,
        }


class RAGFeedbackLoop:
    """
    Records retrieval feedback and computes per-document quality scores.

    Quality scores drive temporal decay in the vector store retriever:
    documents with consistent poor quality get penalized in future rankings.
    """

    def __init__(
        self,
        feedback_log_path: Path = _FEEDBACK_LOG_PATH,
        stats_path: Path = _STATS_PATH,
    ) -> None:
        """
        Args:
            feedback_log_path: Path to the JSONL feedback log.
            stats_path: Path to the JSON quality stats file.
        """
        self._log_path = feedback_log_path
        self._stats_path = stats_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        chunk_id: str,
        document_source: str,
        query: str,
        relevance_score: float,
        used_in_response: bool,
        user_feedback: str = "none",
    ) -> None:
        """
        Record a retrieval feedback event.

        Args:
            chunk_id: Unique chunk identifier from the vector store.
            document_source: Source document path or URL.
            query: The query that triggered retrieval.
            relevance_score: Retriever's relevance score (0-1).
            used_in_response: True if the chunk was cited in the LLM response.
            user_feedback: "positive", "negative", or "none".
        """
        event = RAGFeedbackEvent(
            chunk_id=chunk_id,
            document_source=document_source,
            query=query,
            relevance_score=relevance_score,
            used_in_response=used_in_response,
            user_feedback=user_feedback,
        )
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except OSError as exc:
            log.error("rag_feedback_write_error", error=str(exc))

    def compute_document_quality(self, window_days: int = 30) -> dict[str, float]:
        """
        Compute quality scores (0-1) for each source document.

        Quality formula:
          quality = 0.5 * use_rate + 0.3 * avg_relevance + 0.2 * positive_feedback_rate

        Args:
            window_days: Only consider feedback within this many days.

        Returns:
            Dict of {document_source: quality_score}.
        """
        cutoff = time.time() - window_days * 86400

        # Accumulate stats per document
        doc_stats: dict[str, dict[str, Any]] = {}

        if not self._log_path.exists():
            return {}

        with open(self._log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("ts", 0) < cutoff:
                        continue
                    src = data.get("document_source", "unknown")
                    if src not in doc_stats:
                        doc_stats[src] = {
                            "total": 0,
                            "used": 0,
                            "positive": 0,
                            "negative": 0,
                            "scores": [],
                        }
                    s = doc_stats[src]
                    s["total"] += 1
                    if data.get("used_in_response"):
                        s["used"] += 1
                    if data.get("user_feedback") == "positive":
                        s["positive"] += 1
                    elif data.get("user_feedback") == "negative":
                        s["negative"] += 1
                    s["scores"].append(float(data.get("relevance_score", 0.5)))
                except (json.JSONDecodeError, ValueError):
                    continue

        quality_scores: dict[str, float] = {}
        for src, s in doc_stats.items():
            n = max(s["total"], 1)
            use_rate = s["used"] / n
            avg_relevance = sum(s["scores"]) / max(len(s["scores"]), 1)
            fb_total = s["positive"] + s["negative"]
            pos_rate = (s["positive"] / max(fb_total, 1)) if fb_total > 0 else 0.5
            quality = 0.5 * use_rate + 0.3 * avg_relevance + 0.2 * pos_rate
            quality_scores[src] = round(quality, 4)

        self._save_stats(quality_scores)
        return quality_scores

    def get_low_quality_documents(self, threshold: float = 0.3) -> list[str]:
        """
        Return documents with quality scores below the threshold.

        These documents may need re-ingestion or deletion.

        Args:
            threshold: Quality score below which a document is flagged.

        Returns:
            List of document source paths.
        """
        scores = self.compute_document_quality()
        return [src for src, q in scores.items() if q < threshold]

    def _save_stats(self, scores: dict[str, float]) -> None:
        """Persist quality stats to disk."""
        try:
            self._stats_path.write_text(
                json.dumps({"updated_at": time.time(), "scores": scores}, indent=2)
            )
        except OSError as exc:
            log.error("rag_stats_save_error", error=str(exc))

    def apply_negative_feedback(self, chunk_id: str) -> None:
        """
        Mark a specific chunk as explicitly unhelpful.

        This signal propagates to the vector store's temporal decay mechanism.

        Args:
            chunk_id: Chunk identifier to penalize.
        """
        log.info("rag_negative_feedback", chunk_id=chunk_id)
        self.record(
            chunk_id=chunk_id,
            document_source="unknown",
            query="",
            relevance_score=0.0,
            used_in_response=False,
            user_feedback="negative",
        )
