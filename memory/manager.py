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
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from memory.episodic import Episode, EpisodicMemory

if TYPE_CHECKING:
    from config import EmilySettings
    from llm.fleet import LLMFleet
import contextlib

from memory.interaction_logger import InteractionLogger
from memory.procedural import ProceduralMemory
from memory.sensory_buffer import PerceptionEvent, SensoryBuffer
from memory.working import WorkingMemory
from observability.logger import get_logger
from observability.metrics import RAG_RETRIEVAL_LATENCY
from observability.tracing import async_trace_span

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
        self._fleet: LLMFleet | None = None
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

        # Fire background summarization if fleet is available
        if self._fleet is not None:
            asyncio.create_task(self._summarize_episode(episode))

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

    def set_fleet(self, fleet: LLMFleet) -> None:
        """Attach the LLM fleet for background summarization tasks.

        Args:
            fleet: The LLMFleet instance.
        """
        self._fleet = fleet

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

        import time as _time

        _t0 = _time.monotonic()
        async with async_trace_span(
            "memory.rag_retrieval",
            attributes={"top_k": str(top_k)},
        ):
            try:
                results = await self._retriever.retrieve(query, top_k=top_k)
                RAG_RETRIEVAL_LATENCY.observe(_time.monotonic() - _t0)
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

    _RECALL_RE = re.compile(
        r"\b(?:remember\s+when|do\s+you\s+remember|what\s+did\s+we\s+(?:discuss|talk)\s+about|"
        r"last\s+time\s+(?:we|I)|we\s+(?:talked|discussed|mentioned)\s+(?:about\s+)?|"
        r"you\s+(?:told|said|mentioned)\s+(?:that\s+)?|recall\s+(?:when|our|the)|"
        r"from\s+(?:our\s+)?(?:last|previous|earlier)\s+conversation)\b",
        re.IGNORECASE,
    )

    def has_recall_intent(self, text: str) -> bool:
        """Detect if the user is asking about past conversations."""
        return bool(self._RECALL_RE.search(text))

    async def recall_cross_session(
        self,
        query: str,
        max_episodes: int = 5,
        max_interactions: int = 10,
    ) -> list[dict[str, Any]]:
        """Search episodic memory and interaction logs for cross-session context.

        Args:
            query: The user's recall query.
            max_episodes: Max episodic results.
            max_interactions: Max interaction results.

        Returns:
            List of context chunks formatted for RAG injection.
        """
        chunks: list[dict[str, Any]] = []

        # Extract likely topic from the query (strip the recall intent prefix)
        topic = self._RECALL_RE.sub("", query).strip().strip("?.,!")

        # 1. Search episodic summaries
        try:
            episodes = await self.episodic.search_by_topic(topic, limit=max_episodes)
            for ep in episodes:
                chunks.append(
                    {
                        "content": f"[Session {ep.id[:8]}] {ep.summary}",
                        "source": f"past conversation ({ep.emotional_tone})",
                        "score": 0.8,
                        "chunk_id": f"episode-{ep.id}",
                    }
                )
        except Exception as exc:
            log.debug("episodic_recall_failed", error=str(exc))

        # 2. Search interaction logs (full-text)
        if self.interaction_logger and topic:
            try:
                interactions = await self.interaction_logger.search_interactions(
                    topic, limit=max_interactions
                )
                for ix in interactions:
                    chunks.append(
                        {
                            "content": f"[{ix.role}] {ix.content}",
                            "source": f"past interaction ({ix.session_id[:8]})",
                            "score": 0.7,
                            "chunk_id": f"interaction-{ix.session_id}-{ix.timestamp}",
                        }
                    )
            except Exception as exc:
                log.debug("interaction_recall_failed", error=str(exc))

        log.info("cross_session_recall", query=topic[:80], n_results=len(chunks))
        return chunks

    async def _summarize_episode(self, episode: Episode) -> None:
        """Summarize a single episode using the FAST tier and update it in the DB."""
        if self._fleet is None:
            return
        try:
            from llm.client import ChatMessage
            from llm.router import ModelTier

            transcript_text = episode.summary  # Currently the raw prefix
            if episode.full_transcript_path:
                with contextlib.suppress(Exception):
                    transcript_text = Path(episode.full_transcript_path).read_text(
                        encoding="utf-8"
                    )[:4000]

            messages = [
                ChatMessage(
                    role="system",
                    content=(
                        "You are a concise summarizer. Extract: 1) a 2-3 sentence summary, "
                        "2) a list of topics discussed, 3) key decisions made, "
                        "4) any action items. Respond in JSON with keys: "
                        "summary, topics, key_decisions, action_items, emotional_tone."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=f"Summarize this conversation:\n\n{transcript_text}",
                ),
            ]

            result = await self._fleet.chat(
                user_message="summarize conversation",
                messages=messages,
                force_tier=ModelTier.FAST,
                max_tokens=512,
            )

            import json

            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError:
                # LLM didn't return valid JSON — use the raw text as summary
                episode.summary = result.content.strip()[:500]
                await self.episodic.save_episode(episode)
                return

            episode.summary = parsed.get("summary", episode.summary)
            episode.topics = parsed.get("topics", episode.topics)
            episode.key_decisions = parsed.get("key_decisions", episode.key_decisions)
            episode.action_items = parsed.get("action_items", episode.action_items)
            episode.emotional_tone = parsed.get("emotional_tone", episode.emotional_tone)
            await self.episodic.save_episode(episode)
            log.info("episode_summarized", episode_id=episode.id)
        except Exception as exc:
            log.warning("episode_summarization_failed", episode_id=episode.id, error=str(exc))

    async def summarize_unsummarized(self, limit: int = 20) -> int:
        """Consolidation pass: summarize any episodes still using raw transcript prefixes.

        Args:
            limit: Maximum episodes to process per run.

        Returns:
            Number of episodes summarized.
        """
        episodes = await self.episodic.get_unsummarized_episodes(limit=limit)
        count = 0
        for ep in episodes:
            await self._summarize_episode(ep)
            count += 1
        if count:
            log.info("consolidation_complete", summarized=count)
        return count

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
