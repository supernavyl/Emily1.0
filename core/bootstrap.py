"""
Emily system bootstrap and dependency injection.

`Bootstrap` is the root composition root. It initializes all subsystems
in dependency order, holds references to shared singletons, and manages
graceful startup/shutdown of every component.

Usage:
    async with Bootstrap.create() as emily:
        await emily.run()
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import signal
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from types import TracebackType

from agents.registry import AgentRegistry
from config import EmilySettings, get_settings
from core.bus import AgentBus, PerceptionBus
from core.fsm import SystemFSM, SystemState
from core.scheduler import Scheduler
from llm.fleet import LLMFleet
from memory.manager import MemoryManager
from observability.logger import configure_logging, get_logger
from observability.metrics import start_metrics_server
from observability.tracing import configure_tracing
from perception.audio.pipeline import AudioPipeline
from perception.vision.pipeline import VisionPipeline
from security.manager import SecurityManager
from self_improvement.engine import SelfImprovementEngine
from users.owner_identity import OwnerIdentityManager
from voice.output_stream import AudioOutputStream
from voice.singing import SingingManager
from voice.tts import TTSManager

_automation_available = True
try:
    from integrations.automation import AutomationEngine
except ImportError:
    _automation_available = False

log = get_logger(__name__)

# Patterns that indicate the user wants Emily to sing / generate music.
_SING_RE = re.compile(
    r"\b(?:"
    r"sing(?:\s+(?:me\s+)?(?:a\s+)?(?:song|tune|melody|lullaby|ballad|jingle))?"
    r"|serenade\s+me"
    r"|(?:can|could|please|would)\s+you\s+sing"
    r"|start\s+singing"
    r"|perform\s+(?:a\s+)?(?:song|tune)"
    r")\b",
    re.IGNORECASE,
)


def _is_singing_request(text: str) -> bool:
    return bool(_SING_RE.search(text))


_voice_engine_available = True
try:
    from voice_engine.config import VoiceEngineConfig as VE13Config
    from voice_engine.conversation import VoiceConversation
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider
    from voice_engine.providers.tts.emily_tts import EmilyTTSProvider
except ImportError:
    _voice_engine_available = False


class Bootstrap:
    """
    Root composition object. Owns and manages all Emily subsystem lifetimes.

    All subsystems are initialized lazily in `startup()` and torn down in
    reverse order in `shutdown()`. External code accesses subsystems via
    the public attributes on this object.
    """

    def __init__(self, settings: EmilySettings, brain_hub: Any | None = None) -> None:
        self.settings = settings
        self.brain_hub = brain_hub
        self.fsm = SystemFSM()
        self.scheduler = Scheduler()
        self.perception_bus = PerceptionBus()
        self.agent_bus = AgentBus(port=settings.agents.message_bus_port)
        self.vision_pipeline: VisionPipeline | None = None
        self.audio_pipeline: AudioPipeline | None = None
        self.tts_manager: TTSManager | None = None
        self.singing_manager: SingingManager | None = None
        self.audio_output: AudioOutputStream | None = None
        self.voice_engine_instance: object | None = None
        self.security: SecurityManager = SecurityManager(settings.security)
        self.self_improvement: SelfImprovementEngine = SelfImprovementEngine()
        self.fleet: LLMFleet = LLMFleet(settings.llm, brain_hub=brain_hub)
        self.memory: MemoryManager = MemoryManager(settings, brain_hub=brain_hub)
        self.identity_manager: OwnerIdentityManager = OwnerIdentityManager(
            data_path=settings.owner.identity_file
        )
        self.registry: AgentRegistry | None = None
        self.automation_engine: object | None = None
        self._background_tasks: list[asyncio.Task[None]] = []
        self._shutdown_event = asyncio.Event()

        if brain_hub is not None:
            self.perception_bus.set_brain_hub(brain_hub)
            self.agent_bus.set_brain_hub(brain_hub)

    @classmethod
    def create(
        cls,
        config_path: str = "config.yaml",
        brain_hub: Any | None = None,
    ) -> Bootstrap:
        """
        Factory: load settings and return an unstarted Bootstrap instance.

        Args:
            config_path: Path to config.yaml.
            brain_hub: Optional BrainEventHub for Brain Dashboard integration.

        Returns:
            A Bootstrap instance ready for `async with` or manual startup.
        """
        settings = get_settings()
        return cls(settings, brain_hub=brain_hub)

    async def startup(self) -> None:
        """
        Initialize all subsystems in dependency order.

        Raises:
            RuntimeError: If a critical subsystem fails to start.
        """
        s = self.settings

        # 1. Observability (must be first)
        configure_logging(log_level=s.log_level, log_format=s.observability.log_format)
        configure_tracing(
            service_name="emily",
            service_version=s.version,
            otlp_endpoint=s.observability.otlp_endpoint,
            enabled=s.observability.tracing_enabled,
        )

        log.info("emily_starting", version=s.version, name=s.name)

        hub = self.brain_hub
        if hub is not None:

            async def _on_fsm_change(old: Any, new: Any) -> None:
                await hub.emit(
                    "fsm",
                    "state_change",
                    {
                        "old": old.name,
                        "new": new.name,
                    },
                )

            self.fsm.on_transition(_on_fsm_change)

        # 2. Ensure data directories exist
        for dir_name in [s.data_dir, s.logs_dir, s.knowledge_dir, s.prompts_dir]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)
        Path("prompts/archive").mkdir(parents=True, exist_ok=True)
        Path("plugins/generated").mkdir(parents=True, exist_ok=True)

        # 3. Metrics server
        start_metrics_server(port=s.observability.metrics_port)

        # 4. Security (before any data access)
        await self.security.start()

        # 5. Core buses
        await self.perception_bus.start_publisher()
        await self.perception_bus.start_subscriber()
        await self.agent_bus.start()

        # 6. Scheduler
        await self.scheduler.start()

        # 7. LLM fleet
        await self.fleet.startup()

        # 8. Memory system
        await self.memory.startup()
        await self._wire_retriever()

        # Load owner identity (non-critical)
        try:
            await self.identity_manager.load()
        except Exception as exc:
            log.warning("identity_manager_load_failed", error=str(exc))

        # 9. Agent registry
        self.registry = AgentRegistry(self.agent_bus, self.fleet, self.memory)
        await self.registry.start_all()
        self.add_background_task(self.agent_bus.run())

        # 10. Vision pipeline (non-critical — degrade gracefully)
        try:
            self.vision_pipeline = VisionPipeline(
                config=s.vision,
                bus=self.perception_bus,
                vision_model=s.llm.models.vision,
                ollama_url=s.llm.ollama_base_url,
            )
            await self.vision_pipeline.start()
        except Exception as exc:
            log.warning("vision_pipeline_start_failed", error=str(exc))
            self.vision_pipeline = None

        # 8-10. Voice mode selection
        self._voice_mode_enabled = (
            _voice_engine_available and hasattr(s, "voice_engine") and s.voice_engine.enabled
        )

        # TTS is always loaded (used by API routes and legacy bridge)
        self.tts_manager = TTSManager(s.tts)
        self.audio_output = AudioOutputStream(output_device=s.audio.output_device)
        self.add_background_task(self._load_tts())

        # Singing engine (non-critical — degrades gracefully if no engines installed)
        if s.singing.enabled:
            self.singing_manager = SingingManager(s.singing)
            self.add_background_task(self._load_singing())

        if self._voice_mode_enabled:
            log.info("voice_mode_v13", msg="Using VoiceEngine 1.3 integrated with Emily brain")
            from llm.prompt_builder import PromptBuilder

            ve_config = VE13Config(  # type: ignore[possibly-undefined]
                stt_provider=s.voice_engine.stt_provider,
                stt_model=s.stt.model,
                vad_threshold=s.voice_engine.vad_threshold,
                min_speech_ms=s.voice_engine.min_speech_ms,
                min_silence_ms=s.voice_engine.min_silence_ms,
            )

            # Adapter: routes voice LLM calls through Emily's fleet + memory
            emily_llm = EmilyLLMProvider(  # type: ignore[possibly-undefined]
                fleet=self.fleet,
                memory=self.memory,
                prompt_builder=PromptBuilder(),
                identity_manager=self.identity_manager,
            )
            # Adapter: reuses Emily's already-loaded Kokoro TTS instance
            emily_tts = EmilyTTSProvider(tts_manager=self.tts_manager)  # type: ignore[possibly-undefined]

            self.voice_engine_instance = VoiceConversation(  # type: ignore[possibly-undefined]
                ve_config,
                llm=emily_llm,
                tts=emily_tts,
            )
            self.add_background_task(self._start_voice_engine())
        else:
            log.info("voice_mode_legacy", msg="Using legacy half-duplex pipeline + bridge")
            self.audio_pipeline = AudioPipeline(settings=s, bus=self.perception_bus)
            self.add_background_task(self._start_audio_pipeline())
            self.add_background_task(self._perception_tts_bridge())

        # 11b. Automation engine (integrations layer)
        if _automation_available:
            try:
                from plugins.registry import PluginRegistry

                plugin_reg = PluginRegistry()
                plugin_reg.load_builtins(
                    tool_kwargs={
                        "discord": {
                            "bot_token": getattr(
                                getattr(s, "integrations", None), "discord", {}
                            ).get("bot_token", "")
                            if hasattr(s, "integrations")
                            else "",
                            "default_channel_id": getattr(
                                getattr(s, "integrations", None), "discord", {}
                            ).get("default_channel_id", "")
                            if hasattr(s, "integrations")
                            else "",
                        },
                    }
                )
                self.automation_engine = AutomationEngine(  # type: ignore[possibly-undefined]
                    plugin_registry=plugin_reg,
                    fleet=self.fleet,
                )
                self.add_background_task(self.automation_engine.start())  # type: ignore[union-attr]
                log.info("automation_engine_initialized")
            except Exception as exc:
                log.warning("automation_engine_init_failed", error=str(exc)[:200])

        # Wire voice engine refs into API routes
        self._wire_api_voice_state()

        # 11. Register signal handlers for graceful shutdown
        #     (fails gracefully when the loop runs on a non-main thread,
        #      e.g. inside a QThread for the GUI; Qt handles quit instead)
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal)
        except (ValueError, RuntimeError):
            log.info("signal_handlers_skipped_non_main_thread")

        log.info("emily_ready")

    async def shutdown(self) -> None:
        """
        Gracefully shut down all subsystems in reverse initialization order.
        """
        log.info("emily_shutting_down")
        await self.fsm.force_transition(SystemState.SHUTDOWN)

        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Voice engine (VoiceConversation) stops when its task is cancelled above

        # Stop automation engine
        if self.automation_engine is not None:
            await self.automation_engine.stop()  # type: ignore[union-attr]

        # Stop audio pipeline
        if self.audio_pipeline:
            self.audio_pipeline.stop()

        # Stop vision pipeline
        if self.vision_pipeline:
            await self.vision_pipeline.stop()

        # Stop agent registry
        if self.registry is not None:
            await self.registry.stop_all()

        # Stop memory
        await self.memory.shutdown()

        # Stop security services
        await self.security.stop()

        # Stop buses
        await self.scheduler.stop()
        self.agent_bus.stop()
        self.perception_bus.stop()

        log.info("emily_shutdown_complete")

    def _handle_signal(self) -> None:
        """Signal handler: trigger graceful shutdown."""
        log.info("shutdown_signal_received")
        self._shutdown_event.set()

    def add_background_task(
        self,
        coro: Coroutine[Any, Any, None],
    ) -> asyncio.Task[None]:
        """
        Register and start a long-running background coroutine.

        Args:
            coro: A coroutine to run indefinitely.

        Returns:
            The created asyncio Task.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        return task

    async def _wire_retriever(self) -> None:
        """Create HybridRetriever with Qdrant + BM25 + reranker and attach to memory."""
        try:
            from memory.semantic.bm25 import BM25Index
            from memory.semantic.reranker import CrossEncoderReranker
            from memory.semantic.retriever import HybridRetriever
            from memory.semantic.vector_store import QdrantVectorStore

            s = self.settings
            vector_store = QdrantVectorStore(config=s.memory.semantic)
            await vector_store.ensure_collection()

            bm25 = BM25Index(index_path=s.memory.semantic.bm25_index_path)

            reranker = CrossEncoderReranker()
            await reranker.load()

            async def _embed(text: str) -> list[float]:
                result = await self.fleet.embed(text)
                return result.embedding

            retriever = HybridRetriever(
                config=s.rag,
                vector_store=vector_store,
                bm25=bm25,
                embedder=_embed,
                reranker=reranker,
            )
            self.memory.set_retriever(retriever)
            log.info("retriever_wired")
        except Exception as exc:
            log.warning("retriever_unavailable_degraded_mode", error=str(exc))

    async def _start_audio_pipeline(self) -> None:
        """Background task: load audio models and start the capture pipeline."""
        try:
            assert self.audio_pipeline is not None
            log.info("audio_pipeline_loading")
            await self.audio_pipeline.load()
            await self.audio_pipeline.start()
        except Exception as exc:
            log.error("audio_pipeline_start_failed", error=str(exc))

    async def _load_tts(self) -> None:
        """Background task: load TTS engine models."""
        try:
            assert self.tts_manager is not None
            await self.tts_manager.load()
            log.info("tts_engines_loaded")
            if self.audio_output is not None:
                ai = getattr(self, "identity_manager", None)
                name = ai.ai_name if ai else "Emily"
                greeting = f"Hey, {name} here. What's on your mind?"
                log.info("startup_greeting_speaking")
                chunks = self.tts_manager.speak(text=greeting)
                await self.audio_output.play_stream(chunks)
                log.info("startup_greeting_complete")
        except Exception as exc:
            log.error("tts_load_failed", error=str(exc))

    async def _load_singing(self) -> None:
        """Background task: load singing engine models."""
        try:
            assert self.singing_manager is not None
            await self.singing_manager.load()
            log.info("singing_engines_loaded")
        except Exception as exc:
            log.warning("singing_load_failed", error=str(exc)[:200])

    def _wire_api_voice_state(self) -> None:
        """Inject voice engine and audio state into API route modules."""
        try:
            from api.routes import audio as audio_routes

            audio_routes.set_audio_state(
                input_device=self.settings.audio.input_device,
                output_device=self.settings.audio.output_device,
                audio_pipeline=self.audio_pipeline,
                tts_manager=self.tts_manager,
                voice_engine=self.voice_engine_instance,
            )
        except ImportError:
            pass

        try:
            from api.routes.voice_engine import configure_voice_engine_routes

            configure_voice_engine_routes(engine=self.voice_engine_instance)
        except ImportError:
            pass

        try:
            from api.routes.settings import set_identity_manager

            set_identity_manager(self.identity_manager)
        except ImportError:
            pass

        try:
            from api.routes.integrations import configure as configure_integrations

            configure_integrations(
                automation_engine=self.automation_engine,
                fleet=self.fleet,
            )
        except ImportError:
            pass

        try:
            from api.routes.singing import configure as configure_singing

            if self.singing_manager is not None:
                configure_singing(self.singing_manager)
        except ImportError:
            pass

    async def _start_voice_engine(self) -> None:
        """Background task: run the VoiceEngine 1.3 conversation loop."""
        try:
            assert self.voice_engine_instance is not None
            log.info("voice_engine_v13_starting")

            # First-run onboarding: trigger before conversation loop if no owner
            if not self.identity_manager.has_owner and self.tts_manager is not None:
                try:
                    from users.onboarding_enhanced import run_owner_onboarding

                    ve = self.voice_engine_instance

                    async def _speak(text: str) -> None:
                        chunks = self.tts_manager.speak(text=text)  # type: ignore[union-attr]
                        if self.audio_output:
                            await self.audio_output.play_stream(chunks)

                    async def _listen() -> str:
                        return await ve.listen_once()  # type: ignore[union-attr]

                    log.info("first_run_onboarding_starting")
                    await run_owner_onboarding(
                        fleet=self.fleet,
                        memory=self.memory,
                        identity_manager=self.identity_manager,
                        speak=_speak,
                        listen=_listen,
                    )
                    log.info("first_run_onboarding_complete")
                except Exception as exc:
                    log.warning("onboarding_failed", error=str(exc))

            await self.voice_engine_instance.run()  # type: ignore[union-attr]
        except Exception as exc:
            log.error("voice_engine_start_failed", error=str(exc)[:200])
            self.voice_engine_instance = None
            log.info("falling_back_to_legacy_bridge")
            await self._perception_tts_bridge()

    async def _perception_tts_bridge(self) -> None:
        """
        Bridge: listen for audio.transcript on PerceptionBus, run LLM, speak back.

        Uses streaming LLM -> sentence chunking -> per-sentence TTS for low latency.
        Falls back to batch mode if streaming client is unavailable.
        """
        log.info("perception_tts_bridge_started")

        await asyncio.sleep(5)

        async for event in self.perception_bus.iter_events():
            try:
                if event.type == "audio.transcript":
                    text = event.payload.get("text", "").strip()
                    if not text:
                        continue

                    log.info("voice_input_received", text=text[:80])
                    self._write_transcript("user", text)
                    await self.fsm.force_transition(SystemState.PROCESSING)

                    response = await self._stream_llm_and_speak(text)
                    if response:
                        self._write_transcript("emily", response)

                    await self.fsm.force_transition(SystemState.IDLE)

                elif event.type == "audio.wake_word_detected":
                    log.info("wake_word_detected_in_bridge", keyword=event.payload.get("keyword"))
                    await self.fsm.force_transition(SystemState.LISTENING)

            except Exception as exc:
                log.error("perception_bridge_error", error=str(exc))
                with contextlib.suppress(Exception):
                    await self.fsm.force_transition(SystemState.IDLE)

    async def _stream_llm_and_speak(self, user_text: str) -> str:
        """
        Stream LLM tokens, chunk into sentences, synthesize each sentence
        immediately for low perceived latency.

        Falls back to batch mode (full response then speak) on error.
        Intercepts singing requests before they reach the LLM.

        Args:
            user_text: Transcribed user speech.

        Returns:
            Full response text.
        """
        if self.singing_manager is not None and _is_singing_request(user_text):
            return await self._sing_response(user_text)
        try:
            return await self._streaming_pipeline(user_text)
        except Exception as exc:
            log.warning("streaming_pipeline_unavailable_batch_fallback", error=str(exc))
            return await self._batch_pipeline(user_text)

    async def _sing_response(self, user_text: str) -> str:
        """Handle a singing request from the voice bridge.

        Streams audio from SingingManager directly to the audio output device.

        Args:
            user_text: The original user utterance (used as the song prompt).

        Returns:
            Acknowledgment string written to the transcript.
        """
        assert self.singing_manager is not None

        # Tell the user something before generation starts (can take a few seconds).
        if self.tts_manager and self.audio_output:
            intro = "Sure, let me sing something for you!"
            chunks = self.tts_manager.speak(text=intro)
            await self.audio_output.play_stream(chunks)

        await self.fsm.force_transition(SystemState.RESPONDING)
        log.info("singing_request_detected", prompt=user_text[:80])

        try:
            if self.audio_output:
                await self.audio_output.play_stream(self.singing_manager.sing(user_text, mode=None))
        except RuntimeError as exc:
            log.error("singing_failed", error=str(exc)[:200])
            if self.tts_manager and self.audio_output:
                msg = "Sorry, no singing engine is available right now."
                chunks = self.tts_manager.speak(text=msg)
                await self.audio_output.play_stream(chunks)
            return "Sorry, no singing engine is available right now."

        return f"[sang: {user_text[:60]}]"

    async def _streaming_pipeline(self, user_text: str) -> str:
        """
        Stream LLM output sentence by sentence into TTS.

        Each sentence is synthesized and played as soon as it is complete,
        without waiting for the full LLM response.
        """
        from llm.client import ChatMessage
        from llm.streaming import StreamProcessor
        from llm.tabbyapi_client import TabbyAPIClient

        client = TabbyAPIClient(
            base_url=self.settings.llm.tabbyapi_base_url,
            api_key=self.settings.llm.tabbyapi_api_key,
        )
        processor = StreamProcessor(tts_chunk_min_chars=40)
        full_response = ""

        try:
            from llm.prompt_builder import PromptBuilder

            _voice_prompt = PromptBuilder().build_voice_system_prompt()
            messages = [
                ChatMessage(role="system", content=_voice_prompt),
                ChatMessage(role="user", content=user_text),
            ]

            async def _token_iter():
                async for chunk in client.chat_stream(
                    model=self.settings.llm.models.fast,
                    messages=messages,
                ):
                    if chunk.content:
                        yield chunk.content

            await self.fsm.force_transition(SystemState.RESPONDING)

            async for sentence in processor.iter_sentences(_token_iter()):
                full_response += sentence + " "
                log.info("streaming_sentence", text=sentence[:60])

                if self.tts_manager and self.audio_output:
                    chunks = self.tts_manager.speak(text=sentence)
                    await self.audio_output.play_stream(chunks)

        finally:
            await client.close()

        return full_response.strip()

    async def _batch_pipeline(self, user_text: str) -> str:
        """Batch fallback: get full LLM response, then speak it."""
        response = await self._get_llm_response(user_text)
        if not response:
            return ""

        log.info("voice_response_ready", response=response[:80])
        await self.fsm.force_transition(SystemState.RESPONDING)

        if self.tts_manager and self.audio_output:
            chunks = self.tts_manager.speak(text=response)
            await self.audio_output.play_stream(chunks)

        return response

    _TRANSCRIPT_PATH = Path("logs/voice_transcript.jsonl")

    def _write_transcript(self, role: str, text: str) -> None:
        """Append a voice transcript entry to the shared JSONL log."""
        try:
            self._TRANSCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            entry = {"role": role, "text": text, "ts": time.time(), "source": "voice"}
            with self._TRANSCRIPT_PATH.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            log.error("transcript_write_failed", error=str(exc))

    async def _get_llm_response(self, user_text: str) -> str:
        """
        Quick LLM call for voice conversation.

        Uses Ollama directly for the fast model to keep the bridge simple.

        Args:
            user_text: Transcribed user speech.

        Returns:
            LLM response text.
        """
        try:
            from llm.client import ChatMessage
            from llm.tabbyapi_client import TabbyAPIClient

            client = TabbyAPIClient(
                base_url=self.settings.llm.tabbyapi_base_url,
                api_key=self.settings.llm.tabbyapi_api_key,
            )
            try:
                from llm.prompt_builder import PromptBuilder

                _voice_prompt = PromptBuilder().build_voice_system_prompt()
                result = await client.chat(
                    model=self.settings.llm.models.fast,
                    messages=[
                        ChatMessage(role="system", content=_voice_prompt),
                        ChatMessage(role="user", content=user_text),
                    ],
                )
                return result.content
            finally:
                await client.close()
        except Exception as exc:
            log.error("llm_voice_response_failed", error=str(exc))
            return ""

    async def run_until_shutdown(self) -> None:
        """
        Block until a shutdown signal is received.

        Shutdown is handled by the context manager (__aexit__).
        """
        await self._shutdown_event.wait()

    async def __aenter__(self) -> Self:
        await self.startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.shutdown()
