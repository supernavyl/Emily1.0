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
import re
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
from modes.engine import get_mode_engine
from observability.logger import get_logger
from persona.emotional_state import get_emotional_state
from plugins.base import BaseTool, ExecutionContext
from plugins.registry import PluginRegistry
from reasoning.orchestrator import ReasoningContext, ReasoningEvent, ReasoningOrchestrator

_FRUSTRATION_RE = re.compile(
    r"\b(wrong|incorrect|not right|that'?s not|stupid|useless|terrible|awful|"
    r"doesn'?t work|doesn'?t make sense|you don'?t understand|try again|"
    r"start over|forget it|that'?s wrong|still wrong)\b",
    re.IGNORECASE,
)
_POSITIVE_RE = re.compile(
    r"\b(great|perfect|exactly|thank(?:s| you)|awesome|love it|that'?s right|"
    r"well done|brilliant|excellent|good job|that helped|nailed it|spot on)\b",
    re.IGNORECASE,
)

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
        settings: Any | None = None,
        self_improvement: Any | None = None,
    ) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._stream_processor = StreamProcessor()
        self._critic = CriticLoop(fleet, self._prompts)
        self._settings = settings
        self._self_improvement = self_improvement
        self._interrupted = asyncio.Event()
        self._turn_count = 0
        self._pending_approval: dict[str, Any] = {}

        # Plugin registry and tool executor
        self._plugin_registry = PluginRegistry()
        tool_kwargs: dict[str, dict[str, Any]] = {}
        if settings and hasattr(settings, "tools"):
            tool_kwargs["web_search"] = {"searxng_url": settings.tools.web_search_url}
        self._plugin_registry.load_builtins(tool_kwargs=tool_kwargs)

        # Web search: prefer explicitly injected, fall back to registry
        self._web_search = web_search or self._plugin_registry.get("web_search")

        self._react_loop = ReActLoop(
            fleet,
            self._prompts,
            tool_executor=self._execute_tool,
            available_tools=self._plugin_registry.all_schemas(),
        )

        # Reasoning orchestrator for non-direct strategies
        self._orchestrator = ReasoningOrchestrator(fleet, self._prompts)

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
        mode_id = message.payload.get("mode_id", "normal")
        await self._generate_response(text, message.task_id, voice_mode=False, mode_id=mode_id)

    async def _generate_response(
        self,
        user_text: str,
        task_id: str,
        voice_mode: bool = False,
        mode_id: str = "normal",
    ) -> None:
        """
        Generate a response, optionally using the voice pipeline.

        When ``voice_mode`` is True the pipeline prefers VOICE_FAST for low
        complexity turns, but allows escalation for harder requests.
        RAG retrieval is skipped for simple queries (complexity below
        ``voice_skip_rag_below``), web search only fires on explicit intent,
        and the CriticAgent is bypassed.

        For non-direct reasoning strategies (chain_of_thought, tree_of_thought,
        consensus, escalation), the ReasoningOrchestrator handles multi-step
        execution and emits reasoning events to the bus.

        Args:
            user_text: The user's input text.
            task_id: Correlation task ID.
            voice_mode: Force VOICE_FAST tier and lightweight pipeline.
            mode_id: Operational mode ID (ignored in voice_mode; defaults to "normal").
        """
        from observability.tracing import get_tracer

        _span = get_tracer("emily").start_span("conversation.generate")
        _span.set_attribute("task_id", task_id)
        _span.set_attribute("voice_mode", str(voice_mode))

        t0 = time.monotonic()
        routing_cfg = self._fleet._config.routing

        await self._memory.add_user_turn(user_text, importance=0.6)

        # Detect user emotional signals before generating response
        emotions = get_emotional_state()
        if _FRUSTRATION_RE.search(user_text):
            emotions.on_user_frustration()
        elif _POSITIVE_RE.search(user_text):
            emotions.on_user_positive_signal()

        # Resolve operational mode
        mode_engine = get_mode_engine()
        active_mode = mode_engine.get("voice" if voice_mode else mode_id)

        # Derive urgency from emotional concern — high concern = prefer smarter model
        urgency = min(1.0, emotions.state.concern * 1.5)
        routing = self._fleet.route(user_text, voice_mode=voice_mode, urgency=urgency)
        skip_rag = voice_mode and routing.complexity_score < routing_cfg.voice_skip_rag_below

        if voice_mode and routing.complexity_score < routing_cfg.voice_fast_complexity_threshold:
            force_tier: ModelTier | None = ModelTier.VOICE_FAST
        else:
            force_tier = None

        if skip_rag:
            rag_chunks: list[dict[str, Any]] = []
        else:
            rag_chunks = await self._memory.retrieve_context(user_text)

        # Cross-session recall when user asks about past conversations
        if self._memory.has_recall_intent(user_text):
            recall_chunks = await self._memory.recall_cross_session(user_text)
            rag_chunks = recall_chunks + rag_chunks

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
        emotions = get_emotional_state()
        emotional_state = {
            "engagement": emotions.state.engagement,
            "confidence": emotions.state.confidence,
            "concern": emotions.state.concern,
            "enthusiasm": emotions.state.enthusiasm,
        }
        # Inject live system profile so Emily knows the host hardware
        _sys_excerpt: str | None = None
        try:
            from plugins.builtin.system_profiler import get_scheduler

            _sched = get_scheduler()
            if _sched is not None:
                _sys_excerpt = _sched.get_summary_excerpt()
        except Exception:
            pass

        if effective_tier == ModelTier.REASONING:
            system_prompt = self._prompts.get_reasoning_system_prompt(  # noqa
                user_profile=self._memory.procedural.user_profile,
                system_profile_excerpt=_sys_excerpt,
            )
        else:
            system_prompt = self._prompts.get_system_prompt(  # noqa
                user_profile=self._memory.procedural.user_profile,
                emotional_state=emotional_state,
                system_profile_excerpt=_sys_excerpt,
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

        use_orchestrator = active_mode.reasoning_strategy != "direct" and not voice_mode

        if use_orchestrator:
            # ── Non-direct strategy: delegate to ReasoningOrchestrator ──
            async def _emit_reasoning_event(event: ReasoningEvent) -> None:
                await self._bus.send_to(
                    recipient="*",
                    msg_type="reasoning.event",
                    payload={
                        "event_type": event.event_type,
                        "step_name": event.step_name,
                        "model": event.model,
                        "content": event.content[:500],
                        "metadata": event.metadata,
                        "task_id": task_id,
                    },
                    sender=self.name,
                    priority=Priority.NORMAL,
                )

            ctx = ReasoningContext(
                mode=active_mode,
                skill_id="normal",
                user_text=user_text,
                messages=messages,
                system_prompt=system_prompt,
                rag_context=context_block,
                temperature=active_mode.temperature_override,
                max_tokens=active_mode.max_tokens_override,
            )
            result = await self._orchestrator.execute(
                strategy=active_mode.reasoning_strategy,
                context=ctx,
                event_emitter=_emit_reasoning_event,
            )
            full_response = result.text

            # Send complete response to TTS
            if full_response:
                await self._bus.send_to(
                    recipient="tts",
                    msg_type="tts.speak",
                    payload={"text": full_response, "task_id": task_id},
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

            self._log.info(
                "orchestrator_complete",
                strategy=active_mode.reasoning_strategy,
                models_used=result.models_used,
                total_tokens=result.total_tokens,
                latency_ms=f"{result.total_latency_ms:.0f}",
            )
        else:
            # ── Direct strategy: sentence-streaming for TTS pacing ──────
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
            _span.end()
            return

        skip_critic = (voice_mode and routing_cfg.voice_skip_critic) or (
            use_orchestrator and not active_mode.enable_critic
        )
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
                "mode_id": active_mode.name,
                "reasoning_strategy": active_mode.reasoning_strategy,
                "latency_ms": (time.monotonic() - t0) * 1000,
            },
        )

        # Update emotional state based on response outcome
        if critic_score >= 0.7:
            get_emotional_state().on_successful_task()
        elif critic_score < 0.5:
            get_emotional_state().on_failed_task()
            # Log capability gap for very poor responses
            if self._self_improvement is not None and critic_score < 0.3:
                self._self_improvement.log_capability_gap(
                    gap_type="model_limitation",
                    description=f"Low critic score ({critic_score:.2f}) on: {user_text[:100]}",
                    context={
                        "tier": effective_tier.value,
                        "model": routing.model_name,
                        "critic_score": critic_score,
                    },
                )

        # Self-improvement: record LLM outcome + RAG quality
        elapsed_ms = (time.monotonic() - t0) * 1000
        if self._self_improvement is not None:
            self._self_improvement.record_llm_outcome(
                model_tier=effective_tier.value,
                latency_ms=elapsed_ms,
                critic_score=critic_score,
                prompt_slot="conversation",
                prompt_version="v1",
            )
            for chunk in rag_chunks:
                self._self_improvement.record_rag_retrieval(
                    chunk_id=chunk.get("chunk_id", "unknown"),
                    source=chunk.get("source", "unknown"),
                    query=user_text[:200],
                    relevance_score=chunk.get("score", 0.0),
                    used=True,
                )

        # Fact extraction every 5th turn (background, non-blocking)
        self._turn_count += 1
        if self._turn_count % 5 == 0 and not voice_mode:
            asyncio.create_task(self._extract_user_facts(user_text, final_response))

        self._log.info(
            "response_complete",
            response_len=len(final_response),
            voice_mode=voice_mode,
            critic_score=f"{critic_score:.2f}",
            elapsed_ms=f"{elapsed_ms:.0f}",
        )

        # Record latency breakdown for the dashboard
        try:
            from api.app import record_latency_breakdown

            record_latency_breakdown(
                {
                    "llm_total_ms": round(elapsed_ms, 1),
                    "model": effective_tier.value
                    if hasattr(effective_tier, "value")
                    else str(effective_tier),
                    "tier": effective_tier.value
                    if hasattr(effective_tier, "value")
                    else str(effective_tier),
                    "voice_mode": voice_mode,
                    "critic_score": round(critic_score, 3),
                    "total_ms": round(elapsed_ms, 1),
                }
            )
        except Exception:
            pass  # Dashboard not available (CLI mode)

        _span.end()

    async def _execute_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Execute a tool from the plugin registry.

        Tools with ``requires_approval=True`` wait for user consent via the
        agent bus (SSE to frontend → user clicks approve/deny → response).
        Timeout after 30s defaults to deny.

        Args:
            tool_name: Name of the tool to execute.
            params: Parameters for the tool.

        Returns:
            Tool output on success.

        Raises:
            ValueError: If tool is not found.
            RuntimeError: If tool execution fails or is denied.
        """
        tool = self._plugin_registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Approval gate for high-risk tools
        if tool.requires_approval:
            dry_run_explanation = await tool.dry_run(params)
            approved = await self._request_tool_approval(tool_name, params, dry_run_explanation)
            if not approved:
                raise RuntimeError(f"User denied execution of '{tool_name}'")

        session_id = self._memory.working.session_id
        allowed_paths = (
            self._settings.tools.allowed_paths
            if self._settings and hasattr(self._settings, "tools")
            else []
        )
        sandbox_enabled = (
            self._settings.tools.sandbox != "none"
            if self._settings and hasattr(self._settings, "tools")
            else True
        )

        ctx = ExecutionContext(
            session_id=session_id,
            allowed_paths=allowed_paths,
            sandbox_enabled=sandbox_enabled,
        )
        result = await tool.safe_execute(params, ctx)
        if not result.success:
            raise RuntimeError(result.error or "Tool execution failed")
        return result.output

    async def _request_tool_approval(
        self,
        tool_name: str,
        params: dict[str, Any],
        dry_run: str,
    ) -> bool:
        """Request user approval for a tool execution.

        Stores a pending approval event and sends a bus message.
        The API layer (SSE) forwards this to the frontend, which calls
        ``resolve_tool_approval()`` with the user's decision.

        Returns:
            True if approved, False if denied or timed out.
        """
        event = asyncio.Event()
        self._pending_approval = {"event": event, "approved": False}

        await self._bus.send_to(
            recipient="ConversationAgent",
            msg_type="tool.approval_request",
            payload={
                "tool_name": tool_name,
                "parameters": params,
                "dry_run_explanation": dry_run,
            },
            sender=self.name,
            priority=Priority.HIGH,
        )
        self._log.info("tool_approval_requested", tool=tool_name, dry_run=dry_run[:100])

        try:
            await asyncio.wait_for(event.wait(), timeout=30.0)
        except TimeoutError:
            self._log.warning("tool_approval_timeout", tool=tool_name)
            return False
        finally:
            result = self._pending_approval.get("approved", False)
            self._pending_approval = {}
        return result

    def resolve_tool_approval(self, approved: bool) -> None:
        """Called by the API layer when the user approves or denies a tool.

        Args:
            approved: True if user approved, False if denied.
        """
        if self._pending_approval and "event" in self._pending_approval:
            self._pending_approval["approved"] = approved
            self._pending_approval["event"].set()

    async def _extract_user_facts(self, user_text: str, response_text: str) -> None:
        """Extract factual information about the user and store in procedural memory.

        Runs in background via the NANO tier to minimize overhead.
        """
        try:
            from llm.client import ChatMessage

            messages = [
                ChatMessage(
                    role="system",
                    content=(
                        "Extract any NEW factual information about the user from this "
                        "conversation exchange. Return a JSON object where keys are fact "
                        "categories (name, location, job, preference, hobby, goal, etc.) "
                        "and values are the extracted facts. If no new facts are present, "
                        "return an empty JSON object: {}"
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=f"User said: {user_text}\n\nAssistant replied: {response_text[:500]}",
                ),
            ]

            result = await self._fleet.chat(
                user_message="extract user facts",
                messages=messages,
                force_tier=ModelTier.NANO,
                max_tokens=256,
            )

            import json

            try:
                facts = json.loads(result.content)
            except json.JSONDecodeError:
                return

            if not isinstance(facts, dict) or not facts:
                return

            for key, value in facts.items():
                if isinstance(key, str) and value:
                    await self._memory.procedural.set_user_fact(key, value)

            self._log.info("user_facts_extracted", n_facts=len(facts))
        except Exception as exc:
            self._log.debug("fact_extraction_failed", error=str(exc))

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
