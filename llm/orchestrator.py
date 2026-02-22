"""
Streaming LLM orchestrator for Emily's voice conversation engine.

Manages LLM inference for real-time conversation with:
- Streaming output chunked at sentence boundaries for TTS
- Interrupt-safe: can abandon generation mid-stream
- Speculative pre-generation when turn probability reaches 0.65
- Context assembly with emotion, rhythm, memory, and persona
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

from observability.logger import get_logger
from conversation.emotion_sync import ResponseStyleParameters
from perception.audio.emotion_detector import EmotionState

log = get_logger(__name__)


@dataclass
class GenerationConfig:
    """Configuration for the LLM orchestrator."""

    fast_model: str = "qwen3:14b"
    smart_model: str = "qwq:latest"
    ollama_base_url: str = "http://localhost:11434"
    max_tokens: int = 512
    temperature: float = 0.7
    speculative_start_probability: float = 0.65


class ConversationLLMOrchestrator:
    """
    Streaming LLM interface with interrupt awareness and speculative generation.

    Yields complete sentences (not individual tokens) for TTS handoff.
    Monitors an interrupt signal every iteration and stops cleanly if set.
    """

    def __init__(
        self,
        config: GenerationConfig | None = None,
        client: Any | None = None,
    ) -> None:
        """
        Args:
            config: Generation configuration.
            client: Pre-built LLM client satisfying
                :class:`~llm.base.LLMClientProtocol`.  When *None*, a default
                :class:`~llm.client.OllamaClient` is created lazily.
        """
        self.config = config or GenerationConfig()
        self._client: Any = client
        self._conversation_history: list[dict[str, str]] = []
        self._speculative_cache: str | None = None
        self._speculative_transcript: str | None = None

    async def _ensure_client(self) -> Any:
        """Return the injected client or lazily create an OllamaClient."""
        if self._client is None:
            try:
                from llm.client import OllamaClient
                self._client = OllamaClient(base_url=self.config.ollama_base_url)
            except ImportError:
                log.error("ollama_client_not_available")
                raise
        return self._client

    async def generate_streaming(
        self,
        transcript: Any = None,
        emotion: EmotionState | None = None,
        style: ResponseStyleParameters | None = None,
        interrupt_signal: asyncio.Event | None = None,
        memory_context: str = "",
    ) -> AsyncIterator[str]:
        """
        Generate a streaming response, yielding complete sentences.

        Args:
            transcript: FinalTranscript from STT.
            emotion: Detected user emotion.
            style: Emotional response style parameters.
            interrupt_signal: Event to monitor for interrupts.
            memory_context: Retrieved memory/context.

        Yields:
            Complete sentence strings for TTS.
        """
        user_text = transcript.text if transcript else ""
        if not user_text:
            return

        system_prompt = self._build_system_prompt(emotion, style, memory_context)

        self._conversation_history.append({"role": "user", "content": user_text})
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-16:]

        try:
            client = await self._ensure_client()
            from llm.client import ChatMessage

            messages = [ChatMessage(role="system", content=system_prompt)]
            for msg in self._conversation_history:
                messages.append(ChatMessage(role=msg["role"], content=msg["content"]))

            buffer = ""
            full_response = ""

            async for chunk in client.chat_stream(
                model=self.config.fast_model,
                messages=messages,
                max_tokens=self.config.max_tokens,
            ):
                if interrupt_signal and interrupt_signal.is_set():
                    log.info("llm_generation_interrupted")
                    break

                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                buffer += text
                full_response += text

                sentences = self._extract_sentences(buffer)
                if len(sentences) > 1:
                    for sent in sentences[:-1]:
                        sent = sent.strip()
                        if sent:
                            yield sent
                    buffer = sentences[-1]

            remaining = buffer.strip()
            if remaining:
                yield remaining

            if full_response.strip():
                self._conversation_history.append({
                    "role": "assistant",
                    "content": full_response.strip(),
                })

        except Exception as exc:
            log.error("llm_generation_error", error=str(exc))
            yield "I'm sorry, I had trouble with that. Could you say that again?"

    def _build_system_prompt(
        self,
        emotion: EmotionState | None,
        style: ResponseStyleParameters | None,
        memory_context: str,
    ) -> str:
        """Assemble the full system prompt with context."""
        parts = [
            "You are Emily, a warm and attentive conversational AI. "
            "You are speaking out loud, not writing. Keep responses concise — "
            "1-3 sentences is ideal. Be natural and conversational."
        ]

        if emotion is not None:
            emotion_name = emotion.primary.value
            if emotion.confidence > 0.5:
                parts.append(
                    f"The user seems {emotion_name}. "
                    "Respond appropriately to their emotional state."
                )

        if style is not None:
            from conversation.emotion_sync import EmotionSynchronizer
            sync = EmotionSynchronizer()
            style_inst = sync.get_llm_style_instructions(style)
            if style_inst:
                parts.append(style_inst)

        if memory_context:
            parts.append(f"Relevant context: {memory_context}")

        return " ".join(parts)

    @staticmethod
    def _extract_sentences(text: str) -> list[str]:
        """Split text at sentence boundaries."""
        import re
        parts = re.split(r'(?<=[.!?])\s+', text)
        return parts if parts else [text]

    async def start_speculative(
        self,
        partial_transcript: str,
        emotion: EmotionState | None = None,
    ) -> None:
        """
        Begin speculative pre-generation from partial transcript.

        Called when turn probability reaches 0.65.

        Args:
            partial_transcript: Partial STT text.
            emotion: Current detected emotion.
        """
        self._speculative_transcript = partial_transcript
        self._speculative_cache = None

        try:
            client = await self._ensure_client()
            from llm.client import ChatMessage

            messages = [
                ChatMessage(
                    role="system",
                    content="You are Emily. Respond briefly and conversationally.",
                ),
                ChatMessage(role="user", content=partial_transcript),
            ]

            response = ""
            async for chunk in client.chat_stream(
                model=self.config.fast_model,
                messages=messages,
                max_tokens=self.config.max_tokens,
            ):
                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                response += text
                if len(response) > 200:
                    break

            self._speculative_cache = response
            log.debug(
                "speculative_generation_cached",
                transcript_preview=partial_transcript[:50],
                cache_len=len(response),
            )
        except Exception as exc:
            log.debug("speculative_generation_failed", error=str(exc))

    def check_speculative_match(self, final_transcript: str) -> str | None:
        """
        Check if the speculative cache matches the final transcript.

        Uses edit distance to determine if the speculation is usable.

        Args:
            final_transcript: The committed final transcript.

        Returns:
            Cached response if match is close enough, else None.
        """
        if self._speculative_cache is None or self._speculative_transcript is None:
            return None

        distance = self._edit_distance(
            self._speculative_transcript.lower(),
            final_transcript.lower(),
        )
        max_len = max(len(self._speculative_transcript), len(final_transcript), 1)
        divergence = distance / max_len

        if divergence < 0.2:
            log.info("speculative_cache_hit", divergence=f"{divergence:.2f}")
            return self._speculative_cache

        log.debug("speculative_cache_miss", divergence=f"{divergence:.2f}")
        self._speculative_cache = None
        return None

    @staticmethod
    def _edit_distance(a: str, b: str) -> int:
        """Compute Levenshtein edit distance."""
        n, m = len(a), len(b)
        if n == 0:
            return m
        if m == 0:
            return n

        prev = list(range(m + 1))
        curr = [0] * (m + 1)

        for i in range(1, n + 1):
            curr[0] = i
            for j in range(1, m + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            prev, curr = curr, prev

        return prev[m]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()
        self._speculative_cache = None

    async def close(self) -> None:
        """Close the LLM client."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
