"""
Master conversation state machine for Emily's voice engine.

Coordinates all voice modules in a 100Hz main loop:
- Audio capture and processing
- Turn detection
- Backchannel generation
- LLM response generation
- TTS output
- Interrupt handling
- Rhythm and emotion synchronization

States:
    IDLE → LISTENING → PROCESSING → SPEAKING
           ↕ BACKCHANNELING  ↕ FILLING  ↕ INTERRUPTED
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from observability.logger import get_logger
from perception.audio.stream import AudioChunk

log = get_logger(__name__)


class VoiceState(Enum):
    """Voice engine conversation states."""

    IDLE = auto()
    LISTENING = auto()
    BACKCHANNELING = auto()
    PROCESSING = auto()
    FILLING = auto()
    SPEAKING = auto()
    INTERRUPTED = auto()
    ONBOARDING = auto()


@dataclass
class ResponseContext:
    """Preserved context from an interrupted or completed response."""

    text_spoken: str = ""
    text_remaining: str = ""
    topic: str = ""
    importance: float = 0.5
    can_resume: bool = False


class ConversationFSM:
    """
    Master state machine coordinating all voice engine modules.

    Runs concurrent async loops for each subsystem at 100Hz,
    with the FSM state governing which loops are active.
    """

    def __init__(self) -> None:
        self._state = VoiceState.IDLE
        self._prev_state = VoiceState.IDLE
        self._state_enter_time: float = time.monotonic()
        self._response_context: ResponseContext | None = None
        self._interrupt_event = asyncio.Event()
        self._running = False
        self._listeners: list[Callable[[VoiceState, VoiceState], Any]] = []

        self._audio_capture = None
        self._aec = None
        self._noise_suppress = None
        self._speaker_engine = None
        self._streaming_stt = None
        self._prosody_analyzer = None
        self._emotion_detector = None
        self._turn_detector = None
        self._interrupt_handler = None
        self._backchannel_engine = None
        self._rhythm_sync = None
        self._emotion_sync = None
        self._llm_orchestrator = None
        self._tts_engine = None
        self._filler_engine = None
        self._breath_injector = None
        self._latency_budget = None

        self._agent_bus: Any | None = None
        self._fleet: Any | None = None
        self._memory: Any | None = None
        self._brain_hub: Any | None = None
        self._tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._onboarding_handler: Any | None = None
        self._fast_mode: bool = False
        self._speculative_started: bool = False

        self._last_user_speech_time: float = 0.0
        self._silence_prompt_count: int = 0

        self._interrupt_config: dict[str, Any] = {
            "energy_threshold": 0.03,
            "cooldown_s": 0.3,
            "fade_ms": 20,
            "lookahead_ms": 300,
            "ack_enabled": True,
            "resume_enabled": True,
            "resume_expiry_s": 30.0,
            "adaptive_threshold": True,
        }
        self._last_interrupt_time: float = 0.0
        self._noise_floor: float = 0.01
        self._noise_floor_alpha: float = 0.005

    def configure(self, **modules: Any) -> None:
        """
        Inject module dependencies.

        Args:
            **modules: Named module instances (audio_capture, aec, turn_detector,
                       agent_bus, fleet, memory, etc.)
        """
        for name, module in modules.items():
            attr = f"_{name}"
            if hasattr(self, attr):
                setattr(self, attr, module)
            else:
                log.warning("fsm_unknown_module", name=name)

        if self._agent_bus is not None:
            self._agent_bus.register_handler("tts", self._handle_tts_message)
            log.info("fsm_agent_bus_wired")

    def transition(self, new_state: VoiceState) -> None:
        """
        Transition to a new conversation state.

        Args:
            new_state: Target state.
        """
        if new_state == self._state:
            return

        old = self._state
        self._prev_state = old
        self._state = new_state
        self._state_enter_time = time.monotonic()

        log.debug("fsm_transition", old=old.name, new=new_state.name)

        if self._brain_hub is not None:
            self._brain_hub.emit_sync("fsm", "state_change", {
                "old": old.name, "new": new_state.name,
            })

        for listener in self._listeners:
            try:
                listener(old, new_state)
            except Exception as exc:
                log.error("fsm_listener_error", error=str(exc))

    def on_transition(self, callback: Callable[[VoiceState, VoiceState], Any]) -> None:
        """Register a state transition listener."""
        self._listeners.append(callback)

    def set_fast_mode(self, enabled: bool) -> None:
        """Enable or disable fast voice mode (bypasses agent bus for simple turns)."""
        self._fast_mode = enabled
        log.info("fsm_fast_mode", enabled=enabled)

    _COMPLEX_KEYWORDS = frozenset({
        "search", "find", "look up", "calculate", "code", "write",
        "analyze", "compare", "explain in detail", "step by step",
        "debug", "refactor", "file", "open", "run", "execute",
        "remember", "remind", "schedule", "email", "summarize",
        "home assistant", "turn on", "turn off", "set timer",
    })

    def _is_simple_turn(self, text: str) -> bool:
        """
        Determine if a voice turn is simple enough to skip the full agent pipeline.

        Simple turns go directly through the LLM orchestrator (no memory, RAG, or
        critic overhead). Complex turns still route through the agent bus.

        Args:
            text: Committed transcript text.

        Returns:
            True if the turn can use the fast-path orchestrator.
        """
        if not self._fast_mode:
            return False
        if len(text.split()) > 50:
            return False
        text_lower = text.lower()
        return not any(kw in text_lower for kw in self._COMPLEX_KEYWORDS)

    async def run(self) -> None:
        """
        Main loop. Runs at 100Hz (every 10ms).

        Launches all subsystem loops as concurrent tasks.
        """
        self._running = True
        self._last_user_speech_time = time.monotonic()
        self._silence_prompt_count = 0
        self.transition(VoiceState.IDLE)
        log.info("conversation_fsm_started")

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._audio_capture_loop())
                tg.create_task(self._perception_loop())
                tg.create_task(self._turn_detection_loop())
                tg.create_task(self._backchannel_loop())
                tg.create_task(self._response_loop())
                tg.create_task(self._interrupt_monitor_loop())
                tg.create_task(self._silence_watchdog_loop())
        except* asyncio.CancelledError:
            pass
        except* Exception as exc_group:
            for exc in exc_group.exceptions:
                log.error("fsm_loop_error", error=str(exc))
        finally:
            self._running = False
            log.info("conversation_fsm_stopped")

    async def _audio_capture_loop(self) -> None:
        """Read audio chunks from capture engine and push through processing."""
        if self._audio_capture is None:
            return

        while self._running:
            try:
                chunk = await self._audio_capture.get_input_chunk()

                if self._aec is not None:
                    ref = self._audio_capture.get_aec_reference(len(chunk.data))
                    if ref is not None:
                        chunk = AudioChunk(
                            data=self._aec.process(chunk.data, ref),
                            sample_rate=chunk.sample_rate,
                            channels=chunk.channels,
                        )

                if self._noise_suppress is not None:
                    is_speech = self._state in (VoiceState.LISTENING, VoiceState.BACKCHANNELING)
                    chunk = self._noise_suppress.process(chunk, is_speech=is_speech)

                self._current_chunk = chunk
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("audio_capture_loop_error", error=str(exc))
                await asyncio.sleep(0.01)

    async def _perception_loop(self) -> None:
        """Run STT, prosody, and emotion analysis on incoming audio."""
        while self._running:
            try:
                if not hasattr(self, "_current_chunk"):
                    await asyncio.sleep(0.01)
                    continue

                chunk = self._current_chunk

                energy = float(np.sqrt(np.mean(chunk.data ** 2)))

                if self._state in (VoiceState.IDLE, VoiceState.LISTENING):
                    self._noise_floor += self._noise_floor_alpha * (energy - self._noise_floor)

                if self._state == VoiceState.IDLE:
                    if energy > 0.01:
                        self.transition(VoiceState.LISTENING)

                if self._state in (VoiceState.LISTENING, VoiceState.BACKCHANNELING):
                    speaker_id = "default"
                    if self._speaker_engine is not None:
                        frame = await self._speaker_engine.process_frame(chunk)
                        if frame.dominant_speaker:
                            speaker_id = frame.dominant_speaker

                    if self._streaming_stt is not None:
                        stt_frame = await self._streaming_stt.process_chunk(chunk)
                        if stt_frame is not None:
                            self._current_stt_frame = stt_frame

                    if self._prosody_analyzer is not None:
                        prosody = self._prosody_analyzer.process(chunk, speaker_id)
                        self._current_prosody = prosody

                        if self._emotion_detector is not None:
                            baseline = self._prosody_analyzer.get_baseline(speaker_id)
                            text = getattr(self, "_current_stt_frame", None)
                            partial = text.partial_text if text else ""
                            self._current_emotion = self._emotion_detector.detect(
                                prosody, baseline, partial
                            )

                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("perception_loop_error", error=str(exc))
                await asyncio.sleep(0.01)

    async def _turn_detection_loop(self) -> None:
        """Run turn detection fusion and trigger state transitions."""
        while self._running:
            try:
                if self._state not in (VoiceState.LISTENING, VoiceState.BACKCHANNELING):
                    await asyncio.sleep(0.01)
                    continue

                if self._turn_detector is None:
                    await asyncio.sleep(0.01)
                    continue

                from conversation.turn_detector import ConversationState as TurnState

                stt = getattr(self, "_current_stt_frame", None)
                prosody = getattr(self, "_current_prosody", None)
                emotion = getattr(self, "_current_emotion", None)

                from perception.audio.prosody_analyzer import ProsodyFeatures, SpeakerBaseline
                from perception.audio.emotion_detector import EmotionState

                turn_state = TurnState(
                    prosody=prosody or ProsodyFeatures(),
                    baseline=self._prosody_analyzer.get_baseline() if self._prosody_analyzer else SpeakerBaseline(),
                    emotion=emotion or EmotionState(),
                    partial_text=stt.partial_text if stt else "",
                    committed_text=" ".join(w.text for w in stt.committed_words) if stt else "",
                    emily_speaking=self._state == VoiceState.SPEAKING,
                )

                signal = self._turn_detector.compute(turn_state)

                from conversation.turn_detector import TurnAction

                if (
                    self._fast_mode
                    and self._llm_orchestrator is not None
                    and not self._speculative_started
                    and signal.action not in (TurnAction.RESPOND, TurnAction.YIELD_AND_RESPOND)
                    and hasattr(signal, "probability")
                    and signal.probability >= 0.65
                    and stt is not None
                    and stt.partial_text.strip()
                ):
                    self._speculative_started = True
                    asyncio.create_task(
                        self._llm_orchestrator.start_speculative(
                            stt.partial_text.strip(),
                            emotion=emotion,
                        )
                    )
                    log.debug("speculative_generation_triggered",
                              partial=stt.partial_text[:50])

                if signal.action == TurnAction.RESPOND:
                    self._speculative_started = False
                    self.transition(VoiceState.PROCESSING)
                elif signal.action == TurnAction.BACKCHANNEL:
                    if self._state != VoiceState.BACKCHANNELING:
                        self.transition(VoiceState.BACKCHANNELING)
                elif signal.action == TurnAction.YIELD_AND_RESPOND:
                    self._speculative_started = False
                    self._interrupt_event.set()
                    self.transition(VoiceState.PROCESSING)

                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("turn_detection_loop_error", error=str(exc))
                await asyncio.sleep(0.01)

    async def _backchannel_loop(self) -> None:
        """Generate backchannels when in BACKCHANNELING state."""
        while self._running:
            try:
                if self._state != VoiceState.BACKCHANNELING or self._backchannel_engine is None:
                    await asyncio.sleep(0.05)
                    continue

                from conversation.turn_detector import TurnSignal, TurnAction
                signal = self._turn_detector.last_signal if self._turn_detector else None

                stt = getattr(self, "_current_stt_frame", None)
                emotion = getattr(self, "_current_emotion", None)
                prosody = getattr(self, "_current_prosody", None)

                completion_score = 0.0
                if signal is not None and hasattr(signal, "signals"):
                    completion_score = signal.signals.get(
                        "syntactic_completeness", 0.0,
                    )

                event = await self._backchannel_engine.should_backchannel(
                    partial_text=stt.partial_text if stt else "",
                    emotion=emotion,
                    turn_signal=signal,
                    prosody=prosody,
                    completion_prediction_score=completion_score,
                )

                if event is not None and self._audio_capture is not None:
                    audio = await self._backchannel_engine.render_backchannel(event)
                    if audio is not None:
                        self._audio_capture.write_output(audio)

                self.transition(VoiceState.LISTENING)
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("backchannel_loop_error", error=str(exc))
                await asyncio.sleep(0.1)

    async def _handle_tts_message(self, message: Any) -> None:
        """Handle tts.speak messages from ConversationAgent via AgentBus."""
        if message.type == "tts.speak":
            text = message.payload.get("text", "")
            if text:
                await self._tts_queue.put(text)
        elif message.type == "tts.done":
            await self._tts_queue.put(None)

    async def _speak_sentence(self, sentence: str, sentence_index: int) -> bool:
        """
        Synthesize and stream audio to the speaker chunk-by-chunk.

        Plays audio as it arrives from TTS instead of buffering the full
        sentence first, cutting perceived latency significantly.  When an
        interrupt fires, the remaining TTS buffer is faded out at the
        nearest word boundary (via InterruptHandler) so Emily never stops
        mid-word.

        Returns False if interrupted, True if completed.
        """
        if self._tts_engine is None or self._audio_capture is None:
            return True

        if self._brain_hub is not None:
            await self._brain_hub.emit("perception", "tts_speaking", {
                "text": sentence[:200],
                "sentence_index": sentence_index,
            })

        pending_chunks: list[np.ndarray] = []

        async for audio_chunk in self._tts_engine.speak(text=sentence):
            if self._interrupt_event.is_set():
                pending_np = np.frombuffer(
                    audio_chunk, dtype=np.int16,
                ).astype(np.float32) / 32768.0
                pending_chunks.append(pending_np)
                break
            audio_np = np.frombuffer(
                audio_chunk, dtype=np.int16,
            ).astype(np.float32) / 32768.0
            self._audio_capture.write_output(audio_np)

        if self._interrupt_event.is_set():
            await self._apply_graceful_trailoff(sentence, pending_chunks)
            return False

        if self._brain_hub is not None:
            await self._brain_hub.emit("perception", "emily_spoke", {
                "text": sentence,
            })

        return True

    async def _apply_graceful_trailoff(
        self,
        sentence_so_far: str,
        pending_chunks: list[np.ndarray],
    ) -> None:
        """
        Fade remaining TTS audio at a word boundary and play an acknowledgment.

        Args:
            sentence_so_far: The sentence Emily was speaking.
            pending_chunks: Unplayed TTS audio chunks buffered at interrupt time.
        """
        if pending_chunks and self._interrupt_handler is not None and self._audio_capture is not None:
            remaining = np.concatenate(pending_chunks)
            stop = self._interrupt_handler.find_graceful_stop_point(remaining, 24000)
            faded = self._interrupt_handler.apply_fade_out(remaining, stop)
            self._audio_capture.write_output(faded[:stop])

        stt = getattr(self, "_current_stt_frame", None)
        partial_user = stt.partial_text if stt else ""
        chunk = getattr(self, "_current_chunk", None)
        user_energy = float(np.sqrt(np.mean(chunk.data ** 2))) if chunk is not None else 0.0

        if self._interrupt_handler is not None:
            prosody = getattr(self, "_current_prosody", None)
            emotion = getattr(self, "_current_emotion", None)
            resp = await self._interrupt_handler.handle_user_interrupt(
                sentence_so_far=sentence_so_far,
                partial_user_text=partial_user,
                user_energy=user_energy,
                prosody=prosody,
                emotion=emotion,
            )

            from timing.metrics import record_interrupt
            record_interrupt(resp.interrupt_type.value)

            if self._brain_hub is not None:
                await self._brain_hub.emit("voice", "interrupt", {
                    "type": resp.interrupt_type.value,
                    "ack": resp.acknowledgment,
                })

            ack_enabled = self._interrupt_config.get("ack_enabled", True)
            if ack_enabled and resp.acknowledgment and self._tts_engine is not None and self._audio_capture is not None:
                ack_audio = bytearray()
                async for ack_chunk in self._tts_engine.speak(text=resp.acknowledgment):
                    ack_audio.extend(ack_chunk)
                if ack_audio:
                    ack_np = np.frombuffer(
                        bytes(ack_audio), dtype=np.int16,
                    ).astype(np.float32) / 32768.0
                    ack_np *= 0.7
                    self._audio_capture.write_output(ack_np)

    async def _response_via_agent_bus(self, transcript_text: str) -> None:
        """Route transcript through ConversationAgent and play TTS responses."""
        from core.bus import Message, Priority

        while not self._tts_queue.empty():
            self._tts_queue.get_nowait()

        await self._agent_bus.send(Message(
            type="audio.transcript",
            payload={"text": transcript_text, "confidence": 1.0, "source": "voice"},
            sender="VoiceEngine",
            recipient="ConversationAgent",
            priority=Priority.REALTIME,
        ))

        self.transition(VoiceState.SPEAKING)
        sentence_index = 0
        timeout_s = 30.0
        last_activity = time.monotonic()

        spoken_sentences: list[str] = []

        while True:
            if self._interrupt_event.is_set():
                await self._apply_graceful_trailoff(
                    " ".join(spoken_sentences), [],
                )
                await self._agent_bus.send(Message(
                    type="audio.interrupt",
                    payload={"reason": "user_barge_in"},
                    sender="VoiceEngine",
                    recipient="ConversationAgent",
                    priority=Priority.REALTIME,
                ))
                self.transition(VoiceState.INTERRUPTED)
                return

            try:
                sentence = await asyncio.wait_for(self._tts_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if time.monotonic() - last_activity > timeout_s:
                    log.warning("agent_response_timeout")
                    break
                continue

            if sentence is None:
                break

            last_activity = time.monotonic()
            if not await self._speak_sentence(sentence, sentence_index):
                self.transition(VoiceState.INTERRUPTED)
                return
            spoken_sentences.append(sentence)
            sentence_index += 1

    async def _response_via_orchestrator(self, transcript: Any) -> None:
        """Fallback: use the local LLM orchestrator directly (no memory/RAG)."""
        if self._llm_orchestrator is None or transcript is None:
            return

        self.transition(VoiceState.SPEAKING)
        emotion = getattr(self, "_current_emotion", None)
        style = None
        if self._emotion_sync is not None and emotion is not None:
            style = self._emotion_sync.compute_response_style(emotion)

        sentence_index = 0
        async for sentence in self._llm_orchestrator.generate_streaming(
            transcript=transcript,
            emotion=emotion,
            style=style,
            interrupt_signal=self._interrupt_event,
        ):
            if self._interrupt_event.is_set():
                await self._apply_graceful_trailoff(sentence, [])
                self.transition(VoiceState.INTERRUPTED)
                return

            if not await self._speak_sentence(sentence, sentence_index):
                self.transition(VoiceState.INTERRUPTED)
                return
            sentence_index += 1

    async def _response_loop(self) -> None:
        """Generate and speak responses when in PROCESSING state."""
        while self._running:
            try:
                if self._state != VoiceState.PROCESSING:
                    await asyncio.sleep(0.01)
                    continue

                self._interrupt_event.clear()

                if self._filler_engine is not None and self._audio_capture is not None:
                    self.transition(VoiceState.FILLING)
                    filler_coro = self._filler_engine.get_filler(
                        expected_latency_ms=300,
                        emotion_context=getattr(self, "_current_emotion", None),
                    )
                    if self._latency_budget is not None:
                        filler = await self._latency_budget.check_stage(
                            "filler_start", filler_coro,
                        )
                    else:
                        filler = await filler_coro
                    if filler is not None:
                        self._audio_capture.write_output(filler)

                transcript = None
                if self._streaming_stt is not None:
                    commit_coro = self._streaming_stt.commit_utterance()
                    if self._latency_budget is not None:
                        transcript = await self._latency_budget.check_stage(
                            "stt_commit", commit_coro,
                        )
                    else:
                        transcript = await commit_coro

                transcript_text = ""
                if transcript is not None:
                    transcript_text = getattr(transcript, "text", "") or ""
                    if not transcript_text and hasattr(transcript, "words"):
                        transcript_text = " ".join(
                            w.text for w in (transcript.words or [])
                        )

                if not transcript_text.strip():
                    self.transition(VoiceState.IDLE)
                    await asyncio.sleep(0.01)
                    continue

                log.info("stt_utterance_committed", text=transcript_text[:100])
                self._last_user_speech_time = time.monotonic()
                self._silence_prompt_count = 0

                resume_prefix = ""
                if (self._interrupt_handler is not None
                        and self._interrupt_config.get("resume_enabled")):
                    phrase = self._interrupt_handler.get_resume_phrase()
                    if phrase:
                        resume_prefix = phrase
                        self._interrupt_handler.clear_preserved_context()
                        log.info("interrupt_resume_phrase", phrase=phrase)

                if self._brain_hub is not None:
                    await self._brain_hub.emit("perception", "stt_committed", {
                        "text": transcript_text[:200],
                        "words": len(transcript_text.split()),
                    })

                simple = (
                    self._fast_mode
                    and self._llm_orchestrator is not None
                    and self._is_simple_turn(transcript_text)
                )

                if resume_prefix:
                    self.transition(VoiceState.SPEAKING)
                    await self._speak_sentence(resume_prefix, 0)

                if simple:
                    cached = self._llm_orchestrator.check_speculative_match(
                        transcript_text,
                    )
                    if cached:
                        log.info("speculative_cache_used",
                                 text=transcript_text[:50])
                        self.transition(VoiceState.SPEAKING)
                        await self._speak_sentence(cached, 0)
                    else:
                        if self._brain_hub is not None:
                            await self._brain_hub.emit("llm", "request", {
                                "model": "qwen3:4b",
                                "tier": "voice_fast",
                                "path": "orchestrator",
                            })
                        await self._response_via_orchestrator(transcript)
                elif self._agent_bus is not None:
                    if self._brain_hub is not None:
                        await self._brain_hub.emit("llm", "request", {
                            "tier": "voice_fast",
                            "path": "agent_bus",
                        })
                    await self._response_via_agent_bus(transcript_text)
                else:
                    await self._response_via_orchestrator(transcript)

                if self._state == VoiceState.SPEAKING:
                    self.transition(VoiceState.IDLE)
                elif self._state == VoiceState.INTERRUPTED:
                    self.transition(VoiceState.LISTENING)

                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("response_loop_error", error=str(exc))
                self.transition(VoiceState.IDLE)
                await asyncio.sleep(0.1)

    async def _interrupt_monitor_loop(self) -> None:
        """Monitor for user interrupts during Emily's speech.

        Uses configurable energy threshold with optional adaptive adjustment
        based on ambient noise floor, plus a cooldown to prevent rapid re-triggering.
        """
        while self._running:
            try:
                if self._state in (VoiceState.SPEAKING, VoiceState.FILLING):
                    if hasattr(self, "_current_chunk"):
                        energy = float(np.sqrt(np.mean(self._current_chunk.data ** 2)))
                        base_threshold = self._interrupt_config["energy_threshold"]
                        if self._interrupt_config["adaptive_threshold"]:
                            threshold = max(base_threshold, self._noise_floor * 3.0)
                        else:
                            threshold = base_threshold

                        cooldown_s = self._interrupt_config["cooldown_s"]
                        now = time.monotonic()

                        if energy > threshold and (now - self._last_interrupt_time) >= cooldown_s:
                            self._interrupt_event.set()
                            self._last_interrupt_time = now
                            log.info(
                                "interrupt_detected",
                                energy=f"{energy:.4f}",
                                threshold=f"{threshold:.4f}",
                                noise_floor=f"{self._noise_floor:.4f}",
                            )

                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.01)

    _SILENCE_PROMPTS = [
        "Hey, I'm not picking up any audio. You might be on mute.",
        "I'm still here, but I can't hear you. Check if your mic is on?",
        "It's pretty quiet over there. Let me know if you can hear me.",
    ]
    _INITIAL_SILENCE_S = 30.0
    _REPEAT_SILENCE_S = 120.0
    _MAX_SILENCE_PROMPTS = 3

    async def _silence_watchdog_loop(self) -> None:
        """Speak a prompt when no user speech is detected for an extended period."""
        while self._running:
            try:
                await asyncio.sleep(5.0)

                if self._state not in (VoiceState.IDLE, VoiceState.LISTENING):
                    continue
                if self._silence_prompt_count >= self._MAX_SILENCE_PROMPTS:
                    continue

                elapsed = time.monotonic() - self._last_user_speech_time
                threshold = (
                    self._INITIAL_SILENCE_S
                    if self._silence_prompt_count == 0
                    else self._REPEAT_SILENCE_S
                )

                if elapsed < threshold:
                    continue

                prompt = self._SILENCE_PROMPTS[
                    self._silence_prompt_count % len(self._SILENCE_PROMPTS)
                ]
                log.info(
                    "silence_watchdog_triggered",
                    elapsed_s=f"{elapsed:.0f}",
                    prompt_num=self._silence_prompt_count + 1,
                )

                if self._brain_hub is not None:
                    await self._brain_hub.emit("fsm", "silence_watchdog", {
                        "elapsed_s": round(elapsed),
                        "prompt_num": self._silence_prompt_count + 1,
                        "prompt": prompt[:100],
                    })

                await self._onboarding_speak(prompt)
                self._silence_prompt_count += 1
                self._last_user_speech_time = time.monotonic()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("silence_watchdog_error", error=str(exc))
                await asyncio.sleep(10.0)

    async def stop(self) -> None:
        """Stop the conversation FSM."""
        self._running = False
        self.transition(VoiceState.IDLE)

    @property
    def state(self) -> VoiceState:
        """Current conversation state."""
        return self._state

    @property
    def state_duration_s(self) -> float:
        """How long we've been in the current state."""
        return time.monotonic() - self._state_enter_time

    @property
    def is_running(self) -> bool:
        """True if the FSM is active."""
        return self._running

    # ------------------------------------------------------------------
    # Onboarding mode
    # ------------------------------------------------------------------

    async def start_onboarding(self) -> None:
        """
        Run the first-time onboarding interview before normal conversation starts.

        Requires fleet, memory, tts_engine and streaming_stt to be configured.
        """
        if self._fleet is None or self._memory is None:
            log.warning("onboarding_skipped_no_agent_stack")
            return
        if self._tts_engine is None or self._streaming_stt is None:
            log.warning("onboarding_skipped_no_audio")
            return

        self.transition(VoiceState.ONBOARDING)

        from agents.onboarding import run_onboarding

        await run_onboarding(
            fleet=self._fleet,
            memory=self._memory,
            speak=self._onboarding_speak,
            listen=self._onboarding_listen,
        )

        self.transition(VoiceState.IDLE)
        log.info("onboarding_finished")

    async def _onboarding_speak(self, text: str) -> None:
        """TTS callback for onboarding — synthesize and play text."""
        if self._tts_engine is None or self._audio_capture is None:
            return

        if self._brain_hub is not None:
            await self._brain_hub.emit("perception", "tts_speaking", {
                "text": text[:200],
                "sentence_index": 0,
            })

        audio_buf = bytearray()
        async for chunk in self._tts_engine.speak(text=text):
            audio_buf.extend(chunk)

        if audio_buf:
            audio_np = np.frombuffer(
                bytes(audio_buf), dtype=np.int16
            ).astype(np.float32) / 32768.0
            self._audio_capture.write_output(audio_np)

        if self._brain_hub is not None:
            await self._brain_hub.emit("perception", "emily_spoke", {
                "text": text,
            })

    async def _onboarding_listen(self) -> str:
        """STT callback for onboarding — capture audio until the user finishes speaking."""
        if self._streaming_stt is None or self._audio_capture is None:
            return ""

        silence_threshold = 0.01
        speech_started = False
        silence_duration = 0.0
        max_silence_s = 2.0
        max_listen_s = 30.0
        t0 = time.monotonic()

        while True:
            elapsed = time.monotonic() - t0
            if elapsed > max_listen_s:
                break

            try:
                chunk = await asyncio.wait_for(
                    self._audio_capture.get_input_chunk(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            energy = float(np.sqrt(np.mean(chunk.data ** 2)))

            if energy > silence_threshold:
                speech_started = True
                silence_duration = 0.0
            elif speech_started:
                silence_duration += 0.01

            if self._streaming_stt is not None:
                await self._streaming_stt.process_chunk(chunk)

            if speech_started and silence_duration >= max_silence_s:
                break

            await asyncio.sleep(0.005)

        result = await self._streaming_stt.commit_utterance()
        if result is None:
            return ""

        text = getattr(result, "text", "") or ""
        if not text and hasattr(result, "words"):
            text = " ".join(w.text for w in (result.words or []))
        return text.strip()
