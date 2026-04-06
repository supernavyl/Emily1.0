"""Emily LLM provider — routes voice queries through Emily's LLMFleet + memory."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from voice_engine.processing.anti_parrot import filter_voice_parroting
from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# Autobiography cache with mtime-based invalidation.
# ReflectionAgent writes to data/autobiography.md — we detect changes via file mtime.
_autobiography_text: str | None = None
_autobiography_mtime: float = 0.0
_AUTOBIOGRAPHY_PATH = Path("data/autobiography.md")


def _get_autobiography() -> str:
    """Return Emily's living autobiography, reloading when the file changes on disk."""
    global _autobiography_text, _autobiography_mtime
    try:
        current_mtime = _AUTOBIOGRAPHY_PATH.stat().st_mtime if _AUTOBIOGRAPHY_PATH.exists() else 0.0
    except OSError:
        current_mtime = 0.0

    if _autobiography_text is None or current_mtime != _autobiography_mtime:
        try:
            from persona.autobiography import AutobiographyManager

            mgr = AutobiographyManager()
            mgr.load_sync()
            _autobiography_text = mgr.get_for_prompt()
            _autobiography_mtime = current_mtime
        except Exception:
            logger.warning("autobiography_load_failed", exc_info=True)
            _autobiography_text = ""
            _autobiography_mtime = current_mtime
    return _autobiography_text


# System query regex — moved to module level to avoid recompilation per call
_SYS_QUERY_RE = re.compile(
    r"\b(cpu|gpu|ram|memory|vram|disk|storage|temperature|temp|"
    r"nvidia|rtx|cores?|threads?|utilization|hardware|system\s*info|"
    r"how much memory|how much ram|what gpu|what cpu|specs?)\b",
    re.IGNORECASE,
)


