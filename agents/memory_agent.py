"""
MemoryAgent — manages all memory tier operations on behalf of other agents.

The MemoryAgent is the single point of entry for memory writes and
complex retrieval operations. Simple working memory reads go directly
through MemoryManager; the MemoryAgent handles:
- Cross-tier semantic search (RAG + episodic + procedural)
- Memory importance scoring
- Pinning important working memory entries
- Triggering consolidation when idle
"""

from __future__ import annotations

from agents.base import BaseAgent
from core.bus import Message, Priority
from observability.logger import get_logger

log = get_logger(__name__)


class MemoryAgent(BaseAgent):
    """
    Coordinator for Emily's multi-tier memory system.

    Handles memory read/write requests from other agents and
    manages the promotion and consolidation of memories across tiers.
    """

    name = "MemoryAgent"
    description = "Manages all memory tiers: read, write, promote, consolidate."

    async def handle(self, message: Message) -> None:
        """Handle memory operation requests."""
        handlers = {
            "memory.search": self._handle_search,
            "memory.write_fact": self._handle_write_fact,
            "memory.pin_entry": self._handle_pin,
            "memory.get_context": self._handle_get_context,
            "memory.consolidate": self._handle_consolidate,
        }
        handler = handlers.get(message.type)
        if handler:
            await handler(message)

    async def _handle_search(self, message: Message) -> None:
        """
        Search across memory tiers for relevant context.

        Args:
            message: Contains "query" and optional "tiers" list.
        """
        query = message.payload.get("query", "")
        result_recipient = message.payload.get("reply_to", message.sender)

        results = {
            "episodic": [],
            "working_context": self._memory.working.to_dict_list()[-6:],  # Last 6 turns
        }

        # Episodic search
        try:
            episodes = await self._memory.episodic.search_by_topic(query, limit=3)
            results["episodic"] = [
                {"summary": ep.summary, "topics": ep.topics, "timestamp": ep.timestamp}
                for ep in episodes
            ]
        except Exception as exc:
            self._log.warning("episodic_search_error", error=str(exc))

        await self.send(
            result_recipient,
            "memory.search_result",
            {"query": query, "results": results, "task_id": message.task_id},
            priority=Priority.ACTIVE,
            task_id=message.task_id,
        )

    async def _handle_write_fact(self, message: Message) -> None:
        """
        Write a fact to procedural memory.

        Args:
            message: Contains "key" and "value" in payload.
        """
        key = message.payload.get("key", "")
        value = message.payload.get("value")
        if key and value is not None:
            await self._memory.procedural.set_user_fact(key, value)
            self._log.info("user_fact_written", key=key)

    async def _handle_pin(self, message: Message) -> None:
        """Pin a working memory entry by ID."""
        entry_id = message.payload.get("entry_id", "")
        if entry_id:
            success = self._memory.working.pin(entry_id)
            self._log.debug("working_memory_pin", entry_id=entry_id, success=success)

    async def _handle_get_context(self, message: Message) -> None:
        """
        Return full LLM context (working memory + user profile).

        Args:
            message: Includes "reply_to" for the response destination.
        """
        context = await self._memory.get_context_for_llm()
        reply_to = message.payload.get("reply_to", message.sender)
        await self.send(
            reply_to,
            "memory.context_result",
            {"context": context, "task_id": message.task_id},
            priority=Priority.ACTIVE,
        )

    async def _handle_consolidate(self, message: Message) -> None:
        """Trigger the memory consolidation pipeline."""
        self._log.info("memory_consolidation_triggered")
        # Consolidation implementation in Phase 10-13
        # For now, log and end the current session if enough turns have passed
        if self._memory.working.entry_count > 20:
            await self._memory.end_session()
