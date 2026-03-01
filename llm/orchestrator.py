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
import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from observability.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from conversation.emotion_sync import ResponseStyleParameters
    from perception.audio.emotion_detector import EmotionState

log = get_logger(__name__)


@dataclass
class GenerationConfig:
    """Configuration for the LLM orchestrator."""

    fast_model: str = "Qwen2.5-14B-Instruct-abliterated"
    smart_model: str = "QwQ-32B-abliterated"
    ollama_base_url: str = "http://localhost:11434"
    tabbyapi_base_url: str = "http://localhost:5000"
    tabbyapi_api_key: str = ""
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
        """Return the injected client or lazily create a TabbyAPIClient."""
        if self._client is None:
            try:
                from llm.tabbyapi_client import TabbyAPIClient

                self._client = TabbyAPIClient(
                    base_url=self.config.tabbyapi_base_url,
                    api_key=self.config.tabbyapi_api_key,
                )
            except ImportError:
                log.error("tabbyapi_client_not_available")
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

        system_prompt = self._build_system_prompt(emotion, style, memory_context)  # noqa

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
            raw_buf = ""  # accumulates raw tokens for <think> tag detection
            in_thinking = False
            last_yield_time = asyncio.get_event_loop().time()

            async for chunk in client.chat_stream(
                model=self.config.fast_model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                enable_thinking=False,
            ):
                if interrupt_signal and interrupt_signal.is_set():
                    log.info("llm_generation_interrupted")
                    break

                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                full_response += text
                raw_buf += text

                # Strip <think>...</think> blocks — Qwen3/QwQ emit these
                # and they must never reach TTS.  Uses raw_buf to handle
                # tags that arrive split across multiple chunks.
                clean = ""
                while raw_buf:
                    if in_thinking:
                        end_idx = raw_buf.find("</think>")
                        if end_idx == -1:
                            # Might be a partial closing tag at the tail
                            if raw_buf.endswith(
                                ("<", "</", "</t", "</th", "</thi", "</thin", "</think")
                            ):
                                break  # wait for more tokens
                            raw_buf = ""
                            break
                        in_thinking = False
                        raw_buf = raw_buf[end_idx + len("</think>") :]
                        continue

                    start_idx = raw_buf.find("<think>")
                    if start_idx == -1:
                        # Check for partial opening tag at the tail
                        for i in range(1, min(len("<think>"), len(raw_buf)) + 1):
                            if "<think>".startswith(raw_buf[-i:]):
                                clean += raw_buf[:-i]
                                raw_buf = raw_buf[-i:]
                                break
                        else:
                            clean += raw_buf
                            raw_buf = ""
                        break

                    clean += raw_buf[:start_idx]
                    in_thinking = True
                    raw_buf = raw_buf[start_idx + len("<think>") :]

                if not clean:
                    continue

                buffer += clean

                sentences = self._extract_sentences(buffer)
                if len(sentences) > 1:
                    for sent in sentences[:-1]:
                        sent = sent.strip()
                        if sent:
                            yield sent
                            last_yield_time = asyncio.get_event_loop().time()
                    buffer = sentences[-1]
                elif len(buffer) > 20 and asyncio.get_event_loop().time() - last_yield_time > 0.4:
                    yield buffer.strip()
                    buffer = ""
                    last_yield_time = asyncio.get_event_loop().time()

            remaining = buffer.strip()
            if remaining:
                yield remaining

            if full_response.strip():
                self._conversation_history.append(
                    {
                        "role": "assistant",
                        "content": full_response.strip(),
                    }
                )

        except Exception as exc:
            log.error("llm_generation_error", error=str(exc))
            return

    def _build_system_prompt(
        self,
        emotion: EmotionState | None,
        style: ResponseStyleParameters | None,
        memory_context: str,
    ) -> str:
        """Assemble the full system prompt with context."""
        emotion_context = None
        if emotion is not None:
            emotion_name = emotion.primary.value
            if emotion.confidence > 0.5:
                emotion_context = (
                    f"The user seems {emotion_name}. "
                    "Respond appropriately to their emotional state."
                )

        style_inst = None
        if style is not None:
            from conversation.emotion_sync import EmotionSynchronizer

            sync = EmotionSynchronizer()
            style_inst = sync.get_llm_style_instructions(style) or None

        from llm.prompt_builder import PromptBuilder

        return PromptBuilder().build_voice_system_prompt(
            emotion_context=emotion_context,
            style_instructions=style_inst,
            memory_context=memory_context or None,
        )

    @staticmethod
    def _extract_sentences(text: str) -> list[str]:
        """Split text at sentence boundaries."""
        import re

        parts = re.split(r"(?<=[.!?])\s+", text)
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
            in_thinking = False
            async for chunk in client.chat_stream(
                model=self.config.fast_model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                enable_thinking=False,
            ):
                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                # Strip <think> blocks from speculative cache (safety net)
                if "<think>" in text:
                    in_thinking = True
                if in_thinking:
                    if "</think>" in text:
                        in_thinking = False
                        after = text.split("</think>", 1)[-1]
                        if after:
                            response += after
                    continue
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
            with contextlib.suppress(Exception):
                await self._client.close()
            self._client = None