class EmilyLLMProvider(LLMProvider):
    """Wraps Emily's LLMFleet behind the VoiceEngine LLMProvider interface.

    Adds: model routing, persona-driven system prompt, RAG context,
    5-tier memory reads/writes on every voice turn, and voice tool execution.
    """

    def __init__(
        self,
        fleet: Any,
        memory: Any,
        prompt_builder: Any,
        persona: Any | None = None,
        emotional_state: Any | None = None,
        identity_manager: Any | None = None,
        tool_orchestrator: Any | None = None,
    ) -> None:
        self._fleet = fleet
        self._memory = memory
        self._prompt_builder = prompt_builder
        self._persona = persona
        self._emotional_state = emotional_state
        self._identity_manager = identity_manager
        self._tool_orchestrator = tool_orchestrator
        logger.info(
            "EmilyLLMProvider initialised (fleet=%s, tools=%s)",
            type(fleet).__name__,
            "enabled" if tool_orchestrator else "disabled",
        )

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str = "",
    ) -> AsyncIterator[str]:
        """Stream an LLM response using Emily's full brain.

        1. Write user turn to memory
        2. Retrieve RAG context
        3. Build persona-aware voice system prompt
        4. Route through LLMFleet (voice_mode=True)
        5. Strip <think> blocks
        6. Write assistant turn to memory after stream ends
        """
        from llm.client import ChatMessage

        # Extract the latest user message
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        if not user_text:
            return

        # 0. Voice tool interception — check before anything else
        if self._tool_orchestrator and self._tool_orchestrator.matches_tool_intent(user_text):
            tool_stream = await self._tool_orchestrator.handle_voice_tool(user_text, messages)
            if tool_stream is not None:
                # Write user turn to memory, then yield tool tokens
                try:
                    await self._memory.add_user_turn(user_text, importance=0.7)
                except Exception as exc:
                    logger.warning("memory_add_user_failed: %s", exc)

                full_response: list[str] = []
                async for token in tool_stream:
                    full_response.append(token)
                    yield token

                # Write assistant turn to memory
                response_text = "".join(full_response).strip()
                if response_text:
                    try:
                        await self._memory.add_assistant_turn(
                            response_text,
                            importance=0.8,
                            metadata={"source": "voice_tool"},
                        )
                    except Exception as exc:
                        logger.warning("memory_add_assistant_failed: %s", exc)
                return

        # 1. Write user turn to memory
        try:
            await self._memory.add_user_turn(user_text, importance=0.7)
        except Exception as exc:
            logger.warning("memory_add_user_failed: %s", exc)

        # 2. Retrieve RAG context + cross-session recall
        memory_context = ""
        try:
            rag_chunks = await self._memory.retrieve_context(user_text, top_k=3)
            if rag_chunks:
                context_lines = [f"- {c.get('content', '')[:200]}" for c in rag_chunks]
                memory_context = "Relevant context from memory:\n" + "\n".join(context_lines)
        except Exception as exc:
            logger.warning("memory_retrieve_failed: %s", exc)

        # Cross-session recall — search past conversations when user asks
        try:
            if self._memory.has_recall_intent(user_text):
                recall_chunks = await self._memory.recall_cross_session(user_text)
                if recall_chunks:
                    recall_lines = [f"- {c.get('content', '')[:300]}" for c in recall_chunks]
                    recall_block = "From past conversations:\n" + "\n".join(recall_lines)
                    memory_context = (
                        (memory_context + "\n\n" + recall_block) if memory_context else recall_block
                    )
        except Exception as exc:
            logger.warning("cross_session_recall_failed: %s", exc)

        # 3. Build Emily's persona-aware voice system prompt
        emotion_context = None
        if self._emotional_state:
            try:
                state = self._emotional_state.state
                emotion_context = (
                    f"Your current emotional state — "
                    f"engagement: {state.engagement:.1f}, "
                    f"confidence: {state.confidence:.1f}, "
                    f"enthusiasm: {state.enthusiasm:.1f}."
                )
            except Exception:
                logger.warning("emotional_state_load_failed", exc_info=True)

        ai_name = "Emily"
        if self._identity_manager is not None:
            try:
                ai_name = self._identity_manager.ai_name or "Emily"
            except Exception:
                logger.warning("identity_manager_failed", exc_info=True)

        # Inject the living autobiography — the real personality carrier
        autobiography = _get_autobiography()
        style_parts: list[str] = []
        if autobiography:
            style_parts.append(f"WHO I AM:\n{autobiography}")

        # Inject persona traits if available
        if self._persona:
            try:
                traits = self._persona.personality
                style_parts.append(self._prompt_builder._format_persona_injection(traits))
            except Exception:
                logger.warning("persona_traits_load_failed", exc_info=True)

        style_instructions = "\n\n".join(p for p in style_parts if p) or None

        # Inject user profile so Emily knows who she's talking to
        user_profile = None
        try:
            profile = self._memory.procedural.user_profile
            if profile and profile.get("name"):
                user_profile = profile
        except Exception:
            logger.warning("user_profile_load_failed", exc_info=True)

        # Inject live system profile ONLY when the user is asking about hardware/system
        _sys_excerpt: str | None = None
        if _SYS_QUERY_RE.search(user_text):
            try:
                from plugins.builtin.system_profiler import get_scheduler

                _sched = get_scheduler()
                if _sched is not None:
                    _sys_excerpt = _sched.get_summary_excerpt()
            except Exception:
                logger.warning("system_profiler_load_failed", exc_info=True)

        # 3.5 Route through ModelRouter — unified routing for all paths
        from llm.router import ModelTier, RoutingDecision

        # Derive urgency from emotional state concern dimension
        urgency = 0.5
        if self._emotional_state:
            try:
                urgency = min(1.0, self._emotional_state.state.concern * 1.5)
            except Exception:
                logger.debug("urgency_derivation_failed", exc_info=True)

        routing: RoutingDecision = self._fleet.route(
            user_text, voice_mode=True, urgency=urgency,
        )
        tier = routing.tier
        is_heavy = tier in (ModelTier.SMART, ModelTier.REASONING, ModelTier.DEEP_THINK)
        import time as _time
        _t0 = _time.monotonic()

        # Inject config intelligence — Emily's knowledge of her own config
        _config_excerpt: str | None = None
        if routing.complexity_score >= 5:
            try:
                from perception.system.config_store import get_config_store

                _cstore = get_config_store()
                if _cstore is not None:
                    _config_excerpt = _cstore.get_excerpt() or None
            except Exception:
                logger.warning("config_store_load_failed", exc_info=True)

        voice_system = self._prompt_builder.build_voice_system_prompt(
            emotion_context=emotion_context,
            style_instructions=style_instructions,
            memory_context=memory_context or None,
            ai_name=ai_name,
            user_profile=user_profile,
            system_profile_excerpt=_sys_excerpt,
            config_excerpt=_config_excerpt,
        )

        # 4. Convert message history to ChatMessage objects, enforcing context budget
        from voice_engine.processing.think_filter import strip_think_tags

        max_tok = 1200 if is_heavy else 800

        # Context window budget: 8B=8192, 27B=32768. Reserve for system + max_tokens.
        ctx_limit = 32768 if is_heavy else 8192
        system_tokens = len(voice_system) // 4
        budget = ctx_limit - system_tokens - max_tok

        chat_messages: list[ChatMessage] = [
            ChatMessage(role="system", content=voice_system),
        ]
        # Collect non-system messages, then trim oldest if over budget
        history_msgs: list[dict[str, str]] = [m for m in messages if m.get("role") != "system"]
        # Walk backwards (newest first) and keep messages that fit
        kept: list[ChatMessage] = []
        used_tokens = 0
        for msg in reversed(history_msgs):
            content = msg.get("content", "")
            msg_tokens = len(content) // 4 + 4  # +4 for role/framing overhead
            if used_tokens + msg_tokens > budget:
                break
            kept.append(ChatMessage(role=msg.get("role", "user"), content=content))
            used_tokens += msg_tokens
        kept.reverse()
        chat_messages.extend(kept)

        if len(kept) < len(history_msgs):
            logger.debug(
                "context_trim: kept %d/%d messages (%d est tokens, budget %d)",
                len(kept),
                len(history_msgs),
                used_tokens,
                budget,
            )

        # 5. Stream via LLMFleet — simple questions use the 8B voice_fast model;
        # hard questions escalate to the 27B smart model (already VRAM-resident).
        # The 14B fast tier is deliberately skipped — it can't coexist with the
        # 27B on a 24 GB card without triggering Ollama 500 errors.
        full_response: list[str] = []

        async def _raw_stream() -> AsyncIterator[str]:
            async for token in self._fleet.chat_stream(
                user_message=user_text,
                messages=chat_messages,
                force_tier=tier,
                max_tokens=max_tok,
            ):
                yield token

        try:
            cleaned_stream = filter_voice_parroting(
                strip_think_tags(_raw_stream()),
                user_text=user_text,
            )
            async for token in cleaned_stream:
                full_response.append(token)
                yield token
        except Exception as exc:
            logger.error("fleet_stream_error: %s", exc)
            yield "Sorry, I had trouble processing that. Could you say that again?"

        # 6. Write assistant turn to memory
        response_text = "".join(full_response).strip()
        if response_text:
            try:
                await self._memory.add_assistant_turn(
                    response_text,
                    importance=0.8,
                    metadata={
                        "source": "voice_engine",
                        "tier": routing.tier.value,
                        "model": routing.model_name,
                        "complexity": routing.complexity_score,
                        "latency_ms": round((_time.monotonic() - _t0) * 1000),
                    },
                )
            except Exception as exc:
                logger.warning("memory_add_assistant_failed: %s", exc)
