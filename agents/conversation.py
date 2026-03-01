"""
ConversationAgent — real-time dialogue handler.

Responsibilities:
- Process audio transcript events from the PerceptionBus
- Assemble LLM context (system prompt + working memory + RAG retrieval)
- Stream LLM response via the fast or smart model
- Emit TTS events for audio playback
- Coordinate with MemoryAgent for memory reads/writes
- Coordinate with PlannerAgent for complex multi-step tasks
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.critic_loop import CriticLoop
from llm.prompt_builder import PromptBuilder
from llm.react_loop import ReActLoop
from llm.recency_detector import needs_web_search, needs_web_search_voice
from llm.router import ModelTier
from llm.streaming import StreamProcessor
from observability.logger import get_logger
from plugins.base import BaseTool, ExecutionContext

log = get_logger(__name__)


class ConversationAgent(BaseAgent):
    """
    Handles real-time voice and text conversations with the user.

    Every incoming transcript is processed through:
    1. Memory retrieval (MemoryAgent)
    2. Context assembly (PromptBuilder)
    3. Model routing (LLMFleet.route)
    4. LLM inference (streaming)
    5. CriticAgent evaluation
    6. TTS emission
    7. Memory persistence
    """

    name = "ConversationAgent"
    description = "Handles real-time dialogue and coordinates response generation."

    def __init__(
        self,
        bus: Any,
        fleet: Any,
        memory: Any,
        web_search: BaseTool | None = None,
    ) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._stream_processor = StreamProcessor()
        self._critic = CriticLoop(fleet, self._prompts)
        self._react_loop = ReActLoop(fleet, self._prompts)
        self._web_search = web_search
        self._interrupted = asyncio.Event()

    async def handle(self, message: Message) -> None:
        """
        Dispatch message to the appropriate handler based on type.

        Args:
            message: Incoming AgentBus or PerceptionBus message.
        """
        handlers = {
            "audio.transcript": self._handle_transcript,
            "audio.interrupt": self._handle_interrupt,
            "text.input": self._handle_text_input,
            "conversation.start": self._handle_session_start,
            "conversation.end": self._handle_session_end,
        }
        handler = handlers.get(message.type)
        if handler:
            await handler(message)
        else:
            self._log.debug("unknown_message_type", type=message.type)

    async def _handle_interrupt(self, message: Message) -> None:
        """Handle an interrupt signal from the voice engine."""
        self._interrupted.set()
        self._log.info(
            "interrupt_received",
            reason=message.payload.get("reason", "unknown"),
        )

    async def _handle_transcript(self, message: Message) -> None:
        """Process a voice transcript and generate a response via voice fast path."""
        self._interrupted.clear()

        text = message.payload.get("text", "").strip()
        confidence = message.payload.get("confidence", 1.0)

        if not text or confidence < 0.4:
            return

        self._log.info(
            "processing_transcript",
            text_preview=text[:60],
            confidence=f"{confidence:.2f}",
        )
        await self._generate_response(text, message.task_id, voice_mode=True)

    async def _handle_text_input(self, message: Message) -> None:
        """Process a text input (from API or TUI) via the full pipeline."""
        text = message.payload.get("text", "").strip()
        if not text:
            return
        await self._generate_response(text, message.task_id, voice_mode=False)

    async def _generate_response(
        self,
        user_text: str,
        task_id: str,
        voice_mode: bool = False,
    ) -> None:
        """
        Generate a response, optionally using the voice pipeline.

        When ``voice_mode`` is True the pipeline prefers VOICE_FAST for low
        complexity turns, but allows escalation for harder requests.
        RAG retrieval is skipped for simple queries (complexity below
        ``voice_skip_rag_below``), web search only fires on explicit intent,
        and the CriticAgent is bypassed.

        Args:
            user_text: The user's input text.
            task_id: Correlation task ID.
            voice_mode: Force VOICE_FAST tier and lightweight pipeline.
        """
        t0 = time.monotonic()
        routing_cfg = self._fleet._config.routing

        await self._memory.add_user_turn(user_text, importance=0.6)

        routing = self._fleet.route(user_text, voice_mode=voice_mode)
        skip_rag = voice_mode and routing.complexity_score < routing_cfg.voice_skip_rag_below

        if voice_mode and routing.complexity_score < routing_cfg.voice_fast_complexity_threshold:
            force_tier: ModelTier | None = ModelTier.VOICE_FAST
        else:
            force_tier = None

        if skip_rag:
            rag_chunks: list[dict[str, Any]] = []
        else:
            rag_chunks = await self._memory.retrieve_context(user_text)

        web_chunks: list[dict[str, Any]] = []
        if voice_mode:
            if needs_web_search_voice(user_text) and self._web_search is not None:
                web_chunks = await self._run_web_search(user_text, task_id)
        else:
            if needs_web_search(user_text) and self._web_search is not None:
                web_chunks = await self._run_web_search(user_text, task_id)

        context_block = self._prompts.build_rag_context_block(
            rag_chunks + web_chunks,
        )

        # Use QwQ-32B reasoning prompt when the reasoning tier is selected
        effective_tier = force_tier or routing.tier
        if effective_tier == ModelTier.REASONING:
            system_prompt = self._prompts.get_reasoning_system_prompt(  # noqa
                user_profile=self._memory.procedural.user_profile,
            )
        else:
            system_prompt = self._prompts.get_system_prompt(  # noqa
                user_profile=self._memory.procedural.user_profile,
            )

        messages = self._prompts.build_messages(
            system_prompt=system_prompt,  # noqa
            conversation_history=self._memory.working.to_dict_list()[:-1],
            user_message=user_text,
            context_block=context_block,
        )

        self._log.info(
            "routing_decision",
            tier=effective_tier.value,
            model=routing.model_name,
            complexity=routing.complexity_score,
            task_type=routing.task_type.name,
            voice_mode=voice_mode,
            skip_rag=skip_rag,
            n_rag_chunks=len(rag_chunks),
            n_web_chunks=len(web_chunks),
        )

        full_response = ""
        async for sentence in self._stream_processor.iter_sentences(
            self._fleet.chat_stream(
                user_text,
                messages,
                task_type=routing.task_type,
                force_tier=force_tier,
            )
        ):
            if self._interrupted.is_set():
                self._log.info("generation_interrupted_by_user")
                break

            full_response += sentence + " "
            await self._bus.send_to(
                recipient="tts",
                msg_type="tts.speak",
                payload={"text": sentence, "task_id": task_id},
                sender=self.name,
                priority=Priority.REALTIME,
            )

        await self._bus.send_to(
            recipient="tts",
            msg_type="tts.done",
            payload={"task_id": task_id},
            sender=self.name,
            priority=Priority.REALTIME,
        )

        full_response = full_response.strip()
        if not full_response:
            return

        skip_critic = voice_mode and routing_cfg.voice_skip_critic
        if skip_critic:
            final_response = full_response
            critic_score = 1.0
        else:
            final_response, score = await self._critic.evaluate_and_retry(
                initial_response=full_response,
                task=user_text,
                messages=messages,
            )
            critic_score = score.overall

        await self._memory.add_assistant_turn(
            final_response,
            importance=0.7,
            metadata={
                "critic_score": critic_score,
                "model": routing.model_name,
                "voice_mode": voice_mode,
                "latency_ms": (time.monotonic() - t0) * 1000,
            },
        )

        self._log.info(
            "response_complete",
            response_len=len(final_response),
            voice_mode=voice_mode,
            critic_score=f"{critic_score:.2f}",
            elapsed_ms=f"{(time.monotonic() - t0) * 1000:.0f}",
        )

    async def _run_web_search(
        self,
        query: str,
        task_id: str,
    ) -> list[dict[str, Any]]:
        """
        Execute a web search and normalise results into the RAG chunk format.

        Args:
            query: User's search query.
            task_id: Correlation task ID.

        Returns:
            List of dicts with ``content``, ``source``, and ``score`` keys.
        """
        assert self._web_search is not None
        ctx = ExecutionContext(
            session_id=self._memory.working.session_id,
        )
        try:
            result = await self._web_search.execute(
                {"query": query, "num_results": 3},
                ctx,
            )
        except Exception as exc:
            self._log.warning("web_search_failed", error=str(exc))
            return []

        if not result.success:
            self._log.warning("web_search_no_results", error=result.error)
            return []

        chunks: list[dict[str, Any]] = []
        for item in result.output or []:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            chunks.append(
                {
                    "content": f"{title}\n{snippet}" if title else snippet,
                    "source": url or "web_search",
                    "score": 0.75,
                }
            )
        return chunks

    async def _handle_session_start(self, message: Message) -> None:
        """Initialize a new conversation session."""
        self._log.info("session_started", session_id=self._memory.working.session_id)

    async def _handle_session_end(self, message: Message) -> None:
        """End the current session and save the episode."""
        summary = message.payload.get("summary", {})
        episode = await self._memory.end_session(summary)
        self._log.info("session_ended", episode_id=episode.id)
