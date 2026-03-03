"""Main conversation loop — the state machine that drives the voice engine."""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
import random
import re
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.audio.microphone import MIC_SAMPLE_RATE, MicrophoneStream
from voice_engine.audio.speaker import Speaker
from voice_engine.audio.vad import SileroVAD
from voice_engine.pipeline import VoicePipeline
from voice_engine.processing.interruption import InterruptionHandler
from voice_engine.providers.factory import ProviderFactory
from voice_engine.ui.terminal import TerminalUI

if TYPE_CHECKING:
    from voice_engine.config import VoiceEngineConfig
    from voice_engine.providers.base import LLMProvider, STTProvider, TTSProvider

logger = logging.getLogger(__name__)

# Backchannel sounds to synthesize during processing delays
_BACKCHANNEL_SOUNDS = ["hmm", "mm", "mmm"]


class ConversationState(enum.Enum):
    """States of the conversation finite-state machine."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"


class VoiceConversation:
    """Top-level conversation controller.

    Manages the microphone -> VAD -> STT -> LLM -> TTS -> speaker loop,
    including barge-in (interruption) when the user speaks while the assistant
    is still responding.
    """

    def __init__(
        self,
        config: VoiceEngineConfig,
        *,
        stt: STTProvider | None = None,
        llm: LLMProvider | None = None,
        tts: TTSProvider | None = None,
    ) -> None:
        self._config = config
        self._state = ConversationState.IDLE
        self._injected_llm = llm is not None

        # Providers — use injected instances when available, else factory
        self._stt = stt or ProviderFactory.create_stt(config)
        self._llm = llm or ProviderFactory.create_llm(config)
        self._tts = tts or ProviderFactory.create_tts(config)

        # Components
        self._vad = SileroVAD(threshold=config.vad_threshold)
        raw_out = config.audio_output_device.strip()
        output_device: int | str | None = int(raw_out) if raw_out.isdigit() else (raw_out or None)
        self._speaker = Speaker(device=output_device)
        self._interruption = InterruptionHandler()
        self._pipeline = VoicePipeline(
            stt=self._stt,
            llm=self._llm,
            tts=self._tts,
            interruption=self._interruption,
        )
        self._ui = TerminalUI()

        # Audio device selection
        raw_dev = config.audio_input_device.strip()
        self._input_device: int | str | None = (
            int(raw_dev) if raw_dev.isdigit() else (raw_dev or None)
        )

        # Conversation state
        self._conversation_history: list[dict[str, str]] = []
        self._max_history_turns = 50  # keep last N messages (+ system prompt)
        self._min_speech_samples = int(config.min_speech_ms * MIC_SAMPLE_RATE / 1000)
        self._min_silence_samples = int(config.min_silence_ms * MIC_SAMPLE_RATE / 1000)

        # Backchannel engine — synthesizes "hmm"/"mm" during processing delays
        self._backchannel_probability = 0.20
        self._backchannel_task: asyncio.Task[None] | None = None
        try:
            from voice.expressive_engine import ExpressiveEngine

            self._expressive = ExpressiveEngine(voice_pitch_hz=210.0)
        except Exception:
            self._expressive = None

        logger.info(
            "VoiceConversation initialised: stt=%s llm=%s tts=%s",
            config.stt_provider,
            config.llm_provider,
            config.tts_provider,
        )

    def _set_state(self, state: ConversationState) -> None:
        """Transition to a new state."""
        logger.debug("State: %s -> %s", self._state.value, state.value)
        self._state = state

    async def run(self) -> None:
        """Main conversation loop — runs until KeyboardInterrupt or cancellation."""
        self._ui.show_welcome()
        llm_label = type(self._llm).__name__
        if llm_label == "EmilyLLMProvider":
            llm_label = "emily (fleet)"
        else:
            llm_label = f"{self._config.llm_provider} ({self._config.llm_model})"
        self._ui.show_status(
            f"STT: {self._config.stt_provider} | "
            f"LLM: {llm_label} | "
            f"TTS: {self._config.tts_provider}"
        )

        # Prepend system prompt to history (skip when using injected LLM —
        # EmilyLLMProvider builds its own persona-aware system prompt)
        if not self._injected_llm:
            system_prompt = self._config.get_system_prompt()
            self._conversation_history.append({"role": "system", "content": system_prompt})

        # Background task for utterance processing (kept separate so mic loop
        # continues running during LLM generation and TTS playback).
        _process_task: asyncio.Task[None] | None = None

        try:
            async with MicrophoneStream(device=self._input_device) as mic:
                self._ui.show_listening()
                self._set_state(ConversationState.LISTENING)

                speech_buffer: list[np.ndarray] = []
                silence_samples = 0
                is_speaking = False

                async for chunk in mic.stream():
                    is_speech = self._vad.is_speech(chunk)

                    # ── Barge-in: speech detected while responding/processing ──
                    if is_speech and self._state in (
                        ConversationState.RESPONDING,
                        ConversationState.PROCESSING,
                    ):
                        logger.info("Barge-in detected — interrupting response.")
                        self._cancel_backchannel()
                        self._interruption.signal_interrupt()
                        self._speaker.cancel()
                        if _process_task and not _process_task.done():
                            _process_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await _process_task
                        self._set_state(ConversationState.LISTENING)
                        self._ui.show_listening()
                        self._vad.reset()
                        speech_buffer.clear()
                        silence_samples = 0
                        is_speaking = True
                        speech_buffer.append(chunk)
                        continue

                    # Only accumulate speech when idle/listening
                    if self._state not in (
                        ConversationState.LISTENING,
                        ConversationState.IDLE,
                    ):
                        continue

                    # ── Speech accumulation ────────────────────
                    if is_speech:
                        if not is_speaking:
                            is_speaking = True
                            logger.debug("Speech started.")
                        speech_buffer.append(chunk)
                        silence_samples = 0

                    elif is_speaking:
                        silence_samples += len(chunk)
                        speech_buffer.append(chunk)

                        if silence_samples >= self._min_silence_samples:
                            total_samples = sum(len(c) for c in speech_buffer)

                            if total_samples >= self._min_speech_samples:
                                audio = np.concatenate(speech_buffer)
                                speech_buffer.clear()
                                silence_samples = 0
                                is_speaking = False

                                # Fire-and-forget so the mic loop keeps running
                                _process_task = asyncio.create_task(self._process_utterance(audio))
                            else:
                                logger.debug(
                                    "Speech too short (%d samples) — discarding.",
                                    total_samples,
                                )
                                speech_buffer.clear()
                                silence_samples = 0
                                is_speaking = False

        except KeyboardInterrupt:
            logger.info("Conversation ended by user.")
        except asyncio.CancelledError:
            logger.info("Conversation task cancelled.")
        finally:
            if _process_task and not _process_task.done():
                _process_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await _process_task
            self._ui.show_goodbye()

    async def listen_once(self, timeout: float = 30.0) -> str:
        """Listen for a single utterance and return the transcribed text.

        Opens the mic, waits for speech via VAD, collects until silence,
        then transcribes with STT and returns the result.  Used by
        onboarding and other one-shot listen scenarios.

        Args:
            timeout: Max seconds to wait for speech before returning empty.

        Returns:
            Transcribed text, or empty string on timeout / no speech.
        """
        import asyncio as _aio

        async with MicrophoneStream(device=self._input_device) as mic:
            speech_buffer: list[np.ndarray] = []
            silence_samples = 0
            is_speaking = False
            deadline = _aio.get_event_loop().time() + timeout

            async for chunk in mic.stream():
                if _aio.get_event_loop().time() > deadline:
                    logger.debug("listen_once timed out")
                    break

                is_speech = self._vad.is_speech(chunk)

                if is_speech:
                    if not is_speaking:
                        is_speaking = True
                    speech_buffer.append(chunk)
                    silence_samples = 0
                elif is_speaking:
                    silence_samples += len(chunk)
                    speech_buffer.append(chunk)

                    if silence_samples >= self._min_silence_samples:
                        total_samples = sum(len(c) for c in speech_buffer)
                        if total_samples >= self._min_speech_samples:
                            audio = np.concatenate(speech_buffer)
                            text = await self._stt.transcribe(audio)
                            logger.info("listen_once transcribed: %s", text[:80] if text else "")
                            return text
                        speech_buffer.clear()
                        silence_samples = 0
                        is_speaking = False

        return ""

    # ── Voice command handling ──────────────────────────────────────────

    _VOICE_MAP: dict[str, str] = {
        "nicole": "af_nicole",
        "sky": "af_sky",
        "heart": "af_heart",
        "bella": "af_bella",
        "sarah": "af_sarah",
        "nova": "af_nova",
    }

    _VOICE_CMD_PATTERNS = [
        re.compile(r"(?:switch|change)\s+(?:to|your\s+voice\s+to)\s+(\w+)", re.I),
        re.compile(r"use\s+(?:the\s+)?(\w+)\s+voice", re.I),
    ]

    def _match_voice_command(self, text: str) -> str | None:
        """Check if text is a voice switch command. Returns voice_id or None."""
        for pat in self._VOICE_CMD_PATTERNS:
            m = pat.search(text)
            if m:
                name = m.group(1).lower()
                return self._VOICE_MAP.get(name)
        return None

    async def _handle_voice_switch(self, voice_id: str) -> None:
        """Switch the TTS voice and speak a confirmation."""
        friendly = voice_id.replace("af_", "").title()
        self._tts.set_voice(voice_id)

        confirm = f"Done, I've switched to the {friendly} voice."
        tts_audio = await self._tts.synthesize(confirm)
        if len(tts_audio) > 0:
            tts_rate = self._get_tts_sample_rate()
            await self._speaker.play(tts_audio, sample_rate=tts_rate)

        logger.info("Voice switched to %s via voice command", voice_id)

    def _trim_history(self) -> None:
        """Keep conversation history bounded to prevent memory leaks.

        Preserves the system prompt (if present) and the most recent messages.
        """
        has_system = (
            self._conversation_history and self._conversation_history[0]["role"] == "system"
        )
        non_system = self._conversation_history[1:] if has_system else self._conversation_history
        if len(non_system) > self._max_history_turns:
            trimmed = non_system[-self._max_history_turns :]
            if has_system:
                self._conversation_history = [self._conversation_history[0]] + trimmed
            else:
                self._conversation_history = trimmed

    async def _maybe_play_backchannel(self) -> None:
        """Optionally play a backchannel sound after a processing delay.

        Waits 1.5-2.5s, then if still in PROCESSING state, synthesizes
        and plays a "hmm"/"mm" sound to signal Emily is thinking.
        """
        try:
            await asyncio.sleep(random.uniform(1.5, 2.5))

            if self._state != ConversationState.PROCESSING:
                return
            if self._expressive is None:
                return

            sound = random.choice(_BACKCHANNEL_SOUNDS)
            segments = self._expressive.process(sound)

            for seg in segments:
                if hasattr(seg, "audio") and len(seg.audio) > 0:
                    await self._speaker.play(seg.audio, sample_rate=24000)
                    logger.debug("Backchannel played: %s", sound)
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Backchannel playback failed", exc_info=True)

    def _cancel_backchannel(self) -> None:
        """Cancel any pending backchannel task."""
        if self._backchannel_task and not self._backchannel_task.done():
            self._backchannel_task.cancel()
            self._backchannel_task = None

    async def _process_utterance(self, audio: np.ndarray) -> None:
        """Process a single user utterance through the full pipeline.

        Uses the streaming pipeline so each TTS sentence is played as soon as
        it is synthesised, enabling sentence-level barge-in interruption.
        """
        self._set_state(ConversationState.PROCESSING)
        self._ui.show_processing()

        # Reset interruption and speaker state for this new response
        self._interruption.clear()
        self._speaker.reset()

        try:
            # ── Voice command pre-check ──────────────────────────────
            # Quick STT to see if this is a voice switch command before
            # sending through the full LLM pipeline.
            pre_text = await self._stt.transcribe(audio, sample_rate=16000)
            voice_id = self._match_voice_command(pre_text) if pre_text else None
            if voice_id:
                self._ui.show_transcript(pre_text)
                await self._handle_voice_switch(voice_id)
                self._set_state(ConversationState.LISTENING)
                self._ui.show_listening()
                return

            # Start backchannel task (20% chance of playing "hmm" during delay)
            if random.random() < self._backchannel_probability:
                self._backchannel_task = asyncio.create_task(self._maybe_play_backchannel())

            tts_sample_rate = self._get_tts_sample_rate()
            full_response_parts: list[str] = []
            first_sentence = True

            async for sentence, audio_chunk in self._pipeline.process_streaming(
                audio=audio,
                conversation_history=self._conversation_history,
                transcript=pre_text,
            ):
                if self._interruption.is_interrupted():
                    break

                if first_sentence:
                    # Cancel backchannel — real response is arriving
                    self._cancel_backchannel()
                    # Show transcript (last user message now in history)
                    user_messages = [m for m in self._conversation_history if m["role"] == "user"]
                    if user_messages:
                        self._ui.show_transcript(user_messages[-1]["content"])
                    self._set_state(ConversationState.RESPONDING)
                    first_sentence = False

                full_response_parts.append(sentence)
                self._ui.show_response(sentence)

                await self._speaker.play(audio_chunk, sample_rate=tts_sample_rate)

                if self._interruption.is_interrupted():
                    break

        except asyncio.CancelledError:
            logger.info("Utterance processing interrupted.")
            raise
        except Exception:
            logger.exception("Error processing utterance")
            self._ui.show_error("An error occurred while processing your speech.")
        finally:
            self._cancel_backchannel()
            self._trim_history()
            self._set_state(ConversationState.LISTENING)
            self._ui.show_listening()

    def _get_tts_sample_rate(self) -> int:
        """Infer the TTS output sample rate from the provider type."""
        provider_name = self._config.tts_provider.lower().strip()
        if provider_name == "kokoro":
            return 24000
        if provider_name == "edge_tts":
            return 24000
        if provider_name == "elevenlabs":
            return 24000
        return 24000
