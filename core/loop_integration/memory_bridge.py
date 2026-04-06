"""MemoryBridge — bidirectional sync between emily-loop's FailureDB and Emily's memory."""

from __future__ import annotations

from typing import Any

from emily_loop.failures import FailureDB
from memory.manager import MemoryManager
from observability.logger import get_logger

log = get_logger(__name__)


class MemoryBridge:
    """Bridges emily-loop's failure patterns to Emily's 5-tier memory.

    Before planning: enriches the goal with episodic context from past sessions.
    After goal completion: syncs new failure patterns to procedural memory.
    """

    def __init__(self, memory: Any, failure_db: Any) -> None:
        self._memory = memory
        self._failure_db = failure_db
        self._last_sync_count: int = 0

    async def enrich_goal(self, goal: str) -> str:
        """Pull episodic context from Emily's memory to improve planning.

        Args:
            goal: The raw goal string.

        Returns:
            The goal enriched with relevant past context, or unchanged if none found.
        """
        chunks = await self._memory.retrieve_context(goal, top_k=3)
        if not chunks:
            return goal

        context = "\n".join(c["content"] for c in chunks)
        return f"{goal}\n\nRelevant context from past sessions:\n{context}"

    async def sync_failures(self) -> int:
        """Push new failure patterns to Emily's procedural memory.

        Returns:
            Number of new patterns synced.
        """
        all_patterns = await self._failure_db.all()
        total = len(all_patterns)
        new_count = total - self._last_sync_count

        if new_count <= 0:
            return 0

        new_patterns = all_patterns[:new_count]

        for pattern in new_patterns:
            await self._memory.procedural.add_skill(
                name=f"failure:{pattern.id}",
                description=(
                    f"[{pattern.category.value}] "
                    f"{pattern.trigger} -> {pattern.prevention}"
                ),
                tool_sequence=[{
                    "trigger": pattern.trigger,
                    "root_cause": pattern.root_cause,
                    "prevention": pattern.prevention,
                    "severity": pattern.severity,
                    "occurrences": pattern.occurrences,
                }],
            )

        self._last_sync_count = total
        log.info("failure_patterns_synced", count=new_count)
        return new_count
