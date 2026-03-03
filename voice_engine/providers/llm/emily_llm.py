"""Emily LLM provider — routes voice queries through Emily's LLMFleet + memory."""

from __future__ import annotations

import contextlib
import logging
import re
from typing import TYPE_CHECKING, Any

from voice_engine.providers.base import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# Same complexity gate as audio.py — 8B for simple voice, 27B for hard questions
_COMPLEX_VOICE_RE = re.compile(
    r"\b(explain|analyze|analyse|compare|difference|between|because|"
    r"why|how does|how do|what causes|calculate|derive|prove|argue|"
    r"evaluate|summarize|summarise|elaborate|break.?down|"
    r"step.?by.?step|walk me through|pros.?and.?cons|"
    r"advantages|disadvantages|trade.?off|in detail|"
    r"code|program|function|algorithm|debug|refactor|"
    r"math|integral|equation|probability|statistics)\b",
    re.IGNORECASE,
)


def _is_complex_voice_query(text: str) -> bool:
    """Return True if this voice turn should use the 27B smart model."""
    return len(text.split()) > 25 or bool(_COMPLEX_VOICE_RE.search(text))


class EmilyLLMProvider(LLMProvider):
    """Wraps Emily's LLMFleet behind the VoiceEngine LLMProvider interface.

    Adds: model routing, persona-driven system prompt, RAG context, and
    5-tier memory reads/writes on every voice turn.
    """

    def __init__(
        self,
        fleet: Any,
        memory: Any,
        prompt_builder: Any,
        persona: Any | None = None,
        emotional_state: Any | None = None,
        identity_manager: Any | None = None,
    ) -> None:
        self._fleet = fleet
        self._memory = memory
        self._prompt_builder = prompt_builder
        self._persona = persona
        self._emotional_state = emotional_state
        self._identity_manager = identity_manager
        logger.info("EmilyLLMProvider initialised (fleet=%s)", type(fleet).__name__)

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

        # 1. Write user turn to memory
        try:
            await self._memory.add_user_turn(user_text, importance=0.6)
        except Exception as exc:
            logger.debug("memory_add_user_failed: %s", exc)

        # 2. Retrieve RAG context
        memory_context = ""
        try:
            rag_chunks = await self._memory.retrieve_context(user_text, top_k=3)
            if rag_chunks:
                context_lines = [f"- {c.get('content', '')[:200]}" for c in rag_chunks]
                memory_context = "Relevant context from memory:\n" + "\n".join(context_lines)
        except Exception as exc:
            logger.debug("memory_retrieve_failed: %s", exc)

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
                pass

        ai_name = "Emily"
        if self._identity_manager is not None:
            with contextlib.suppress(Exception):
                ai_name = self._identity_manager.ai_name or "Emily"

        voice_system = self._prompt_builder.build_voice_system_prompt(
            emotion_context=emotion_context,
            memory_context=memory_context or None,
            ai_name=ai_name,
        )

        # 4. Convert message history to ChatMessage objects
        chat_messages: list[ChatMessage] = [
            ChatMessage(role="system", content=voice_system),
        ]
        # Include recent conversation history (skip system messages from voice engine)
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue
            chat_messages.append(ChatMessage(role=role, content=content))

        # 5. Stream via LLMFleet — simple questions use the 8B voice_fast model;
        # hard questions escalate to the 27B smart model (already VRAM-resident).
        # The 14B fast tier is deliberately skipped — it can't coexist with the
        # 27B on a 24 GB card without triggering Ollama 500 errors.
        from llm.router import ModelTier
        from voice_engine.processing.think_filter import strip_think_tags

        full_response: list[str] = []

        complex_query = _is_complex_voice_query(user_text)
        tier = ModelTier.SMART if complex_query else ModelTier.VOICE_FAST
        max_tok = 1200 if complex_query else 800

        async def _raw_stream() -> AsyncIterator[str]:
            async for token in self._fleet.chat_stream(
                user_message=user_text,
                messages=chat_messages,
                force_tier=tier,
                max_tokens=max_tok,
            ):
                yield token

        try:
            async for token in strip_think_tags(_raw_stream()):
                full_response.append(token)
                yield token
        except Exception as exc:
            logger.error("fleet_stream_error: %s", exc)

        # 6. Write assistant turn to memory
        response_text = "".join(full_response).strip()
        if response_text:
            try:
                await self._memory.add_assistant_turn(
                    response_text,
                    importance=0.7,
                    metadata={"source": "voice_engine"},
                )
            except Exception as exc:
                logger.debug("memory_add_assistant_failed: %s", exc)
