"""
Unified memory interface for Emily.

MemoryManager is the single point of entry for all memory operations.
Agents call MemoryManager rather than individual tier implementations,
enabling the manager to:
- Route reads/writes to the correct tier
- Coordinate cross-tier operations (e.g., promote working → episodic)
- Enforce access control and rate limiting
- Log all memory operations to the audit trail
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from memory.episodic import Episode, EpisodicMemory

if TYPE_CHECKING:
    from config import EmilySettings
from memory.interaction_logger import InteractionLogger
from memory.procedural import ProceduralMemory
from memory.sensory_buffer import PerceptionEvent, SensoryBuffer
from memory.working import WorkingMemory
from observability.logger import get_logger

log = get_logger(__name__)


class MemoryManager:
    """
    Unified access layer to Emily's five-tier memory system.

    Semantic memory (Qdrant) and graph memory (networkx) are lazily
    connected: if a ``HybridRetriever`` is attached via
    ``set_retriever()`` the manager exposes ``retrieve_context()``
    for RAG lookups. Otherwise the method gracefully returns ``[]``.
    """

    def __init__(self, settings: EmilySettings, brain_hub: Any | None = None) -> None:
        """
        Args:
            settings: Global Emily settings.
            brain_hub: Optional BrainEventHub for live event streaming.
        """
        self.settings = settings
        self.sensory = SensoryBuffer(capacity=settings.memory.sensory_buffer_size)
        self.working = WorkingMemory(settings.memory.working)
        self.episodic = EpisodicMemory(settings.memory.episodic)
        self.procedural = ProceduralMemory(settings.memory.procedural)

        # Initialize interaction logger if enabled
        self.interaction_logger: InteractionLogger | None = None
        if settings.memory.episodic.save_all_interactions:
            self.interaction_logger = InteractionLogger(
                db_path=settings.memory.episodic.interactions_db_path,
                auto_backup_interval_minutes=settings.memory.episodic.auto_backup_interval_minutes,
            )

        self._session_start: float = time.time()
        self._retriever: Any | None = None
        self._brain_hub = brain_hub

    async def startup(self) -> None:
        """Initialize all persistent memory tiers."""
        tasks = [
            self.episodic.connect(),
            self.procedural.load(),
        ]

        # Connect interaction logger if enabled
        if self.interaction_logger:
            tasks.append(self.interaction_logger.connect())

        await asyncio.gather(*tasks)
        log.info("memory_manager_ready", interaction_logging=self.interaction_logger is not None)

    async def add_user_turn(
        self,
        text: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add a user utterance to working memory and log it permanently.

        Args:
            text: The user's message text.
            importance: Importance score [0.0, 1.0].
            metadata: Optional metadata (e.g., STT confidence, language).
        """
        self.working.add(
            role="user",
            content=text,
            importance=importance,
            metadata=metadata or {},
        )

        # Immediately save to interaction logger for permanent storage
        if self.interaction_logger:
            await self.interaction_logger.log_user_turn(
                session_id=self.working.session_id,
                content=text,
                importance=importance,
                metadata=metadata,
            )

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "memory",
                "user_turn",
                {
                    "text_len": len(text),
                    "importance": importance,
                },
            )

    async def add_assistant_turn(
        self,
        text: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add Emily's response to working memory and log it permanently.

        Args:
            text: Emily's response text.
            importance: Importance score.
            metadata: Optional metadata (e.g., model used, critic score).
        """
        self.working.add(
            role="assistant",
            content=text,
            importance=importance,
            metadata=metadata or {},
        )

        # Immediately save to interaction logger for permanent storage
        if self.interaction_logger:
            await self.interaction_logger.log_assistant_turn(
                session_id=self.working.session_id,
                content=text,
                importance=importance,
                metadata=metadata,
            )

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "memory",
                "assistant_turn",
                {
                    "text_len": len(text),
                    "importance": importance,
                },
            )

    async def end_session(self, summary: dict[str, Any] | None = None) -> Episode:
        """
        End the current session and save it as an episode.

        Args:
            summary: Optional pre-computed summary dict. If None, a basic
                     episode is created from the working memory transcript.

        Returns:
            The saved Episode record.
        """
        duration = time.time() - self._session_start
        transcript = self.working.get_transcript()
        transcript_path = await self.episodic.save_transcript(self.working.session_id, transcript)

        summary = summary or {}
        episode = Episode(
            id=self.working.session_id,
            duration_seconds=duration,
            topics=summary.get("topics", []),
            emotional_tone=summary.get("emotional_tone", "neutral"),
            key_decisions=summary.get("key_decisions", []),
            action_items=summary.get("action_items", []),
            summary=summary.get("summary", transcript[:500] + "..."),
            full_transcript_path=transcript_path,
        )

        await self.episodic.save_episode(episode)
        self.working.clear()
        self._session_start = time.time()

        log.info(
            "session_ended",
            episode_id=episode.id,
            duration_s=f"{duration:.0f}",
            topics=episode.topics,
        )
        return episode

    def set_retriever(self, retriever: Any) -> None:
        """
        Attach a HybridRetriever for semantic/RAG lookups.

        Args:
            retriever: A ``HybridRetriever`` instance (or any object with an
                       async ``retrieve(query, top_k)`` method).
        """
        self._retriever = retriever
        log.info("retriever_attached", retriever=type(retriever).__name__)

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant chunks from the semantic memory / RAG index.

        Returns an empty list when no retriever is configured so callers
        never have to guard against ``None``.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of chunks to return.

        Returns:
            Ranked list of chunk dicts (keys: content, source, score, ...).
        """
        if self._retriever is None:
            return []
        try:
            results = await self._retriever.retrieve(query, top_k=top_k)
            if self._brain_hub is not None:
                await self._brain_hub.emit(
                    "memory",
                    "context_retrieved",
                    {
                        "query": query[:120],
                        "top_k": top_k,
                        "results": len(results),
                    },
                )
            return results
        except Exception as exc:
            log.warning("retrieval_failed", query=query[:80], error=str(exc))
            return []

    def push_perception(self, event_type: str, payload: dict[str, Any]) -> None:
        """
        Add a raw perception event to the sensory buffer.

        Args:
            event_type: Event type tag.
            payload: Event payload data.
        """
        self.sensory.push(PerceptionEvent(event_type=event_type, payload=payload))

    async def get_context_for_llm(
        self,
        include_procedural: bool = True,
    ) -> dict[str, Any]:
        """
        Gather all relevant context for an LLM inference call.

        Returns:
            Dict with working memory messages, user profile, and recent episodes.
        """
        context: dict[str, Any] = {
            "messages": self.working.to_dict_list(),
            "session_id": self.working.session_id,
            "token_count": self.working.total_tokens,
        }

        if include_procedural:
            context["user_profile"] = self.procedural.user_profile
            context["emily_self_model"] = self.procedural.self_model

        return context

    async def shutdown(self) -> None:
        """
        Gracefully shutdown memory manager and close all connections.

        Creates final backup of interactions before closing.
        """
        if self.interaction_logger:
            await self.interaction_logger.close()

        await self.episodic.close()
        log.info("memory_manager_shutdown_complete")
