"""
Voice engine bootstrap — creates and wires all voice modules.

This is the single entry point for the full-duplex conversation system.
It replaces the linear _perception_tts_bridge in core/bootstrap.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

from config import EmilySettings
from core.bus import PerceptionBus
from observability.logger import get_logger

log = get_logger(__name__)


class VoiceEngine:
    """
    Top-level voice engine that creates and wires all conversation modules.

    Usage:
        engine = VoiceEngine(settings, bus)
        await engine.start()
        # ... runs until stopped
        await engine.stop()
    """

    def __init__(
        self,
        settings: EmilySettings,
        bus: PerceptionBus,
        agent_bus: Any | None = None,
        fleet: Any | None = None,
        memory: Any | None = None,
        brain_hub: Any | None = None,
    ) -> None:
        """
        Args:
            settings: Emily settings.
            bus: PerceptionBus for event integration.
            agent_bus: AgentBus for routing voice through the full agent stack.
            fleet: LLMFleet for direct LLM access (onboarding, etc.).
            memory: MemoryManager for procedural/episodic memory access.
            brain_hub: BrainEventHub for live dashboard events.
        """
        self._settings = settings
        self._bus = bus
        self._agent_bus = agent_bus
        self._fleet = fleet
        self._memory = memory
        self._brain_hub = brain_hub
        self._fsm = None
        self._modules: dict[str, Any] = {}
        self._running = False

    async def start(self) -> None:
        """Initialize all modules and start the conversation FSM."""
        ve = self._settings.voice_engine
        if not ve.enabled:
            log.info("voice_engine_disabled")
            return

        log.info("voice_engine_initializing")

        from perception.audio.capture import AudioCaptureEngine, CaptureConfig
        capture_config = CaptureConfig(
            input_sample_rate=ve.input_sample_rate,
            output_sample_rate=ve.output_sample_rate,
            output_channels=ve.output_channels,
            input_chunk_ms=ve.chunk_ms,
            input_device=self._settings.audio.input_device,
            output_device=self._settings.audio.output_device,
        )
        capture = AudioCaptureEngine(capture_config)
        self._modules["audio_capture"] = capture

        if ve.aec_enabled:
            from perception.audio.aec import AcousticEchoCanceller, AECConfig
            aec = AcousticEchoCanceller(AECConfig(
                tail_length_ms=ve.aec_tail_ms,
                sample_rate=ve.input_sample_rate,
            ))
            self._modules["aec"] = aec

        if ve.noise_suppress_enabled:
            from perception.audio.noise_suppress import NoiseSuppressionEngine, NoiseConfig
            noise = NoiseSuppressionEngine(NoiseConfig(
                adaptive_threshold_db=ve.noise_threshold_db,
            ))
            await noise.load()
            self._modules["noise_suppress"] = noise

        skip_speaker = ve.fast_mode and ve.fast_mode_skip_speaker_tracking
        if ve.speaker_tracking and not skip_speaker:
            from perception.audio.speaker_engine import SpeakerEngine
            speaker = SpeakerEngine(max_speakers=ve.max_speakers)
            await speaker.load()
            self._modules["speaker_engine"] = speaker

        from perception.audio.streaming_stt import StreamingSTTEngine
        stt = StreamingSTTEngine(self._settings.stt)
        await stt.load()
        self._modules["streaming_stt"] = stt

        from perception.audio.prosody_analyzer import ProsodyAnalyzer
        prosody = ProsodyAnalyzer(sample_rate=16000)
        self._modules["prosody_analyzer"] = prosody

        skip_emotion = ve.fast_mode and ve.fast_mode_skip_emotion
        if ve.emotion_adapt_enabled and not skip_emotion:
            from perception.audio.emotion_detector import EmotionDetector
            emotion = EmotionDetector()
            self._modules["emotion_detector"] = emotion

        from conversation.turn_detector import TurnDetectionEngine
        turn = TurnDetectionEngine()
        self._modules["turn_detector"] = turn

        from conversation.interrupt_handler import InterruptHandler
        interrupt = InterruptHandler(
            lookahead_ms=ve.interrupt_lookahead_ms,
            fade_ms=ve.interrupt_fade_ms,
            resume_expiry_s=ve.interrupt_resume_expiry_s,
        )
        self._modules["interrupt_handler"] = interrupt

        if ve.backchannels_enabled:
            from conversation.backchannel import BackchannelEngine
            bc = BackchannelEngine()
            await bc.load_prerecorded()
            self._modules["backchannel_engine"] = bc

        skip_rhythm = ve.fast_mode and ve.fast_mode_skip_rhythm
        if ve.rhythm_sync_enabled and not skip_rhythm:
            from conversation.rhythm_sync import RhythmSynchronizer
            rhythm = RhythmSynchronizer(entrainment_degree=ve.entrainment_degree)
            self._modules["rhythm_sync"] = rhythm

        if ve.emotion_adapt_enabled and not skip_emotion:
            from conversation.emotion_sync import EmotionSynchronizer
            emotion_sync = EmotionSynchronizer()
            self._modules["emotion_sync"] = emotion_sync

        if ve.fillers_enabled:
            from voice.filler_engine import FillerEngine
            filler = FillerEngine()
            await filler.load()
            self._modules["filler_engine"] = filler

        skip_breath = ve.fast_mode and ve.fast_mode_skip_breathing
        if ve.breathing_enabled and not skip_breath:
            from voice.breath_injector import BreathInjector
            breath = BreathInjector()
            await breath.load()
            self._modules["breath_injector"] = breath

        voice_model = self._settings.llm.models.voice_fast
        from llm.orchestrator import ConversationLLMOrchestrator, GenerationConfig
        llm = ConversationLLMOrchestrator(GenerationConfig(
            fast_model=voice_model,
            smart_model=self._settings.llm.models.smart,
            ollama_base_url=self._settings.llm.ollama_base_url,
            speculative_start_probability=ve.speculative_start_probability,
            max_tokens=256,
        ))
        self._modules["llm_orchestrator"] = llm

        from voice.tts import TTSManager
        tts = TTSManager(self._settings.tts)
        await tts.load()
        self._modules["tts_engine"] = tts

        from timing.latency_budget import LatencyBudget
        latency_budget = LatencyBudget()
        self._modules["latency_budget"] = latency_budget

        interrupt_config = {
            "energy_threshold": ve.interrupt_energy_threshold,
            "cooldown_s": ve.interrupt_cooldown_ms / 1000.0,
            "fade_ms": ve.interrupt_fade_ms,
            "lookahead_ms": ve.interrupt_lookahead_ms,
            "ack_enabled": ve.interrupt_ack_enabled,
            "resume_enabled": ve.interrupt_resume_enabled,
            "resume_expiry_s": ve.interrupt_resume_expiry_s,
            "adaptive_threshold": ve.interrupt_adaptive_threshold,
        }

        from conversation.fsm import ConversationFSM
        self._fsm = ConversationFSM()
        self._fsm.configure(
            **self._modules,
            interrupt_config=interrupt_config,
            agent_bus=self._agent_bus,
            fleet=self._fleet,
            memory=self._memory,
            brain_hub=self._brain_hub,
        )
        if ve.fast_mode:
            self._fsm.set_fast_mode(True)

        # Pre-warm voice model in Ollama VRAM
        try:
            from llm.client import OllamaClient
            warmup_client = OllamaClient(
                base_url=self._settings.llm.ollama_base_url,
            )
            await warmup_client.keep_alive(voice_model)
            await warmup_client.close()
            log.info("voice_model_pre_warmed", model=voice_model)
        except Exception as exc:
            log.debug("voice_model_warmup_failed", error=str(exc))

        await capture.start()
        self._running = True

        log.info(
            "voice_engine_started",
            modules=list(self._modules.keys()),
            fast_mode=ve.fast_mode,
            voice_model=voice_model,
            aec=ve.aec_enabled,
            backchannels=ve.backchannels_enabled,
            fillers=ve.fillers_enabled,
            breathing=ve.breathing_enabled and not skip_breath,
            rhythm_sync=ve.rhythm_sync_enabled and not skip_rhythm,
            emotion_adapt=ve.emotion_adapt_enabled and not skip_emotion,
        )

        if (
            self._memory is not None
            and hasattr(self._memory, "procedural")
            and self._memory.procedural.is_new_user
        ):
            log.info("first_run_detected_starting_onboarding")
            await self._fsm.start_onboarding()

        await self._fsm.run()

    async def stop(self) -> None:
        """Stop the voice engine and release all native resources."""
        self._running = False

        if self._fsm is not None:
            try:
                await self._fsm.stop()
            except Exception:
                pass
            self._fsm = None

        for name in ("audio_capture",):
            mod = self._modules.get(name)
            if mod is not None and hasattr(mod, "stop"):
                try:
                    await mod.stop()
                except Exception:
                    pass

        for name in ("llm_orchestrator",):
            mod = self._modules.get(name)
            if mod is not None and hasattr(mod, "close"):
                try:
                    await mod.close()
                except Exception:
                    pass

        for name in ("speaker_engine",):
            mod = self._modules.get(name)
            if mod is not None and hasattr(mod, "release"):
                try:
                    mod.release()
                except Exception:
                    pass

        self._modules.clear()
        log.info("voice_engine_stopped")

    @property
    def is_running(self) -> bool:
        """True if the voice engine is active."""
        return self._running

    @property
    def fsm(self):
        """The conversation FSM instance."""
        return self._fsm
