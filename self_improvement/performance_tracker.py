"""
Performance tracker for Emily's self-improvement engine.

Tracks metrics for:
- LLM inference latency and quality
- STT accuracy (confidence scores)
- TTS latency
- RAG retrieval quality (relevance scores, hit rates)
- Agent task completion rates
- ReAct loop iteration counts

Data is stored in a JSONL log (`data/performance_log.jsonl`) and
periodically summarized to drive prompt evolution and capability gap detection.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_LOG_PATH = Path("data/performance_log.jsonl")


@dataclass
class PerformanceEvent:
    """A single performance measurement."""

    category: str          # "llm", "stt", "tts", "rag", "agent", "react"
    metric: str            # e.g., "latency_ms", "confidence", "relevance_score"
    value: float
    context: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "metric": self.metric,
            "value": self.value,
            "context": self.context,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerformanceEvent":
        return cls(
            category=data["category"],
            metric=data["metric"],
            value=data["value"],
            context=data.get("context", {}),
            ts=data.get("ts", 0.0),
        )


@dataclass
class PerformanceSummary:
    """Aggregate statistics for a category/metric."""

    category: str
    metric: str
    count: int
    mean: float
    median: float
    std: float
    p95: float
    window_hours: float


class PerformanceTracker:
    """
    Lightweight append-only performance logger with rolling statistics.

    Writes events to a JSONL file and can compute rolling summaries
    over a configurable time window.
    """

    def __init__(self, log_path: Path = _LOG_PATH) -> None:
        """
        Args:
            log_path: Path to the JSONL performance log file.
        """
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        category: str,
        metric: str,
        value: float,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a performance measurement.

        Args:
            category: High-level category ("llm", "rag", etc.)
            metric: Specific metric name ("latency_ms", "relevance_score", etc.)
            value: Numeric value.
            context: Optional additional context (model name, tool name, etc.)
        """
        event = PerformanceEvent(
            category=category,
            metric=metric,
            value=value,
            context=context or {},
        )
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except OSError as exc:
            log.error("performance_log_write_error", error=str(exc))

    def get_summary(
        self,
        category: str,
        metric: str,
        window_hours: float = 24.0,
    ) -> PerformanceSummary | None:
        """
        Compute aggregate statistics for a category/metric over a time window.

        Args:
            category: Category to filter on.
            metric: Metric name to filter on.
            window_hours: Look back this many hours.

        Returns:
            PerformanceSummary or None if no data.
        """
        cutoff = time.time() - window_hours * 3600
        values: list[float] = []

        if not self._path.exists():
            return None

        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if (data.get("category") == category
                            and data.get("metric") == metric
                            and data.get("ts", 0) >= cutoff):
                        values.append(float(data["value"]))
                except (json.JSONDecodeError, ValueError):
                    continue

        if not values:
            return None

        sorted_vals = sorted(values)
        p95_idx = int(0.95 * len(sorted_vals))

        return PerformanceSummary(
            category=category,
            metric=metric,
            count=len(values),
            mean=mean(values),
            median=median(values),
            std=stdev(values) if len(values) > 1 else 0.0,
            p95=sorted_vals[min(p95_idx, len(sorted_vals) - 1)],
            window_hours=window_hours,
        )

    def get_all_summaries(self, window_hours: float = 24.0) -> list[PerformanceSummary]:
        """
        Compute summaries for all category/metric pairs in the log.

        Args:
            window_hours: Time window in hours.

        Returns:
            List of PerformanceSummary objects.
        """
        cutoff = time.time() - window_hours * 3600
        data_map: dict[tuple[str, str], list[float]] = {}

        if not self._path.exists():
            return []

        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("ts", 0) >= cutoff:
                        key = (data["category"], data["metric"])
                        data_map.setdefault(key, []).append(float(data["value"]))
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

        summaries = []
        for (cat, met), vals in data_map.items():
            if not vals:
                continue
            sorted_vals = sorted(vals)
            p95_idx = int(0.95 * len(sorted_vals))
            summaries.append(PerformanceSummary(
                category=cat,
                metric=met,
                count=len(vals),
                mean=mean(vals),
                median=median(vals),
                std=stdev(vals) if len(vals) > 1 else 0.0,
                p95=sorted_vals[min(p95_idx, len(sorted_vals) - 1)],
                window_hours=window_hours,
            ))
        return summaries

    def prune_old_entries(self, keep_days: int = 30) -> int:
        """
        Remove log entries older than `keep_days` days.

        Args:
            keep_days: Entries older than this many days are deleted.

        Returns:
            Number of entries removed.
        """
        if not self._path.exists():
            return 0

        cutoff = time.time() - keep_days * 86400
        kept: list[str] = []
        removed = 0

        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("ts", 0) >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except (json.JSONDecodeError, ValueError):
                    kept.append(line)

        self._path.write_text("".join(kept))
        log.info("performance_log_pruned", removed=removed, kept=len(kept))
        return removed
