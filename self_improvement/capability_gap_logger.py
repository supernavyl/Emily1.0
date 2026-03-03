"""
Capability gap logger for Emily's self-improvement engine.

When Emily fails to complete a task, expresses low confidence,
or receives negative user feedback, the gap is logged here for
later analysis by the ToolBuilderAgent and ReflectionAgent.

Gap types:
- "tool_missing": A requested capability has no tool implementation
- "knowledge_gap": RAG retrieval returned no relevant results
- "reasoning_failure": ReAct loop exhausted retries without a good answer
- "skill_gap": Task requires a skill Emily hasn't developed yet
- "model_limitation": The selected LLM tier was insufficient

Gaps drive:
1. ToolBuilderAgent to generate new tools
2. RAG ingestion of targeted knowledge
3. Prompt evolution for specific failure patterns
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_GAP_LOG_PATH = Path("data/capability_gaps.jsonl")


@dataclass
class CapabilityGap:
    """A single detected capability gap."""

    gap_type: str  # "tool_missing", "knowledge_gap", etc.
    description: str  # Human-readable description of what Emily couldn't do
    context: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # How confident we are this is a real gap (0-1)
    resolved: bool = False
    ts: float = field(default_factory=time.time)
    gap_id: str = field(default_factory=lambda: f"gap_{int(time.time() * 1000)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "gap_type": self.gap_type,
            "description": self.description,
            "context": self.context,
            "confidence": self.confidence,
            "resolved": self.resolved,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityGap:
        return cls(
            gap_id=data.get("gap_id", f"gap_{int(time.time() * 1000)}"),
            gap_type=data["gap_type"],
            description=data["description"],
            context=data.get("context", {}),
            confidence=data.get("confidence", 1.0),
            resolved=data.get("resolved", False),
            ts=data.get("ts", time.time()),
        )


class CapabilityGapLogger:
    """
    Append-only log of capability gaps with deduplication and resolution tracking.

    Provides gap prioritization for the ToolBuilderAgent and ReflectionAgent
    to decide what to work on next during idle cycles.
    """

    def __init__(self, log_path: Path = _GAP_LOG_PATH) -> None:
        """
        Args:
            log_path: Path to the JSONL gap log file.
        """
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log_gap(
        self,
        gap_type: str,
        description: str,
        context: dict[str, Any] | None = None,
        confidence: float = 1.0,
    ) -> CapabilityGap:
        """
        Log a new capability gap.

        Args:
            gap_type: Type of gap ("tool_missing", "knowledge_gap", etc.)
            description: What Emily failed to do.
            context: Additional context (query, task, error messages, etc.)
            confidence: Confidence that this is a real gap.

        Returns:
            The created CapabilityGap.
        """
        gap = CapabilityGap(
            gap_type=gap_type,
            description=description,
            context=context or {},
            confidence=confidence,
        )
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(gap.to_dict()) + "\n")
        except OSError as exc:
            log.error("gap_log_write_error", error=str(exc))

        log.info(
            "capability_gap_logged",
            gap_type=gap_type,
            gap_id=gap.gap_id,
            description=description[:80],
        )
        return gap

    def mark_resolved(self, gap_id: str) -> bool:
        """
        Mark a gap as resolved (e.g., after a tool is built or knowledge ingested).

        Rewrites the log file to update the resolved flag.

        Args:
            gap_id: The gap ID to mark as resolved.

        Returns:
            True if the gap was found and updated.
        """
        if not self._path.exists():
            return False

        updated = False
        lines = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("gap_id") == gap_id:
                        data["resolved"] = True
                        updated = True
                    lines.append(json.dumps(data) + "\n")
                except json.JSONDecodeError:
                    lines.append(line)

        if updated:
            self._path.write_text("".join(lines))
            log.info("capability_gap_resolved", gap_id=gap_id)

        return updated

    def get_unresolved(
        self,
        gap_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[CapabilityGap]:
        """
        Get unresolved capability gaps, sorted by confidence (highest first).

        Args:
            gap_type: Filter by gap type. If None, returns all types.
            min_confidence: Only return gaps with confidence >= this value.
            limit: Maximum number of gaps to return.

        Returns:
            List of unresolved CapabilityGap objects.
        """
        if not self._path.exists():
            return []

        gaps: list[CapabilityGap] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("resolved", False):
                        continue
                    if gap_type and data.get("gap_type") != gap_type:
                        continue
                    if data.get("confidence", 1.0) < min_confidence:
                        continue
                    gaps.append(CapabilityGap.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    continue

        # Sort by confidence descending, then by recency
        gaps.sort(key=lambda g: (-g.confidence, -g.ts))
        return gaps[:limit]

    def get_gap_type_distribution(self) -> dict[str, int]:
        """
        Count unresolved gaps by type.

        Returns:
            Dict of {gap_type: count}.
        """
        dist: dict[str, int] = {}
        for gap in self.get_unresolved(limit=1000):
            dist[gap.gap_type] = dist.get(gap.gap_type, 0) + 1
        return dist

    def top_priority_gap(self) -> CapabilityGap | None:
        """
        Return the single highest-priority unresolved gap.

        Returns:
            The most important gap, or None if no gaps exist.
        """
        gaps = self.get_unresolved(limit=1)
        return gaps[0] if gaps else None
