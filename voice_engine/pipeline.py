"""Voice pipeline — STT -> LLM -> TTS orchestration with streaming."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger
from voice_engine.processing.breath_injector import (
    SAMPLE_RATE as BREATH_SAMPLE_RATE,
)
from voice_engine.processing.breath_injector import (
    BreathInjector,
    BreathSegment,
    SpeechSegment,
)
from voice_engine.processing.sentence_collector import SentenceCollector

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from voice_engine.processing.interruption import InterruptionHandler
    from voice_engine.providers.base import LLMProvider, STTProvider, TTSProvider

logger = get_logger(__name__)
# Inline voice switch tag: <voice:nicole>, <voice:sky>, etc.
_VOICE_TAG_RE = re.compile(r"<voice:(\w+)>", re.IGNORECASE)

# Strip paralinguistic stage directions the LLM likes to insert.
# Catches: [laughs], *laughs*, (laughs), *sighing*, [soft chuckle], etc.
_STAGE_DIRECTION_RE = re.compile(
    r"[\[\(*]"
    r"(?:laughs?|laughing|laughter|chuckles?|chuckling|giggles?|giggling"
    r"|sighs?|sighing|gasps?|gasping|groans?|groaning"
    r"|whispers?|whispering|hums?|humming|yawns?|yawning"
    r"|cries|crying|sniffles?|sniffling|coughs?|coughing"
    r"|clears?\s*throat|breaths?|breathing|inhales?|exhales?"
    r"|pauses?|pausing|beats?|silence|softly|gently|quietly"
    r"|smiles?|smiling|grins?|grinning|nods?|nodding"
    r"|soft\s+\w+|nervous\s+\w+|sad\s+\w+|happy\s+\w+)"
    r"[\]\)*]",
    re.IGNORECASE,
)


class VoicePipeline:
    """Orchestrates the STT -> LLM -> TTS streaming pipeline.

    Each stage runs concurrently: LLM tokens are collected into sentences by
    ``SentenceCollector``, and each sentence is synthesized by TTS as soon as
    it's ready, rather than waiting for the full LLM response.
    """

    def __init__(
        self,
        stt: STTProvider,
        llm: LLMProvider,
        tts: TTSProvider,
        interruption: InterruptionHandler,
        breath_injector: BreathInjector | None = None,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._interruption = interruption
        self._breath = breath_injector
        self._prev_sentence_len = 0
        self._cumulative_speech_s = 0.0
        logger.info("VoicePipeline initialised.")

    async def process(
        self,
        audio: np.ndarray,
        conversation_history: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
    ) -> tuple[str, np.ndarray]:
        """Run the full STT -> LLM -> TTS pipeline.

        Args:
            audio: Raw float32 audio from the microphone (16 kHz mono).
            conversation_history: Mutable list of ``{"role": ..., "content": ...}``
                messages. The user transcript is appended in-place.
            on_token: Optional callback invoked for each LLM token (for live UI).

        Returns:
            A tuple of ``(full_response_text, combined_audio)`` where
            ``combined_audio`` is the concatenated TTS output as float32.

        Raises:
            asyncio.CancelledError: If the interruption handler fires mid-stream.
        """
        self._prev_sentence_len = 0
        self._cumulative_speech_s = 0.0

        # ── Step 1: Speech-to-Text ────────────────────────────────
        logger.info("Pipeline: transcribing audio (%d samples) ...", len(audio))
        transcript = await self._stt.transcribe(audio, sample_rate=16000)

        if not transcript.strip():
            logger.info("Pipeline: empty transcript — skipping.")
            return ("", np.empty(0, dtype=np.float32))

        logger.info("Pipeline: user said: %s", transcript)
        conversation_history.append({"role": "user", "content": transcript})

        # ── Step 2: LLM Streaming → Sentence Collection → TTS ────
        collector = SentenceCollector()
        full_response: list[str] = []
        audio_parts: list[np.ndarray] = []

        # Extract system prompt from the first message if it exists
        system_prompt = ""
        llm_messages = conversation_history
        if conversation_history and conversation_history[0]["role"] == "system":
            system_prompt = conversation_history[0]["content"]
            llm_messages = conversation_history[1:]

        token_stream = self._llm.stream_response(llm_messages, system=system_prompt)
        wrapped_stream = self._interruption.wrap_stream(token_stream)

        async for token in wrapped_stream:
            full_response.append(token)

            if on_token is not None:
                on_token(token)

            sentences = collector.feed(token)
            for sentence in sentences:
                if self._breath is not None:
                    segments = self._breath.process(
                        sentence,
                        prev_sentence_len=self._prev_sentence_len,
                        cumulative_speech_s=self._cumulative_speech_s,
                    )
                    parts = await self._synthesize_segments(segments)
                    audio_parts.extend(parts)
                    self._prev_sentence_len = len(sentence)
                else:
                    audio_chunk = await self._synthesize_sentence(sentence)
                    if len(audio_chunk) > 0:
                        audio_parts.append(audio_chunk)

        # Flush remaining text in the collector
        remainder = collector.flush()
        if remainder:
            if self._breath is not None:
                segments = self._breath.process(
                    remainder,
                    prev_sentence_len=self._prev_sentence_len,
                    cumulative_speech_s=self._cumulative_speech_s,
                )
                parts = await self._synthesize_segments(segments)
                audio_parts.extend(parts)
            else:
                audio_chunk = await self._synthesize_sentence(remainder)
                if len(audio_chunk) > 0:
                    audio_parts.append(audio_chunk)

        response_text = "".join(full_response)
        logger.info("Pipeline: assistant response: %s", response_text[:120])

        # Append assistant response to history
        conversation_history.append({"role": "assistant", "content": response_text})

        combined_audio = (
            np.concatenate(audio_parts) if audio_parts else np.empty(0, dtype=np.float32)
        )

        return (response_text, combined_audio)

    async def _synthesize_segments(
        self,
        segments: list[SpeechSegment | BreathSegment],
    ) -> list[np.ndarray]:
        """Synthesize a list of audio segments, returning audio arrays."""
        parts: list[np.ndarray] = []
        for seg in segments:
            if isinstance(seg, BreathSegment):
                parts.append(seg.audio)
            elif isinstance(seg, SpeechSegment):
                audio = await self._synthesize_sentence(seg.text)
                if len(audio) > 0:
                    parts.append(audio)
                    self._cumulative_speech_s += len(audio) / BREATH_SAMPLE_RATE
        return parts

    def _clean_for_tts(self, sentence: str) -> str:
        """Strip voice tags and stage directions before TTS."""
        # Apply voice switch tags
        match = _VOICE_TAG_RE.search(sentence)
        if match:
            voice_name = match.group(1).lower()
            voice_id = f"af_{voice_name}"
            self._tts.set_voice(voice_id)
            logger.info("LLM triggered voice switch to %s", voice_id)
            sentence = _VOICE_TAG_RE.sub("", sentence)
        # Strip stage directions: [laughs], *sighs*, (chuckles), etc.
        sentence = _STAGE_DIRECTION_RE.sub("", sentence)
        return sentence.strip()

    async def _synthesize_sentence(self, sentence: str) -> np.ndarray:
        """Synthesize a single sentence, returning float32 audio."""
        try:
            sentence = self._clean_for_tts(sentence)
            if not sentence:
                return np.empty(0, dtype=np.float32)
            audio = await self._tts.synthesize(sentence)
            logger.debug("Synthesized %d samples for: %s", len(audio), sentence[:60])
            return audio
        except Exception:
            logger.exception("TTS synthesis failed for: %s", sentence[:80])
            return np.empty(0, dtype=np.float32)

    async def process_streaming(
        self,
        audio: np.ndarray,
        conversation_history: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
        transcript: str | None = None,
    ) -> AsyncIterator[tuple[str, np.ndarray]]:
        """Streaming variant that yields ``(sentence, audio)`` pairs as they're produced.

        This allows the caller to start playback immediately without waiting
        for the full response.

        Args:
            audio: Raw float32 audio from the microphone (16 kHz mono).
            conversation_history: Mutable message history list.
            on_token: Optional callback for each LLM token.
            transcript: Pre-transcribed text. When provided, skips the STT step
                entirely (avoids re-transcribing audio that was already processed).
        """
        # ── STT (skip if caller already transcribed) ──────────────
        if transcript is None:
            transcript = await self._stt.transcribe(audio, sample_rate=16000)

        if not transcript.strip():
            return

        conversation_history.append({"role": "user", "content": transcript})

        # ── LLM + TTS ─────────────────────────────────────────────
        self._prev_sentence_len = 0
        self._cumulative_speech_s = 0.0

        collector = SentenceCollector()
        full_response: list[str] = []

        system_prompt = ""
        llm_messages = conversation_history
        if conversation_history and conversation_history[0]["role"] == "system":
            system_prompt = conversation_history[0]["content"]
            llm_messages = conversation_history[1:]

        token_stream = self._llm.stream_response(llm_messages, system=system_prompt)
        wrapped_stream = self._interruption.wrap_stream(token_stream)

        async for token in wrapped_stream:
            full_response.append(token)
            if on_token is not None:
                on_token(token)

            sentences = collector.feed(token)
            for sentence in sentences:
                if self._breath is not None:
                    segments = self._breath.process(
                        sentence,
                        prev_sentence_len=self._prev_sentence_len,
                        cumulative_speech_s=self._cumulative_speech_s,
                    )
                    for seg in segments:
                        if isinstance(seg, BreathSegment):
                            yield ("", seg.audio)
                        elif isinstance(seg, SpeechSegment):
                            audio_chunk = await self._synthesize_sentence(seg.text)
                            if len(audio_chunk) > 0:
                                self._cumulative_speech_s += len(audio_chunk) / BREATH_SAMPLE_RATE
                                yield (seg.text, audio_chunk)
                    self._prev_sentence_len = len(sentence)
                else:
                    audio_chunk = await self._synthesize_sentence(sentence)
                    if len(audio_chunk) > 0:
                        yield (sentence, audio_chunk)

        remainder = collector.flush()
        if remainder:
            if self._breath is not None:
                segments = self._breath.process(
                    remainder,
                    prev_sentence_len=self._prev_sentence_len,
                    cumulative_speech_s=self._cumulative_speech_s,
                )
                for seg in segments:
                    if isinstance(seg, BreathSegment):
                        yield ("", seg.audio)
                    elif isinstance(seg, SpeechSegment):
                        audio_chunk = await self._synthesize_sentence(seg.text)
                        if len(audio_chunk) > 0:
                            yield (seg.text, audio_chunk)
            else:
                audio_chunk = await self._synthesize_sentence(remainder)
                if len(audio_chunk) > 0:
                    yield (remainder, audio_chunk)

        # Always commit whatever was generated to history, even if interrupted
        response_text = "".join(full_response)
        if response_text.strip():
            conversation_history.append({"role": "assistant", "content": response_text})
